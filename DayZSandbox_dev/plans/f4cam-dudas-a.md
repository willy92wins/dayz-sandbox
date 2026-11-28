# Dudas lane A (F4 parte 1)

- `ReadJson` pide yaw/pitch de `GetCurrentCameraDirection` sin formula. Implementado: `yaw = Atan2(dir.x, dir.z)` envuelto a `[0, 360)`, `pitch = Asin(dir.y)`.
- Redondeo de pose a enteros: el brief no lo dice. Se usa `Math.Round` como `DSBX_SceneWire.MetersToMmChecked`.
- Si `EnsureActiveCam` falla al crear `staticcamera`, `Play` igual devuelve `""` (el brief no da codigo de error propio).
