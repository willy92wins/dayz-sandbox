# Dudas lane B (F4 parte 1)

- Una cámara del documento con 0 claves no está en la tabla de errores. No la trato como `invalid`; si llega, se encola con arrays vacíos.
- Si una clave no trae `t`/`x`/`y`/`z`/`yaw`/`pitch`/`fov`/`focus`, el brief no dice el código. Asumo el esquema; no hay rama extra.
