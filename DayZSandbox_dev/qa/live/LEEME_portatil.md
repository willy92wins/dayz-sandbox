# Portátil: humo y partida F2P desde la «Sesión de pruebas»

Todo se hace en interactivo, desde la «Sesión de pruebas», sobre el
paquete descomprimido en `C:\dsbx-m1\`. No hace falta repo git ni
herramientas de build: el runner comprueba el paquete por sha256
contra su `manifest.json` y usa los PBO del paquete, sin construir
nada. DayZDiag 1.30 y el Python de la Store.

## 1. Comprobar el zip y descomprimir

1. Calcula el sha256 del zip recibido y compáralo con el valor que
   acompaña al envío (el fichero del sha256 junto al zip). Si no casa,
   para y avisa: no descomprimas ni lances nada.

   ```powershell
   Get-FileHash .\dsbx-m1.zip -Algorithm SHA256
   ```

2. Descomprime el zip en `C:\dsbx-m1\`, de modo que queden dentro,
   entre otros, `run_f2p_partida.ps1`, `f2p_partida.py`,
   `manifest.json`, `pbo\@DayZSandbox\addons\DayZSandbox.pbo` y
   `pbo\@DayZSandbox_QA\addons\DayZSandbox_QA.pbo`.
3. Cierra cualquier DayZ abierto: antes de arrancar no puede vivir
   ningún `DayZ*` (`DayZDiag_x64`, `DayZ_x64`, `DayZServer_x64` o
   `DayZ_BE`). El runner lo comprueba y, si hay alguno, no lanza y lo
   dice en el log.

## 2. El humo real (una sola orden)

Desde `C:\dsbx-m1\`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dsbx-m1\run_f2p_partida.ps1 -Maquina portatil -Build diag -Cliente lanzar -Humo -PackageDir C:\dsbx-m1 -DayZDir "<carpeta de DayZ con DayZDiag_x64.exe>" -MissionB1 "<carpeta b1>" -WorkRoot C:\dsbx-m1\trabajo -ResultsDir C:\dsbx-m1\resultados
```

El humo, en orden: comprueba el paquete y los DayZ ajenos, arranca
servidor y cliente con una copia nueva de la misión, espera el
`/hello` aceptado del producto, el `hello` de la sonda, el `hello`
del peer cliente y el UID por `per_status`, hace un ciclo de
reinicio como el de F4 (parar los dos, drenar, arrancar los dos, los
mismos saludos y el mismo UID) y cierra los PID propios por
`WM_CLOSE`. Sin oráculo ni partida.

**Criterio de término del humo:** `C:\dsbx-m1\resultados\humo.json`
con todos los pasos en `ok` y ningún `DayZ*` propio vivo. Comprueba
lo segundo con:

```powershell
Get-Process -Name 'DayZ*' -ErrorAction SilentlyContinue
```

Si algún paso sale en `fallo`, no lances la partida: devuelve lo del
punto 4 y avisa.

## 3. La partida (una sola orden)

Con el humo en ok, desde `C:\dsbx-m1\`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dsbx-m1\run_f2p_partida.ps1 -Maquina portatil -Build diag -Cliente lanzar -PackageDir C:\dsbx-m1 -DayZDir "<carpeta de DayZ con DayZDiag_x64.exe>" -MissionB1 "<carpeta b1>" -WorkRoot C:\dsbx-m1\trabajo -ResultsDir C:\dsbx-m1\resultados
```

**Criterio de término de la partida:** `resultados\run\manifest.json`
y `resultados\run\samples\` completos, y ningún `DayZ*` propio vivo
(comprobación de arriba). La evidencia queda por defecto bajo
`resultados\`, no bajo ningún repo.

## 4. Qué devolver

Devuelve la carpeta `C:\dsbx-m1\resultados\` entera: tras el humo,
`humo.json`, `humo_pasos.json` y `logs\`; tras la partida, además
`run\manifest.json` y `run\samples\` completos. Si algo falló,
devuelve también el texto de la consola del runner tal cual.

## 5. Aviso de Steam

Si Steam se queja de que la cuenta está jugando en otro equipo, se
para todo y se avisa: no se reintenta ni se sigue con la partida.
