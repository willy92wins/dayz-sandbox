#Requires -Version 5.1
# F1b-peers en partida (brief plans/2026-11-15-m1-f1b-peers-partida-brief.md, v1.2, sec. 1 y 8).
# Esqueleto del lanzador de F0.3-0 (C:\tmp\dsbx-f030-work\partida\run_f030_partida.ps1), con lo de L-12:
# cada proceso propio se identifica por PID e instante de creacion, y el lease solo se suelta cuando
# ninguno sigue vivo. Nunca mata procesos: solo WM_CLOSE a los PID propios.
# Protocolo con el orquestador (f1bp_live.py run): el orquestador escribe las configuraciones del peer y
# <ev>\ready.json; aqui se lanza el juego y se escribe pids.json; el orquestador corre los escenarios y
# deja <ev>\scenarios_done.json; aqui se cierra el juego, se copian los logs y se escribe
# <ev>\logs_ready.json; el orquestador busca las claves en los logs y sale; aqui se lanza el evaluador.
param(
  [Parameter(Mandatory = $true)][ValidateSet('diag', 'retail')][string]$Build,
  [Parameter(Mandatory = $true)][string]$Mod,          # carpeta @DayZSandbox con Addons\DayZSandbox.pbo
  [Parameter(Mandatory = $true)][string]$Scenarios,    # p. ej. 'G1,G2,G3'
  [string]$WorkRoot = 'C:\tmp\dsbx-f1bpeers-work\partida',
  [string]$WS = 'C:\tmp\dsbx-f1bpeers\DayZSandbox_dev',
  [int]$RunTimeoutMin = 120,
  [string]$Orchestrator = 'qa/live/f1bp_live.py'   # otro orquestador con el mismo protocolo (p. ej. una prueba de humo)
)
$ErrorActionPreference = 'Continue'
# probe-lib.ps1 fija $script:Root a su propia carpeta: por eso aqui la raiz de trabajo se llama $WorkRoot.
. 'C:\Users\guill\MCPTest_autotest\harness\probe-lib.ps1'
$ErrorActionPreference = 'Continue'
$S = "$WorkRoot\profiles_$Build\server"; $C = "$WorkRoot\profiles_$Build\client"
$B1 = "$WorkRoot\b1"
$Port = 2502
$Py = 'C:\Python314\python.exe'
$Lease = 'C:\Users\guill\.claude\tools\gpu_lease.py'
$LeaseSesion = 'f1b-peers-partida'
$Log = "$WorkRoot\run_$Build.log"
function L([string]$m) { $line = "$(Get-Date -Format 'HH:mm:ss.fff') $m"; Add-Content -Path $Log -Value $line -Encoding UTF8; Write-Host $line }
function Utc { (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }
function Start-ExeViaWmi([string]$Exe, [string]$Cwd, [string]$ArgLine) {
  $cmd = '"' + $Exe + '" ' + $ArgLine
  $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $Cwd }
  if ($r.ReturnValue -ne 0) { throw "Win32_Process.Create devolvio $($r.ReturnValue) para $Exe" }
  return [int]$r.ProcessId
}
# Identidad de un proceso propio: PID + instante de creacion (un PID reutilizado por otro proceso no es nuestro).
function Own([string]$Role, [int]$ProcessId) {
  $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  $st = $null; if ($p) { try { $st = $p.StartTime.ToUniversalTime().ToString('o') } catch { $st = $null } }
  [pscustomobject]@{ role = $Role; pid = $ProcessId; start_time = $st }
}
# EVIDENCIA v1.5, R14: sin instante de creacion no hay identidad. Ese proceso cuenta como vivo mientras
# exista su PID (bloquea la suelta del lease) y nunca recibe WM_CLOSE.
function IsAlive($o) {
  $p = Get-Process -Id $o.pid -ErrorAction SilentlyContinue
  if (-not $p) { return $false }
  if (-not $o.start_time) { return $true }
  try { return ($p.StartTime.ToUniversalTime().ToString('o') -eq $o.start_time) } catch { return $true }
}
function CloseOwn($o) {
  if (-not (IsAlive $o)) { return "$($o.role) pid $($o.pid) ya no estaba" }
  if (-not $o.start_time) { return "$($o.role) pid $($o.pid) SIN instante de creacion: no lo cierro" }
  foreach ($h in [MCPWin]::WindowsOf([uint32]$o.pid)) { [void][MCPWin]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
  for ($i = 0; $i -lt 240; $i++) { Start-Sleep -Milliseconds 500; if (-not (IsAlive $o)) { return "$($o.role) pid $($o.pid) cerrado por WM_CLOSE" } }
  return "$($o.role) pid $($o.pid) SIGUE VIVO tras WM_CLOSE"
}
# R16 (rev. H-15). Bajo BattlEye el padre de DayZ_x64 puede ser un intermedio que ya ha salido (medido el
# 15-nov: padre 66172 inexistente), y entonces la cadena no llega al lanzador. El juego escribe su linea de
# ordenes completa en el RPT de su perfil: si un RPT del perfil propio, posterior al lanzador, lleva nuestro
# -mod, -profiles y -port exactos, devuelve el instante (local) de su nombre; si no, $null.
function RptPropio([string]$Dir, [string]$ModArg, [int]$PortArg, [datetime]$Desde) {
  foreach ($f in @(Get-ChildItem -LiteralPath $Dir -Filter 'DayZ_x64_*.RPT' -File -ErrorAction SilentlyContinue)) {
    if ($f.LastWriteTime -lt $Desde) { continue }
    $m = [regex]::Match($f.Name, '^DayZ_x64_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.RPT$')
    if (-not $m.Success) { continue }
    $t = New-Object DateTime ([int]$m.Groups[1].Value), ([int]$m.Groups[2].Value), ([int]$m.Groups[3].Value), ([int]$m.Groups[4].Value), ([int]$m.Groups[5].Value), ([int]$m.Groups[6].Value)
    # La cabecera tiene dos lineas '== ': la del ejecutable y la de la linea de ordenes (medido el 15-nov).
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
# JSON con LF (EVIDENCIA); las claves van ya ordenadas en los [ordered] de quien llama.
function WriteJson([string]$Path, $Obj) {
  $tmp = "$Path.tmp"
  $text = (($Obj | ConvertTo-Json -Depth 6) -replace "`r`n", "`n") + "`n"
  [IO.File]::WriteAllText($tmp, $text, (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -Force $tmp $Path
}

# --- comprobaciones previas
New-Item -ItemType Directory -Force $WorkRoot | Out-Null
$pbo = Join-Path $Mod 'Addons\DayZSandbox.pbo'
if (-not (Test-Path $pbo)) { L "no existe $pbo : no lanzo"; exit 3 }
# EVIDENCIA v1.5, R1: todo el worktree (tambien el mod hermano DayZSandbox/), menos la evidencia.
$RepoRoot = Split-Path $WS -Parent
$dirty = (& git -C $RepoRoot status --porcelain -- . ':(exclude)DayZSandbox_dev/evidence') -join "`n"
if ($LASTEXITCODE -ne 0) { L "git status fallo en $RepoRoot (exit $LASTEXITCODE): no lanzo"; exit 3 }
if ($dirty) { L "worktree sucio fuera de DayZSandbox_dev/evidence (git_dirty): no lanzo`n$dirty"; exit 3 }
$ajenos = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'DayZ*' -and $_.ProcessName -ne 'DayZToolsLauncher' })
if ($ajenos.Count) { L "hay DayZ abiertos ($(($ajenos | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ', ')): no lanzo"; exit 3 }
$co = & $Py -I $Lease comprobar --min-vram-libre 4000 2>&1 | Out-String
L "gpu_lease comprobar (exit $LASTEXITCODE): $($co.Trim())"
if ($LASTEXITCODE -ne 0) { L "GPU OCUPADA: no lanzo"; exit 4 }
$lo = & $Py -I $Lease adquirir --motivo "F1b-peers partida $Build" --minutos $($RunTimeoutMin + 30) --sesion $LeaseSesion 2>&1 | Out-String
L "gpu_lease adquirir (exit $LASTEXITCODE): $($lo.Trim())"
if ($LASTEXITCODE -ne 0) { L "sin lease de GPU: no lanzo"; exit 4 }

$own = @()
$identityProblem = $false   # R14: un proceso propio sin identidad acreditada impide soltar el lease
$ev = "evidence/m1/F1b-peers/$Build-$(Utc)"
$evAbs = Join-Path $WS $ev
$allClosed = $false
try {
  if (-not (Test-Path $B1)) { Copy-Item -Recurse 'C:\tmp\dsbx-f030-work\partida\b1' $B1 }
  New-Item -ItemType Directory -Force $S, $C | Out-Null
  Remove-Item "$S\dsbx_peer.json", "$C\dsbx_peer.json" -ErrorAction SilentlyContinue
  $arch = "$WorkRoot\old_logs_${Build}_$(Utc)"
  foreach ($pair in @(@('server', $S), @('client', $C))) {
    $old = @(Get-ChildItem $pair[1] -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.log', '.RPT', '.ADM', '.mdmp' })
    if ($old.Count) { New-Item -ItemType Directory -Force "$arch\$($pair[0])" | Out-Null; $old | Move-Item -Destination "$arch\$($pair[0])" -Force; L "$($pair[0]): $($old.Count) logs viejos archivados" }
  }
  $pidsFile = "$WorkRoot\pids_$Build.json"
  Remove-Item $pidsFile -ErrorAction SilentlyContinue
  $out = "$WorkRoot\orq_$Build.out"; $err = "$WorkRoot\orq_$Build.err"
  $orqArgs = @($Orchestrator, 'run', '--build', $Build, '--evidence', $ev, '--server-profile', $S, '--client-profile', $C, '--pids-file', $pidsFile, '--scenarios', $Scenarios, '--pbo', $pbo)
  $h = Start-Process -FilePath $Py -ArgumentList $orqArgs -WorkingDirectory $WS -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -NoNewWindow
  $null = $h.Handle
  L "orquestador pid=$($h.Id): $($orqArgs -join ' ')"
  for ($i = 0; $i -lt 120 -and -not (Test-Path "$evAbs\ready.json"); $i++) { Start-Sleep -Milliseconds 500 }
  if (-not (Test-Path "$evAbs\ready.json")) { L "el orquestador no escribio ready.json: no lanzo el juego"; throw 'ready' }

  if ($Build -eq 'diag') {
    $sp = Start-DayZViaWmi "-server `"-config=$B1\server\serverDZ.cfg`" `"-profiles=$S`" `"-mission=$B1\mpmissions\dayzOffline.chernarusplus`" `"-mod=$Mod`" -port=$Port -dologs -adminlog -freezecheck"
    $own += Own 'server' $sp.pid; L "servidor diag pid=$($sp.pid)"
    Start-Sleep -Seconds 60
    $cp = Start-DayZViaWmi "`"-mod=$Mod`" -connect=127.0.0.1 -port=$Port `"-profiles=$C`" -name=DSBXQA -window -x=1280 -y=720 -noPause"
    $own = @(Own 'client' $cp.pid) + $own; L "cliente diag pid=$($cp.pid)"
  } else {
    $GameDir = 'C:\Program Files (x86)\Steam\steamapps\common\DayZ'
    $SrvDir = 'C:\Program Files (x86)\Steam\steamapps\common\DayZServer'
    $cfgRet = "$B1\server\serverDZ_retail.cfg"
    $cfgText = Get-Content "$B1\server\serverDZ.cfg" -Raw
    if ($cfgText -notmatch '(?im)^\s*BattlEye\s*=') { $re = [regex]'(?im)^(\s*class\s+Missions)'; $cfgText = $re.Replace($cfgText, "BattlEye = 1;`r`n`$1", 1) }
    $posBe = $cfgText.IndexOf('BattlEye = 1;'); $posMis = $cfgText.IndexOf('class Missions')
    if ($posBe -lt 0 -or $posMis -lt 0 -or $posBe -gt $posMis) { L "serverDZ_retail.cfg sin BattlEye = 1 antes de class Missions: no lanzo"; throw 'cfg' }
    [IO.File]::WriteAllText($cfgRet, $cfgText, (New-Object System.Text.UTF8Encoding($false)))
    $spid = Start-ExeViaWmi (Join-Path $SrvDir 'DayZServer_x64.exe') $SrvDir "`"-config=$cfgRet`" `"-profiles=$S`" `"-mission=$B1\mpmissions\dayzOffline.chernarusplus`" `"-mod=$Mod`" -port=$Port -dologs -adminlog -freezecheck"
    $own += Own 'server' $spid; L "servidor retail pid=$spid"
    Start-Sleep -Seconds 60
    $antes = @(Get-Process -Name DayZ_x64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    $bepid = Start-ExeViaWmi (Join-Path $GameDir 'DayZ_BE.exe') $GameDir "0 1 1 -exe DayZ_x64.exe `"-mod=$Mod`" -connect=127.0.0.1 -port=$Port `"-profiles=$C`" -name=DSBXQA -window -x=1280 -y=720 -noPause"
    $beOwn = Own 'battleye_launcher' $bepid
    $own += $beOwn; L "lanzador BattlEye pid=$bepid"
    # R14 y R16 (Z-01 de Sol; rev. H-15). Bajo BattlEye la linea de ordenes de DayZ_x64 sale vacia en WMI
    # (F0.3-0). Un DayZ_x64 nuevo tiene procedencia si (a) su cadena de ParentProcessId (hasta 3 niveles) llega
    # al lanzador BattlEye, o (b) un RPT del perfil propio, posterior al lanzador, lleva nuestro -mod, -profiles
    # y -port exactos y su instante dista 10 s o menos de la creacion del candidato (RptPropio). Sin adopcion
    # solo por tiempo. Un candidato con procedencia se adopta; cero o varios: no se adopta ni se cierra ninguno y
    # no se suelta el lease.
    $beStart = $null
    try { $beStart = (Get-Process -Id $bepid -ErrorAction Stop).StartTime } catch { $beStart = (Get-Date).AddSeconds(-5) }
    $adopted = $false
    for ($i = 0; $i -lt 240; $i++) {
      Start-Sleep -Milliseconds 500
      $todos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
      $padre = @{}; foreach ($p in $todos) { $padre[[int]$p.ProcessId] = [int]$p.ParentProcessId }
      $nuevos = @($todos | Where-Object { $_.Name -eq 'DayZ_x64.exe' -and ($antes -notcontains [int]$_.ProcessId) })
      if ($nuevos.Count -eq 0) { continue }
      $rpt = RptPropio $C $Mod $Port $beStart
      $cands = @()
      foreach ($q in $nuevos) {
        $via = $null
        $x = [int]$q.ParentProcessId
        for ($n = 0; $n -lt 3 -and $x -gt 0; $n++) { if ($x -eq $bepid) { $via = 'desciende del lanzador BattlEye'; break }; if ($padre.ContainsKey($x)) { $x = $padre[$x] } else { break } }
        if (-not $via -and $rpt -and [math]::Abs(($q.CreationDate - $rpt).TotalSeconds) -le 10) { $via = 'su RPT en el perfil propio lleva nuestra linea de ordenes' }
        if ($via) { $cands += [pscustomobject]@{ pid = [int]$q.ProcessId; via = $via } }
      }
      if ($cands.Count -eq 0) { continue }
      if ($cands.Count -eq 1) {
        $cli = Own 'client' $cands[0].pid
        if (-not $cli.start_time) { $identityProblem = $true; L "cliente retail pid=$($cli.pid) sin instante de creacion: identidad sin acreditar" }
        $own = @($cli) + $own; $adopted = $true; L "cliente retail (juego) pid=$($cli.pid): $($cands[0].via)"; break
      }
      $identityProblem = $true; L "hay $($cands.Count) DayZ_x64 con procedencia: no adopto ninguno"; break
    }
    if (-not $adopted -and -not $identityProblem) { $identityProblem = $true; L "ningun DayZ_x64 con procedencia (cadena ni RPT propio) en 120 s: identidad sin acreditar, no cierro ni adopto nada" }
  }
  foreach ($o in $own) { if (-not $o.start_time) { $identityProblem = $true; L "$($o.role) pid $($o.pid) sin instante de creacion: identidad sin acreditar" } }
  WriteJson $pidsFile @{ processes = $own }
  L "pids.json: $(($own | ForEach-Object { "$($_.role)=$($_.pid)" }) -join ', ')"

  for ($i = 0; $i -lt ($RunTimeoutMin * 120) -and -not (Test-Path "$evAbs\scenarios_done.json") -and -not $h.HasExited; $i++) { Start-Sleep -Milliseconds 500 }
  L "escenarios terminados: $(Test-Path "$evAbs\scenarios_done.json") (orquestador vivo: $(-not $h.HasExited))"
}
finally {
  foreach ($o in $own) { L (CloseOwn $o) }
  $vivos = @($own | Where-Object { IsAlive $_ })
  # R2 y R14: logs finales solo con todo lo propio cerrado y todas las identidades acreditadas.
  $allClosed = ($vivos.Count -eq 0) -and (-not $identityProblem)
  if (Test-Path $evAbs) {
    $logs = "$evAbs\logs"; New-Item -ItemType Directory -Force $logs | Out-Null
    # R3: por perfil, su carpeta y todos sus logs; y la correspondencia de cada copia.
    $perPeer = @{}
    $copies = @()
    foreach ($pair in @(@('server', $S), @('client', $C))) {
      $files = @(Get-ChildItem $pair[1] -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.log', '.RPT', '.ADM', '.mdmp' })
      $perPeer[$pair[0]] = [ordered]@{ dir = (Resolve-Path $pair[1]).Path; files = @($files | ForEach-Object { $_.Name } | Sort-Object) }
      $sl = @($files | Where-Object { $_.Name -like 'script_*.log' })
      if ($sl.Count -eq 1) { Copy-Item $sl[0].FullName "$logs\$($pair[0])_script.log" -Force; $copies += [ordered]@{ dest = "$($pair[0])_script.log"; peer = $pair[0]; src = $sl[0].Name } }
      elseif ($sl.Count -gt 1) { L "$($pair[0]): $($sl.Count) script_*.log de la sesion (log_ambiguous): no copio ninguno" }
      $rpt = @($files | Where-Object { $_.Extension -eq '.RPT' })
      if ($rpt.Count -eq 1) { Copy-Item $rpt[0].FullName "$logs\$($pair[0]).RPT" -Force; $copies += [ordered]@{ dest = "$($pair[0]).RPT"; peer = $pair[0]; src = $rpt[0].Name } }
      elseif ($rpt.Count -gt 1) { L "$($pair[0]): $($rpt.Count) RPT de la sesion: no copio ninguno" }
    }
    $inv = [ordered]@{ client = $perPeer['client']; copies = @($copies); server = $perPeer['server'] }
    WriteJson "$logs\inventory.json" $inv
    WriteJson "$evAbs\logs_ready.json" ([ordered]@{ all_closed = $allClosed })
    if ($h -and -not $h.HasExited) { $h.WaitForExit(15 * 60000) | Out-Null }
    if ($h) { L "orquestador exit $($h.ExitCode)" }
    & $Py (Join-Path $WS 'qa\live\f1bp_eval.py') $evAbs 2>&1 | ForEach-Object { L "eval: $_" }
    L "evaluador exit $LASTEXITCODE ($ev)"
  }
  if ($allClosed) {
    $so = & $Py -I $Lease soltar --sesion $LeaseSesion 2>&1 | Out-String
    L "gpu_lease soltar (exit $LASTEXITCODE): $($so.Trim())"
  } elseif ($identityProblem) {
    L "IDENTIDAD DE PROCESOS SIN ACREDITAR (R14): NO suelto el lease; revisar a mano los DayZ abiertos"
    exit 5
  } else {
    L "QUEDAN PROCESOS PROPIOS VIVOS ($(($vivos | ForEach-Object { "$($_.role)=$($_.pid)" }) -join ', ')): NO suelto el lease"
    exit 5
  }
  L "fin"
}
