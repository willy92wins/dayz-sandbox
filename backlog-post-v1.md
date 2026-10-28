# Backlog post-v1 — DayZ Sandbox

> Etiqueta: **post-v1**. Nada de esto entra en M1 ni toca F0.1. Es lo que se considera cuando M1 esté cerrado.
> Origen: council extendido del 2026-10-27 (Muse Wonder 1.0, Argon / gemini-4-argon-high, Grok 4.7, Opus 5.5, Astra / gpt-6-astra).
> Corrida completa (briefs con SHA, 39 propuestas, 5 votos íntegros, manifiesto): `reviews/2026-10-27-council-post-v1/`.

## Resumen

- 5 lanes propusieron 39 mejoras (ronda 1, brief idéntico). El orquestador las agrupó en 26 temas y las 5 votaron a ciegas (ronda 2, anonimizado). Regla: entra con 3/5 votos a favor.
- **Aprobados: 25 de 26. Rechazado: 1** (T25, modo Eventos/RP, 0/5).
- Ojo con la lectura: el council aprueba casi todo, así que el "sí" discrimina poco. Lo que sí separa es la **prioridad** (1 = lo primero tras M1) y el **TOP5** de cada lane. La tabla está ordenada por eso.
- Casi todos los votos son "aprueba con cambio". Las condiciones de cada tema forman parte de lo aprobado: un tema no se construye sin ellas.

## Decisiones que son tuyas (Guillermo)

1. **Licencia vs. uso comercial (T16, unanimidad + DISENSO-FUERTE).** "Uso comercial: sí" convive con el repo público bajo PolyForm Noncommercial. Las 5 lanes piden resolverlo, y confirmar con Bohemia (F3, `product-spec.md:112`), **antes** de aceptar PR externos y antes de invertir en C6. Opciones que salieron: CLA, o repos separados (mod gratis / web+backend con otra licencia). No son equivalentes; decides tú.
2. **Mando por LAN (T22).** Abrir `/surface` en la red local choca con E1 ("Bridge y API solo en 127.0.0.1", `product-spec.md:98`) y con su negativa "IP de la LAN → 0 efectos" (`plans/2026-10-26-m1-cine-v2.md:172`). Opus y Argon lo aprueban **solo en 127.0.0.1** (dock de OBS, Stream Deck, atajos), Astra y Muse lo rechazan por la LAN, y solo Grok la acepta (apagada por defecto). Con 4/5 en contra de la LAN, queda fuera salvo que cambies E1. **Decidido por Guillermo (2026-10-27): de momento, solo 127.0.0.1.**
3. **Reorientar C6 a "marioneta de ruta" (T17).** Aprobado como función, pero cambiar el sentido de C6 (`product-spec.md:78`) es un cambio de alcance: pasa por un Grill Modo A, gateado por los probes de las fichas 14 y 15. **Decidido por Guillermo (2026-10-27): sí; aplicado en el spec (M2, C6, Fuera de alcance y Changelog).**
4. **Eventos/RP (T25) queda fuera.** 0/5 y cinco DISENSO-FUERTE: el spec lo excluye y solo se reabre con Grill Modo A (`product-spec.md:142`), y choca con la prioridad cine. Si algún día quieres el segmento RP, es un Grill aparte.

## Backlog aprobado

Votos = a favor/5. Prio = mediana de las 5 (1 alta, 3 baja). TOP5 = cuántas lanes lo pusieron entre sus 5 primeros.

### Prioridad 1 — lo primero tras M1

| # | Tema | Votos | Horizonte | TOP5 | Condiciones del council |
|---|---|---|---|---|---|
| T26 | **Validar con 3-5 creadores externos** el tiempo hasta la primera toma utilizable y la repetición de uso, antes de abrir M2 | 5/5 | transversal | 5 | Es un gate, no una función. Sale de las críticas del encuadre de varias lanes (la demanda de cine es cualitativa, `consolidado.md:44`) |
| T16 | **Licencias y orden comercial**: resolver PolyForm NC vs. venta, CLA o repos separados, adelantar F1/F3 (Bohemia) antes de C6 | 5/5 | transversal | 5 | Ver "Decisiones" 1 |
| T01 | **Adaptador OBS opcional**: graba con la toma, nombra el fichero, claqueta/sidecar con hash, plano, toma, desfases y ambiente; estados "toma ejecutada / captura confirmada / archivo comprobado" | 5/5 | M2 | 4 | Lo propusieron las 5 lanes. OBS ausente no bloquea la toma salvo que la toma exija captura. El producto sigue sin grabar vídeo (`product-spec.md:134`). Reabre el "adaptador de OBS" del plan §7 |
| T02 | **Cues temporizadas** dentro de la toma (marca, gesto, corte de cámara a t+Δ del GO) con desfase observado por cue | 5/5 | M2 | 4 | Solo tras pasar S-toma; tolerancia sacada de la variación medida en B5, no fijada a priori; anclada a la base temporal común; las rampas de ambiente van en T06 |
| T17 | **Locomoción determinista**: el creador graba su pase (o traza una curva) y un NPC lo repite | 5/5 | M2 | 3 | Primero los probes `survivor_drive` y `nav_path_query` en retail; sin prometer identidad tick a tick; la reorientación de C6 va a Grill (Decisiones 3) |
| T15 | **Instalador + "doctor" + primera toma guiada**, actualizaciones reversibles con copia de proyectos | 5/5 | M2 | 2 | Reabre "sin instalador" (`product-spec.md:23`). No redistribuye nada de BI |
| T14 | **Matriz de compatibilidad por build y modset**: sondas, `capabilities.json`, la web desactiva lo no certificado | 5/5 | transversal | 1 | Las sondas se limpian solas; lo que necesita cliente con interfaz no se vende como CI desatendida |

### Prioridad 2

| # | Tema | Votos | Horizonte | Condiciones |
|---|---|---|---|---|
| T10 | Paquete de escena portable `.dzscene` (documento + presets + manifiesto build/mapa/modset + hashes), validación de dependencias y remapeo de clases ausentes | 5/5 | M2 | Rechaza con la lista exacta de lo que falta y 0 órdenes al juego |
| T12 | Capturar el estado vivo como escena (selección explícita, interiores y tejados con Y absoluta, vestuario) | 5/5 | M2 | Nunca reclama propiedad de lo no seleccionado ni toca persistencia |
| T11 | Importar/exportar datos con Object Spawner, con informe de lo que se pierde | 5/5 | M2 | **Solo Object Spawner** de entrada. El `.dze` de DayZ Editor (CC BY-NC-ND) queda fuera hasta que F1 aclare si leer el formato es obra derivada (DISENSO de Muse). Importar deja borrador sin aplicar |
| T19 | Rechazar al editar las marcas inalcanzables (ruta por navmesh, polilínea en el mapa 2D) | 5/5 | M2 | Adelanta la ficha 14 al flujo de M2; gateado por su probe |
| T20 | Director fuera de cuadro de verdad: ocultar su cuerpo durante la toma y restaurarlo por cualquier salida | 5/5 | M2 | Primero un spike que nombre la API real; si no existe, se retira. **Prohibido trasladar el cuerpo** lejos del set (riesgo de burbuja de red) |
| T06 | Ambiente con claves: timelapse, niebla, lluvia y nubes en rampa durante la toma, leído con `GetActual` | 5/5 | M2 | Medir antes si el motor interpola entre `Set` o salta |
| T07 | Lente física (focal en mm → FOV), roll y shake con semilla guardada | 5/5 | M2 | B2 se mide sobre la pose sin shake. Sin apertura mientras B3 no demuestre desenfoque; sin postproceso sin API verificada. Reabre "shake y lente 8-400 mm" del plan §7 |
| T08 | Cámara que sigue al actor: look-at, autofoco y avisos de composición en el ensayo | 5/5 | M2 | Separable: seguimiento/composición y autofoco se certifican por separado |
| T04 | Cobertura: la misma acción con N cámaras en serie con reset, y export de montaje (OTIO/EDL) | 5/5 | M2 | Grok pide separar rodaje y formato de export |
| T05 | Proyecto con continuidad entre planos: revisiones inmutables de reparto, vestuario y decorado, informe de continuidad | 5/5 | M2 | **Solo la parte documental.** Los "planos encadenados sin reset" quedan fuera (rompen B6, `product-spec.md:64`): 4/5 lo excluyen y Astra lo dejaría como modo aparte con su propia aceptación |
| T18 | Infectado "hero" con rumbo y velocidad repetibles tras cada reset | 5/5 | M2 | Opus lo ve como el mismo controlador de T17 |
| T21 | Mapa 2D autogenerado (relieve desde `SurfaceY`) para cualquier mapa instalado | 5/5 | M2 | Muestreo escalonado para no hundir el FPS del servidor |

### Prioridad 3

| # | Tema | Votos | Horizonte | Condiciones |
|---|---|---|---|---|
| T03 | Partitura con dependencias observadas ("cuando A llegue, B saluda") | 4/5 | M3 | No como motor aparte: un tipo de disparador dentro de T02, con límite de espera. Argon en contra: mete la variabilidad de la FSM dentro del plano |
| T24 | IA que propone correcciones tras el ensayo, con nueva aprobación ligada al hash | 5/5 | M3 | Amplía H2; nunca ejecuta sin aprobar |
| T09 | Luces de escena registradas que el reset borra | 5/5 | M3 | Sin verificar qué luces vanilla sirven por script en retail |
| T22 | Mando de toma en segunda pantalla, frustum 2D con oclusión y storyboard de un fotograma por clave | 3/5 (Astra y Muse en contra) | M3 | **Solo en 127.0.0.1** (Decisiones 2). Storyboard por captura de ventana: `MakeScreenshot` está roto (`consolidado.md:88`). Las 5 lanes piden separar las tres piezas |
| T13 | Paquetes comunitarios curados con procedencia y licencia, sin ejecutables ni assets | 4/5 | post-M3 | Opus en contra: exige moderación antes de tener un solo usuario externo |
| T23 | Banco visual A/B para modders | 5/5 | post-M3 | Tolerancias fijadas antes de ejecutar |

## Rechazado

| # | Tema | Votos | Motivo |
|---|---|---|---|
| T25 | Modo Eventos/RP: exportar a JSON de patrullas de Expansion y comprobar visibilidad de jugadores | 0/5 | Fuera de alcance explícito, solo se reabre con Grill Modo A (`product-spec.md:142`); choca con la prioridad cine; la comprobación de visibilidad solo aproxima |

## Avisos del encuadre (ronda 1, sin votar)

- Varias lanes advierten de que nada se ha ejecutado aún en partida (`plans/2026-10-26-m1-cine-v2.md:282`) y de que todo M2 cuelga de C6, marcado `[verify]` (`product-spec.md:78`). Este backlog no sustituye a S-toma, S3 ni S-persist.
- Argon y Grok señalan que el volumen de usuarios está en RP y el de cine es un nicho; la decisión de cine sigue vigente y el council no la reabre.

## Cómo se decidió (procedencia)

- Ronda 1: brief byte-idéntico (`sha256 b7cd98ed…`), lanes solo lectura sobre copias de spec, plan v2, consolidado, fichas MCP y decisiones. 5/5 completas.
- Ronda 2: brief `sha256 446c7638…`; propuestas anonimizadas LANE-A..E. 5/5 completas, 26/26 votos parseados en cada una.
- Opus 5.5 es de la misma familia que el orquestador que agrupó y redactó esto: su acuerdo con la agrupación es señal débil.
- La agrupación en 26 temas es del orquestador; todas las lanes pidieron partir T05 y T22, y así se recoge en las condiciones.
