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
function IsAlive($o) {
  $p = Get-Process -Id $o.pid -ErrorAction SilentlyContinue
  if (-not $p) { return $false }
  if (-not $o.start_time) { return $true }
  try { return ($p.StartTime.ToUniversalTime().ToString('o') -eq $o.start_time) } catch { return $true }
}
function CloseOwn($o) {
  if (-not (IsAlive $o)) { return "$($o.role) pid $($o.pid) ya no estaba" }
  foreach ($h in [MCPWin]::WindowsOf([uint32]$o.pid)) { [void][MCPWin]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
  for ($i = 0; $i -lt 240; $i++) { Start-Sleep -Milliseconds 500; if (-not (IsAlive $o)) { return "$($o.role) pid $($o.pid) cerrado por WM_CLOSE" } }
  return "$($o.role) pid $($o.pid) SIGUE VIVO tras WM_CLOSE"
}
function WriteJson([string]$Path, $Obj) {
  $tmp = "$Path.tmp"
  [IO.File]::WriteAllText($tmp, ($Obj | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -Force $tmp $Path
}

# --- comprobaciones previas
New-Item -ItemType Directory -Force $WorkRoot | Out-Null
$pbo = Join-Path $Mod 'Addons\DayZSandbox.pbo'
if (-not (Test-Path $pbo)) { L "no existe $pbo : no lanzo"; exit 3 }
$dirty = (& git -C $WS status --porcelain -- . ':(exclude)evidence') -join "`n"
if ($dirty) { L "repo sucio fuera de evidence/ (git_dirty): no lanzo`n$dirty"; exit 3 }
$ajenos = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'DayZ*' -and $_.ProcessName -ne 'DayZToolsLauncher' })
if ($ajenos.Count) { L "hay DayZ abiertos ($(($ajenos | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ', ')): no lanzo"; exit 3 }
$co = & $Py -I $Lease comprobar --min-vram-libre 4000 2>&1 | Out-String
L "gpu_lease comprobar (exit $LASTEXITCODE): $($co.Trim())"
if ($LASTEXITCODE -ne 0) { L "GPU OCUPADA: no lanzo"; exit 4 }
$lo = & $Py -I $Lease adquirir --motivo "F1b-peers partida $Build" --minutos $($RunTimeoutMin + 30) --sesion $LeaseSesion 2>&1 | Out-String
L "gpu_lease adquirir (exit $LASTEXITCODE): $($lo.Trim())"
if ($LASTEXITCODE -ne 0) { L "sin lease de GPU: no lanzo"; exit 4 }

$own = @()
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
    $own += Own 'battleye_launcher' $bepid; L "lanzador BattlEye pid=$bepid"
    for ($i = 0; $i -lt 120; $i++) {
      Start-Sleep -Milliseconds 500
      $nuevos = @(Get-Process -Name DayZ_x64 -ErrorAction SilentlyContinue | Where-Object { $antes -notcontains $_.Id })
      if ($nuevos.Count -eq 1) { $own = @(Own 'client' $nuevos[0].Id) + $own; L "cliente retail (juego) pid=$($nuevos[0].Id)"; break }
      elseif ($nuevos.Count -gt 1) { L "aparecen $($nuevos.Count) DayZ_x64 nuevos: no adopto ninguno"; break }
    }
  }
  WriteJson $pidsFile @{ processes = $own }
  L "pids.json: $(($own | ForEach-Object { "$($_.role)=$($_.pid)" }) -join ', ')"

  for ($i = 0; $i -lt ($RunTimeoutMin * 120) -and -not (Test-Path "$evAbs\scenarios_done.json") -and -not $h.HasExited; $i++) { Start-Sleep -Milliseconds 500 }
  L "escenarios terminados: $(Test-Path "$evAbs\scenarios_done.json") (orquestador vivo: $(-not $h.HasExited))"
}
finally {
  foreach ($o in $own) { L (CloseOwn $o) }
  $vivos = @($own | Where-Object { IsAlive $_ })
  $allClosed = ($vivos.Count -eq 0)
  if (Test-Path $evAbs) {
    $logs = "$evAbs\logs"; New-Item -ItemType Directory -Force $logs | Out-Null
    $inv = @{}
    foreach ($pair in @(@('server', $S), @('client', $C))) {
      $files = @(Get-ChildItem $pair[1] -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.log', '.RPT' })
      $inv[$pair[0]] = @($files | ForEach-Object { $_.Name })
      $sl = @($files | Where-Object { $_.Name -like 'script_*.log' })
      if ($sl.Count -eq 1) { Copy-Item $sl[0].FullName "$logs\$($pair[0])_script.log" -Force }
      elseif ($sl.Count -gt 1) { L "$($pair[0]): $($sl.Count) script_*.log de la sesion (log_ambiguous): no copio ninguno" }
      $rpt = @($files | Where-Object { $_.Extension -eq '.RPT' })
      if ($rpt.Count -eq 1) { Copy-Item $rpt[0].FullName "$logs\$($pair[0]).RPT" -Force }
      elseif ($rpt.Count -gt 1) { L "$($pair[0]): $($rpt.Count) RPT de la sesion: no copio ninguno" }
    }
    WriteJson "$logs\inventory.json" $inv
    WriteJson "$evAbs\logs_ready.json" @{ all_closed = $allClosed }
    if ($h -and -not $h.HasExited) { $h.WaitForExit(15 * 60000) | Out-Null }
    if ($h) { L "orquestador exit $($h.ExitCode)" }
    & $Py (Join-Path $WS 'qa\live\f1bp_eval.py') $evAbs 2>&1 | ForEach-Object { L "eval: $_" }
    L "evaluador exit $LASTEXITCODE ($ev)"
  }
  if ($allClosed) {
    $so = & $Py -I $Lease soltar --sesion $LeaseSesion 2>&1 | Out-String
    L "gpu_lease soltar (exit $LASTEXITCODE): $($so.Trim())"
  } else {
    L "QUEDAN PROCESOS PROPIOS VIVOS ($(($vivos | ForEach-Object { "$($_.role)=$($_.pid)" }) -join ', ')): NO suelto el lease"
    exit 5
  }
  L "fin"
}
