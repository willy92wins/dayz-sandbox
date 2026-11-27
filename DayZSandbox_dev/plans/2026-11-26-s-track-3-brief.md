# S-track·3: réplica, actor de IA, coche y pérdida del objetivo

2026-11-26 · borrador del spec (R25/R26) de la tercera corrida de la sonda S-track del [plan de cámara que sigue objetos](2026-11-10-camara-sigue-objetos.md) · **v0.1, sin cerrar**. Queda pendiente del resultado de [S-track·2](2026-11-12-s-track-2-brief.md): la lectura ganadora, el hook de cada modo y el detector enmascarado se heredan tal como salgan de allí. Si S-track·2 no decide algo, este brief se reescribe antes de implementarse.

## 0. Qué es y qué no

**Es** todo lo que el plan §4 deja fuera de S-track·2 porque necesita red o servidor:
- T-red;
- `mount` sobre el coche;
- las negativas de pérdida del objetivo y de «cámara lista» (plan §4.3).

**No es:**
- los criterios K del producto (§5), que van después de la sonda y sobre el código de F4;
- código del producto.

## 1. Banco

- **Instancia propia:** DayZDiag 1.30 en el puerto 2402, como S-track·1 y S-track·2.
  - El cliente es el director; el actor de IA y el coche viven en el servidor.
  - No se usa el portátil de M1 ni sus puertos.
- **El actor de IA** sale con el adaptador de Expansion AI del producto (plan v1, `dayz-sandbox-tech-findings`):
  - clase fija `eAI_SurvivorM_<Nombre>` y un grupo propio;
  - dos waypoints a 15 m, y en cada uno un giro de 180°;
  - sin `ROAMING`.
  - En las manos, el M4A1 con mira y silenciador de S-track·2; puesta, la mochila.
- **El coche:** un `OffroadHatchback` creado por el servidor en una cuesta. Recibe un impulso cuesta abajo con `dBodyApplyImpulse`, cada 10 s.
  - Antes de escribir se comprueban en el código vanilla la clase y la firma.
- **Base temporal de S-toma** para comparar la pose del servidor con la del cliente (plan §4.2, T-red (3)). Se usa la de M1 si ya está congelada; si no, (3) sale INCONCLUSA y se dice.

## 2. Casos

| Caso | Objetivo | Modo | Hook |
|---|---|---|---|
| `ia_lookat` | Boca del fusil del actor (`on: hands`) | `look_at`, cámara fija | El ganador de S-track·2 para `look_at` |
| `ia_follow` | Actor | `follow`, `smooth_s` 0, 0,3 y 0,8 | El ganador para `follow` |
| `coche_mount` | Coche (memory point del capó, comprobado con `MemoryPointExists`) | `mount` rígido y con 0,3 | El ganador para `mount` |
| `coche_follow` | Coche | `follow` 0,3 | El ganador para `follow` |
| `perdida` | Objeto suelto; el servidor lo borra a los 5 s | `mount` (H-c si ganó) y `follow` | Los dos |
| `espalda` | El actor guarda el arma a la espalda a los 5 s | `on: hands`, y otra vez con el arma nombrada | El ganador |
| `listo` | Punto inexistente, ranura ausente, objetivo fuera de la burbuja | `mount` | No llega a armarse |

## 3. Medidas y PASA

Son las del plan §4.2 (T-red, con sus tres partes separadas) y las de §4.3, sin cambiar ningún umbral:
- **T-red (1) en imagen:** con el detector enmascarado y las marcas a mano de S-track·2, sobre el actor y sobre el coche.
- **T-red (2) el filtro:** error ≤ 2 cm p95 frente a la respuesta analítica.
- **T-red (3) la réplica:** solo se informa, y vale si la cota de la base temporal por la velocidad es ≤ 1 cm. También se informa el `smooth_s` mínimo que cumple «ningún paso mayor que 3 veces la mediana».
- **`perdida`:**
  - `target_lost` con su frame;
  - la pose siguiente igual a la última escrita (≤ 1 mm y ≤ 0,01°);
  - sin salto al soltar la cámara hija.
- **`espalda`:**
  - con `on: hands`, `target_lost`;
  - con el arma nombrada, el informe dice qué pasa.
- **`listo`:**
  - no hay «cámara lista» y la toma no se arma;
  - el error dice qué falta;
  - si la retirada de «listo» se retrasa hasta después del GO, la toma acaba `fallida` con su parada observada.

## 4. Negativas

- Cámara congelada en `ia_follow`: T-red (1) y (2) FALLAN.
- Pose del ancla con un frame de retraso en `coche_mount`: FALLA en imagen.
- Referencia vieja después de `perdida` (la cámara sigue leyendo el objeto borrado): FALLA.

## 5. Criterios de cierre

1. Los tests offline del evaluador, sus fixtures negativas y los mutantes pasan.
2. Hay 0 `SCRIPT (E)` del mod.
3. Todas las corridas pasan el preflight de FPS y dejan su evidencia con `SHA256SUMS`.
4. Las negativas salen FALLA.
5. Sale una decisión, o un INCONCLUSO con causa medida, para:
   - T-red, por tipo de réplica (actor y coche);
   - `mount` sobre el coche;
   - cada caso de pérdida y de «listo».

## 6. Reparto

Sigue el de S-track·2: Muse implementa y Sol revisa en bucle, con tope de 4 vueltas por pieza. Claude orquesta en el sobremesa de Guillermo, de noche y sin usar el portátil de M1. La corrida en partida necesita su visto bueno.
