# Lanzador de la partida F2P (R2-04/R2-05).
# Rutas por parametro o por -ConfigJson; sin valores fijos de una maquina.
# En willy: lease de GPU y bandera de espera. En portatil: ni lease ni
# bandera, y el log lo dice. Ningun JSON de evidencia de la partida lo
# escribe PowerShell (lo escriben PartContext y el orquestador); el
# humo.json del -Humo lo compone el lanzador con los pasos del
# orquestador (humo_pasos.json) y los suyos (paquete, arranque, cierre).
[CmdletBinding()]
param(
    [ValidateSet('diag','retail','humo')][string]$Build = 'diag',
    [ValidateSet('willy','portatil')][string]$Maquina = 'willy',
    [ValidateSet('lanzar','operador')][string]$Cliente = 'lanzar',
    [string]$ConfigJson = '',
    [string]$Evidence = '',
    [string]$DayZDir = '',
    [string]$DayZServerDir = '',
    [string]$ProbeLib = '',
    [string]$LibReinicio = '',
    [string]$ServerCtl = '',
    [string]$BuildPbo = '',
    [string]$MissionB1 = '',
    [string]$GpuLease = '',
    [string]$FlagPath = '',
    [string]$Python = '',
    [string]$WorkRoot = '',
    [string]$ResultsDir = '',
    [string]$PackageDir = '',
    [string]$RemoteHost = '',
    [string]$RemoteRoot = 'C:/dsbx-m1',
    [int]$MinVramLibre = 4000,
    [int]$HelloTimeoutS = 120,
    [switch]$SmokeServerOnly,
    [switch]$MontarPaquete,
    [switch]$Humo,
    [switch]$Comprobar,
    [switch]$SondaLease,
    [string]$PboSub = 'pbo',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$script:AllPids = @()
$script:PidStart = @{}

function L([string]$Msg) { Write-Host ("[f2p] {0}" -f $Msg) }

function RegisterOwn([int]$ProcessId) {
    if (-not $ProcessId) { return }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $script:AllPids += $ProcessId
    if ($proc) { $script:PidStart[[string]$ProcessId] = $proc.StartTime.ToUniversalTime().ToString('o') }
}

function CloseOwn {
    # WM_CLOSE solo a PID propios con la misma hora de arranque; nunca matar. Espera acotada a que el proceso
    # tenga ventana y a que salga, reenviando WM_CLOSE: un DayZ recien arrancado aun no tiene ventana y antes se
    # quedaba vivo sin aviso (3b de t4-d940786, 24-nov). En orden inverso al de registro: juego, lanzador BattlEye
    # y servidor; el lanzador BattlEye no se cierra mientras su juego siga vivo (montaje retail, t4-d38c552).
    $ordenCierre = @($script:AllPids)
    [array]::Reverse($ordenCierre)
    foreach ($pidValue in $ordenCierre) {
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if (-not $proc) { L ("PID {0} ya no vive: parada valida" -f $pidValue); continue }
        $started = $script:PidStart[[string]$pidValue]
        if ($started -and $proc.StartTime.ToUniversalTime().ToString('o') -ne $started) {
            L ("PID {0} reutilizado; no se toca" -f $pidValue); continue
        }
        $deadline = (Get-Date).AddSeconds(90)
        $nextClose = Get-Date
        while ((Get-Date) -lt $deadline) {
            $proc.Refresh()
            if ($proc.HasExited) { break }
            if ((Get-Date) -ge $nextClose -and $proc.MainWindowHandle -ne 0) {
                [void]$proc.CloseMainWindow()
                $nextClose = (Get-Date).AddSeconds(5)
            }
            Start-Sleep -Milliseconds 500
        }
        if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
            L ("PID {0} sigue vivo tras WM_CLOSE acotado: se anota, no se mata" -f $pidValue)
        } else {
            L ("PID {0} cerrado por WM_CLOSE" -f $pidValue)
        }
    }
}

function Test-OwnAlive {
    foreach ($pidValue in @($script:AllPids)) {
        if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

function Start-ExeViaWmi([string]$Exe, [string]$Cwd, [string]$ArgLine) {
    $cmd = '"' + $Exe + '" ' + $ArgLine
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $Cwd }
    if ($r.ReturnValue -ne 0) { throw ("Win32_Process.Create devolvio {0}" -f $r.ReturnValue) }
    return [int]$r.ProcessId
}

function Test-PackageManifest([string]$Root) {
    # R2c-3: sha256 de cada fichero del paquete contra su manifest.json.
    $mpath = Join-Path $Root 'manifest.json'
    if (-not (Test-Path $mpath)) { throw ("falta manifest.json en el paquete {0}: no se lanza" -f $Root) }
    $manifest = Get-Content $mpath -Raw | ConvertFrom-Json
    $bad = @()
    foreach ($row in @($manifest.files)) {
        $rel = ([string]$row.file).Replace('/', '\')
        $target = Join-Path $Root $rel
        if ($row.missing -or -not $row.sha256) { $bad += ("sin sha256 en manifest: {0}" -f $row.file); continue }
        if (-not (Test-Path $target)) { $bad += ("falta el fichero del paquete: {0}" -f $row.file); continue }
        $got = (Get-FileHash -Path $target -Algorithm SHA256).Hash.ToLower()
        if ($got -ne ([string]$row.sha256).ToLower()) { $bad += ("sha256 no casa: {0}" -f $row.file) }
    }
    if ($bad.Count) { foreach ($b in $bad) { L $b }; throw 'la comprobacion del paquete fallo: no se lanza' }
    L ("paquete comprobado contra manifest.json: {0} ficheros, sha256 ok" -f @($manifest.files).Count)
    return $true
}

# R16 (run_f1bp_partida.ps1:63-86): RPT del perfil propio del cliente.
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

# R14/R16 (run_f1bp_partida.ps1:152-191): el PID propio del cliente
# retail es el del DayZ_x64 adoptado por procedencia, con su arranque.
function Adopt-DayZX64([int]$BePid, [string]$ProfileDir, [string]$Mods, [int]$PortArg, [object[]]$Antes) {
    $beStart = $null
    try { $beStart = (Get-Process -Id $BePid -ErrorAction Stop).StartTime } catch { $beStart = (Get-Date).AddSeconds(-5) }
    for ($i = 0; $i -lt 240; $i++) {
        Start-Sleep -Milliseconds 500
        $todos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        $padre = @{}; foreach ($p in $todos) { $padre[[int]$p.ProcessId] = [int]$p.ParentProcessId }
        $nuevos = @($todos | Where-Object { $_.Name -eq 'DayZ_x64.exe' -and ($Antes -notcontains [int]$_.ProcessId) })
        if ($nuevos.Count -eq 0) { continue }
        $rpt = RptPropio $ProfileDir $Mods $PortArg $beStart
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
            RegisterOwn $cands[0].pid
            L ("cliente retail (juego) pid={0} start={1}: {2}" -f $cands[0].pid, $script:PidStart[[string]$cands[0].pid], $cands[0].via)
            return [int]$cands[0].pid
        }
        throw ("hay {0} DayZ_x64 con procedencia: no se adopta ninguno" -f $cands.Count)
    }
    throw 'ningun DayZ_x64 con procedencia (cadena ni RPT propio) en 120 s: no se adopta ninguno'
}

function Start-ClientOwn([string]$Exe, [string]$Cwd, [string]$ArgLine, [string]$BuildKind, [string]$ProfileDir, [string]$Mods) {
    if ($BuildKind -eq 'retail') {
        $antes = @(Get-Process -Name DayZ_x64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
        $bePid = Start-ExeViaWmi $Exe $Cwd $ArgLine
        RegisterOwn $bePid
        L ("lanzador BattlEye pid={0} start={1}" -f $bePid, $script:PidStart[[string]$bePid])
        return Adopt-DayZX64 $bePid $ProfileDir $Mods 2302 $antes
    }
    $pidNew = Start-ExeViaWmi $Exe $Cwd $ArgLine
    RegisterOwn $pidNew
    L ("cliente WMI pid={0} start={1}" -f $pidNew, $script:PidStart[[string]$pidNew])
    return $pidNew
}

function Move-OldProfileLogs([string]$ProfileDir, [string]$Dest) {
    # T4, 24-nov: el runner reutiliza trabajo\ y la evidencia copiaba tambien los logs de partidas anteriores.
    # Se mueven fuera del perfil (no se borran) antes de arrancar.
    if (-not $ProfileDir -or -not (Test-Path $ProfileDir)) { return 0 }
    $old = @(Get-ChildItem -Path (Join-Path $ProfileDir '*') -File -Include 'script_*.log','*.RPT','*.ADM','*.mdmp','error_*.log','crash_*.log' -ErrorAction SilentlyContinue)
    if ($old.Count -eq 0) { return 0 }
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    foreach ($f in $old) { Move-Item -LiteralPath $f.FullName -Destination $Dest -Force }
    return $old.Count
}

function Copy-FreshMission([string]$B1, [string]$Dest) {
    # R2c-2: cada intento copia una mision nueva; -mission y -config
    # salen de la copia, con zombis y animales a 0 (R-36).
    if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
    Copy-Item -Path $B1 -Destination $Dest -Recurse -Force
    $globals = Get-ChildItem -Path $Dest -Recurse -Filter 'globals.xml' | Select-Object -First 1
    if ($globals) {
        $text = Get-Content $globals.FullName -Raw
        # El formato real lleva type entre name y value: <var name="ZombieMaxCount" type="0" value="1000"/>
        # (24-nov: el patrón anterior no casaba y la misión quedaba con 1000 zombis y 200 animales).
        $text = [regex]::Replace($text, '(name="ZombieMaxCount"[^>]*?value=")\d+(")', '${1}0${2}')
        $text = [regex]::Replace($text, '(name="AnimalMaxCount"[^>]*?value=")\d+(")', '${1}0${2}')
        [IO.File]::WriteAllText($globals.FullName, $text, (New-Object Text.UTF8Encoding $false))
    }
}

function Write-RetailCfg([string]$BaseCfg, [string]$RetailCfg) {
    # Retail (como F1b, run_f1bp_partida.ps1:146-151): el servidor va con BattlEye = 1 antes de class Missions,
    # o el cliente con BattlEye no entra. Se genera en la copia desechable desde la cfg de diag; si no casa, no
    # se lanza.
    $t = Get-Content $BaseCfg -Raw
    if ($t -notmatch '(?im)^\s*BattlEye\s*=') {
        $re = [regex]'(?im)^(\s*class\s+Missions)'
        $t = $re.Replace($t, "BattlEye = 1;`r`n`$1", 1)
    }
    $posBe = $t.IndexOf('BattlEye = 1;'); $posMis = $t.IndexOf('class Missions')
    if ($posBe -lt 0 -or $posMis -lt 0 -or $posBe -gt $posMis) {
        throw 'serverDZ_retail.cfg sin BattlEye = 1 antes de class Missions: no se lanza'
    }
    [IO.File]::WriteAllText($RetailCfg, $t, (New-Object Text.UTF8Encoding $false))
}

# --- ConfigJson: valores de la maquina fuera del codigo -----------------
if ($ConfigJson -and (Test-Path $ConfigJson)) {
    $cfg = Get-Content $ConfigJson -Raw | ConvertFrom-Json
    foreach ($name in @('DayZDir','DayZServerDir','ProbeLib','LibReinicio','ServerCtl','BuildPbo','MissionB1','GpuLease','FlagPath','Python','WorkRoot','ResultsDir','PackageDir','RemoteHost')) {
        if ($cfg.$name -and -not (Get-Variable $name -ValueOnly)) { Set-Variable $name $cfg.$name }
    }
    if ($cfg.Maquina) { $Maquina = [string]$cfg.Maquina }
    if ($cfg.MinVramLibre) { $MinVramLibre = [int]$cfg.MinVramLibre }
}
if (-not $Python) { $pyCmd = Get-Command python -ErrorAction SilentlyContinue; if ($pyCmd) { $Python = $pyCmd.Source } }
if (-not $ServerCtl) { $ServerCtl = Join-Path $PSScriptRoot 'f2p_server_ctl.ps1' }
if (-not $WorkRoot) { $WorkRoot = Join-Path $env:TEMP 'dsbx-f2p-work' }
if ($Maquina -eq 'portatil' -and -not $PackageDir) { $PackageDir = $PSScriptRoot }
if (-not $ResultsDir) {
    if ($Maquina -eq 'portatil') { $ResultsDir = Join-Path $PackageDir 'resultados' }
    else { $ResultsDir = Join-Path $WorkRoot 'resultados' }
}
$isHumo = [bool]$Humo
if ($isHumo -and $Build -eq 'humo') { $Build = 'diag' }
$effBuild = if ($Build -eq 'humo') { 'diag' } else { $Build }

$serverExeName = 'DayZDiag_x64.exe'
if ($effBuild -eq 'retail') { $serverExeName = 'DayZServer_x64.exe'; $serverBase = $DayZServerDir } else { $serverBase = $DayZDir }
$serverExe = if ($serverBase) { Join-Path $serverBase $serverExeName } else { $serverExeName }
# R2c-1: en diag el cliente es el mismo DayZDiag_x64 sin -server (F1b
# :141); en retail, DayZ_BE con adopcion del DayZ_x64 (F1b :152-191).
if ($effBuild -eq 'retail') { $clientExe = if ($DayZDir) { Join-Path $DayZDir 'DayZ_BE.exe' } else { 'DayZ_BE.exe' } }
else { $clientExe = if ($DayZDir) { Join-Path $DayZDir 'DayZDiag_x64.exe' } else { 'DayZDiag_x64.exe' } }
$serverProfile = Join-Path $WorkRoot 'profile-server'
$clientProfile = Join-Path $WorkRoot 'profile-client'
$missionDir = Join-Path $WorkRoot 'mission'
if ($Maquina -eq 'portatil') { $pboRoot = Join-Path $PackageDir $PboSub } else { $pboRoot = Join-Path $WorkRoot 'pbo' }
$mods = "{0};{1}" -f (Join-Path $pboRoot '@DayZSandbox'), (Join-Path $pboRoot '@DayZSandbox_QA')
# R2c-2: -config y -mission salen de la copia desechable, no de la b1.
$serverCfg = Join-Path $missionDir 'server\serverDZ.cfg'
if ($effBuild -eq 'retail') { $serverCfg = Join-Path $missionDir 'server\serverDZ_retail.cfg' }
$missionPath = Join-Path $missionDir 'mpmissions\dayzOffline.chernarusplus'
$cliArgsBase = "`"-mod=$mods`" -connect=127.0.0.1 -port=2302 `"-profiles=$clientProfile`" -name=DSBXQA -window -x=1280 -y=720 -noPause"
if ($effBuild -eq 'retail') { $cliArgsBase = "0 1 1 -exe DayZ_x64.exe $cliArgsBase" }
$rootSlash = $RemoteRoot.Replace('\', '/')

# --- Dry-run: ordenes exactas, sin ejecutar nada (R2-05) -----------------
if ($DryRun) {
    L ("dry-run maquina={0} build={1} cliente={2}" -f $Maquina, $Build, $Cliente)
    if ($Maquina -eq 'willy') {
        L ("lease GPU: {0} {1} comprobar --min-vram-libre {2}; adquirir; soltar" -f $Python, $GpuLease, $MinVramLibre)
        L ("bandera de espera: {0} con token propio" -f $FlagPath)
    } else {
        L 'portatil: sin lease de GPU ni bandera de espera'
    }
    if ($Maquina -eq 'portatil') {
        L ("comprobacion del paquete: sha256 de cada fichero contra {0}; si no casa, no se lanza" -f (Join-Path $PackageDir 'manifest.json'))
        L 'DayZ ajenos: cualquier DayZ* vivo (DayZDiag_x64, DayZ_x64, DayZServer_x64, DayZ_BE) para el lanzamiento y se dice en el log'
        L ("PBO del paquete: {0} y {1} comprobados por manifest; no se construye nada" -f (Join-Path $pboRoot '@DayZSandbox\addons\DayZSandbox.pbo'), (Join-Path $pboRoot '@DayZSandbox_QA\addons\DayZSandbox_QA.pbo'))
        L ("evidencia: por defecto bajo -ResultsDir {0} (resultados/run/manifest.json), no bajo el repo" -f $ResultsDir)
    }
    L ("mision desechable: copia nueva de la b1 en {0} en cada intento; -mission y -config salen de la copia" -f $missionDir)
    L ("WMI servidor: Invoke-CimMethod Win32_Process Create `"{0} -server `"-config={1}`" `"-profiles={2}`" `"-mission={3}`" `"-mod={4}`" -port=2302 -dologs -adminlog -freezecheck`"" -f $serverExe, $serverCfg, $serverProfile, $missionPath, $mods)
    if ($Cliente -eq 'lanzar') {
        L ("WMI cliente: Invoke-CimMethod Win32_Process Create `"{0} {1}`"" -f $clientExe, $cliArgsBase)
        if ($effBuild -eq 'retail') { L 'cliente retail: el PID propio es el del DayZ_x64 adoptado por procedencia (cadena BattlEye o RPT del perfil propio), con su hora de arranque' }
    } else {
        L ("cliente operador: aviso en {0} y espera del hello del peer cliente (tope {1} s)" -f (Join-Path $ResultsDir 'ESPERA_OPERADOR.txt'), $HelloTimeoutS)
    }
    $srvArgsDry = "-server `"-config=$serverCfg`" `"-profiles=$serverProfile`" `"-mission=$missionPath`" `"-mod=$mods`" -port=2302 -dologs -adminlog -freezecheck"
    L ("reinicio servidor: powershell -NoProfile -ExecutionPolicy Bypass -File {0} -Action restart -Build {1} -ServerExe {2} -ServerArgs '{3}' -WorkingDir {4} -ServerPid <pid> -ServerStart <iso> -ProfileDir {5} -Port 2302 -ClientPid <pid> -ClientStart <iso> -ClientExe {6} -ClientArgs '{7}' -ClientProfileDir {8} -ClientMods '{9}'" -f $ServerCtl, $effBuild, $serverExe, $srvArgsDry, $serverBase, $serverProfile, $clientExe, $cliArgsBase, $clientProfile, $mods)
    if ($isHumo) {
        L 'humo: comprobacion del paquete y de los ajenos, arranque con la mision copiada, hello del producto, hello de la sonda, hello del peer cliente y UID por per_status'
        L 'humo: ciclo de reinicio como el de F4 (parar los dos, drenar, arrancar los dos, mismos saludos, mismo UID) y cierre por WM_CLOSE de los PID propios'
        L ("humo: escribe {0} con cada paso y copia los logs a {1}; sin oraculo ni partida" -f (Join-Path $ResultsDir 'humo.json'), $ResultsDir)
    }
    L ("orquestador: {0} -B {1} --build {2} --mode {2} --evidence <BASE> --work-root {3} --server-profile {4} --client-profile {5}" -f $Python, (Join-Path $PSScriptRoot 'f2p_partida.py'), $effBuild, $WorkRoot, $serverProfile, $clientProfile)
    if ($Maquina -eq 'portatil' -or $RemoteHost) {
        L ("scp paquete: scp -r {0}/* {1}:{2}/" -f $PackageDir, $RemoteHost, $rootSlash)
        L ("ssh partida: ssh {0} `"powershell -NoProfile -ExecutionPolicy Bypass -File {1}/run_f2p_partida.ps1 -Maquina portatil`"" -f $RemoteHost, $rootSlash)
        L ("scp vuelta: scp -r {0}:{1}/resultados/* {2}/" -f $RemoteHost, $rootSlash, $ResultsDir)
    }
    if ($MontarPaquete) { L ("paquete: {0} -B {1} --out {2}" -f $Python, (Join-Path $PSScriptRoot 'f2p_paquete.py'), $PackageDir) }
    return
}

# --- Comprobaciones previas: si alguna falla, no se lanza ----------------
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:HumoSteps = @()
function Add-HumoStep([string]$Paso, [bool]$Ok, [string]$Motivo, [double]$Dur) {
    $script:HumoSteps += [ordered]@{ paso = $Paso; estado = $(if ($Ok) { 'ok' } else { 'fallo' }); motivo = $Motivo; duracion_s = [math]::Round($Dur, 3) }
}
function Write-HumoJson {
    if (-not $isHumo) { return }
    try {
        New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
        $allOk = @($script:HumoSteps | Where-Object { $_.estado -ne 'ok' }).Count -eq 0
        $doc = [ordered]@{ ok = $allOk; pasos = @($script:HumoSteps) }
        ($doc | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $ResultsDir 'humo.json') -Encoding utf8
    } catch { L ("no se pudo escribir humo.json: {0}" -f $_.Exception.Message) }
}
if ($isHumo -and -not ($Maquina -eq 'portatil' -and $Cliente -eq 'lanzar')) {
    throw 'el humo real (-Humo) exige -Maquina portatil y -Cliente lanzar'
}
# R2c-3/5: en el portatil, manifest del paquete y ningun DayZ ajeno; en
# Willy, git como hasta ahora.
if ($Maquina -eq 'portatil') {
    $swH = [Diagnostics.Stopwatch]::StartNew()
    try { $null = Test-PackageManifest $PackageDir; Add-HumoStep 'comprobacion_paquete_manifest' $true 'sha256 ok contra manifest.json' $swH.Elapsed.TotalSeconds }
    catch { Add-HumoStep 'comprobacion_paquete_manifest' $false $_.Exception.Message $swH.Elapsed.TotalSeconds; Write-HumoJson; throw }
    $swH = [Diagnostics.Stopwatch]::StartNew()
    $foreign = @(Get-Process -Name 'DayZ*' -ErrorAction SilentlyContinue)
    if ($foreign.Count) {
        $desc = ($foreign | ForEach-Object { "{0}:{1}" -f $_.ProcessName, $_.Id }) -join ', '
        L ("hay DayZ ajenos en el portatil: {0}; no se lanza" -f $desc)
        Add-HumoStep 'sin_dayz_ajenos' $false ("DayZ ajenos vivos: " + $desc) $swH.Elapsed.TotalSeconds
        Write-HumoJson
        throw 'hay procesos DayZ ajenos en el portatil: no se lanza'
    }
    Add-HumoStep 'sin_dayz_ajenos' $true 'ningun DayZ* vivo' $swH.Elapsed.TotalSeconds
} else {
    $dirty = & git -c core.autocrlf=false -C $repoRoot status --porcelain -- . ':(exclude)DayZSandbox_dev/evidence'
    if ($dirty) { throw 'worktree sucio fuera de evidence' }
    $foreign = Get-Process -Name 'DayZ*' -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -notmatch 'Diag|Launcher' }
    if ($foreign -and $Build -ne 'humo') { throw 'hay procesos DayZ ajenos' }
}

$leaseHeld = $false
$flagToken = [guid]::NewGuid().ToString()
try {
    if ($Maquina -eq 'willy') {
        if ($FlagPath) {
            if (Test-Path $FlagPath) {
                $owner = Get-Content $FlagPath -Raw
                if ($owner -notmatch 'f2p') { throw 'la bandera de espera no es nuestra' }
            }
            $flagDir = Split-Path $FlagPath
            if ($flagDir -and -not (Test-Path $flagDir)) { New-Item -ItemType Directory -Path $flagDir -Force | Out-Null }
            Set-Content -Path $FlagPath -Value ("f2p {0}" -f $flagToken) -Encoding ascii
        }
        if ($GpuLease -and (Test-Path $GpuLease)) {
            & $Python $GpuLease comprobar --min-vram-libre $MinVramLibre
            if ($LASTEXITCODE -ne 0) { throw 'gpu_lease comprobar fallo' }
            & $Python $GpuLease adquirir
            if ($LASTEXITCODE -ne 0) { throw 'gpu_lease adquirir fallo' }
            $leaseHeld = $true
        }
    } else {
        L 'portatil: sin lease de GPU ni bandera de espera'
    }

    if ($MontarPaquete) {
        & $Python (Join-Path $PSScriptRoot 'f2p_paquete.py') --out $PackageDir --lib-reinicio $LibReinicio --probe-lib $ProbeLib --pbo-dir $pboRoot
        if ($LASTEXITCODE -ne 0) { throw 'montar el paquete fallo' }
    }
    if ($SmokeServerOnly) { L 'humo solo servidor: lo corre la orquestadora con smoke -Exe'; return }

    New-Item -ItemType Directory -Path $WorkRoot, $serverProfile, $clientProfile, $ResultsDir -Force | Out-Null

    # R2c-4: en el portatil no se construye nada (PBO del paquete,
    # comprobados por manifest); en Willy se construyen. Nunca un PBO
    # de relleno en modo real: si falta la sonda, no se lanza.
    $productAddons = Join-Path $pboRoot '@DayZSandbox\addons'
    $probeAddons = Join-Path $pboRoot '@DayZSandbox_QA\addons'
    $productPbo = Join-Path $productAddons 'DayZSandbox.pbo'
    $probePbo = Join-Path $probeAddons 'DayZSandbox_QA.pbo'
    if ($Maquina -eq 'portatil') {
        if (-not (Test-Path $productPbo)) { throw ("falta el PBO del producto del paquete {0}: no se lanza" -f $productPbo) }
        if (-not (Test-Path $probePbo)) { throw ("falta la sonda del paquete {0}: no se lanza" -f $probePbo) }
        L ("PBO del paquete (sin construir): {0} y {1}" -f $productPbo, $probePbo)
    } else {
        New-Item -ItemType Directory -Path $productAddons, $probeAddons -Force | Out-Null
        & $Python (Join-Path $repoRoot 'DayZSandbox_dev\qa\build_core_pbo.py') --out $pboRoot
        if ($LASTEXITCODE -ne 0) { throw 'build_core_pbo fallo' }
        if (-not (Test-Path $productPbo)) { throw 'falta el PBO del producto tras construir: no se lanza' }
        if ($BuildPbo -and (Test-Path $BuildPbo)) { & $Python $BuildPbo --out $probePbo }
        if (-not (Test-Path $probePbo)) { throw 'falta la sonda: no se lanza (nunca un PBO de relleno en modo real)' }
    }

    # R2c-2: cada intento copia una mision nueva desde la b1.
    if ($MissionB1 -and (Test-Path $MissionB1)) { Copy-FreshMission $MissionB1 $missionDir }
    if ($effBuild -eq 'retail') { Write-RetailCfg (Join-Path $missionDir 'server\serverDZ.cfg') $serverCfg }
    if ($ProbeLib -and (Test-Path $ProbeLib)) { . $ProbeLib }

    # Comprobación previa (24-nov): el mismo camino hasta justo antes de abrir DayZ. Paquete, PBO, misión
    # copiada, procedencia y sello, puertos, backend y tap, y dsbx_peer.json en los dos perfiles. No abre DayZ
    # ni cuenta como tanda; deja <ResultsDir>\comprobacion.json y sale con 0 si todo está bien.
    if ($Comprobar) {
        $chkArgs = @('-B', (Join-Path $PSScriptRoot 'f2p_partida.py'), '--comprobar',
                     '--build', $effBuild, '--work-root', $WorkRoot, '--results-dir', $ResultsDir,
                     '--server-profile', $serverProfile, '--client-profile', $clientProfile,
                     '--pbo', $probePbo, '--product-pbo', $productPbo,
                     '--server-exe', $serverExe, '--client-exe', $clientExe,
                     '--mission-dir', $missionDir, '--package-dir', $PackageDir)
        & $Python @chkArgs
        $chkRc = $LASTEXITCODE
        L ("comprobacion previa: rc={0} (0 = todo bien; si no, no se abre DayZ)" -f $chkRc)
        exit $chkRc
    }

    # Logs de partidas anteriores fuera de los perfiles (T4, 24-nov): se mueven a trabajo\logs_archivados.
    $archStamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
    foreach ($pairA in @(@($serverProfile, 'server'), @($clientProfile, 'client'))) {
        $nA = Move-OldProfileLogs $pairA[0] (Join-Path $WorkRoot ("logs_archivados\{0}\{1}" -f $archStamp, $pairA[1]))
        if ($nA -gt 0) { L ("logs viejos de {0}: {1} movidos a logs_archivados\{2}" -f $pairA[1], $nA, $archStamp) }
    }

    # Arranque real por WMI, con PID propio y hora de arranque (R2-05)
    $srvPid = 0; $cliPid = 0; $srvArgs = ''; $cliArgs = ''
    if ($Build -ne 'humo' -or $isHumo) {
        $srvArgs = "-server `"-config=$serverCfg`" `"-profiles=$serverProfile`" `"-mission=$missionPath`" `"-mod=$mods`" -port=2302 -dologs -adminlog -freezecheck"
        $swH = [Diagnostics.Stopwatch]::StartNew()
        $srvPid = Start-ExeViaWmi $serverExe $serverBase $srvArgs
        RegisterOwn $srvPid
        L ("servidor WMI pid={0} start={1}" -f $srvPid, $script:PidStart[[string]$srvPid])
        if ($SondaLease) {
            L 'sonda de lease (T4, 24-nov): solo servidor, sin cliente'
        } elseif ($Cliente -eq 'lanzar') {
            $cliArgs = $cliArgsBase
            $cliPid = Start-ClientOwn $clientExe $DayZDir $cliArgs $effBuild $clientProfile $mods
        } else {
            $aviso = Join-Path $ResultsDir 'ESPERA_OPERADOR.txt'
            Set-Content -Path $aviso -Value 'Abra el cliente desde la Sesion de pruebas; el runner espera su hello.' -Encoding utf8
            L ("cliente operador: aviso en {0}; espera del hello con tope {1} s" -f $aviso, $HelloTimeoutS)
        }
        Add-HumoStep 'arranque_servidor_y_cliente_mision_copiada' $true ("servidor pid={0} cliente pid={1} mision={2}" -f $srvPid, $cliPid, $missionPath) $swH.Elapsed.TotalSeconds
    }

    # R2c-6: en el portatil la evidencia va bajo -ResultsDir.
    if (-not $Evidence) {
        if ($Maquina -eq 'portatil') { $Evidence = $ResultsDir }
        else {
            $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
            $Evidence = Join-Path $repoRoot ("DayZSandbox_dev\evidence\m1\F2P\{0}-{1}" -f $effBuild, $stamp)
        }
    }
    if ($isHumo) {
        $orchArgs = @('-B', (Join-Path $PSScriptRoot 'f2p_partida.py'),
                      '--build', $effBuild, '--mode', 'humo', '--evidence', $ResultsDir,
                      '--work-root', $WorkRoot,
                      '--hello-timeout-s', [string]$HelloTimeoutS,
                      '--cliente', $Cliente,
                      '--server-profile', $serverProfile, '--client-profile', $clientProfile,
                      '--server-ctl', $ServerCtl, '--server-exe', $serverExe,
                      '--server-args', $srvArgs, '--working-dir', $serverBase,
                      '--server-pid', [string]$srvPid,
                      '--server-start', [string]$script:PidStart[[string]$srvPid],
                      '--client-exe', $clientExe, '--client-args', $cliArgs,
                      '--client-pid', [string]$cliPid,
                      '--client-start', [string]$script:PidStart[[string]$cliPid])
        & $Python @orchArgs
        $orchRc = $LASTEXITCODE
        L ("humo: orquestador salio con {0}" -f $orchRc)
        $pasosPath = Join-Path $ResultsDir 'humo_pasos.json'
        if (Test-Path $pasosPath) {
            $pasosDoc = Get-Content $pasosPath -Raw | ConvertFrom-Json
            foreach ($p in @($pasosDoc.pasos)) { Add-HumoStep ([string]$p.paso) ($p.estado -eq 'ok') ([string]$p.motivo) ([double]$p.duracion_s) }
        } else {
            Add-HumoStep 'saludos_y_reinicio' $false 'sin humo_pasos.json del orquestador' 0
        }
        # PID finales tras el reinicio (los escribe el orquestador).
        $pidsFinal = Join-Path $WorkRoot 'f2p_pids_final.json'
        if (Test-Path $pidsFinal) {
            $pf = Get-Content $pidsFinal -Raw | ConvertFrom-Json
            if ($pf.server.pid) { RegisterOwn ([int]$pf.server.pid) }
            if ($pf.client.pid) { RegisterOwn ([int]$pf.client.pid) }
        }
        $logDirH = Join-Path $ResultsDir 'logs'
        foreach ($pair in @(@($serverProfile, 'server'), @($clientProfile, 'client'))) {
            $destH = Join-Path $logDirH $pair[1]
            New-Item -ItemType Directory -Path $destH -Force | Out-Null
            Get-ChildItem -Path $pair[0] -Recurse -Include 'script_*.log','*.RPT','*.ADM','*.mdmp' -ErrorAction SilentlyContinue |
                ForEach-Object { Copy-Item $_.FullName -Destination $destH -Force -ErrorAction SilentlyContinue }
        }
        $swH = [Diagnostics.Stopwatch]::StartNew()
        CloseOwn
        $ownAlive = Test-OwnAlive
        Add-HumoStep 'cierre_wm_close_pid_propios' (-not $ownAlive) $(if ($ownAlive) { 'queda un PID propio vivo tras WM_CLOSE' } else { 'ningun DayZ propio vivo tras WM_CLOSE' }) $swH.Elapsed.TotalSeconds
        Write-HumoJson
        if ($orchRc -ne 0 -or $ownAlive) { exit 1 }
        exit 0
    }
    $mode = $effBuild
    if ($SondaLease) { $mode = 'lease' }
    $orchArgs = @('-B', (Join-Path $PSScriptRoot 'f2p_partida.py'),
                  '--build', $effBuild, '--mode', $mode, '--evidence', $Evidence,
                  '--work-root', $WorkRoot,
                  '--hello-timeout-s', [string]$HelloTimeoutS,
                  '--cliente', $Cliente,
                  '--server-profile', $serverProfile, '--client-profile', $clientProfile)
    if ($Build -ne 'humo') {
        # Los PBO con los que se arrancó (paquete en el portátil, construidos en Willy): el orquestador
        # sella pbo.stamp con su sha256 y no arranca sin ellos (24-nov).
        $orchArgs += @('--pbo', $probePbo, '--product-pbo', $productPbo)
        $orchArgs += @('--server-ctl', $ServerCtl, '--server-exe', $serverExe,
                       '--server-args', $srvArgs, '--working-dir', $serverBase,
                       '--server-pid', [string]$srvPid,
                       '--server-start', [string]$script:PidStart[[string]$srvPid],
                       '--client-exe', $clientExe)
        # Sin cliente (-SondaLease) $cliArgs es '' y PowerShell 5.1 descarta el argumento vacio: argparse veia
        # --client-args sin valor y salia con 2 (3b de t4-d940786). Solo se pasa si hay cliente.
        if ($cliArgs) { $orchArgs += @('--client-args', $cliArgs) }
        if ($Cliente -eq 'lanzar' -and $cliPid) {
            $orchArgs += @('--client-pid', [string]$cliPid,
                           '--client-start', [string]$script:PidStart[[string]$cliPid])
        }
    }
    & $Python @orchArgs
    $orchRc = $LASTEXITCODE
    L ("orquestador salio con {0}" -f $orchRc)
    $pidsFinal = Join-Path $WorkRoot 'f2p_pids_final.json'
    if (Test-Path $pidsFinal) {
        $pf = Get-Content $pidsFinal -Raw | ConvertFrom-Json
        if ($pf.server.pid) { RegisterOwn ([int]$pf.server.pid) }
        if ($pf.client.pid) { RegisterOwn ([int]$pf.client.pid) }
    }

    $logDir = Join-Path $Evidence 'run\logs'
    foreach ($pair in @(@($serverProfile, 'server'), @($clientProfile, 'client'))) {
        $destL = Join-Path $logDir $pair[1]
        New-Item -ItemType Directory -Path $destL -Force | Out-Null
        Get-ChildItem -Path $pair[0] -Recurse -Include 'script_*.log','*.RPT','*.ADM','*.mdmp' -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item $_.FullName -Destination $destL -Force -ErrorAction SilentlyContinue }
    }
    exit $orchRc
}
finally {
    CloseOwn
    # Segunda copia de logs, ya cerrados los procesos propios (24-nov: los del cliente no se copiaban en la
    # primera porque seguían abiertos). Incluye los error_*.log del cliente.
    if ($logDir -and (Test-Path $logDir)) {
        foreach ($pair in @(@($serverProfile, 'server'), @($clientProfile, 'client'))) {
            $destF = Join-Path $logDir $pair[1]
            New-Item -ItemType Directory -Path $destF -Force | Out-Null
            if ($pair[0] -and (Test-Path $pair[0])) {
                Get-ChildItem -Path $pair[0] -Recurse -Include 'script_*.log','*.RPT','*.ADM','*.mdmp','error_*.log' -ErrorAction SilentlyContinue |
                    ForEach-Object { Copy-Item $_.FullName -Destination $destF -Force -ErrorAction SilentlyContinue }
            }
        }
    }
    if ($leaseHeld -and $GpuLease -and -not (Test-OwnAlive)) { & $Python $GpuLease soltar }
    if ($Maquina -eq 'willy' -and $FlagPath -and (Test-Path $FlagPath)) {
        $owner = Get-Content $FlagPath -Raw
        if ($owner -match [regex]::Escape($flagToken)) { Remove-Item $FlagPath -Force }
    }
}
