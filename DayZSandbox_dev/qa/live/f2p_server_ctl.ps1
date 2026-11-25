# Ayudante de servidor F2P: arranque por WMI y parada/reinicio propios.
# Falla cerrado: stop sale con rc != 0 si el servidor propio sigue vivo, y
# restart no arranca nada si la parada no fue valida ni si los puertos UDP
# no quedan libres. Solo toca PID propios con su hora de arranque; un PID
# reutilizado (otra hora de arranque) cuenta como parado y no se toca.
# Los CrashReporter hijos del PID propio se cierran por WM_CLOSE sin
# enviar, tambien con el padre ya muerto; a un CrashReporter no se le mata
# nunca: si no cierra en un tiempo acotado, se anota.
[CmdletBinding()]
param(
    [ValidateSet('start','stop','restart')][string]$Action = 'restart',
    [string]$ServerExe = '',
    [string]$ServerArgs = '',
    [string]$WorkingDir = '',
    [string]$ProfileDir = '',
    [int]$ServerPid = 0,
    [string]$ServerStart = '',
    [string]$ClientExe = '',
    [string]$ClientArgs = '',
    [string]$ClientWorkingDir = '',
    [int]$ClientPid = 0,
    [string]$ClientStart = '',
    [string]$LibReinicio = '',
    [ValidateSet('diag','retail')][string]$Build = 'diag',
    [string]$ClientProfileDir = '',
    [string]$ClientMods = '',
    [int]$Port = 2302,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function L([string]$Msg) { Write-Host ("[f2p-ctl] {0}" -f $Msg) }

# Estado que esperan las funciones de lib_reinicio_caja.ps1
# (OwnCrashReporters, CloseOwnCrashReporters, EnsureServerPortsFree).
$script:Port = $Port
$Dry = [bool]$DryRun
$script:AllPids = @()
$script:PidStart = @{}
foreach ($pair in @(@($ServerPid, $ServerStart), @($ClientPid, $ClientStart))) {
    if ($pair[0]) {
        $script:AllPids += [int]$pair[0]
        if ($pair[1]) {
            try { $script:PidStart[[int]$pair[0]] = [datetime]::Parse([string]$pair[1]).ToUniversalTime() } catch { }
        }
    }
}

# CloseOwn que espera lib_reinicio_caja.ps1 (CloseOwnCrashReporters):
# WM_CLOSE, espera acotada, nunca matar. Devuelve el texto del cierre.
function CloseOwn([int]$ProcessId, [string]$What, [string]$ExpectName = '') {
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $p) { return "$What pid $ProcessId ya no estaba" }
    if ($ExpectName -and $p.ProcessName -ne $ExpectName) { return "$What pid $ProcessId no es $ExpectName (es $($p.ProcessName)): no se toca" }
    if ($script:PidStart.ContainsKey($ProcessId)) {
        try {
            if ([math]::Abs(($p.StartTime.ToUniversalTime() - $script:PidStart[$ProcessId]).TotalSeconds) -ge 1.0) {
                return "$What pid $ProcessId reutilizado; no se toca"
            }
        } catch { return "$What pid $ProcessId sin hora legible: no se toca" }
    }
    if ($Dry) { return "$What pid $ProcessId (seco) se cerraria por WM_CLOSE" }
    if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return "$What pid $ProcessId cerrado por WM_CLOSE sin enviar" }
    }
    return "$What pid $ProcessId sigue vivo tras WM_CLOSE acotado: se anota, no se mata"
}

# lib_reinicio_caja.ps1 va en el paquete, junto a este ayudante. Si no
# esta, se usa la logica equivalente copiada de sus lineas 12-72.
$libPath = $LibReinicio
if (-not $libPath) { $libPath = Join-Path $PSScriptRoot 'lib_reinicio_caja.ps1' }
if ($libPath -and (Test-Path $libPath)) {
    . $libPath
} else {
    # Equivalente a _ref/lib_reinicio_caja.ps1:12-40 (OwnCrashReporters y
    # CloseOwnCrashReporters) y :42-72 (UdpPortsInUse, EnsureServerPortsFree).
    function OwnCrashReporters([string]$Paso) {
        $elegidos = @()
        foreach ($cr in @(Get-CimInstance Win32_Process -Filter "Name='CrashReporter.exe'" -ErrorAction SilentlyContinue)) {
            $crPid = [int]$cr.ProcessId; $parent = [int]$cr.ParentProcessId
            if ($script:AllPids -notcontains $parent) { L "${Paso}: CrashReporter pid $crPid (padre $parent) no es hijo de un proceso propio: no se toca"; continue }
            if (-not $script:PidStart.ContainsKey($parent)) { L "${Paso}: CrashReporter pid $crPid (padre $parent) sin hora de arranque del padre registrada: no se toca"; continue }
            $crStart = $null
            if ($cr.CreationDate -is [datetime]) { $crStart = $cr.CreationDate }
            else { try { $crStart = [Management.ManagementDateTimeConverter]::ToDateTime([string]$cr.CreationDate) } catch { $crStart = $null } }
            if ($null -eq $crStart) { L "${Paso}: CrashReporter pid $crPid (padre $parent) sin hora de arranque legible: no se toca"; continue }
            if ($crStart -le $script:PidStart[$parent]) { L "${Paso}: CrashReporter pid $crPid (padre $parent) arranco antes que el proceso propio: pid reutilizado, no se toca"; continue }
            $elegidos += $cr
        }
        return ,$elegidos
    }
    function CloseOwnCrashReporters([string]$Paso) {
        $crs = OwnCrashReporters $Paso
        foreach ($cr in $crs) {
            if ($Dry) { L "${Paso}: (seco) CrashReporter pid $([int]$cr.ProcessId), hijo del pid propio $([int]$cr.ParentProcessId): se cerraria por WM_CLOSE"; continue }
            L "${Paso}: $(CloseOwn ([int]$cr.ProcessId) "CrashReporter del pid propio $([int]$cr.ParentProcessId)" 'CrashReporter')"
        }
        if ($crs.Count -eq 0) { L "${Paso}: ningun CrashReporter hijo de un proceso propio" }
        return $crs.Count
    }
    function UdpPortsInUse { return @(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | ForEach-Object { [int]$_.LocalPort }) }
    function EnsureServerPortsFree([string]$Paso, [int]$EsperaS = 30) {
        $vieja = [int]$script:Port
        $sw = [Diagnostics.Stopwatch]::StartNew()
        do {
            $usados = UdpPortsInUse
            if (($usados -notcontains $vieja) -and ($usados -notcontains ($vieja + 2))) { L ("${Paso}: puertos $vieja y $($vieja + 2) libres ({0:N1} s)" -f $sw.Elapsed.TotalSeconds); return $true }
            Start-Sleep -Seconds 1
        } while ($sw.Elapsed.TotalSeconds -lt $EsperaS)
        L "${Paso}: AVISO: puertos $vieja/$($vieja + 2) siguen tomados tras $EsperaS s"
        return $false
    }
}

function Test-OwnAlive([int]$PidValue, [string]$StartIso) {
    if (-not $PidValue) { return $false }
    $p = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    if ($StartIso) {
        try {
            if ($p.StartTime.ToUniversalTime().ToString('o') -ne $StartIso) { return $false }
        } catch { return $false }
    }
    return $true
}

function StartServerViaWmi {
    $cmd = '"' + $ServerExe + '" ' + $ServerArgs
    if ($DryRun) {
        L ("dry-run WMI start: Invoke-CimMethod Win32_Process Create CommandLine={0} CurrentDirectory={1}" -f $cmd, $WorkingDir)
        return [pscustomobject]@{ pid = 0; start_time = '' }
    }
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $WorkingDir }
    if ($r.ReturnValue -ne 0) { throw ("Win32_Process.Create devolvio {0}" -f $r.ReturnValue) }
    $pidNew = [int]$r.ProcessId
    $proc = Get-Process -Id $pidNew -ErrorAction Stop
    $start = $proc.StartTime.ToUniversalTime().ToString('o')
    L ("servidor arrancado pid={0} start={1}" -f $pidNew, $start)
    return [pscustomobject]@{ pid = $pidNew; start_time = $start }
}

# R16 (F1b run_f1bp_partida.ps1:63-86): RPT del perfil propio del cliente
# posterior al lanzador y con nuestro -mod, -profiles y -port exactos.
function RptPropio([string]$Dir, [string]$ModArg, [int]$PortArg, [datetime]$Desde) {
    foreach ($f in @(Get-ChildItem -LiteralPath $Dir -Filter 'DayZ_x64_*.RPT' -File -ErrorAction SilentlyContinue)) {
        if ($f.LastWriteTime -lt $Desde) { continue }
        $m = [regex]::Match($f.Name, '^DayZ_x64_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.RPT$')
        if (-not $m.Success) { continue }
        $t = New-Object DateTime ([int]$m.Groups[1].Value), ([int]$m.Groups[2].Value), ([int]$m.Groups[3].Value), ([int]$m.Groups[4].Value), ([int]$m.Groups[5].Value), ([int]$m.Groups[6].Value)
        $lines = @()
        try {
            $fs = [IO.File]::Open($f.FullName, 'Open', 'Read', 'ReadWrite')
            try {
                $sr = New-Object IO.StreamReader($fs)
                for ($k = 0; $k -lt 20 -and -not $sr.EndOfStream; $k++) { $l = $sr.ReadLine(); if ($l.StartsWith('== ')) { $lines += $l } }
            } finally { $fs.Dispose() }
        } catch { $lines = @() }
        foreach ($line in $lines) {
            $okMod = $line -match ('-mod=' + [regex]::Escape($ModArg) + '("|\s|$)')
            $okPro = $line -match ('-profiles=' + [regex]::Escape($Dir) + '("|\s|$)')
            $okPort = $line -match ('(^|\s)-port=' + $PortArg + '(\s|$)')
            if ($okMod -and $okPro -and $okPort) { return $t }
        }
    }
    return $null
}

# R14/R16 (F1b :152-191): adopta el unico DayZ_x64 nuevo con procedencia
# (cadena ParentProcessId hasta 3 niveles al lanzador BattlEye, o RPT
# propio a 10 s). Con cero o varios no se adopta ninguno: falla cerrado.
function Adopt-DayZX64([int]$BePid, [string]$ProfileDir, [string]$Mods, [int]$PortArg) {
    # La foto de DayZ_x64 previos la toma el llamador antes de lanzar el
    # BattlEye ($script:AntesRetail, como F1b :155).
    $antes = @($script:AntesRetail)
    $beStart = $null
    try { $beStart = (Get-Process -Id $BePid -ErrorAction Stop).StartTime } catch { $beStart = (Get-Date).AddSeconds(-5) }
    for ($i = 0; $i -lt 240; $i++) {
        Start-Sleep -Milliseconds 500
        $todos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        $padre = @{}; foreach ($p in $todos) { $padre[[int]$p.ProcessId] = [int]$p.ParentProcessId }
        $nuevos = @($todos | Where-Object { $_.Name -eq 'DayZ_x64.exe' -and ($antes -notcontains [int]$_.ProcessId) })
        if ($nuevos.Count -eq 0) { continue }
        $rpt = $null
        if ($ProfileDir -and $Mods) { $rpt = RptPropio $ProfileDir $Mods $PortArg $beStart }
        $cands = @()
        foreach ($q in $nuevos) {
            $via = $null
            $x = [int]$q.ParentProcessId
            for ($n = 0; $n -lt 3 -and $x -gt 0; $n++) { if ($x -eq $BePid) { $via = 'desciende del lanzador BattlEye'; break }; if ($padre.ContainsKey($x)) { $x = $padre[$x] } else { break } }
            if (-not $via -and $rpt -and [math]::Abs(($q.CreationDate - $rpt).TotalSeconds) -le 10) { $via = 'su RPT en el perfil propio lleva nuestra linea de ordenes' }
            if ($via) { $cands += [pscustomobject]@{ pid = [int]$q.ProcessId; via = $via } }
        }
        if ($cands.Count -eq 0) { continue }
        if ($cands.Count -eq 1) {
            $proc = Get-Process -Id $cands[0].pid -ErrorAction Stop
            $start = $proc.StartTime.ToUniversalTime().ToString('o')
            L ("cliente retail (juego) pid={0} start={1}: {2}" -f $cands[0].pid, $start, $cands[0].via)
            return [pscustomobject]@{ pid = $cands[0].pid; start_time = $start; role = 'client' }
        }
        throw ("hay {0} DayZ_x64 con procedencia: no se adopta ninguno" -f $cands.Count)
    }
    throw 'ningun DayZ_x64 con procedencia (cadena ni RPT propio) en 120 s: no se adopta ninguno'
}

function StartClientViaWmi {
    if (-not $ClientExe) { return $null }
    $cmd = '"' + $ClientExe + '" ' + $ClientArgs
    if ($DryRun) {
        L ("dry-run WMI cliente: Invoke-CimMethod Win32_Process Create CommandLine={0} CurrentDirectory={1}" -f $cmd, $ClientWorkingDir)
        return [pscustomobject]@{ pid = 0; start_time = ''; role = 'client' }
    }
    $cwd = if ($ClientWorkingDir) { $ClientWorkingDir } else { $WorkingDir }
    if ($Build -eq 'retail') { $script:AntesRetail = @(Get-Process -Name DayZ_x64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) }
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $cwd }
    if ($r.ReturnValue -ne 0) { throw ("Win32_Process.Create (cliente) devolvio {0}" -f $r.ReturnValue) }
    $pidNew = [int]$r.ProcessId
    if ($Build -eq 'retail') {
        L ("lanzador BattlEye pid={0}" -f $pidNew)
        return Adopt-DayZX64 $pidNew $ClientProfileDir $ClientMods $Port
    }
    $proc = Get-Process -Id $pidNew -ErrorAction Stop
    $start = $proc.StartTime.ToUniversalTime().ToString('o')
    L ("cliente arrancado pid={0} start={1}" -f $pidNew, $start)
    return [pscustomobject]@{ pid = $pidNew; start_time = $start; role = 'client' }
}

function StopBothOwn {
    # StopBoth: cliente y servidor propios, WM_CLOSE, sin matar. Vale
    # aunque el servidor termine con caida: CrashReporter y puertos se
    # miran tambien con el padre ya muerto (run_diag_spersist.ps1:152-165).
    if ($DryRun) {
        L ("dry-run StopBoth: guardar .mdmp de {0}, cerrar cliente pid={1} y servidor pid={2} por WM_CLOSE, cerrar CrashReporter por WM_CLOSE sin enviar, mirar puertos {3} y {4}" -f $ProfileDir, $ClientPid, $ServerPid, $Port, ($Port + 2))
        return $true
    }
    if ($ProfileDir -and (Test-Path $ProfileDir)) {
        Get-ChildItem -Path $ProfileDir -Recurse -Filter '*.mdmp' -ErrorAction SilentlyContinue |
            ForEach-Object { L ("mdmp guardado: {0}" -f $_.FullName) }
    }
    # Cliente primero (StopBoth de F0.3), luego el servidor propio.
    if ($ClientPid -and (Test-OwnAlive $ClientPid $ClientStart)) {
        L (CloseOwn $ClientPid 'cliente')
    } elseif ($ClientPid) {
        L ("cliente pid={0} ya no vive o reutilizado: parada valida, no se toca" -f $ClientPid)
    }
    $srvAlive = Test-OwnAlive $ServerPid $ServerStart
    if ($ServerPid -and $srvAlive) {
        L (CloseOwn $ServerPid 'servidor')
    } elseif ($ServerPid) {
        L ("servidor pid={0} ya no vive o reutilizado: parada valida, no se toca" -f $ServerPid)
    }
    # CrashReporter hijos propios: tambien con el padre ya muerto, porque
    # heredan los sockets UDP y el servidor nuevo no podria arrancar.
    $null = CloseOwnCrashReporters 'stop'
    for ($i = 0; $i -lt 240; $i++) {
        if (-not (Test-OwnAlive $ServerPid $ServerStart)) { break }
        Start-Sleep -Milliseconds 500
    }
    $alive = Test-OwnAlive $ServerPid $ServerStart
    $cliAlive = Test-OwnAlive $ClientPid $ClientStart
    L ("StopBoth servidor_vivo={0} cliente_vivo={1}" -f $alive, $cliAlive)
    return ((-not $alive) -and (-not $cliAlive))
}

if ($Action -eq 'stop') {
    $okStop = StopBothOwn
    if (-not $okStop) { L 'stop: el servidor o el cliente propio sigue vivo: rc 2'; exit 2 }
    return
}
if ($Action -eq 'restart') {
    $okStop = StopBothOwn
    if (-not $okStop) { L 'restart: parada no valida: no se arranca nada, rc 2'; exit 2 }
    $script:Port = $Port
    $portsOk = EnsureServerPortsFree 'restart'
    if (-not $portsOk -or [int]$script:Port -ne $Port) { L 'restart: puertos UDP no libres: no se arranca nada, rc 3'; exit 3 }
}
if ($Action -eq 'start') {
    $script:Port = $Port
    $portsOk = EnsureServerPortsFree 'start'
    if (-not $portsOk -or [int]$script:Port -ne $Port) { L 'start: puertos UDP no libres: no se arranca nada, rc 3'; exit 3 }
}
$result = StartServerViaWmi
$result | ConvertTo-Json -Compress
$cliResult = StartClientViaWmi
if ($cliResult) { $cliResult | ConvertTo-Json -Compress }
