// Criterios R26 de las mejoras de noviembre (ui/2026-11-04-ui-mejoras-consolidado.md: AHORA y la segunda pasada, §2 y §6, y lo que pidió y eligió
// Guillermo el 5 de noviembre, §8): un caso + y uno − por mejora.
// Uso: node ui/prototipo/pruebas-mejoras.js (necesita Playwright con Chromium). Cada caso abre una página nueva.
// Contra el prototipo de antes (ESTUDIO_URL=file://… con `git show de37c03:ui/prototipo/estudio.html`) los + tienen que fallar;
// un − que ya se cumplía antes pasa también allí. El contraste de CU-38 en los dos temas sigue en pruebas.js; el del mapa, aquí (AR-03).
// Los casos AR-xx son los arreglos de la revisión de Astra (ui/astra/2026-11-04-ui-revision-astra.md), y los AR2-xx, los de su segunda
// revisión (ui/astra/2026-11-05-ui-revision2-astra.md). Lo que se pinta en el mapa se mira con una sonda del lienzo, no con contadores de la
// propia página (AR-04), y desde AR2-01 también en el fotograma acabado; mutantes.js comprueba que esas pruebas fallan cuando el dibujo se
// rompe. SOLO=<expresión> pasa solo los casos cuyo nombre encaje.
const path = require('path');
const { chromium } = require('playwright');
const URL = process.env.ESTUDIO_URL || 'file://' + path.resolve(__dirname, 'estudio.html');
let fails = 0, passes = 0;
const expect = (c, m) => { if (c) { passes++; console.log('PASS', m); } else { fails++; console.log('FAIL', m); } };

// Dentro de la página. Visible es lo que se pinta: lo de un «Detalles técnicos» plegado no cuenta.
const LIB = () => {
  const shown = el => el.getClientRects().length > 0 && (!el.checkVisibility || el.checkVisibility());
  const vis = el => { if (!shown(el)) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden' && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const own = el => [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ');
  const list = root => [...root.querySelectorAll('*')].filter(el => own(el).trim() && vis(el));
  const texts = root => list(root || document.body).map(own).join(' ').replace(/\s+/g, ' ');
  // las mismas cuentas que la crítica: textos con jerga, en monoespaciada y por debajo de 12 px
  const metrics = () => {
    const t = list(document.body), cs = el => getComputedStyle(el);
    const jerga = t.map(own).filter(x => /\bop-[0-9a-f]{3,}|\br\d{1,3}\b|hash|scene_apply|\b[A-Z][A-Za-z]+_[A-Za-z0-9_]+|epoch|[0-9a-f]{6,}/.test(x));
    const small = t.filter(el => parseFloat(cs(el).fontSize) < 12);
    return { n: t.length, mono: t.filter(el => /mono|Consolas|Cascadia|Menlo/i.test(cs(el).fontFamily)).length, small: small.length, smallEj: small.slice(0, 4).map(el => own(el).trim().slice(0, 24)), jerga: jerga.length, jergaEj: jerga.slice(0, 4).map(x => x.trim().slice(0, 30)) };
  };
  window.__r26 = { shown, vis, texts, metrics };
};
// Sonda del lienzo del mapa: cada texto pintado (con fillText o strokeText) con su tamaño en px de CSS y, en cada píxel de su letra,
// el contraste de WCAG entre el color del texto y lo que ya estaba pintado debajo. La letra es la que pinta el propio lienzo: antes
// de pintarla se pinta una vez en blanco y otra en negro, la diferencia dice cuánto cubre cada píxel, y se deja el fondo como estaba.
// Cuenta como letra cada píxel cubierto al menos a la mitad. Y cada trazo y relleno con su posición, su discontinuo y su grosor, y si el
// relleno es un patrón, como el rayado de lo estimado (UX-30).
// Desde la segunda revisión de Astra (AR2-01) mira también lo que se ve, no solo las órdenes de dibujo, y desde la tercera (AR3-01), también
// la letra:
// - cada letra, otra vez en el fotograma acabado: el color final de cada píxel de su letra, quitada la parte del fondo que deja ver su borde,
//   frente al fondo que queda alrededor (el color mediano de los píxeles que rodean la letra sin tocarla, que son su halo o su placa). Así
//   cuenta lo que se pinte después encima en el lienzo: un velo, unos píxeles repintados o un filtro que borra la letra. Son los píxeles que
//   su letra cubría al pintarla, no la forma que acaba teniendo (AR4-01, abajo);
// - las imágenes que se componen en el mapa. Se apunta qué textos se pintan en cada lienzo, también en los auxiliares y en los que reciben
//   la imagen de otro (con drawImage, con getImageData y putImageData o como patrón), y una imagen con texto solo vale si es el halo de la
//   letra que el mapa pinta justo después dentro de ella. Cualquier otra imagen con texto, una imagen que no sea un lienzo, unos píxeles
//   puestos en el mapa con putImageData y un relleno con un patrón que lleve texto o que no salga de un lienzo quedan como no medidos;
// - en cada relleno centrado en su origen, como los marcadores, los píxeles de su interior (a 2 px de CSS del borde) en el fotograma ya
//   acabado: si alternan dos tonos en franjas, como un rayado, o si son del color del relleno, opaco;
// - en cada contorno discontinuo de un marcador, sus guiones y sus huecos: cuántos trozos y cuántos píxeles de hueco salen de su propio trazo,
//   pintado aparte con y sin discontinuo al pintarlo, y en el fotograma acabado, el color de los guiones frente al de los huecos;
// - desde UX-48, el icono de un marcador: lo que se pinta con un Path2D en su mismo origen, después de su relleno. Se guarda el `d` con el
//   que se hizo cada Path2D, y los píxeles que toca el icono salen de su propio dibujo pintado en blanco y en negro, como los de la letra.
//   Esos píxeles se apartan del interior al mirar si es del color del relleno. Y la forma del relleno: la distancia de su origen al borde
//   cada 5°;
// - desde UX-49, de cada trazo discontinuo que rodea su origen, cuánto mide a lo ancho y a lo alto, y sus guiones y huecos en una caja
//   que lo abarca entero, como la planta del objeto que se está colocando;
// - desde UX-50, la caja de cada texto en px de CSS del mapa, para cruzarla con lo que flota encima del mapa y con su borde, que el lienzo
//   no ve.
// Desde la cuarta revisión (AR4-01), además:
// - el fondo de cada píxel de la letra es el del anillo que tiene cerca, a 4 px o menos, no el de todo el texto, y los huecos de la letra (lo
//   que hay en su caja sin tocarla, como el ojo del 6) no pueden acabar con su tinta: así cae una cifra tapada con su misma tinta;
// - las imágenes también por ImageBitmap (createImageBitmap, transferToImageBitmap y bitmaprenderer), y un lienzo con WebGL o WebGPU, o que
//   pinta otro hilo, una imagen <img> o un filtro con url() son de procedencia desconocida: quedan sin medir;
// - el rayado, además, se repite: dos franjas o más de cada tono en su mejor dirección, y cada tono en no más trozos que franjas, más uno;
// - y la pantalla: los píxeles de cada texto en una captura del mapa, frente al lienzo, para lo que CSS hace después (un filtro, una opacidad,
//   un velo encima).
// Desde la quinta (AR5-01 a AR5-03): en la pantalla, cada píxel de cada texto es el suyo del lienzo, no uno entre sus vecinos; no se aparta
// más que lo que tapa lo que flota encima, sin margen, y en su sombra vale el lienzo oscurecido como mucho lo que da su opacidad; en la
// captura, además, la letra llega a 4,5:1 y sus huecos siguen sin tinta, y un texto pintado del que no se ve ningún píxel no pasa. Un
// lienzo con WebGL o WebGPU, o que pinta otro hilo, sigue de procedencia desconocida aunque se le cambie el tamaño.
// Desde la sexta (AR6-01), y dicho así desde la séptima (AR7-02): de lo que flota encima se aparta de la comparación su caja, recortada por lo
// que la contiene, aunque no la pinte entera (un fondo transparente, unas esquinas redondeadas), y solo si nada cambia lo que pinta dentro de
// ella (un recorte, una máscara, un filtro, una opacidad, un giro): si no, se compara; y un texto con algún píxel de su letra o de sus huecos
// sin comparar no se da por leído, aunque se compare el resto. Lo que se aparta queda sin comparar, que no es lo mismo que no verse.
// No sigue un texto copiado a mano, byte a byte, de un ImageData a otro, ni uno hecho con createImageData; no mira si los huecos de un contorno
// se rellenan después con otro color que también se distinga de los guiones, ni reconoce la letra: mide su contraste, sus huecos y de dónde
// sale, no que se lea como el carácter que es. Solo graba cuando __cv.on, y se queda con el último fotograma entero del mapa, que empieza
// pintando el mar en todo el lienzo. Sus propias lecturas y escrituras de píxeles no cuentan como dibujo.
const PROBE = () => {
  const P = CanvasRenderingContext2D.prototype, OP = window.OffscreenCanvasRenderingContext2D ? OffscreenCanvasRenderingContext2D.prototype : null;
  // las originales: la sonda lee y repone píxeles con estas, que no cuentan como dibujo
  const stroke0 = P.stroke, fill0 = P.fill, fillRect0 = P.fillRect, gid0 = P.getImageData, pid0 = P.putImageData, odraw0 = OP && OP.drawImage, ogid0 = OP && OP.getImageData;
  const cv = window.__cv = { on: false, texts: [], strokes: [], fills: [], images: [] }, cache = {};
  // cada Path2D con el `d` con el que se hizo (UX-48)
  const Path2D0 = window.Path2D, PD = new WeakMap();
  window.Path2D = new Proxy(Path2D0, { construct(t, a) { const q = Reflect.construct(t, a), d = typeof a[0] === 'string' ? a[0] : a[0] && PD.get(a[0]); if (d) PD.set(q, d); return q; } });
  const rgba = c => cache[c] || (cache[c] = (() => { const o = new OffscreenCanvas(1, 1).getContext('2d'); o.fillStyle = c; o.fillRect(0, 0, 1, 1); return Array.from(o.getImageData(0, 0, 1, 1).data); })());
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const mine = ctx => cv.on && ctx.canvas && ctx.canvas.id === 'map';
  const dprOf = ctx => ctx.canvas.width / ctx.canvas.clientWidth;
  // qué textos lleva cada lienzo, y si lleva algo que no se sabe de dónde sale (AR4-01); cambiarle el tamaño lo borra, y con él lo que llevaba.
  // Y lo mismo de cada ImageBitmap, de cada ImageData leído de un lienzo y de cada patrón, con si sale de un lienzo
  const TXT = new WeakMap(), IMG = new WeakMap(), PAT = new WeakMap();
  const what = c => { let r = TXT.get(c); if (!r) TXT.set(c, r = { t: new Set(), u: false }); return r; };
  const tag = (c, t) => { if (c) what(c).t.add(String(t)); };
  const taint = c => { if (c) what(c).u = true; };
  const mix = (c, r) => { if (!c || !r) return; const q = what(c); r.t.forEach(x => q.t.add(x)); if (r.u) q.u = true; };
  const copyOf = r => ({ t: new Set(r ? r.t : []), u: !!r && r.u });
  const isCanvas = s => s instanceof HTMLCanvasElement || (!!window.OffscreenCanvas && s instanceof OffscreenCanvas);
  // lo que lleva una fuente de imagen: un lienzo, lo suyo; un ImageBitmap, lo que se apuntó al hacerlo, y si no se apuntó, procedencia
  // desconocida; un ImageData, lo del lienzo de donde se leyó, y si se hizo a mano, nada (byte a byte no se sigue); y cualquier otra imagen
  // (<img>, <video>, un SVG, un VideoFrame), procedencia desconocida. Al cambiarle el tamaño a un lienzo se borra lo pintado, sus textos y lo
  // que le llegó, pero no que pinte con WebGL o WebGPU o desde otro hilo: el contexto sigue ahí y vuelve a pintar sin otro getContext (AR5-03)
  const ODD = new WeakSet(), ofCanvas = c => { const r = copyOf(TXT.get(c)); if (ODD.has(c)) r.u = true; return r; };
  const srcOf = s => isCanvas(s) ? ofCanvas(s) : window.ImageBitmap && s instanceof ImageBitmap ? (TXT.has(s) ? copyOf(TXT.get(s)) : { t: new Set(), u: true }) : s instanceof ImageData ? copyOf(IMG.get(s)) : { t: new Set(), u: true };
  [window.HTMLCanvasElement, window.OffscreenCanvas].filter(Boolean).forEach(C => ['width', 'height'].forEach(k => {
    const d = Object.getOwnPropertyDescriptor(C.prototype, k);
    Object.defineProperty(C.prototype, k, { configurable: true, enumerable: d.enumerable, get: d.get, set(v) { TXT.delete(this); d.set.call(this, v); } });
  }));
  // las vías de un ImageBitmap: hacerlo de una fuente, o sacarlo de un OffscreenCanvas, lleva lo de la fuente; ponerlo en un lienzo con
  // bitmaprenderer le pone lo suyo. Un lienzo con WebGL o WebGPU, o que pinta otro hilo, es de procedencia desconocida (AR4-01)
  if (window.createImageBitmap) { const cib = window.createImageBitmap; window.createImageBitmap = function (src) { const r = srcOf(src); return cib.apply(this, arguments).then(b => { TXT.set(b, r); return b; }); }; }
  if (window.OffscreenCanvas && OffscreenCanvas.prototype.transferToImageBitmap) { const tt = OffscreenCanvas.prototype.transferToImageBitmap; OffscreenCanvas.prototype.transferToImageBitmap = function () { const r = ofCanvas(this), b = tt.apply(this, arguments); TXT.delete(this); TXT.set(b, r); return b; }; }
  if (window.ImageBitmapRenderingContext) { const tf = ImageBitmapRenderingContext.prototype.transferFromImageBitmap; ImageBitmapRenderingContext.prototype.transferFromImageBitmap = function (b) { TXT.delete(this.canvas); if (b) mix(this.canvas, srcOf(b)); return tf.apply(this, arguments); }; }
  [window.HTMLCanvasElement, window.OffscreenCanvas].filter(Boolean).forEach(C => { const gc = C.prototype.getContext; C.prototype.getContext = function (type) { if (/webgl|webgpu/i.test(String(type))) ODD.add(this); return gc.apply(this, arguments); }; });
  if (HTMLCanvasElement.prototype.transferControlToOffscreen) { const tc = HTMLCanvasElement.prototype.transferControlToOffscreen; HTMLCanvasElement.prototype.transferControlToOffscreen = function () { ODD.add(this); return tc.apply(this, arguments); }; }
  // la imagen con texto que espera su letra: la siguiente orden de dibujo del mapa decide si era su halo
  let pending = null;
  const probe = (ctx, draw, style, args) => {
    const t = String(args[0]), x = args[1], y = args[2], T = ctx.getTransform(), m = ctx.measureText(t), dpr = dprOf(ctx);
    const rec = { text: t, px: Math.round(parseFloat((ctx.font.match(/([\d.]+)px/) || [0, 0])[1]) * T.a / dpr * 10) / 10, n: 0, low: 0, min: null,
      box: [T.a * (x - m.actualBoundingBoxLeft) + T.e, T.d * (y - m.actualBoundingBoxAscent) + T.f, T.a * (x + m.actualBoundingBoxRight) + T.e, T.d * (y + m.actualBoundingBoxDescent) + T.f].map(v => Math.round(v / dpr * 10) / 10) };
    if (pending) {
      const b = pending.box, g = [T.a * (x - m.actualBoundingBoxLeft) + T.e, T.d * (y - m.actualBoundingBoxAscent) + T.f, T.a * (x + m.actualBoundingBoxRight) + T.e, T.d * (y + m.actualBoundingBoxDescent) + T.f];
      pending.halo = pending.texts.every(s => s === t) && g[0] >= b[0] - 1 && g[1] >= b[1] - 1 && g[2] <= b[2] + 1 && g[3] <= b[3] + 1; rec.halo = pending.halo; pending = null;
    }
    const pad = Math.ceil(ctx.lineWidth * Math.abs(T.a)) + 2;
    const x0 = Math.max(0, Math.floor(T.a * (x - m.actualBoundingBoxLeft) + T.e) - pad), y0 = Math.max(0, Math.floor(T.d * (y - m.actualBoundingBoxAscent) + T.f) - pad);
    const w = Math.min(ctx.canvas.width, Math.ceil(T.a * (x + m.actualBoundingBoxRight) + T.e) + pad) - x0, h = Math.min(ctx.canvas.height, Math.ceil(T.d * (y + m.actualBoundingBoxDescent) + T.f) + pad) - y0;
    if (w > 0 && h > 0) {
      const under = gid0.call(ctx, x0, y0, w, h), bg = under.data;
      ctx.save(); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.shadowColor = 'transparent'; ctx.filter = 'none';
      ctx[style] = '#fff'; draw.apply(ctx, args); const wh = gid0.call(ctx, x0, y0, w, h).data; pid0.call(ctx, under, x0, y0);
      ctx[style] = '#000'; draw.apply(ctx, args); const bk = gid0.call(ctx, x0, y0, w, h).data; pid0.call(ctx, under, x0, y0);
      ctx.restore();
      const ink = rgba(String(ctx[style])), a = ink[3] / 255 * ctx.globalAlpha;
      // cuánto cubre la letra cada píxel, de 0 a 765; para el fotograma acabado se guardan los de la letra y los que la rodean sin tocarla
      const s = new Float32Array(w * h), glyph = [], ring = [], holes = [];
      for (let k = 0; k < w * h; k++) s[k] = wh[4 * k] - bk[4 * k] + wh[4 * k + 1] - bk[4 * k + 1] + wh[4 * k + 2] - bk[4 * k + 2];
      // la caja de la propia letra, sin margen: lo que hay en ella sin tocar la letra son sus huecos, como el ojo del 6 y lo que separa una cifra
      // de otra. Se guardan los que ahora no se parecen a la tinta (a 3:1 o más de ella), con el color que tendrían pintados con ella (AR4-01)
      const tb = [Math.floor(T.a * (x - m.actualBoundingBoxLeft) + T.e), Math.floor(T.d * (y - m.actualBoundingBoxAscent) + T.f), Math.ceil(T.a * (x + m.actualBoundingBoxRight) + T.e), Math.ceil(T.d * (y + m.actualBoundingBoxDescent) + T.f)];
      const near = (i, j) => { for (let v = -1; v <= 1; v++) for (let u = -1; u <= 1; u++) { const p = i + u, q = j + v; if (p >= 0 && q >= 0 && p < w && q < h && s[q * w + p] >= 16) return true; } return false; };
      let min = 99;
      for (let k = 0; k < w * h; k++) {
        const i = k % w, j = (k - i) / w;
        if (s[k] < 16 && x0 + i >= tb[0] && x0 + i < tb[2] && y0 + j >= tb[1] && y0 + j < tb[3]) { const b = [bg[4 * k], bg[4 * k + 1], bg[4 * k + 2]], e = [0, 1, 2].map(c => ink[c] * a + b[c] * (1 - a)); if (ratio(b, e) >= 3) holes.push([x0 + i, y0 + j].concat(e)); }
        if (s[k] < 383) { if (s[k] < 16 && near(i, j)) ring.push([x0 + i, y0 + j]); continue; }
        const b = [bg[4 * k], bg[4 * k + 1], bg[4 * k + 2]], r = ratio([0, 1, 2].map(c => ink[c] * a + b[c] * (1 - a)), b);
        rec.n++; if (r < 4.5) rec.low++; if (r < min) min = r;
        glyph.push([x0 + i, y0 + j, s[k] / 765]);
      }
      if (rec.n) { rec.min = Math.round(min * 100) / 100; rec.raw = { glyph, ring, holes }; }
    }
    cv.texts.push(rec);
  };
  [P, OP].filter(Boolean).forEach(Q => {
    const fillText0 = Q.fillText, strokeText0 = Q.strokeText, drawImage0 = Q.drawImage;
    Q.fillText = function () { tag(this.canvas, arguments[0]); spread(this, 'fillStyle'); if (mine(this)) probe(this, fillText0, 'fillStyle', arguments); return fillText0.apply(this, arguments); };
    Q.strokeText = function () { tag(this.canvas, arguments[0]); spread(this, 'strokeStyle'); if (mine(this)) probe(this, strokeText0, 'strokeStyle', arguments); return strokeText0.apply(this, arguments); };
    Q.drawImage = function (src) {
      const s = srcOf(src);
      mix(this.canvas, s); spread(this, null);
      if (mine(this)) {
        const a = arguments, T = this.getTransform(), sw = src.width || 0, sh = src.height || 0;
        const [dx, dy, dw, dh] = a.length === 3 ? [a[1], a[2], sw, sh] : a.length === 5 ? [a[1], a[2], a[3], a[4]] : [a[5], a[6], a[7], a[8]], xs = [], ys = [];
        [[dx, dy], [dx + dw, dy], [dx, dy + dh], [dx + dw, dy + dh]].forEach(([u, v]) => { xs.push(T.a * u + T.c * v + T.e); ys.push(T.b * u + T.d * v + T.f); });
        const kind = isCanvas(src) ? 'canvas' : (src && src.constructor && src.constructor.name) || 'imagen';
        const rec = { kind, texts: [...s.t], unknown: s.u, box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], halo: false };
        cv.images.push(rec); pending = rec.texts.length ? rec : null;
      }
      return drawImage0.apply(this, arguments);
    };
    // los píxeles leídos de un lienzo llevan sus textos al lienzo donde se pongan; y en el mapa, unos píxeles puestos a mano no se miden
    const gid = Q.getImageData, pid = Q.putImageData, cp = Q.createPattern;
    Q.getImageData = function () { const d = gid.apply(this, arguments), r = TXT.get(this.canvas); if (r && (r.t.size || r.u)) IMG.set(d, copyOf(r)); return d; };
    Q.putImageData = function (d, dx, dy, sx = 0, sy = 0, sw = d.width, sh = d.height) {
      const r = IMG.get(d);
      mix(this.canvas, r);
      if (mine(this)) { pending = null; cv.images.push({ kind: 'píxeles', texts: r ? [...r.t] : [], unknown: !!r && r.u, box: [dx + sx, dy + sy, dx + sx + sw, dy + sy + sh], halo: false }); }
      return pid.apply(this, arguments);
    };
    Q.createPattern = function (src) {
      const p = cp.apply(this, arguments);
      if (p) PAT.set(p, Object.assign(srcOf(src), { canvas: isCanvas(src) }));
      return p;
    };
    // en los demás lienzos, rellenar o trazar con un patrón les pasa lo que lleva (AR4-01)
    if (Q === OP) ['fill', 'stroke', 'fillRect', 'strokeRect'].forEach(k => { const f0 = Q[k]; Q[k] = function () { spread(this, /^stroke/.test(k) ? 'strokeStyle' : 'fillStyle'); return f0.apply(this, arguments); }; });
  });
  // un relleno o un trazo del mapa con un patrón que lleva texto, o que no sale de un lienzo, es una imagen sin medir; y lo mismo, cualquier
  // dibujo del mapa con un filtro que trae una imagen de fuera, url() (AR4-01)
  const patIn = (ctx, style) => {
    const T = ctx.getTransform();
    if (/url\(/.test(ctx.filter)) cv.images.push({ kind: 'filtro con url()', texts: [], unknown: true, box: [T.e, T.f, T.e, T.f], halo: false });
    const q = style && ctx[style]; if (!q || typeof q !== 'object' || !(q instanceof CanvasPattern)) return;
    const i = PAT.get(q); if (i && i.canvas && !i.t.size && !i.u) return;
    cv.images.push({ kind: i && i.canvas ? 'patrón' : 'patrón sin lienzo', texts: i ? [...i.t] : [], unknown: !i || i.u, box: [T.e, T.f, T.e, T.f], halo: false });
  };
  // en otro lienzo, lo mismo pasa a lo que lleva el lienzo: lo del patrón, o procedencia desconocida
  function spread(ctx, style) {
    if (mine(ctx)) return patIn(ctx, style);
    const q = style && ctx[style];
    if (q && typeof q === 'object' && q instanceof CanvasPattern) { const i = PAT.get(q); if (i) mix(ctx.canvas, i); else taint(ctx.canvas); }
    if (/url\(/.test(ctx.filter)) taint(ctx.canvas);
  }
  P.fillRect = function (x, y, w, h) {
    if (!mine(this)) spread(this, 'fillStyle');
    else {
      pending = null;
      const T = this.getTransform(), c = this.canvas;
      if (!T.b && !T.c && T.a * x + T.e <= 0.5 && T.d * y + T.f <= 0.5 && T.a * (x + w) + T.e >= c.width - 1 && T.d * (y + h) + T.f >= c.height - 1) Object.assign(cv, { texts: [], strokes: [], fills: [], images: [] });
      patIn(this, 'fillStyle');
    }
    return fillRect0.apply(this, arguments);
  };
  { const sr0 = P.strokeRect; P.strokeRect = function () { spread(this, 'strokeStyle'); return sr0.apply(this, arguments); }; }
  let seq = 0;
  const at = (ctx, kind) => { const T = ctx.getTransform(), dpr = dprOf(ctx); return { kind, x: Math.round(T.e / dpr), y: Math.round(T.f / dpr), dash: ctx.getLineDash().join(','), lw: ctx.lineWidth, n: ++seq }; };
  // caja de px del lienzo alrededor del origen, de r px de CSS de radio
  const around = (ctx, T, r) => { const R = Math.ceil(r * dprOf(ctx)), cx = Math.round(T.e), cy = Math.round(T.f), x0 = Math.max(0, cx - R), y0 = Math.max(0, cy - R); return [x0, y0, Math.min(ctx.canvas.width, cx + R) - x0, Math.min(ctx.canvas.height, cy + R) - y0]; };
  // cuánto cubre el propio trazo (o el dibujo draw, como el icono de un marcador) cada píxel de la caja: se pinta en blanco y en negro
  // solo dentro de ella, y se devuelve el fondo
  const cover = (ctx, T, [x0, y0, w, h], dash, draw) => {
    const under = gid0.call(ctx, x0, y0, w, h), clip = new Path2D(); clip.rect(x0, y0, w, h);
    const paint = c => { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clip(clip); ctx.setTransform(T); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.shadowColor = 'transparent'; ctx.filter = 'none'; if (draw) draw(c); else { if (dash) ctx.setLineDash(dash); ctx.strokeStyle = c; stroke0.call(ctx); } ctx.restore(); const d = gid0.call(ctx, x0, y0, w, h).data; pid0.call(ctx, under, x0, y0); return d; };
    const wh = paint('#fff'), bk = paint('#000'), cov = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) cov[i] = (wh[4 * i] - bk[4 * i] + wh[4 * i + 1] - bk[4 * i + 1] + wh[4 * i + 2] - bk[4 * i + 2]) / 765;
    return cov;
  };
  // trozos sueltos, con vecinos en las ocho direcciones, de lo que el trazo cubre al menos a la mitad
  const pieces = (cov, w, h) => {
    const seen = new Uint8Array(w * h); let n = 0;
    for (let i = 0; i < w * h; i++) {
      if (seen[i] || cov[i] < 0.5) continue;
      n++; seen[i] = 1; const st = [i];
      while (st.length) { const j = st.pop(), x = j % w, y = (j - x) / w; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const u = x + dx, v = y + dy, k = v * w + u; if (u >= 0 && v >= 0 && u < w && v < h && !seen[k] && cov[k] >= 0.5) { seen[k] = 1; st.push(k); } } }
    }
    return n;
  };
  // lo que pinta un Path2D, como el icono de un marcador: su `d`, su origen, los píxeles que toca y los que cubre enteros (UX-48)
  const iconOf = (ctx, T, rec, draw) => {
    const box = around(ctx, T, 13), [x0, y0, w, h] = box, W = ctx.canvas.width, t = [], f = [];
    rec.o = [T.e, T.f];
    if (!(w > 0 && h > 0)) return;
    const cov = cover(ctx, T, box, null, draw);
    for (let i = 0; i < w * h; i++) if (cov[i] > 0) { const k = (y0 + Math.floor(i / w)) * W + x0 + i % w; t.push(k); if (cov[i] >= 0.95) f.push(k); }
    rec.raw = { icon: { t, f } };
  };
  P.stroke = function () {
    if (!mine(this)) { spread(this, 'strokeStyle'); return stroke0.apply(this, arguments); }
    pending = null; patIn(this, 'strokeStyle');
    const rec = at(this, 'stroke'), T = this.getTransform();
    // el contorno discontinuo de un marcador: su trazo rodea su origen
    const ring = !arguments.length && rec.dash && this.isPointInPath(T.e, T.f);
    // hasta dónde llega a cada lado de su origen, a lo ancho y a lo alto, como la planta del objeto al colocarlo (UX-49)
    if (ring) {
      const d = dprOf(this), far = (u, v) => { let lo = 0, hi = Math.max(this.canvas.width, this.canvas.height); for (let n = 0; n < 16; n++) { const m = (lo + hi) / 2; if (this.isPointInPath(T.e + u * m, T.f + v * m)) lo = m; else hi = m; } return lo / d; };
      rec.ext = { w: Math.round((far(1, 0) + far(-1, 0)) * 10) / 10, h: Math.round((far(0, 1) + far(0, -1)) * 10) / 10 };
    }
    const box = around(this, T, Math.max(13, rec.ext ? Math.max(rec.ext.w, rec.ext.h) / 2 + 3 : 0));
    if (ring && box[2] > 0 && box[3] > 0) {
      const [x0, y0, w, h] = box, dash = cover(this, T, box, null), full = cover(this, T, box, []), on = [], off = [];
      for (let i = 0; i < w * h; i++) { const q = [x0 + i % w, y0 + Math.floor(i / w)]; if (dash[i] >= 0.75) on.push(q); else if (full[i] >= 0.75 && dash[i] <= 0.1) off.push(q); }
      rec.raw = { on, off }; rec.gaps = { comps: pieces(dash, w, h), gapPx: off.length, dashPx: on.length };
    }
    else if (arguments[0] instanceof Path2D0) { const a = arguments; rec.d = PD.get(a[0]) || null; iconOf(this, T, rec, c => { this.strokeStyle = c; stroke0.apply(this, a); }); }
    cv.strokes.push(rec);
    return stroke0.apply(this, arguments);
  };
  P.fill = function () {
    if (!mine(this)) { spread(this, 'fillStyle'); return fill0.apply(this, arguments); }
    pending = null; patIn(this, 'fillStyle');
    const rec = Object.assign(at(this, 'fill'), { pat: typeof this.fillStyle !== 'string' }), T = this.getTransform();
    if (typeof this.fillStyle === 'string') { const c = rgba(this.fillStyle); rec.ink = [c[0], c[1], c[2], c[3] / 255 * this.globalAlpha]; }
    const r = fill0.apply(this, arguments);
    // el interior de un relleno centrado en su origen, como un marcador, a 2 px de CSS de su borde
    const box = around(this, T, 10);
    if (!arguments.length && box[2] > 0 && box[3] > 0 && this.isPointInPath(T.e, T.f)) {
      const [x0, y0, w, h] = box, e = Math.max(1, Math.round(2 * dprOf(this))), inside = new Uint8Array(w * h), px = [];
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) inside[j * w + i] = this.isPointInPath(x0 + i + 0.5, y0 + j + 0.5) ? 1 : 0;
      const ok = (i, j) => i >= 0 && j >= 0 && i < w && j < h && inside[j * w + i];
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) if ([[0, 0], [e, 0], [-e, 0], [0, e], [0, -e], [e, e], [-e, -e], [e, -e], [-e, e]].every(([u, v]) => ok(i + u, j + v))) px.push([x0 + i, y0 + j]);
      rec.raw = { px }; rec.o = [T.e, T.f];
      // su forma: la distancia del origen al borde cada 5°. Un cuadrado, gire lo que gire, da la misma a 90° y la mayor entre 1,35 y √2
      // veces la menor (UX-48)
      const d = dprOf(this), rho = [];
      for (let k = 0; k < 72; k++) { const a = k * Math.PI / 36; let lo = 0, hi = 14 * d; for (let n = 0; n < 10; n++) { const m = (lo + hi) / 2; if (this.isPointInPath(T.e + Math.cos(a) * m, T.f + Math.sin(a) * m)) lo = m; else hi = m; } rho.push((lo + hi) / 2 / d); }
      rec.shape = { sym: Math.round(Math.max(...rho.map((r, k) => Math.abs(r - rho[(k + 18) % 72]))) * 100) / 100, ratio: Math.round(Math.max(...rho) / Math.min(...rho) * 100) / 100 };
    }
    else if (arguments[0] instanceof Path2D0) { const a = arguments; rec.d = PD.get(a[0]) || null; iconOf(this, T, rec, c => { this.fillStyle = c; fill0.apply(this, a); }); }
    cv.fills.push(rec);
    return r;
  };
  // Al cerrar el fotograma: de cada letra, el contraste de cada píxel suyo frente a su fondo. De cada interior, los dos tonos (se separan
  // por luminancia), qué parte es de cada uno, su contraste, cuántas veces cambia de tono, de media, cada fila de 6 px o más, y si van en
  // franjas: en la dirección, de 3 en 3 grados, en que el tono cambia menos, qué parte de los píxeles lleva el tono que más hay en su línea
  // de 1 px de ancho (en líneas de 3 píxeles o más). Un rayado da casi todo; un tablero, poco más de la mitad en cualquier dirección. Y la
  // parte del color del relleno, si es opaco, en lo que deja ver su icono. De cada contorno discontinuo, el contraste entre el color mediano
  // de sus guiones y el de sus huecos. De cada icono, su `d`, cuánto del interior toca, cuánto se sale de él y el contraste entre el color
  // mediano de lo que cubre entero y el de lo que deja ver (UX-48).
  let KEEP = [], KD = null;
  const med = cs => { if (!cs.length) return null; const s = cs.slice().sort((a, b) => lum(a) - lum(b)); return s[s.length >> 1]; };
  const r2 = v => Math.round(v * 100) / 100;
  // la letra: su color final sin la parte del fondo que deja ver su borde, E = (F − B·(1 − cubierto)) / cubierto, frente al fondo B, el color
  // mediano de los píxeles del anillo que tiene cerca, a 4 px o menos (el de todo el anillo si cerca hay menos de 3): así cuenta un fondo que
  // cambia solo en una parte del texto (AR4-01). Y sus huecos: los que acaban pareciéndose a la tinta, a menos de 1,5:1 de ella, se han
  // rellenado después, como una cifra tapada con un bloque de su misma tinta. `col` dice el color de cada píxel: el del lienzo acabado, o el
  // de la captura de la pantalla (AR5-01)
  const legible = (col, glyph, ring, holes) => {
    const rc = ring.map(col), B0 = med(rc);
    if (!B0) return null;
    let low = 0, min = 99;
    glyph.forEach(([x, y, k]) => {
      const nb = rc.filter((_, i) => Math.abs(ring[i][0] - x) <= 4 && Math.abs(ring[i][1] - y) <= 4), B = nb.length >= 3 ? med(nb) : B0;
      const F = col([x, y]), r = ratio([0, 1, 2].map(c => Math.max(0, Math.min(255, (F[c] - B[c] * (1 - k)) / k))), B); if (r < 4.5) low++; if (r < min) min = r;
    });
    return { n: glyph.length, low, min: r2(min), holes: holes.length, filled: holes.filter(([x, y, ...e]) => ratio(col([x, y]), e) < 1.5).length };
  };
  cv.finish = () => {
    const c = document.querySelector('#map'), W = c.width, D = gid0.call(c.getContext('2d'), 0, 0, W, c.height).data;
    KD = D; KEEP = cv.texts.map(t => t.raw ? [t.raw.glyph, t.raw.ring, t.raw.holes] : null);
    const col = ([x, y]) => { const i = 4 * (y * W + x); return [D[i], D[i + 1], D[i + 2]]; };
    cv.texts.forEach(t => {
      if (!t.raw) return;
      const { glyph, ring, holes } = t.raw, f = legible(col, glyph, ring, holes); delete t.raw;
      if (f) t.fin = f;
    });
    // el icono de un marcador: lo que se pinta con un Path2D en su mismo origen, después de su relleno y antes del siguiente relleno ahí
    const marks = cv.fills.filter(f => f.raw && f.raw.px), icons = cv.fills.concat(cv.strokes).filter(r => r.raw && r.raw.icon);
    const same = (a, b) => a.o[0] === b.o[0] && a.o[1] === b.o[1];
    marks.forEach(f => { const nx = Math.min(Infinity, ...marks.filter(g => same(g, f) && g.n > f.n).map(g => g.n)); f.raw.own = icons.filter(r => same(r, f) && r.n > f.n && r.n < nx); });
    cv.fills.forEach(f => {
      if (!f.raw || !f.raw.px) return;
      const px = f.raw.px, own = f.raw.own, cs = px.map(col), L = cs.map(lum); delete f.raw;
      if (!cs.length) return;
      const lo = Math.min(...L), hi = Math.max(...L); let thr = (lo + hi) / 2;
      for (let k = 0; k < 12; k++) { let a = 0, na = 0, b = 0, nb = 0; L.forEach(v => { if (v < thr) { a += v; na++; } else { b += v; nb++; } }); if (!na || !nb) break; thr = (a / na + b / nb) / 2; }
      const light = L.map(v => hi - lo > 1e-4 && v >= thr), nl = light.filter(Boolean).length;
      const mean = sel => { const q = cs.filter((_, i) => light[i] === sel); return q.length ? [0, 1, 2].map(k => q.reduce((s, x) => s + x[k], 0) / q.length) : null; };
      const ml = mean(true), md = mean(false), rows = {};
      px.forEach(([x, y], i) => (rows[y] = rows[y] || []).push([x, light[i]]));
      let alt = 0, nr = 0;
      Object.values(rows).forEach(r => { if (r.length < 6) return; r.sort((a, b) => a[0] - b[0]); for (let k = 1; k < r.length; k++) if (r[k][0] === r[k - 1][0] + 1 && r[k][1] !== r[k - 1][1]) alt++; nr++; });
      const along = d => {
        const a = d * Math.PI / 180, nx = -Math.sin(a), ny = Math.cos(a), bins = {};
        px.forEach(([x, y], i) => { const b = Math.floor(x * nx + y * ny), q = bins[b] || (bins[b] = [0, 0]); q[light[i] ? 1 : 0]++; });
        let top = 0, all = 0; Object.values(bins).forEach(q => { if (q[0] + q[1] >= 3) { top += Math.max(q[0], q[1]); all += q[0] + q[1]; } });
        return all ? top / all : 0;
      };
      let dir = 0, best = 0;
      for (let d = 0; d < 180; d += 3) { const v = along(d); if (v > dir) { dir = v; best = d; } }
      // y que se repitan, como en un rayado (AR4-01): en su mejor dirección, las líneas de 1 px de ancho (de 3 píxeles o más), cada una con el
      // tono que más lleva, hacen franjas de un tono; y cada tono va en trozos sueltos de 3 px o más, con vecinos en las ocho direcciones
      const bands = { light: 0, dark: 0 }, parts = { light: 0, dark: 0 };
      {
        const a = best * Math.PI / 180, nx = -Math.sin(a), ny = Math.cos(a), bins = {};
        px.forEach(([x, y], i) => { const b = Math.floor(x * nx + y * ny), q = bins[b] || (bins[b] = [0, 0]); q[light[i] ? 1 : 0]++; });
        let prev = null; Object.keys(bins).map(Number).sort((u, v) => u - v).forEach(b => { const q = bins[b]; if (q[0] + q[1] < 3) return; const tn = q[1] > q[0] ? 'light' : 'dark'; if (tn !== prev) { bands[tn]++; prev = tn; } });
        const at = new Map(px.map(([x, y], i) => [y * W + x, i])), seen = new Uint8Array(px.length);
        px.forEach((_, i) => {
          if (seen[i]) return;
          let size = 0; const st = [i]; seen[i] = 1;
          while (st.length) { const j = st.pop(), [x, y] = px[j]; size++; for (let v = -1; v <= 1; v++) for (let u = -1; u <= 1; u++) { const k = at.get((y + v) * W + x + u); if (k !== undefined && !seen[k] && light[k] === light[i]) { seen[k] = 1; st.push(k); } } }
          if (size >= 3) parts[light[i] ? 'light' : 'dark']++;
        });
      }
      f.stripes = { n: cs.length, light: r2(nl / cs.length), dark: r2(1 - nl / cs.length), ratio: ml && md ? r2(ratio(ml, md)) : 1, alt: nr ? r2(alt / nr) : 0, dir: r2(dir), cross: r2(along(best + 90)), bands, parts };
      const keys = px.map(([x, y]) => y * W + x), inner = new Set(keys), touch = new Set(own.flatMap(r => r.raw.icon.t)), full = new Set(own.flatMap(r => r.raw.icon.f));
      const rest = cs.filter((_, i) => !touch.has(keys[i]));
      if (f.ink) f.solid = { share: f.ink[3] < 0.99 || !rest.length ? 0 : r2(rest.filter(x => Math.max(...[0, 1, 2].map(k => Math.abs(x[k] - f.ink[k]))) <= 24).length / rest.length), left: r2(rest.length / cs.length) };
      if (own.length) { const fc = cs.filter((_, i) => full.has(keys[i])); f.icon = { d: (own.find(r => r.d) || {}).d || null, n: cs.length, touched: keys.filter(k => touch.has(k)).length, out: [...touch].filter(k => !inner.has(k)).length, ratio: fc.length && rest.length ? r2(ratio(med(fc), med(rest))) : 1 }; }
    });
    icons.forEach(r => delete r.raw);
    cv.strokes.forEach(s => {
      if (!s.raw) return;
      const on = med(s.raw.on.map(col)), off = med(s.raw.off.map(col)); delete s.raw;
      s.gaps.ratio = on && off ? r2(ratio(on, off)) : 1;
    });
  };
  // Lo que se ve en pantalla, que el lienzo no ve: un filtro o una opacidad de CSS en el mapa o en lo que lo contiene, o algo encima de él
  // (AR4-01). La pantalla pone el lienzo píxel a píxel, sin remuestrearlo, también cuando el alto del mapa en CSS no es entero (855,6 px
  // para 856 del lienzo, a 1600 × 960: corta la última fila); medido en 18 vistas, de 1280 × 800 a 1920 × 1080, en los dos temas, con
  // 1 de 255 de diferencia como mucho. Así que cada píxel de cada texto del último fotograma acabado (su letra, su anillo y sus huecos) tiene
  // que ser en una captura del mapa el suyo del lienzo, a 8 de 255 en cada canal, y no uno cualquiera entre sus vecinos (AR5-01). Antes, el
  // desplazamiento de toda la captura, de −1 a 1 px en cada eje, que mejor casa con el lienzo, por si la pantalla lo pone una fila más allá.
  // No cuentan los píxeles que caen debajo de lo que flota encima del mapa, sin más margen, ni los de los 3 px del borde, donde va el anillo
  // del foco (AR5-02). En la sombra de lo que flota, el píxel vale si es el del lienzo llevado hacia el color de la sombra, en la misma parte
  // en los tres canales y como mucho lo que oscurece su opacidad; y como una sombra le baja el contraste a lo que cae debajo, además, en la
  // captura, la letra de cada texto llega a 4,5:1 en cada píxel frente a su fondo, como en el lienzo, y sus huecos siguen sin tinta. Y
  // cuántos ya no son en el lienzo los que se midieron, si se repintó entre la medida y la captura
  cv.composite = async url => {
    const c = document.querySelector('#map'), W = c.width, H = c.height, d = W / c.clientWidth, im = new Image();
    im.src = url; await im.decode();
    const w = im.naturalWidth, h = im.naturalHeight, o = new OffscreenCanvas(w, h), og = o.getContext('2d'); odraw0.call(og, im, 0, 0);
    const S = ogid0.call(og, 0, 0, w, h).data, D = gid0.call(c.getContext('2d'), 0, 0, W, H).data, m = c.getBoundingClientRect();
    // una captura que no tiene el tamaño del lienzo no se compara píxel a píxel: no hay comparación
    if (Math.abs(w - W) > 1 || Math.abs(h - H) > 1) return KEEP.map(() => null);
    // de lo que flota encima se aparta, sin compararla, su caja (AR6-01, AR7-02), recortada por lo que la contiene si eso recorta lo que se le
    // sale (overflow), aunque no la pinte entera, y solo si nada cambia lo que pinta dentro de ella: se ve (visibility), y ni él ni lo que lo
    // contiene van recortados (clip-path, clip), con máscara, con filtro, fundidos con lo de debajo, transparentes (opacity) ni movidos más que
    // de sitio (transform, rotate, scale, offset-path). Lo que no cumple eso no se aparta, ni su sombra: sus píxeles se comparan, y si tapa
    // algo de un texto, sale distinto
    const plain = e => {
      if (getComputedStyle(e).visibility !== 'visible') return false;
      for (let a = e; a; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (s.clipPath !== 'none' || s.clip !== 'auto' || s.maskImage !== 'none' || (s.webkitMaskImage || 'none') !== 'none' || s.filter !== 'none' || s.mixBlendMode !== 'normal' || s.opacity !== '1' ||
          s.rotate !== 'none' || s.scale !== 'none' || s.offsetPath !== 'none' || !/^(none|matrix\(1, 0, 0, 1, [^,]+, [^)]+\))$/.test(s.transform)) return false;
      }
      return true;
    };
    const painted = e => {
      const q = e.getBoundingClientRect(); let [l, t, r, b] = [q.left, q.top, q.right, q.bottom];
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (s.overflowX === 'visible' && s.overflowY === 'visible' && !/paint|strict|content/.test(s.contain)) continue;
        const z = a.getBoundingClientRect(), x = z.left + a.clientLeft, y = z.top + a.clientTop;
        l = Math.max(l, x); t = Math.max(t, y); r = Math.min(r, x + a.clientWidth); b = Math.min(b, y + a.clientHeight);
      }
      return { left: l, top: t, right: Math.max(l, r), bottom: Math.max(t, b) };
    };
    const els = [...document.querySelectorAll('#mapwrap .ovl, #legend, #hint, #recBadge, #banner, #toasts > *, #menu, #scrim, #guide')].filter(e => e.getClientRects().length > 0 && plain(e));
    const rect = (b, g = 0, u = 0, v = 0) => [(b.left - m.left + u - g) * d, (b.top - m.top + v - g) * d, (b.right - m.left + u + g) * d, (b.bottom - m.top + v + g) * d];
    const ov = els.map(e => rect(painted(e)));
    // la sombra de cada uno (su box-shadow, sin las de dentro): su color, su opacidad y hasta dónde llega, su caja movida y crecida en su
    // extensión y en su desenfoque
    const sh = els.flatMap(e => { const b = e.getBoundingClientRect(); return [...getComputedStyle(e).boxShadow.matchAll(/rgba?\(([^)]*)\)\s+(-?[\d.]+)px\s+(-?[\d.]+)px(?:\s+([\d.]+)px)?(?:\s+(-?[\d.]+)px)?(\s+inset)?/g)].filter(q => !q[6]).map(q => { const k = q[1].split(',').map(Number); return { c: k.slice(0, 3), a: k.length > 3 ? k[3] : 1, r: rect(b, (+q[4] || 0) + (+q[5] || 0), +q[2], +q[3]) }; }); });
    const inside = (q, x, y) => x >= q[0] && x < q[2] && y >= q[1] && y < q[3];
    const off = (x, y) => x < 3 * d || y < 3 * d || x >= W - 3 * d || y >= H - 3 * d || ov.some(q => inside(q, x, y));
    // lo que puede oscurecer la sombra en un píxel: su color y, si caen varias, 1 − el producto de lo que deja pasar cada una
    const shade = (x, y) => { let pass = 1, col = null; sh.forEach(q => { if (inside(q.r, x, y)) { pass *= 1 - q.a; col = col || q.c; } }); return col ? col.concat(1 - pass) : null; };
    const fits = (s, q, z) => {
      let lo = 0, hi = z ? z[3] : 0;
      for (let k = 0; k < 3; k++) {
        const v = D[q + k], e = S[s + k] - v, dd = z ? z[k] - v : 0;
        if (Math.abs(dd) < 0.5) { if (Math.abs(e) > 8) return false; continue; }
        let a = (e - 8) / dd, b = (e + 8) / dd; if (a > b) [a, b] = [b, a];
        lo = Math.max(lo, a); hi = Math.min(hi, b);
      }
      return lo <= hi;
    };
    let ox = 0, oy = 0, best = Infinity;
    for (const [u, v] of [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      let bad = 0;
      for (let y = 4; y < H - 4; y += 5) for (let x = 4; x < W - 4; x += 5) { const X = x + u, Y = y + v; if (X >= 0 && Y >= 0 && X < w && Y < h && !off(x, y) && !fits(4 * (Y * w + X), 4 * (y * W + x), shade(x, y))) bad++; }
      if (bad < best) { best = bad; ox = u; oy = v; }
    }
    const vis = ([x, y]) => !off(x, y) && x + ox >= 0 && y + oy >= 0 && x + ox < w && y + oy < h;
    const sc = ([x, y]) => { const i = 4 * ((y + oy) * w + x + ox); return [S[i], S[i + 1], S[i + 2]]; };
    const dif = (A, B, j) => Math.max(Math.abs(A[j] - B[j]), Math.abs(A[j + 1] - B[j + 1]), Math.abs(A[j + 2] - B[j + 2]));
    return KEEP.map(k => {
      if (!k || !KD) return null;
      let n = 0, diff = 0, moved = 0, dark = 0;
      k.forEach(l => l.forEach(([x, y]) => { if (!vis([x, y])) return; n++; const q = 4 * (y * W + x), z = shade(x, y); if (z) dark++; if (dif(D, KD, q) > 2) moved++; else if (!fits(4 * ((y + oy) * w + x + ox), q, z)) diff++; }));
      // y cuántos píxeles de su letra y de sus huecos se quedan sin comparar: un texto comparado en parte no se da por leído (AR6-01)
      const [g, r, hs] = k.map(l => l.filter(vis)), f = g.length && r.length ? legible(sc, g, r, hs) : null;
      return { n, diff, moved, dark, g: g.length, cut: k[0].length - g.length + k[2].length - hs.length, low: f ? f.low : g.length, min: f ? f.min : null, filled: f ? f.filled : 0, at: [ox, oy] };
    });
  };
};
const TOWN = /^(Chernogorsk|Elektrozavodsk|Berezino|Solnichniy|Kamyshovo|Zelenogorsk|Stary Sobor|Novy Sobor|Vybor|Gorka|Balota|Komarovo|Kabanino|Prigorodki|Svetlojarsk|Krasnostav|Severograd|Novodmitrovsk|Lopatino|Pustoshka)$/i;

(async () => {
  const browser = await chromium.launch();
  const errors = [], external = [];
  const fresh = async (w = 1600, h = 960, scheme = 'dark') => {
    const c = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme });
    await c.addInitScript(LIB); await c.addInitScript(PROBE);
    const p = await c.newPage(); p.setDefaultTimeout(3000);
    p.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
    p.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
    await p.goto(URL); await p.waitForTimeout(900);
    return p;
  };
  // cada caso devuelve una lista de [qué se comprueba, si se cumple, lo que se vio]; si se corta a medias, cuenta como fallo
  const R26 = async (name, fn, w, h, scheme) => {
    if (process.env.SOLO && !new RegExp(process.env.SOLO).test(name)) return;
    let p;
    try { p = await fresh(w, h, scheme); for (const [what, ok, info] of await fn(p)) expect(ok, what + (info ? ' · ' + info : '')); }
    catch (e) { expect(false, `${name} · se cortó: ${String(e.message || e).split('\n')[0]}`); }
    finally { if (p) await p.context().close().catch(() => {}); }
  };
  const T = async (p, sel) => (await p.locator(sel).first().innerText({ timeout: 1000 }).catch(() => '')).replace(/\s+/g, ' ').trim();
  const W = (p, fn, arg, ms) => p.waitForFunction(fn, arg, { timeout: ms }).then(() => true, () => false);
  const shows = (p, sel, re, ms = 6000) => W(p, ([s, r]) => { const el = document.querySelector(s); return !!el && el.getClientRects().length > 0 && new RegExp(r).test(el.innerText); }, [sel, re.source], ms);
  // el menú del simulador se cierra con un clic fuera: con la toma en marcha, Esc la pararía
  const sim = async (p, v) => { await p.click('#bSim'); await p.waitForTimeout(120); await p.click(`#menu [data-act="sim"][data-v="${v}"]`); await p.click('#status', { position: { x: 3, y: 3 } }); await p.waitForTimeout(150); };
  const dock = async p => { if (await p.locator('#center.dock-closed').count()) { await p.click('#dock .strip'); await p.waitForTimeout(150); } };
  // aplicar con Ctrl+Intro y esperar a que Aplicar quede libre otra vez; vale también para el prototipo de antes
  const free = p => W(p, () => { const a = document.querySelector('#bApply'); return !a.disabled && !a.classList.contains('busy') && !/Aplicando/.test(a.innerText); }, null, 15000);
  const apply = async p => { await p.locator('#map').hover(); await p.keyboard.press('Control+Enter'); await W(p, () => document.querySelector('#bApply').disabled, null, 2000); return free(p); };
  const arm = async p => { await p.keyboard.press('2'); await p.waitForTimeout(300); await p.keyboard.press('Shift+F9'); return shows(p, '#bTopStop', /Desarmar/, 6000); };
  const roll = async p => { await p.keyboard.press('Enter'); return shows(p, '#bTopStop', /Parar/, 2000); };
  const nudge = async p => { await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.focus('#map'); await p.keyboard.press('ArrowUp'); await p.waitForTimeout(200); };
  // un fotograma del mapa grabado por la sonda: se fuerza el redibujo cambiando 1 px la ventana y volviéndola a su tamaño
  const frame = async p => {
    const vs = p.viewportSize(); await p.setViewportSize({ width: vs.width, height: vs.height + 1 }); await p.waitForTimeout(200);
    await p.evaluate(() => { Object.assign(window.__cv, { texts: [], strokes: [], fills: [], images: [], on: true }); });
    await p.setViewportSize(vs); await p.waitForTimeout(300);
    return p.evaluate(() => { const cv = window.__cv; cv.on = false; cv.finish(); return { texts: cv.texts, strokes: cv.strokes, fills: cv.fills, images: cv.images }; });
  };
  // contraste de lo pintado en el mapa: cada texto, con todos los píxeles de su letra a 4,5:1 o más al pintarlo y en el fotograma acabado (AR3-01)
  const lowTexts = f => f.texts.filter(t => t.low > 0 || (t.n > 0 && (!t.fin || t.fin.low > 0)));
  const showLow = l => l.slice(0, 4).map(t => t.low > 0 ? `«${t.text}» ${t.min}:1 en ${t.low} de ${t.n} px` : t.fin ? `«${t.text}» al acabar ${t.fin.min}:1 en ${t.fin.low} de ${t.fin.n} px` : `«${t.text}» sin medir al acabar`).join(' · ');
  const mapPct = p => p.evaluate(() => { const r = document.querySelector('#map').getBoundingClientRect(); return Math.round(r.width * r.height / (innerWidth * innerHeight) * 100); });
  const hatched = f => f.fills.filter(x => x.pat);
  // Lo que se ve en el fotograma acabado (AR2-01). Son umbrales de aceptación de esta prueba, calibrados con el dibujo de la página y con
  // ataques, no medidas de percepción (AR3-01):
  // - rayado: dos tonos a 3:1 o más entre sí, cada uno en al menos un 15 % del interior, que alternan a lo ancho (más de un cambio de tono
  //   por fila, de media, no en cada fila) y en franjas: en su mejor dirección, el 83 % o más de los píxeles lleva el tono de su línea, y en
  //   la perpendicular, 0,15 menos o más. El rayado de la página da 0,97 frente a 0,61; su azulejo, girado de 5 a 40° o con la muesca de
  //   un marcador, de 0,87 a 1, con 0,21 a 0,40 de diferencia. Un tablero de 1 a 4 px da 0,80 o menos y 0,07 o menos de diferencia, salvo
  //   el de 2 px corrido 1 px, que da 0,88 sin diferencia y cae también por su tono oscuro (13 %); un ruido de 1 o 2 px, 0,78 o menos.
  //   Y que se repitan (AR4-01): en la mejor dirección, dos franjas o más de cada tono, y cada tono en no más trozos que franjas, más uno.
  //   Un bloque solo, aunque dé 1 frente a 0,63, tiene una franja de su tono; unos puntos alargados en fila, más trozos que franjas;
  // - huecos de un contorno discontinuo: su propio trazo, pintado aparte al pintarlo, se parte en tres trozos o más y deja 6 px de hueco o
  //   más en total (no un hueco de 6 px), y en el fotograma acabado el color de los huecos se distingue del de los guiones (1,5:1 o más);
  // - sólido: el 85 % del interior, a 2 px del borde, es del color del relleno, opaco. No mira el borde: eso lo mira el contorno;
  // - sólido, con un icono dentro (UX-48): el 85 % de lo que deja ver el icono, y eso es al menos la mitad del interior: el color del
  //   relleno es la mayoría del área que no ocupa el icono, que en el extremo es el 42,5 % de todo el interior (AR4, §6 de Astra). Se
  //   apartan los píxeles que el icono toca, aunque sea un poco: es el margen del suavizado, medido en vez de supuesto;
  // - cuadrado (UX-48): la misma distancia al borde a 90° y la mayor entre 1,33 y 1,45 veces la menor (un cuadrado da √2).
  const STRIPES0 = s => !!s && s.light >= 0.15 && s.dark >= 0.15 && s.ratio >= 3 && s.alt > 1 && s.dir >= 0.83 && s.dir - s.cross >= 0.15;
  const STRIPES = s => STRIPES0(s) && !!s.bands && s.bands.light >= 2 && s.bands.dark >= 2 && s.parts.light <= s.bands.light + 1 && s.parts.dark <= s.bands.dark + 1;
  const GAPS = g => !!g && g.comps >= 3 && g.gapPx >= 6 && g.ratio >= 1.5;
  const SOLID = s => !!s && s.share >= 0.85 && s.left >= 0.5;
  const SQUARE = s => !!s && s.sym <= 0.15 && s.ratio >= 1.33 && s.ratio <= 1.45;
  const striped = f => hatched(f).filter(x => STRIPES(x.stripes));
  const showStripes = s => s ? `${Math.round(s.light * 100)} % claro y ${Math.round(s.dark * 100)} % oscuro a ${s.ratio}:1, ${s.alt} cambios por fila, franjas ${s.dir} frente a ${s.cross}${s.bands ? `, ${s.bands.light} claras y ${s.bands.dark} oscuras en ${s.parts.light} y ${s.parts.dark} trozos` : ''}` : 'sin interior';

  // --- UX-01: Parar gana a todo durante la toma ---
  await R26('UX-01 +', async p => {
    const what = 'UX-01 + rodando con un menú abierto, un solo Esc para la toma y Parar sigue a la vista sin tapar';
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(500); await p.click('#bLayers'); await p.waitForTimeout(150);
    const menu = await p.locator('#menu').isVisible();
    const clear = await p.evaluate(() => { const b = document.querySelector('#bTopStop'); if (!b || b.hidden) return false; const r = b.getBoundingClientRect(), el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!el && (el === b || b.contains(el)); });
    await p.keyboard.press('Escape');
    const stopped = await W(p, () => /parada a los/.test(document.querySelector('#toasts').innerText), null, 3000);
    return [[what, menu && clear && stopped, `menú abierto: ${menu} · Parar sin tapar: ${clear} · parada con un Esc: ${stopped}`]];
  });
  await R26('UX-01 − armada', async p => {
    const what = 'UX-01 − con la toma armada no se abren la Guía ni los Atajos';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    await p.evaluate(() => { location.hash = 'guia'; }); await p.waitForTimeout(300);
    const guide = await p.locator('#guide').isVisible();
    if (guide) { await p.evaluate(() => { location.hash = 'rodaje'; }); await p.waitForTimeout(300); }
    if (await p.locator('#bKeys').count()) await p.click('#bKeys', { force: true, timeout: 1000 }).catch(() => {});
    else { await p.click('#bTools'); await p.waitForTimeout(120); await p.evaluate(() => { const b = document.querySelector('#menu [data-act="keys"]'); if (b) b.click(); }); }
    await p.waitForTimeout(200);
    const keys = await p.locator('#scrim').isVisible(), armed = await shows(p, '#bTopStop', /Desarmar/, 500);
    return [[what, !guide && !keys && armed, `Guía ${guide ? 'abierta' : 'cerrada'} · Atajos ${keys ? 'abiertos' : 'cerrados'} · sigue armada: ${armed}`]];
  });
  await R26('UX-01 − corte', async p => {
    const what = 'UX-01 − tras un corte a mitad de toma, Parar sigue en la barra como «Parada sin confirmar» y no sale «Control devuelto» sin lectura';
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600); await sim(p, 'director');
    const failed = await shows(p, '#slateWrap', /Fallida/, 2500), unc = await shows(p, '#bTopStop', /Parada sin confirmar/, 1000);
    const back = /Control devuelto/.test(await p.evaluate(() => __r26.texts(document.querySelector('#app'))));
    return [[what, failed && unc && !back, `Fallida: ${failed} · «Parada sin confirmar» en la barra: ${unc} · «Control devuelto» a la vista: ${back}`]];
  });

  // --- UX-02: paneles acoplados y Actividad plegada ---
  await R26('UX-02 + 1440', async p => { const v = await mapPct(p); return [['UX-02 + el mapa ocupa ≥ 50 % de la ventana a 1440 × 900', v >= 50, v + ' %']]; }, 1440, 900);
  await R26('UX-02 + 1366', async p => { const v = await mapPct(p); return [['UX-02 + el mapa ocupa ≥ 45 % de la ventana a 1366 × 768', v >= 45, v + ' %']]; }, 1366, 768);
  await R26('UX-02 −', async p => {
    await sim(p, 'fault'); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    const ok = await shows(p, '#dock .strip', /Parcial[\s\S]*hace \d+/, 12000);
    return [['UX-02 − con una orden Parcial, la tira plegada de Actividad sigue diciendo Parcial con su edad', ok, (await T(p, '#dock .strip')) || 'no hay tira plegada']];
  });

  // --- UX-03: barra de arriba en tres grupos; las luces, abajo ---
  await R26('UX-03 + barra', async p => {
    const n = await p.evaluate(() => { const top = document.querySelector('.top') || document.querySelector('header'); return [...top.querySelectorAll('button,select,a,[role=button]')].filter(el => !el.closest('.proto') && __r26.vis(el)).length; });
    const e = await T(p, '[data-act="ws"][data-v="escena"]'), r = await T(p, '[data-act="ws"][data-v="rodaje"]');
    return [['UX-03 + a 1366 px, como mucho 9 controles del producto en la barra de arriba, y los modos enseñan 1 y 2', n <= 9 && /Escena\s*1/.test(e) && /Rodaje\s*2/.test(r), `${n} controles · «${e}» · «${r}»`]];
  }, 1366, 768);
  await R26('UX-03 + luces', async p => {
    const out = []; let all = true;
    for (const w of [1280, 1366, 1600]) {
      await p.setViewportSize({ width: w, height: 800 }); await p.waitForTimeout(300);
      const ok = await p.evaluate(() => [['#peerBk', /Backend/], ['#peerSrv', /Servidor/], ['#peerCli', /Tu juego/]].every(([s, re]) => { const el = document.querySelector(s); if (!el || !__r26.vis(el)) return false; const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight && re.test(el.innerText) && /\d+ (s|min|h)\b/.test(el.innerText); }));
      all = all && ok; out.push(`${w} px: ${ok ? 'sí' : 'no'}`);
    }
    return [['UX-03 + las tres luces enseñan su nombre y su edad a 1280, 1366 y 1600 px', all, out.join(' · ') + (all ? '' : ' · ' + await T(p, '#status'))]];
  });
  await R26('UX-03 −', async p => {
    const on = await T(p, '#status');
    await sim(p, 'backend'); await p.waitForTimeout(400);
    const stale = await p.locator('.peer.stale').count(), srv = await T(p, '#peerSrv'), off = await T(p, '#status');
    return [['UX-03 − sin backend, las luces se ponen grises con «hace X» y la barra no dice «Sin errores» a secas', /Escena sin errores/.test(on) && stale === 2 && /hace \d+/.test(srv) && !/sin errores/i.test(off), `${stale} luces grises · Servidor «${srv}» · barra sin backend «${off.slice(0, 110)}»`]];
  });

  // --- UX-04: «Aplicar escena» con nombre fijo ---
  await R26('UX-04 +', async p => {
    const a = await T(p, '#bApply'), d = await T(p, '#docBtn'), t = (await p.getAttribute('#bApply', 'title')) || '', r = await T(p, '#bReset'), rt = (await p.getAttribute('#bReset', 'title')) || '';
    return [['UX-04 + con cambios, el botón dice «Aplicar escena» y la cabecera «2 cambios sin aplicar»; las ayudas dicen que recrea la escena entera y que el documento no cambia', a === 'Aplicar escena' && /2 cambios sin aplicar/.test(d) && /vuelve a crear entera/.test(t) && /Quitar del juego/.test(r) && /El documento no cambia/.test(rt), `«${a}» · «${d}» · «${r}»`]];
  });
  await R26('UX-04 −', async p => {
    const what = 'UX-04 − con cero cambios se puede volver a aplicar, y un cambio no va al juego sin pulsar Aplicar';
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const again = await p.locator('#bApply').isEnabled();
    await nudge(p); await p.waitForTimeout(1500);
    const idle = await p.evaluate(() => { const a = document.querySelector('#bApply'); return !a.disabled && !a.classList.contains('busy'); }), d = await T(p, '#docBtn');
    return [[what, again && idle && /1 cambio sin aplicar/.test(d), `Aplicar libre con cero cambios: ${again} · tras mover un objeto: «${d}»`]];
  });

  // --- UX-05: lo técnico, plegado ---
  await R26('UX-05 +', async p => {
    const m = await p.evaluate(() => __r26.metrics());
    return [['UX-05 + escena recién abierta: como mucho 6 textos con jerga y un 10 % del texto en monoespaciada', m.jerga <= 6 && m.mono <= m.n * 0.10, `jerga ${m.jerga}${m.jerga ? ' (' + m.jergaEj.join(' | ') + ')' : ''} · monoespaciada ${m.mono} de ${m.n} textos`]];
  });
  await R26('UX-05 −', async p => {
    const dk = await p.evaluate(() => __r26.texts(document.querySelector('#dock')));
    const d2 = /\b(Pendiente|Ejecutando|Aplicado|Observado|Fallido|Parcial)\b/.test(dk) && /hace \d+/.test(dk) && /(servidor|tu juego|backend)/i.test(dk);
    await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(200);
    const v = await p.inputValue('#f-beh'), lbl = await p.evaluate(() => { const s = document.querySelector('#f-beh'); return s.options[s.selectedIndex].text; });
    return [['UX-05 − las órdenes enseñan su estado, su edad y su origen sin abrir nada, y el documento guarda el mismo valor con el nombre nuevo', d2 && v === 'ONCE' && lbl === 'Recorrer una vez', `Actividad sin abrir «${dk.slice(0, 90)}» · guardado ${v}, a la vista «${lbl}»`]];
  });

  // --- UX-06: estado por excepción en la Jerarquía ---
  await R26('UX-06 +', async p => {
    const what = 'UX-06 + con todo aplicado y leído, 0 iconos de estado en la Jerarquía; con un cambio, 1';
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const icons = () => p.evaluate(() => [...document.querySelectorAll('#colL .row .st svg')].filter(__r26.shown).length);
    const a = await icons(); await nudge(p); const b = await icons();
    return [[what, a === 0 && b === 1, `${a} con todo aplicado · ${b} con un cambio`]];
  });
  await R26('UX-06 −', async p => {
    const a = await T(p, '#colL .worldline');
    await p.click('#bReset'); await p.waitForTimeout(150); await p.click('#menu [data-act="reset-ok"]');
    const gone = await shows(p, '#colL .worldline', /Nada en el juego/, 8000);
    return [['UX-06 − la línea de arriba dice la edad de la lectura, o «Nada en el juego» si no hay nada', /leída hace \d+/.test(a) && gone, `«${a}» → «${await T(p, '#colL .worldline')}»`]];
  });

  // --- UX-07: siguiente paso a la vista ---
  await R26('UX-07 +', async p => {
    const what = 'UX-07 + tras aplicar con éxito, «Ir a rodaje» lleva a Rodaje';
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    if (!await p.locator('#bGoRod').isVisible()) return [[what, false, '«Ir a rodaje» no está a la vista']];
    await p.click('#bGoRod'); await p.waitForTimeout(300);
    const h = await p.evaluate(() => location.hash), tb = await p.locator('.takebar').isVisible();
    return [[what, h === '#rodaje' && tb, `${h} · cabecera de toma a la vista: ${tb}`]];
  });
  await R26('UX-07 −', async p => {
    const go = await p.locator('#bGoRod').isVisible();
    const t = await p.evaluate(() => __r26.texts(document.querySelector('#app'))), m = t.match(/\bhash\b|\br\d{1,3}\b|\b[0-9a-f]{8}\b|revisión \d+/);
    return [['UX-07 − con cambios sin aplicar no aparece «Ir a rodaje», y sin selección no se ve ningún hash ni revisión', !go && !m, `«Ir a rodaje» a la vista: ${go} · ${m ? 'se ve «' + m[0] + '»' : 'sin hash ni revisión'}`]];
  });

  // --- UX-08: Añadir ---
  await R26('UX-08 + búsqueda', async p => {
    await p.click('[data-act="rtab"][data-v="add"]'); await p.fill('#libq', 'bidón');
    await p.click('[data-act="lib-cat"][data-v="infectado"]'); await p.click('[data-act="lib-cat"][data-v="objeto"]');
    const q = await p.inputValue('#libq'), n = await p.locator('#colR .item').count();
    return [['UX-08 + buscar «bidón», cambiar a Infectados y volver: la búsqueda sigue', q === 'bidón' && n > 0, `búsqueda «${q}» · ${n} resultados en Objetos`]];
  });
  await R26('UX-08 + Tab', async p => {
    await p.focus('#map'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    const a = await p.evaluate(() => document.activeElement && document.activeElement.id);
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const b = await p.evaluate(() => document.activeElement && document.activeElement.id), props = await p.getAttribute('[data-act="rtab"][data-v="props"]', 'aria-selected', { timeout: 1000 }).catch(() => null);
    return [['UX-08 + Tab con el mapa activo abre Añadir y Esc vuelve al mapa', a === 'libq' && b === 'map' && props === 'true', `Tab → #${a || 'nada'} · Esc → #${b || 'nada'} · Propiedades a la vista: ${props}`]];
  });
  await R26('UX-08 −', async p => {
    await p.click('[data-act="rtab"][data-v="add"]'); await p.click('[data-act="lib-cat"][data-v="actor"]'); await p.waitForTimeout(100);
    // una fila al tope dice que no se puede añadir: con disabled, o desde AR4-05 con aria-disabled, para que siga enfocable y con su vista previa
    const n = await p.locator('#colR .item').count(), off = await p.locator('#colR .item[disabled], #colR .item[aria-disabled="true"]').count(), tot = await T(p, '#colR .btotal');
    return [['UX-08 − al tope no se puede añadir, y el total sin certificar no se presenta como ilimitado', n > 0 && off === n && /Tope total aún sin certificar/.test(tot) && !/ilimitad|sin tope|∞/i.test(tot), `${off} de ${n} actores sin poder añadir · «${tot}»`]];
  });

  // --- UX-09: mapa. Lo que se mira es lo pintado (la sonda), no los contadores de la página (AR-04) ---
  await R26('UX-09 +', async p => {
    const labels = async () => (await frame(p)).texts.map(t => t.text);
    await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(250);
    const own = (await labels()).filter(t => /Mirek/.test(t));
    const h0 = await p.evaluate(() => location.hash); await p.click('#bLegend'); await p.waitForTimeout(150);
    const leg = await p.locator('#legend').isVisible(), h1 = await p.evaluate(() => location.hash);
    let towns = [];
    for (let i = 0; i < 10 && !towns.length; i++) { await p.click('#bZout'); await p.waitForTimeout(150); towns = (await labels()).filter(t => TOWN.test(t)); }
    const caps = towns.filter(t => t === t.toUpperCase());
    return [['UX-09 + con Mirek seleccionado sus marcas dicen «Mirek · M1», la leyenda se abre sin salir del estudio y ningún pueblo va en mayúsculas', own.includes('Mirek · M1') && leg && h0 === h1 && towns.length > 0 && !caps.length, `marcas: ${own.join(', ') || 'ninguna'} · leyenda ${leg ? 'abierta' : 'cerrada'} (${h0 || '#'} → ${h1 || '#'}) · pueblos: ${towns.slice(0, 3).join(', ') || 'ninguno'}`]];
  });
  // la entidad cambiada se busca por su icono en la Jerarquía, se encuadra con F y se mira el glifo pintado en el centro del mapa
  const changedId = p => p.evaluate(() => { const r = [...document.querySelectorAll('#colL .row[data-v^="ent:"]')].find(r => r.querySelector('.st svg')); return r ? r.dataset.v : null; });
  const glyphAt = async (p, id) => {
    await p.click(`#colL [data-v="${id}"]`); await p.focus('#map'); await p.keyboard.press('f'); await p.waitForTimeout(250);
    const f = await frame(p), c = await p.evaluate(() => { const m = document.querySelector('#map'); return [m.clientWidth / 2, m.clientHeight / 2]; });
    // los rellenos con interior: el del icono de un objeto no cuenta como otro marcador (UX-48)
    const near = s => Math.abs(s.x - c[0]) <= 3 && Math.abs(s.y - c[1]) <= 3, g = f.strokes.filter(near), fl = f.fills.filter(x => near(x) && x.stripes), d = g.find(s => s.gaps);
    return { nominal: g.filter(s => s.dash).length, dashed: g.filter(s => s.dash && GAPS(s.gaps)).length, solid: g.filter(s => !s.dash && s.lw >= 3).length, filled: fl.filter(x => SOLID(x.solid)).length, fl,
      see: `${d ? `contorno en ${d.gaps.comps} trozos, ${d.gaps.gapPx} px de hueco a ${d.gaps.ratio}:1 de los guiones` : 'sin contorno discontinuo'}, interior ${fl.map(x => x.solid ? `${Math.round(x.solid.share * 100)} % del relleno${x.icon ? ` en el ${Math.round(x.solid.left * 100)} % que deja el icono` : ''}` : '?').join('/') || 'no visto'}` };
  };
  await R26('UX-09 −', async p => {
    const what = 'UX-09 − lo que está sin aplicar se pinta como documento (contorno discontinuo, con huecos que se ven) y pasa a sólido (relleno opaco) solo tras aplicar y leer';
    const id = await changedId(p);
    if (!id) return [[what, false, 'ninguna entidad cambiada en la Jerarquía']];
    const a = await glyphAt(p, id);
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const b = await glyphAt(p, id);
    return [[what, a.dashed > 0 && !a.solid && !a.filled && !b.nominal && b.solid > 0 && b.filled > 0, `${id.slice(4)} con un cambio: ${a.dashed} de ${a.nominal} contornos discontinuos con huecos que se ven y ${a.solid} sólidos (${a.see}) · aplicada y leída: ${b.nominal} discontinuos y ${b.solid} sólidos (${b.see})`]];
  });

  // --- UX-10: sistema visual ---
  await R26('UX-10 +', async p => {
    const m = await p.evaluate(() => __r26.metrics());
    return [['UX-10 + como mucho un 15 % del texto visible por debajo de 12 px', m.small <= m.n * 0.15, `${m.small} de ${m.n} textos por debajo de 12 px`]];
  });
  await R26('UX-10 −', async p => {
    const out = []; let bad = 0;
    const look = async n => { const m = await p.evaluate(() => __r26.metrics()); bad += m.small; out.push(`${n} ${m.small}${m.small ? ' (' + m.smallEj.join(' | ') + ')' : ''}`); };
    await look('escena'); await dock(p); await look('actividad');
    await p.click('[data-act="dtab"][data-v="historial"]'); await look('historial');
    await p.click('[data-act="dtab"][data-v="validacion"]'); await look('validación');
    await p.click('[data-act="rtab"][data-v="add"]'); await look('añadir'); await p.click('[data-act="rtab"][data-v="props"]');
    await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(150); await look('actor');
    await p.keyboard.press('2'); await p.waitForTimeout(300); await look('rodaje');
    await p.click('#colL [data-act="sel"][data-v="cam:cam-travel"]'); await p.waitForTimeout(150); await look('cámara');
    const green = await p.locator('#colR .chip.observado').count();
    await p.click('[data-act="ltab"][data-v="tomas"]'); await p.waitForTimeout(150); await look('tomas');
    const f = await frame(p), tiny = f.texts.filter(t => t.px < 12);
    return [['UX-10 − ningún texto de uso baja de 12 px en Escena, Rodaje y sus paneles, Tomas incluida (AR-05)', bad === 0, out.join(' · ')], ['UX-10 − la cámara elegida no lleva el verde de lo leído en el juego', green === 0, `${green} marcas verdes en sus propiedades`],
      ['UX-10 − ningún texto pintado en el mapa baja de 12 px', f.texts.length > 0 && !tiny.length, `${f.texts.length} textos en el mapa, ${tiny.length} por debajo de 12 px${tiny.length ? ': ' + tiny.slice(0, 3).map(t => `«${t.text}» ${t.px} px`).join(', ') : ''}`]];
  });

  // --- UX-11: Rodaje ---
  await R26('UX-11', async p => {
    const res = [];
    if (!await apply(p)) return [['UX-11 + «Previsualizar» mueve la cámara del mapa', false, 'no llegó a aplicar']];
    await p.keyboard.press('2'); await p.waitForTimeout(300);
    const btn = await T(p, '[data-act="tl-play"]'), t0 = await T(p, '#tlTime');
    await p.click('[data-act="tl-play"]'); await p.waitForTimeout(900);
    const t1 = await T(p, '#tlTime'), st = await T(p, '.takebar .tstate');
    const rolls = await p.locator('[data-act="take-roll"]:not([disabled])').count(), rec = await p.locator('#recBadge').isVisible(), stop = await p.locator('#bTopStop').isVisible();
    res.push(['UX-11 + «Previsualizar» mueve la cámara del mapa y la toma sigue lista para preparar', btn === 'Previsualizar' && t1 !== t0 && /Lista para preparar/.test(st), `botón «${btn}» · ${t0} → ${t1} · toma «${st}»`]);
    res.push(['UX-11 − previsualizar no arma ni rueda', !rolls && !rec && !stop, `Rodar libre: ${rolls} · insignia: ${rec} · Parar o Desarmar: ${stop}`]);
    await p.click('[data-act="tl-play"]');
    const armed = await arm(p), rolling = armed && await roll(p); await p.waitForTimeout(300);
    const n = await p.evaluate(() => [...document.querySelectorAll('button')].filter(b => __r26.shown(b) && /^\s*Parar\b/.test(b.innerText)).length);
    res.push(['UX-11 + rodando hay un solo Parar a la vista', rolling && n === 1, `${n} botones Parar`]);
    await p.keyboard.press('Escape'); await shows(p, '#slateWrap', /Reaplicar y preparar la/, 3000);
    await sim(p, 'director'); await p.click('[data-act="take-reapply"]');
    const named = await shows(p, '.takebar', /Falla «Tu juego conectado»/, 12000);
    const fix = await p.evaluate(() => { const b = document.querySelector('.takebar .tact .btn.primary'); return b && __r26.shown(b) ? b.innerText.replace(/\s+/g, ' ').trim() : ''; });
    res.push(['UX-11 + con una comprobación fallida, la cabecera de toma la nombra y ofrece el arreglo', named && !!fix, `«${(await T(p, '.takebar')).slice(0, 120)}» · arreglo «${fix}»`]);
    const rollBtn = await p.locator('[data-act="take-roll"]:not([disabled])').count();
    await p.locator('#map').hover(); await p.keyboard.press('Enter'); await p.waitForTimeout(600);
    const rec2 = await p.locator('#recBadge').isVisible();
    res.push(['UX-11 − una comprobación que falta impide rodar', !rollBtn && !rec2, `Rodar libre: ${rollBtn} · rueda con Intro: ${rec2}`]);
    return res;
  });

  // --- UX-12 y UX-13: los fallos y la edad de la lectura ---
  await R26('UX-12 y UX-13', async p => {
    const row = () => T(p, '#dock .qrow');
    await dock(p);
    await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    if (!await shows(p, '#dock .qrow', /Creando por lotes/, 6000)) return [['UX-12 + los tres fallos del simulador', false, 'no llegó a «Creando por lotes»']];
    await sim(p, 'server'); await shows(p, '#dock .qrow', /Falta confirmar el resultado/, 3000);
    const lost = await row();
    await p.waitForTimeout(1200); await sim(p, 'server');
    const recon = await shows(p, '#dock .qrow', /Reconciliada tras el corte/, 9000), ra = await T(p, '#dock .qrow .age');
    await free(p);
    // el acuse sin lectura: la orden pasa por Aplicado antes de leer el mundo
    await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    const ack = await p.waitForFunction(() => { const q = [...document.querySelectorAll('#dock .qrow')].find(r => r.querySelector('.chip.aplicado')); return q ? (q.querySelector('.age') || q).innerText : false; }, null, { polling: 'raf', timeout: 12000 }).then(h => h.jsonValue(), () => '');
    await free(p);
    await sim(p, 'fault'); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    await shows(p, '#dock .qrow', /Falló al crear/, 12000); const fault = await row();
    await free(p);
    await sim(p, 'server'); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    await shows(p, '#dock .qrow', /No se entregó/, 14000); const undelivered = await row();
    await sim(p, 'server');
    const L = /Falta confirmar el resultado: se cortó la conexión[\s\S]*Puede que[\s\S]*no se da por hecha ni por fallida[\s\S]*Al volver la conexión se comprueba sola/.test(lost);
    const F = /Falló al crear la entidad 28 de \d+, un «[^»]+»[\s\S]*Se borró todo lo que había creado esta orden: en el juego no queda nada de la escena\. Revisa la causa y vuelve a aplicar\./.test(fault);
    const N = /No se entregó: el servidor no pidió órdenes en 10 s y la orden caducó\. En el juego no ha cambiado nada\. Cuando vuelva la conexión, vuelve a pedirla\./.test(undelivered);
    const secs = re => { const m = ra.match(re); return m ? +m[1] * { s: 1, min: 60, h: 3600 }[m[2]] : null; };
    const A = secs(/Pedida hace (\d+) (s|min|h)/), B = secs(/Leída hace (\d+) (s|min|h)/);
    return [
      ['UX-12 + los tres fallos del simulador dicen qué pasó, qué queda en el juego y qué hacer', L && F && N, `respuesta perdida: ${L} · fallo a mitad: ${F} · sin entregar: ${N}`],
      ['UX-12 − un Parcial por respuesta perdida no ofrece «Reintentar» ni dice que no ocurrió', /Parcial/.test(lost) && !/Reintentar|no ocurri/i.test(lost), `«${lost.slice(0, 150)}»`],
      ['UX-13 + reconciliada tras un corte, la lectura es más nueva que la petición', recon && A !== null && B !== null && B < A, `«${ra}»`],
      ['UX-13 − un acuse sin lectura dice «Sin lectura», nunca «hace 0 s»', /Sin lectura/.test(ack) && !/Leída hace/.test(ack), ack ? `«${ack.replace(/\s+/g, ' ')}»` : 'no se vio la orden en Aplicado'],
    ];
  });

  // --- UX-14: textos y avisos ---
  await R26('UX-14', async p => {
    const res = [], bad = /\b1 gestos\b|Resetear|\btake\b|scene_apply/, seen = [];
    const look = async n => { const t = await p.evaluate(() => __r26.texts(document.querySelector('#app'))), m = t.match(bad); if (m) seen.push(`${n}: «${m[0]}»`); };
    await look('escena'); await dock(p); await look('actividad');
    await p.keyboard.press('2'); await p.waitForTimeout(300); await look('rodaje');
    await p.click('[data-act="rdtab"][data-v="actividad"]'); await look('actividad de rodaje');
    res.push(['UX-14 + ningún texto a la vista con «1 gestos», «Resetear», take o scene_apply', !seen.length, seen.join(' · ') || 'ninguno en Escena, Rodaje y sus actividades']);
    const geo = sel => p.evaluate(s => {
      const ts = [...document.querySelectorAll('#toasts .toast')].filter(__r26.shown), mw = document.querySelector('#mapwrap').getBoundingClientRect(), o = document.querySelector(s), or = o && __r26.shown(o) ? o.getBoundingClientRect() : null;
      const hit = (a, b) => !!b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
      return { n: ts.length, inMap: ts.every(t => { const r = t.getBoundingClientRect(); return r.left >= mw.left && r.right <= mw.right && r.top >= mw.top && r.bottom <= mw.bottom; }), over: ts.some(t => hit(t.getBoundingClientRect(), or)), has: !!or };
    }, sel);
    await p.keyboard.press('1'); await p.waitForTimeout(300);
    await nudge(p); await p.keyboard.press('Control+z'); await p.keyboard.press('Control+y'); await p.waitForTimeout(200);
    const g1 = await geo('#colR .tabs');
    const what = 'UX-14 − los avisos salen de uno en uno dentro del mapa y no tapan Parar ni las pestañas de la derecha';
    if (!await apply(p) || !await arm(p)) return [...res, [what, false, 'no llegó a armar']];
    await p.locator('#map').hover(); await p.keyboard.press('Control+z'); await p.keyboard.press('Space'); await p.waitForTimeout(200);
    const g2 = await geo('#bTopStop');
    res.push([what, g1.n === 1 && g1.inMap && g1.has && !g1.over && g2.n === 1 && g2.inMap && g2.has && !g2.over, `Escena: ${g1.n} aviso, dentro del mapa ${g1.inMap}, sobre las pestañas ${g1.over} · armada: ${g2.n} aviso, dentro del mapa ${g2.inMap}, sobre Parar ${g2.over}`]);
    return res;
  });

  // --- UX-25: paleta de estudio y una sola acción principal ---
  await R26('UX-25 +', async p => {
    const c = await p.evaluate(() => { const bg = s => { const el = [...document.querySelectorAll(s)].find(__r26.shown); return el ? getComputedStyle(el).backgroundColor : null; }; return { chassis: getComputedStyle(document.body).backgroundColor, panel: bg('.panel'), field: bg('.search') || bg('.inp'), primary: bg('.btn.primary') }; });
    const rgb = (c.primary || '').match(/[\d.]+/g) || [], white = rgb.length >= 3 && rgb.slice(0, 3).every(v => +v > 225);
    return [['UX-25 + en oscuro, chasis, panel y campo tienen tres fondos distintos y el botón principal no es blanco', new Set([c.chassis, c.panel, c.field]).size === 3 && !!c.primary && !white, `chasis ${c.chassis} · panel ${c.panel} · campo ${c.field} · principal ${c.primary}`]];
  });
  await R26('UX-25 −', async p => {
    const out = []; let worst = 0;
    const look = async n => { const l = await p.evaluate(() => [...document.querySelectorAll('.btn.primary')].filter(__r26.shown).map(b => b.innerText.replace(/\s+/g, ' ').trim())); worst = Math.max(worst, l.length); out.push(`${n}: ${l.join(' + ') || 'ninguno'}`); };
    await look('escena con cambios');
    if (!await apply(p)) return [['UX-25 − nunca hay dos botones principales a la vista', false, 'no llegó a aplicar']];
    await look('aplicada');
    await nudge(p); await p.keyboard.press('2'); await p.waitForTimeout(300); await look('rodaje con cambios');
    await p.locator('#map').hover(); await p.keyboard.press('Control+z'); await p.waitForTimeout(200);
    await p.keyboard.press('Shift+F9'); await shows(p, '#bTopStop', /Desarmar/, 6000); await look('armada');
    const rolling = await roll(p); await p.waitForTimeout(300); await look('rodando');
    const red = await p.evaluate(() => { const b = document.querySelector('#bTopStop'), t = document.createElement('i'); t.style.background = 'var(--rec)'; document.body.appendChild(t); const want = getComputedStyle(t).backgroundColor; t.remove(); return [getComputedStyle(b).backgroundColor, want]; });
    await p.keyboard.press('Escape'); await shows(p, '#slateWrap', /Reaplicar y preparar la/, 3000); await look('parada');
    return [['UX-25 − nunca hay dos botones principales a la vista', worst <= 1, out.join(' · ')], ['UX-25 − rodando, Parar no pierde el rojo de grabar', rolling && red[0] === red[1], `${red[0]} frente a ${red[1]}`]];
  });

  // --- Segunda pasada (§2, DESPUÉS que no necesita el juego): UX-18, UX-33 y UX-15 ---
  // UX-18: ayuda breve junto al mapa según lo seleccionado, con la rejilla y las teclas de ahora
  await R26('UX-18 +', async p => {
    const res = [], hint = async () => (await p.locator('#hint').isVisible()) ? await T(p, '#hint') : '';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    const h1 = await hint();
    res.push(['UX-18 + con «Bidón azul» seleccionado, una línea junto al mapa dice cómo moverlo y girarlo con la rejilla de ahora y cómo borrarlo', /0,5 m/.test(h1) && /15°/.test(h1) && /Mayús/.test(h1) && /Supr/.test(h1), h1 || 'sin ayuda']);
    await p.click('#bGrid'); await p.waitForTimeout(120); await p.click('#menu [data-act="grid-step"][data-v="m:1"]'); await p.click('#status', { position: { x: 3, y: 3 } }); await p.waitForTimeout(150);
    const h2 = await hint();
    await p.click('#bTools'); await p.waitForTimeout(120); await p.click('#menu [data-act="keys"]'); await p.waitForTimeout(120);
    await p.click('[data-act="key-set"][data-v="del"]'); await p.keyboard.press('x'); await p.waitForTimeout(100);
    await p.click('[data-act="dlg-close"]'); await p.waitForTimeout(150);
    const h3 = await hint();
    res.push(['UX-18 + la línea sigue a la rejilla (1 m) y a la tecla de borrar reasignada (X)', /(^|[^,\d])1 m/.test(h2) && /\bX\b/.test(h3) && !/Supr/.test(h3), `rejilla de 1 m: ${h2 || 'sin ayuda'} · Borrar con X: ${h3 || 'sin ayuda'}`]);
    return res;
  });
  await R26('UX-18 −', async p => {
    const vis = () => p.locator('#hint').isVisible(), edit = /Mayús|arrastra/i;
    const none = !await vis();
    // la escena está al tope de objetos: se borra uno para poder colocar, como en pruebas.js
    await p.click('#colL [data-act="sel"][data-v="ent:obj-20"]'); await p.keyboard.press('Delete'); await p.waitForTimeout(150);
    await p.click('[data-act="rtab"][data-v="add"]'); await p.click('[data-act="lib-item"]:enabled'); await p.waitForTimeout(150);
    const placing = await T(p, '#hint');
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const what = 'UX-18 − sin selección no hay línea, colocando manda la ayuda de colocar y con la toma armada no hay ayuda de edición';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]', { timeout: 1000 }).catch(() => {}); await p.waitForTimeout(150);
    const armed = (await vis()) ? await T(p, '#hint') : '';
    return [[what, none && /Colocando/.test(placing) && !/Mayús/.test(placing) && !edit.test(armed), `sin selección: ${none ? 'nada' : 'hay ayuda'} · colocando: ${placing || 'nada'} · armada: ${armed || 'nada'}`]];
  });

  // UX-33: barra de estado por zonas, con las coordenadas del cursor y el pueblo más cercano
  const TOWNS = [['Chernogorsk', 6700, 2500], ['Elektrozavodsk', 10300, 2250], ['Berezino', 12350, 9550], ['Solnichniy', 13350, 6200], ['Kamyshovo', 12050, 3500], ['Zelenogorsk', 2750, 5250], ['Stary Sobor', 6060, 7760], ['Novy Sobor', 7100, 7700], ['Vybor', 3800, 8900], ['Gorka', 9500, 8900], ['Balota', 4400, 2400], ['Komarovo', 3600, 2400], ['Kabanino', 5300, 8600], ['Prigorodki', 7900, 3200], ['Svetlojarsk', 13900, 13200], ['Krasnostav', 11200, 12300], ['Severograd', 8100, 12700], ['Novodmitrovsk', 11500, 14500], ['Lopatino', 2750, 9900], ['Pustoshka', 3000, 7900]];
  const num = s => parseFloat(s.replace(/[\s.]/g, '').replace(',', '.'));
  await R26('UX-33 +', async p => {
    const b = await p.locator('#map').boundingBox(); await p.mouse.move(b.x + b.width * 0.5, b.y + b.height * 0.5); await p.mouse.move(b.x + b.width * 0.52, b.y + b.height * 0.48); await p.waitForTimeout(150);
    const st = await T(p, '#status'), inMap = await p.evaluate(() => __r26.texts(document.querySelector('#mapwrap')));
    const m = st.match(/X ([\d\s.,]+?) · Z ([\d\s.,]+?)(?: ·|$|\s{2}|[A-Za-zÁÉÍÓÚáéíóú])/);
    let near = '';
    if (m) { const x = num(m[1]), z = num(m[2]); near = TOWNS.map(t => [t[0], Math.hypot(t[1] - x, t[2] - z)]).sort((a, c) => a[1] - c[1])[0][0]; }
    const dist = near && new RegExp(near + '[^\\d]{0,4}[\\d.,]+\\s?(m|km)').test(st);
    return [['UX-33 + con el cursor sobre el mapa, la barra de estado dice X y Z y el pueblo más cercano con su distancia, y el mapa ya no lleva las coordenadas', !!m && dist && !/X [\d.,]+ · Z/.test(inMap), `barra: ${st.slice(0, 160)} · más cerca: ${near || '?'} · coordenadas dentro del mapa: ${/X [\d.,]+ · Z/.test(inMap)}`]];
  });
  await R26('UX-33 −', async p => {
    const b = await p.locator('#map').boundingBox(); await p.mouse.move(b.x + b.width * 0.5, b.y + b.height * 0.5); await p.waitForTimeout(100);
    await p.mouse.move(b.x + b.width * 0.5, b.y - 40); await p.waitForTimeout(150);
    const st = await T(p, '#status'), town = TOWNS.find(t => st.includes(t[0]));
    return [['UX-33 − con el cursor fuera del mapa, la barra dice «X — · Z —» y ningún pueblo', /X — · Z —/.test(st) && !town, `barra: ${st.slice(0, 160)}`]];
  });
  // UX-33: las zonas de la barra no se pisan ni se salen del borde, con el cursor en cualquier punto del mapa; «MCP apagado» se ve entero (CU-35).
  // Y no se mueven al pasar el cursor: se mide dónde empieza cada zona respecto de las coordenadas, para que la edad de las luces no cuente.
  const zones = p => p.evaluate(() => {
    const st = document.querySelector('#status'), sr = st.getBoundingClientRect(), cs = getComputedStyle(st);
    const lo = sr.left + parseFloat(cs.paddingLeft) - 0.5, hi = sr.right - parseFloat(cs.paddingRight) + 0.5;
    const els = [...st.children, ...document.querySelector('#stInfo').children].filter(e => e.id !== 'stInfo' && !e.classList.contains('ssep') && !e.classList.contains('grow') && e.getClientRects().length && e.textContent.trim());
    const z = els.map(e => { const r = document.createRange(); r.selectNodeContents(e); const q = r.getBoundingClientRect(); return { t: e.textContent.replace(/\s+/g, ' ').trim().slice(0, 24), l: q.left, r: q.right, y: q.top + q.height / 2 }; });
    const bad = z.filter(a => a.l < lo || a.r > hi).map(a => `«${a.t}» se sale`);
    z.forEach(a => z.forEach(b => { if (a !== b && Math.abs(a.y - b.y) < 6 && b.l >= a.l && b.l - a.r < 6) bad.push(`«${a.t}» y «${b.t}» a ${Math.round(b.l - a.r)} px`); }));
    const m = z.find(a => /MCP apagado/.test(a.t)), x0 = document.querySelector('#cursorXY').getBoundingClientRect().left, pos = {};
    els.forEach(e => { pos[e.id || e.parentElement.id + ':' + [...e.parentElement.children].indexOf(e)] = [e.textContent.replace(/\s+/g, ' ').trim().slice(0, 24), e.getBoundingClientRect().left - x0]; });
    return { bad, h: Math.round(sr.height), mcp: !!m && m.r <= hi, pos };
  });
  const sweep = async p => {
    const b = await p.locator('#map').boundingBox(), bad = new Set(), hs = new Set(), span = {}; let mcp = true;
    for (let i = 0; i < 6; i++) for (let j = 0; j < 4; j++) {
      await p.mouse.move(b.x + b.width * (0.05 + i * 0.18), b.y + b.height * (0.08 + j * 0.28)); await p.waitForTimeout(25);
      const r = await zones(p); r.bad.forEach(x => bad.add(x)); hs.add(r.h); mcp = mcp && r.mcp;
      Object.entries(r.pos).forEach(([k, [t, x]]) => { const o = span[k] || (span[k] = { t, lo: x, hi: x }); o.lo = Math.min(o.lo, x); o.hi = Math.max(o.hi, x); });
    }
    const moved = Object.values(span).filter(o => o.hi - o.lo > 1).map(o => `«${o.t}» se mueve ${Math.round(o.hi - o.lo)} px`);
    return { bad: [...bad], hs: [...hs], mcp, moved };
  };
  await R26('UX-33 + barra', async p => {
    const out = []; let ok = true;
    for (const [w, h] of [[1280, 800], [1366, 768]]) {
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(200);
      const r = await sweep(p); ok = ok && !r.bad.length && !r.moved.length && r.mcp && r.hs.length === 1 && r.hs[0] <= 30;
      out.push(`${w} px: alto ${r.hs.join('/')} px · ${r.bad.length ? r.bad.slice(0, 3).join(' · ') : 'nada se pisa'} · ${r.moved.length ? r.moved.slice(0, 3).join(' · ') : 'nada se mueve'} · MCP apagado ${r.mcp ? 'entero' : 'cortado'}`);
    }
    return [['UX-33 + a 1280 × 800 y 1366 × 768, con el cursor en 24 puntos del mapa, la barra de estado es una línea que no cambia de alto, sus zonas no se pisan ni se mueven y «MCP apagado» se ve entero', ok, out.join(' · ')]];
  }, 1280, 800);
  await R26('UX-33 − barra', async p => {
    const out = []; let ok = true;
    for (const [w, h, off] of [[1024, 768], [1280, 800, true]]) {
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(200);
      if (off) await sim(p, 'backend');
      const r = await sweep(p); ok = ok && !r.bad.length && r.mcp;
      out.push(`${w} px${off ? ' sin backend' : ''}: alto ${r.hs.join('/')} px · ${r.bad.length ? r.bad.slice(0, 3).join(' · ') : 'nada se pisa'} · MCP apagado ${r.mcp ? 'entero' : 'cortado'}`);
    }
    return [['UX-33 − a 1024 × 768, y a 1280 × 800 sin backend, la barra pasa a dos líneas antes que pisar sus zonas o sacar «MCP apagado» del borde', ok, out.join(' · ')]];
  }, 1024, 768);

  // UX-15: empezar desde una escena vacía; la Guía empieza por el recorrido
  const sceneMenu = async (p, act) => { await p.click('#docBtn'); await p.waitForTimeout(150); await p.click(`#menu [data-act="${act}"]`); await p.waitForTimeout(200); };
  await R26('UX-15 + escenas', async p => {
    const res = [];
    await sceneMenu(p, 'm-new');
    const head = await T(p, '#docBtn'), left = await T(p, '#colL'), title = await p.getAttribute('#bApply', 'title');
    const cta = p.locator('#colL [data-act="first-add"]');
    const hasCta = await cta.count() && /Añade tu primer objeto/.test(await cta.first().innerText());
    if (hasCta) { await cta.first().click(); await p.waitForTimeout(150); }
    const addOpen = await p.evaluate(() => { const t = document.querySelector('[data-act="rtab"][data-v="add"]'); return !!t && t.getAttribute('aria-selected') === 'true' && !!document.querySelector('#libq'); });
    res.push(['UX-15 + «Nueva escena» abre una escena vacía que invita con «Añade tu primer objeto» (abre Añadir), y la cabecera y la ayuda de Aplicar nombran la escena que sigue en el juego', /Escena sin título/.test(head) && /otra escena/i.test(head) && /vacía/i.test(left) && hasCta && addOpen && /Amanecer en Stary Sobor/.test(title || ''), `cabecera: ${head} · Jerarquía: ${left.slice(0, 90)} · Añadir abierto: ${addOpen} · Aplicar: ${title}`]);
    await p.click('#docBtn'); await p.waitForTimeout(150); await p.click('#menu [data-act="m-open"]'); await p.waitForTimeout(200);
    const list = await T(p, '#menu');
    const back = p.locator('#menu [data-act="doc-open"]', { hasText: 'Amanecer en Stary Sobor' });
    if (await back.count()) { await back.first().click(); await p.waitForTimeout(250); }
    const head2 = await T(p, '#docBtn'), sub = await T(p, '#colL .ph .sub');
    res.push(['UX-15 + «Abrir…» lista las dos escenas, y volver a «Amanecer en Stary Sobor» la trae con sus 35 entidades y sus 2 cambios sin aplicar', /Escena sin título/.test(list) && /Amanecer en Stary Sobor/.test(list) && /Amanecer en Stary Sobor/.test(head2) && /2 cambios sin aplicar/.test(head2) && /35 entidades/.test(sub), `lista: ${list.slice(0, 120)} · cabecera: ${head2} · ${sub}`]);
    return res;
  });
  await R26('UX-15 + Guía', async p => {
    await p.click('#bGuide'); await p.waitForTimeout(400);
    const g = await p.evaluate(() => {
      const hs = [...document.querySelectorAll('#guide h2')].map(h => h.textContent.trim());
      const first = document.querySelector('#guide h2'), steps = first ? [...(first.nextElementSibling ? first.nextElementSibling.querySelectorAll('li') : [])].map(li => li.textContent.replace(/\s+/g, ' ').trim()) : [];
      const t = document.querySelector('#refTable'); let h = t, sec = '';
      while (h && !sec) { h = h.previousElementSibling || (h.parentElement && h.parentElement.id !== 'guide' ? h.parentElement : null); if (h && h.tagName === 'H2') sec = h.textContent.trim(); }
      return { hs, steps, sec };
    });
    const order = [/Crea/i, /Aplica/i, /cámara/i, /Prepara/i, /Rueda/i, /Para/i], ok = g.steps.length === 6 && order.every((re, i) => re.test(g.steps[i]));
    return [['UX-15 + la Guía empieza por el recorrido en seis pasos (crear, aplicar, cámara, preparar, rodar y parar), y los referentes van en «Acerca del diseño»', /Recorrido/i.test(g.hs[0] || '') && ok && /Acerca del diseño/.test(g.sec), `primera sección: ${g.hs[0]} · pasos: ${g.steps.map(s => s.slice(0, 18)).join(' | ')} · la tabla de referentes va en: ${g.sec || '?'}`]];
  });
  await R26('UX-15 −', async p => {
    const res = [], orders = () => p.evaluate(() => [...document.querySelectorAll('#dock .qrow')].map(r => r.title.split(' · ')[0]).join(','));
    await dock(p); const before = await orders();
    await sceneMenu(p, 'm-new'); await sceneMenu(p, 'm-open');
    const back = p.locator('#menu [data-act="doc-open"]', { hasText: 'Amanecer en Stary Sobor' }); if (await back.count()) { await back.first().click(); await p.waitForTimeout(250); } else await p.keyboard.press('Escape');
    await dock(p); const after = await orders(), head = await T(p, '#docBtn');
    res.push(['UX-15 − crear y abrir escenas no toca el juego: ninguna orden nueva en Actividad y la escena del juego no cambia hasta aplicar', !!before && before === after && /2 cambios sin aplicar/.test(head), `órdenes antes ${before.split(',').length} y después ${after.split(',').length} · cabecera: ${head}`]);
    const what = 'UX-15 − con la toma armada no se crea ni se abre otra escena';
    if (!await apply(p) || !await arm(p)) return [...res, [what, false, 'no llegó a armar']];
    await p.click('#docBtn', { timeout: 1000 }).catch(() => {}); await p.waitForTimeout(150);
    const nb = p.locator('#menu [data-act="m-new"]'), can = (await nb.count()) && await nb.isVisible() && await nb.isEnabled();
    if (can) { await nb.click(); await p.waitForTimeout(200); }
    const head2 = await T(p, '#docBtn'), still = await shows(p, '#bTopStop', /Desarmar/, 500);
    res.push([what, !can && /Amanecer en Stary Sobor/.test(head2) && still, `Nueva escena disponible: ${!!can} · cabecera: ${head2} · sigue armada: ${still}`]);
    return res;
  });

  // --- Arreglos de la revisión de Astra (AR-01 a AR-07) ---
  const rows = p => p.evaluate(() => [...document.querySelectorAll('#dock .qrow')].length);
  const exposed = p => p.evaluate(() => { const b = document.querySelector('#bTopStop'); if (!b || b.hidden) return false; const r = b.getBoundingClientRect(), el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!el && (el === b || b.contains(el)); });
  await R26('AR-01 +', async p => {
    const what = 'AR-01 + tras cortar Tu juego rodando, ni la Guía ni los Atajos tapan «Parada sin confirmar» y no se reaplica, prepara ni aplica hasta leer el juego; al volver la conexión, la lectura la confirma y deja seguir';
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600); await sim(p, 'director');
    if (!await shows(p, '#bTopStop', /Parada sin confirmar/, 3000)) return [[what, false, 'no salió «Parada sin confirmar»']];
    await dock(p); const n0 = await rows(p);
    await p.evaluate(() => { document.querySelector('#bGuide').click(); }); await p.waitForTimeout(200);
    await p.evaluate(() => { location.hash = 'guia'; }); await p.waitForTimeout(300);
    const guide = await p.locator('#guide').isVisible(), stop1 = await exposed(p);
    // si se abrió (el defecto), se cierra para seguir: la prueba falla por lo que mide, no por un clic tapado
    await p.evaluate(() => { if (location.hash === '#guia') location.hash = 'rodaje'; }); await p.waitForTimeout(200);
    await p.click('#bTools'); await p.waitForTimeout(120); await p.evaluate(() => { const b = document.querySelector('#menu [data-act="keys"]'); if (b) b.click(); }); await p.waitForTimeout(150);
    const keys = await p.locator('#scrim').isVisible();
    if (keys) await p.click('[data-act="dlg-close"]'); else await p.click('#status', { position: { x: 3, y: 3 } });
    const re = p.locator('[data-act="take-reapply"]'), reOff = (await re.count()) > 0 && await re.isDisabled();
    await p.evaluate(() => { const b = document.querySelector('[data-act="take-reapply"]'); if (b) b.click(); });
    await p.locator('#map').hover(); await p.keyboard.press('Shift+F9'); await p.keyboard.press('Control+Enter'); await p.waitForTimeout(400);
    const n1 = await rows(p), stop2 = await exposed(p) && /Parada sin confirmar/.test(await T(p, '#bTopStop'));
    await sim(p, 'director');
    const ok = await W(p, () => document.querySelector('#bTopStop').hidden, null, 4000), reOn = ok && await re.isEnabled();
    const res = [[what, !guide && !keys && stop1 && stop2 && reOff && n1 === n0 && ok && reOn, `Guía ${guide ? 'abierta' : 'cerrada'} · Atajos ${keys ? 'abiertos' : 'cerrados'} · Parar a la vista ${stop1 && stop2} · Reaplicar ${reOff ? 'apagado' : 'libre'} · órdenes nuevas sin lectura: ${n1 - n0} · confirmada al volver: ${ok} · después Reaplicar ${reOn ? 'libre' : 'apagado'}`]];
    await p.click('[data-act="ltab"][data-v="tomas"]'); await p.waitForTimeout(150);
    const m = await p.evaluate(() => __r26.metrics()), tk = await T(p, '#colL .take');
    res.push(['AR-05 + en Tomas, la toma cortada y su causa se leen a 12 px o más', m.small === 0 && /Fallida/.test(tk), `${m.small} textos por debajo de 12 px · «${tk.slice(0, 110)}»`]);
    return res;
  });
  await R26('AR-01 −', async p => {
    const what = 'AR-01 − un corte con un menú abierto no tapa «Parada sin confirmar», y ni el menú ni Esc la dan por confirmada sin lectura';
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600); await p.click('#bSim'); await p.waitForTimeout(120); await p.click('#menu [data-act="sim"][data-v="director"]');
    const unc = await shows(p, '#bTopStop', /Parada sin confirmar/, 3000), menu = await p.locator('#menu').isVisible(), stop1 = await exposed(p);
    await p.keyboard.press('Escape'); await p.waitForTimeout(300);
    const still = /Parada sin confirmar/.test(await T(p, '#bTopStop')) && await exposed(p), back = /Control devuelto|Parada confirmada/.test(await p.evaluate(() => __r26.texts(document.querySelector('#app'))));
    return [[what, unc && menu && stop1 && still && !back, `con el menú abierto: «Parada sin confirmar» ${unc && stop1 ? 'a la vista' : 'tapada o ausente'} · tras Esc: ${still ? 'sigue' : 'desaparece'} · «Control devuelto» o «confirmada» sin lectura: ${back}`]];
  });
  await R26('AR-02 +', async p => {
    const what = 'AR-02 + mientras se aplica, la Jerarquía dice que aún no hay lectura, y no «Nada en el juego»; aplicada y leída, dice qué hay y su edad; quitada del juego y confirmada, dice «Nada en el juego»';
    await dock(p); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    const mid = (await shows(p, '#dock .qrow', /Creando por lotes/, 6000)) ? await T(p, '#colL .worldline') : '';
    if (!await free(p)) return [[what, false, 'no terminó de aplicar']];
    const a = await T(p, '#colL .worldline');
    await p.click('#bReset'); await p.waitForTimeout(150); await p.click('#menu [data-act="reset-ok"]'); await free(p);
    const b = await T(p, '#colL .worldline'), h = await T(p, '#docBtn');
    return [[what, /sin lectura/i.test(mid) && !/Nada en el juego/.test(mid) && /En el juego, leída hace \d+/.test(a) && /Nada en el juego/.test(b) && /Nada en el juego/.test(h), `aplicando: «${mid || 'no se vio'}» · aplicada: «${a}» · quitada: «${b}» · cabecera: «${h}»`]];
  });
  await R26('AR-02 −', async p => {
    const what = 'AR-02 − con la conexión cortada a mitad de crear, ni la cabecera, ni la Jerarquía, ni Propiedades dicen «Nada en el juego» ni Observado; al volver se resuelve leyendo, sin repetir Aplicar';
    await dock(p); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    if (!await shows(p, '#dock .qrow', /Creando por lotes/, 6000)) return [[what, false, 'no llegó a «Creando por lotes»']];
    await sim(p, 'server'); await shows(p, '#dock .qrow', /Falta confirmar el resultado/, 3000);
    const h = await T(p, '#docBtn'), wl = await T(p, '#colL .worldline'), pr = await T(p, '#colR'), obs = await p.locator('#colL .worldline .st-observado').count();
    const n0 = await p.evaluate(() => [...document.querySelectorAll('#dock .qrow')].filter(r => /Aplicar escena/.test(r.innerText)).length);
    await sim(p, 'server');
    const recon = await shows(p, '#dock .qrow', /Reconciliada tras el corte/, 9000), wl2 = await T(p, '#colL .worldline');
    const n1 = await p.evaluate(() => [...document.querySelectorAll('#dock .qrow')].filter(r => /Aplicar escena/.test(r.innerText)).length);
    const none = [h, wl, pr].some(t => /Nada en el juego/.test(t));
    return [[what, !none && !obs && /Falta confirmar/.test(wl) && /Falta confirmar/.test(pr) && recon && /leída hace/.test(wl2) && n1 === n0, `cortada: cabecera «${h.slice(0, 60)}» · Jerarquía «${wl}» · Propiedades ${/Falta confirmar/.test(pr) ? 'dice que falta confirmar' : 'no lo dice'} · al volver: «${wl2}», ${n1 - n0} órdenes de aplicar nuevas`]];
  });
  // Inventario de lo que tiene que leerse en el mapa, sacado de fuera del dibujo (AR2-01). Dos lecturas del cursor en la barra de estado
  // dicen qué trozo del mundo se ve y a qué escala; de ahí salen los números de la rejilla que caen dentro, lejos del borde (con la regla de
  // sus pasos: el primero de 10, 25, 50, 100, 250, 500, 1000, 2500 y 5000 m que mida 70 px o más, en un mapa de 15 360 m) y, de lejos (a menos
  // de 1,2 px por metro), los pueblos de TOWNS que caen dentro. Más las etiquetas que pida cada vista.
  const inventory = async (p, names) => {
    const r = await p.locator('#map').boundingBox(), a = [r.x + r.width * 0.3, r.y + r.height * 0.35], b = [r.x + r.width * 0.7, r.y + r.height * 0.65];
    const read = async q => { await p.mouse.move(q[0], q[1]); await p.waitForTimeout(80); const m = (await T(p, '#cursorXY')).match(/X ([\d.,-]+) · Z ([\d.,-]+)/); return m ? [num(m[1]), num(m[2])] : null; };
    const wa = await read(a), wb = await read(b);
    if (!wa || !wb || wa[0] === wb[0] || wa[1] === wb[1]) return null;
    // lo que flota encima del mapa, en px del mapa: el número de la regla de Y que caería debajo no se pinta (UX-50)
    const fl = await p.evaluate(() => { const m = document.querySelector('#map').getBoundingClientRect(); return [...document.querySelectorAll('#mapwrap .ovl, #legend, #hint, #recBadge')].filter(__r26.shown).map(e => { const b = e.getBoundingClientRect(); return [b.left - m.left, b.top - m.top, b.right - m.left, b.bottom - m.top]; }); });
    const kx = (b[0] - a[0]) / (wb[0] - wa[0]), kz = (b[1] - a[1]) / (wb[1] - wa[1]), s = Math.abs(kx);
    const u = x => a[0] - r.x + (x - wa[0]) * kx, v = z => a[1] - r.y + (z - wa[1]) * kz, wx = q => wa[0] + (q + r.x - a[0]) / kx, wz = q => wa[1] + (q + r.y - a[1]) / kz;
    const sp = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000].find(m => m * s >= 70) || 5000, want = [...names];
    const [x0, x1] = [wx(0), wx(r.width)].sort((m, n) => m - n), [z0, z1] = [wz(0), wz(r.height)].sort((m, n) => m - n);
    for (let x = Math.ceil(x0 / sp) * sp; x <= x1; x += sp) if (x >= 0 && x <= 15360 && u(x) >= 6 && u(x) <= r.width - 56) want.push(String(x));
    for (let z = Math.ceil(z0 / sp) * sp; z <= z1; z += sp) if (z >= 0 && z <= 15360 && v(z) >= 36 && v(z) <= r.height - 6 && !fl.some(o => o[0] < 41 && o[2] > 1 && o[1] < v(z) && o[3] > v(z) - 14)) want.push(String(z));
    if (s < 1.2) TOWNS.forEach(([t, x, z]) => { if (u(x) >= 70 && u(x) <= r.width - 70 && v(z) >= 24 && v(z) <= r.height - 12) want.push(t); });
    return want;
  };
  // Una vista del mapa se lee si cada texto esperado está pintado, con su letra medida; si cada texto pintado llega a 4,5:1 en todos los
  // píxeles de su letra, al pintarlo y en el fotograma acabado (AR3-01), y si ninguna imagen con texto se queda sin medir. Sin textos, o sin
  // inventario, no pasa.
  const unmeasured = i => i.kind !== 'canvas' || !!i.unknown || (i.texts.length > 0 && !i.halo);
  const missing = (want, seen) => { const c = {}; seen.forEach(t => { c[t] = (c[t] || 0) + 1; }); return want.filter(t => c[t] > 0 ? (c[t]--, false) : true); };
  // Desde la cuarta revisión (AR4-01), además: los huecos de cada letra, menos en los pueblos, que van con el mapa y pueden quedar bajo un
  // marcador, siguen sin la tinta de la letra; y en pantalla, cada píxel de cada texto es el del lienzo (sin filtro, opacidad ni nada encima).
  // Y desde la quinta (AR5-01, AR5-02), cada texto pintado se ve en pantalla, y ahí se lee: no vale ninguno del que no se vea ningún píxel,
  // y desde la sexta (AR6-01), tampoco uno comparado a medias
  const composite = async p => {
    const b = await p.locator('#map').boundingBox(), png = await p.screenshot({ clip: { x: b.x, y: b.y, width: b.width, height: b.height } });
    return p.evaluate(u => window.__cv.composite(u), 'data:image/png;base64,' + png.toString('base64'));
  };
  const readable = async (p, names = []) => {
    const want = await inventory(p, names), f = await frame(p), cmp = await composite(p);
    f.texts.forEach((t, i) => { t.comp = cmp[i] || null; });
    const low = lowTexts(f), img = f.images.filter(unmeasured), fill = f.texts.filter(t => t.fin && t.fin.filled > 0 && !TOWN.test(t.text));
    const scr = f.texts.filter(t => t.n > 0 && (!t.comp || !t.comp.g || t.comp.diff > 0 || t.comp.moved > 0 || t.comp.low > 0 || t.comp.cut > 0 || (t.comp.filled > 0 && !TOWN.test(t.text))));
    const miss = want ? missing(want, f.texts.filter(t => t.n > 0).map(t => t.text)) : [];
    return { f, why: { miss, low, img, fill, scr }, ok: !!want && want.length > 0 && f.texts.length > 0 && !miss.length && !low.length && !img.length && !fill.length && !scr.length,
      info: `${f.texts.length} textos, ${want ? want.length : 'sin'} esperados${miss.length ? `, faltan ${miss.slice(0, 4).map(t => '«' + t + '»').join(', ')}` : ''}${low.length ? ', bajos ' + showLow(low) : ''}${img.length ? `, ${img.length} imágenes sin medir${img[0].texts.length ? ' con «' + img[0].texts.slice(0, 2).join('», «') + '»' : ''}${img[0].unknown ? ' de procedencia desconocida' : ''}` : ''}${fill.length ? ', rellenados ' + fill.slice(0, 3).map(t => `«${t.text}» ${t.fin.filled} de ${t.fin.holes} huecos`).join(', ') : ''}${scr.length ? ', sin acreditar en pantalla: ' + scr.slice(0, 3).map(t => !t.comp ? `«${t.text}» sin captura comparable` : !t.comp.g ? `«${t.text}» sin ningún píxel de su letra comparado` : t.comp.moved ? `«${t.text}» repintado antes de la captura (${t.comp.moved} px)` : t.comp.diff ? `«${t.text}» ${t.comp.diff} de ${t.comp.n} px distintos` : t.comp.low ? `«${t.text}» en pantalla ${t.comp.low} de ${t.comp.g} px bajos (${t.comp.min}:1)` : t.comp.cut ? `«${t.text}» comparado a medias, con ${t.comp.cut} px de su letra o de sus huecos sin comparar` : `«${t.text}» en pantalla ${t.comp.filled} huecos con tinta`).join(', ') : ''}` };
  };
  for (const scheme of ['dark', 'light']) {
    await R26(`AR-03 + ${scheme}`, async p => {
      const out = []; let ok = true;
      const look = async (n, names) => { const r = await readable(p, names); ok = ok && r.ok; out.push(`${n}: ${r.info}`); };
      // las etiquetas que siempre se pintan: los nombres de los actores, las marcas del actor elegido y, en Rodaje, las claves y la trayectoria de la cámara de la toma
      await look('inicio', ['Mirek', 'Linda']);
      await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(200); await look('Mirek', ['Mirek · M1', 'Mirek · M2', 'Mirek', 'Linda']);
      for (let i = 0; i < 4; i++) { await p.click('#bZout'); await p.waitForTimeout(120); } await look('alejado', ['Mirek · M1', 'Mirek', 'Linda']);
      await p.keyboard.press('Escape'); await p.keyboard.press('2'); await p.waitForTimeout(300);
      await look('Rodaje', ['Mirek', 'Linda', 'Travelling del autobús · K1', 'Travelling del autobús · K2', 'Travelling del autobús · K3', 'trayectoria prevista']);
      return [[`AR-03 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, a 1366 × 768, en cuatro vistas se pinta cada texto que se espera (los números de la rejilla y los pueblos que caen dentro, y las etiquetas de cada vista), cada texto pintado llega a 4,5:1 en todos los píxeles de su letra, y ningún texto va en una imagen sin medir (AR2-01)`, ok, out.join(' · ')]];
    }, 1366, 768, scheme);
  }
  await R26('AR-03 −', async p => {
    // la sonda no da por bueno lo que fallaba: el número pintado como antes (tinta translúcida sobre el gris de un edificio) sale por debajo de 4,5:1
    const r = await p.evaluate(() => { const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth; window.__cv.texts = []; window.__cv.on = true; g.save(); g.setTransform(d, 0, 0, d, 0, 0); g.fillStyle = 'rgb(88,83,74)'; g.fillRect(40, 40, 60, 20); g.font = '500 12px monospace'; g.fillStyle = 'rgba(25,25,15,.8)'; g.fillText('6150', 44, 54); g.fillStyle = 'rgb(88,83,74)'; g.fillRect(40, 66, 60, 20); g.lineWidth = 1; g.strokeStyle = 'rgba(25,25,15,.8)'; g.strokeText('6250', 44, 80); g.restore(); window.__cv.on = false; return window.__cv.texts; });
    const [f, s] = r || [], ok = t => !!t && t.n > 0 && t.min < 4.5 && t.low === t.n, see = t => t ? `«${t.text}» ${t.min}:1 en ${t.low} de ${t.n} px` : 'la sonda no lo vio';
    return [['AR-03 − la sonda detecta un número de la rejilla pintado como antes, sin placa, sobre un edificio, también si se pinta con strokeText', ok(f) && ok(s), `fillText ${see(f)} · strokeText ${see(s)}`]];
  });
  // «Ver» se busca por la fila de su error, que es igual en la versión de antes
  const ver = (p, code) => p.locator('#dock .vrow', { hasText: code }).locator('[data-act="val-go"]').first().click();
  await R26('AR-06 +', async p => {
    const what = 'AR-06 + con Añadir delante, «Ver» de un error de posición abre Propiedades con la entidad elegida y el campo X a la vista y con el foco, y el código y el puntero siguen en Validación';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.fill('#f-x', '-100'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    await dock(p); await p.click('[data-act="dtab"][data-v="validacion"]'); await p.click('[data-act="rtab"][data-v="add"]'); await p.waitForTimeout(150);
    await ver(p, 'out_of_map'); await p.waitForTimeout(250);
    const r = await p.evaluate(() => { const f = document.querySelector('#f-x'), t = document.querySelector('[data-act="rtab"][data-v="props"]'), s = document.querySelector('#colL [data-v="ent:obj-13"]'); return { props: !!t && t.getAttribute('aria-selected') === 'true', vis: !!f && __r26.vis(f), focus: document.activeElement === f, sel: !!s && s.getAttribute('aria-selected') === 'true', x: f ? f.value : null }; });
    const v = await T(p, '#dock');
    return [[what, r.props && r.vis && r.focus && r.sel && /out_of_map/.test(v) && /\/entities\/\d+/.test(v), `Propiedades ${r.props ? 'delante' : 'detrás'} · X ${r.vis ? 'a la vista' : 'oculto'}${r.focus ? ' y con el foco' : ''} · Bidón azul elegido: ${r.sel} · código y puntero: ${/out_of_map/.test(v)}`]];
  });
  await R26('AR-06 −', async p => {
    const what = 'AR-06 − «Ver» no cambia el documento, y en el error de una clave de cámara lleva a Rodaje con el campo del tiempo a la vista y con el foco';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.fill('#f-x', '-100'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    await p.keyboard.press('2'); await p.waitForTimeout(250); await p.click('#colL [data-act="sel"][data-v="cam:cam-travel"]'); await p.waitForTimeout(150);
    await p.evaluate(() => { const k = document.querySelectorAll('#colR [data-act="sel"][data-v^="key:cam-travel:"]'); if (k[1]) k[1].click(); }); await p.waitForTimeout(150);
    if (!await p.locator('#k-t').count()) return [[what, false, 'no se encontró el tiempo de la K2']];
    await p.fill('#k-t', '0'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    await p.keyboard.press('1'); await p.waitForTimeout(250); await dock(p); await p.click('[data-act="dtab"][data-v="validacion"]'); await p.waitForTimeout(100);
    const undo0 = await p.getAttribute('#bUndo', 'title');
    await ver(p, 'out_of_map'); await p.waitForTimeout(200);
    const x = await p.inputValue('#f-x'), undo1 = await p.getAttribute('#bUndo', 'title');
    await ver(p, 'times_not_increasing'); await p.waitForTimeout(300);
    const r = await p.evaluate(() => { const f = document.querySelector('#k-t'); return { hash: location.hash, vis: !!f && __r26.vis(f), focus: document.activeElement === f }; });
    return [[what, /^-100/.test(x) && undo0 === undo1 && r.hash === '#rodaje' && r.vis && r.focus, `X sigue en ${x} · historial ${undo0 === undo1 ? 'igual' : 'cambiado'} · clave: ${r.hash}, tiempo ${r.vis ? 'a la vista' : 'oculto'}${r.focus ? ' y con el foco' : ''}`]];
  });
  await R26('AR-07 +', async p => {
    const what = 'AR-07 + una Aplicar escena que no se entregó cuenta como problema en la tira, y aplicar y leer después lo resuelve';
    await sim(p, 'server'); await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    const failed = await shows(p, '#dock .strip', /Fallido[\s\S]*Aplicar escena/, 14000), a = await T(p, '#dock .strip');
    await sim(p, 'server'); const ok = await apply(p), b = await T(p, '#dock .strip');
    return [[what, failed && /1 problema/.test(a) && !/Sin problemas/.test(a) && ok && /Sin problemas/.test(b), `sin entregar: «${a}» · aplicada después: «${b}»`]];
  });
  await R26('AR-07 −', async p => {
    const s0 = await T(p, '#dock .strip'); await dock(p);
    const hist = await p.evaluate(() => [...document.querySelectorAll('#dock .qrow')].filter(r => r.querySelector('.chip.fallido, .chip.parcial')).length);
    return [['AR-07 − los fallos ya resueltos por una escena aplicada y leída después no mantienen la alarma: la tira dice «Sin problemas»', /Sin problemas/.test(s0) && hist > 0, `tira «${s0}» con ${hist} órdenes fallidas o parciales antiguas en Actividad`]];
  });

  // --- Lo que pidió y eligió Guillermo el 5 de noviembre (§8): la rueda (UX-44 y UX-45) y sus decisiones de §8.4, §8.3 y §8.5 de octubre ---
  const nHist = p => p.evaluate(() => { const n = document.querySelector('[data-act="dtab"][data-v="historial"] .n'); return n ? +n.textContent : -1; });
  const val = async (p, sel) => +(await p.inputValue(sel));
  const turned = (a, b) => ((b - a) % 360 + 360) % 360;
  const center = async p => { const r = await p.locator('#map').boundingBox(); return [r.x + r.width / 2, r.y + r.height / 2]; };
  const over = async (p, sel) => { const b = await p.locator(sel).first().boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await p.waitForTimeout(350); };
  const wheel = async (p, dy, mod) => { if (mod) await p.keyboard.down(mod); await p.mouse.wheel(0, dy); if (mod) await p.keyboard.up(mod); await p.waitForTimeout(120); };
  // metros por píxel del mapa, por la regla de la escala
  const zoomOf = p => p.evaluate(() => { const t = document.querySelector('#scaleTxt').textContent, m = parseFloat(t) * (/km/.test(t) ? 1000 : 1); return parseFloat(document.querySelector('#scaleBar').style.width) / m; });
  // del mundo a la pantalla, con dos lecturas del cursor en la barra de estado
  const toScreen = async p => {
    const r = await p.locator('#map').boundingBox(), a = [r.x + r.width * 0.3, r.y + r.height * 0.35], b = [r.x + r.width * 0.7, r.y + r.height * 0.65];
    const n = s => parseFloat(s.replace(/\./g, '').replace(',', '.'));
    const read = async q => { await p.mouse.move(q[0], q[1]); await p.waitForTimeout(80); const m = (await T(p, '#cursorXY')).match(/X ([\d.,-]+) · Z ([\d.,-]+)/); return m ? [n(m[1]), n(m[2])] : null; };
    const wa = await read(a), wb = await read(b);
    if (!wa || !wb || wa[0] === wb[0] || wa[1] === wb[1]) return null;
    return (x, z) => [a[0] + (x - wa[0]) * (b[0] - a[0]) / (wb[0] - wa[0]), a[1] + (z - wa[1]) * (b[1] - a[1]) / (wb[1] - wa[1])];
  };
  const scrub = async (p, t) => { const tr = await p.locator('#tlTrack').boundingBox(), ru = await p.locator('#tlRuler').boundingBox(), span = +(await p.getAttribute('#tlTrack', 'data-span')); await p.mouse.click(tr.x + t / span * tr.width, ru.y + ru.height / 2); await p.waitForTimeout(250); };

  // UX-44: la rueda encima de lo seleccionado lo gira
  await R26('UX-44 +', async p => {
    const what = 'UX-44 + con «Bidón azul» seleccionado, la rueda encima lo gira 15° por paso hacia arriba, y con Alt 1°, y los pasos seguidos son un solo cambio del historial; en Rodaje, la rueda encima de la clave K2 elegida gira su rumbo';
    await dock(p);
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.click('#bFit'); await p.waitForTimeout(250);
    const c = await center(p), y0 = await val(p, '#f-yaw'), n0 = await nHist(p);
    await p.mouse.move(c[0], c[1]); await p.waitForTimeout(80);
    await wheel(p, -100); await wheel(p, -100); const y1 = await val(p, '#f-yaw');
    await wheel(p, -100, 'Alt'); const y2 = await val(p, '#f-yaw'), n1 = await nHist(p);
    await p.keyboard.press('2'); await p.waitForTimeout(300);
    await p.click('#colL [data-act="sel"][data-v="cam:cam-travel"]'); await p.waitForTimeout(150);
    await p.evaluate(() => { const k = document.querySelectorAll('#colR [data-act="sel"][data-v^="key:cam-travel:"]'); if (k[1]) k[1].click(); }); await p.waitForTimeout(150);
    if (!await p.locator('#k-yaw').count()) return [[what, false, 'no se encontró el rumbo de la K2']];
    await p.click('#bFit'); await p.waitForTimeout(250);
    const kx = await val(p, '#k-x'), kz = await val(p, '#k-z'), k0 = await val(p, '#k-yaw'), map = await toScreen(p);
    if (!map) return [[what, false, 'no se pudo leer el cursor en la barra de estado']];
    const [sx, sy] = map(kx, kz); await p.mouse.move(sx, sy); await p.waitForTimeout(80);
    await wheel(p, -100); const k1 = await val(p, '#k-yaw');
    return [[what, turned(y0, y1) === 30 && turned(y1, y2) === 1 && n1 === n0 + 1 && turned(k0, k1) === 15, `Bidón azul ${y0}° → ${y1}° → con Alt ${y2}° · historial ${n1 - n0 >= 0 ? '+' : ''}${n1 - n0} · K2 ${k0}° → ${k1}°`]];
  });
  await R26('UX-44 −', async p => {
    const what = 'UX-44 − la rueda encima de algo que no está elegido no lo gira y aleja el mapa, y en un sitio vacío también; con la toma armada no gira lo elegido';
    await dock(p);
    await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.click('#bFit'); await p.waitForTimeout(250);
    const m0 = await val(p, '#f-yaw');
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150);
    const c = await center(p), n0 = await nHist(p), z0 = await zoomOf(p);
    await p.mouse.move(c[0], c[1]); await p.waitForTimeout(80); await wheel(p, 100);
    const z1 = await zoomOf(p);
    await p.mouse.move(c[0] - 160, c[1] - 120); await p.waitForTimeout(80); await wheel(p, 100);
    const z2 = await zoomOf(p), n1 = await nHist(p);
    await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(150); const m1 = await val(p, '#f-yaw');
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150); const b0 = await val(p, '#f-yaw');
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    await p.click('#bFit'); await p.waitForTimeout(250);
    const u0 = await p.getAttribute('#bUndo', 'title'), c2 = await center(p);
    await p.mouse.move(c2[0], c2[1]); await p.waitForTimeout(80); await wheel(p, -100);
    const b1 = await val(p, '#f-yaw'), u1 = await p.getAttribute('#bUndo', 'title');
    return [[what, m1 === m0 && z1 < z0 && z2 < z1 && n1 === n0 && b1 === b0 && u1 === u0, `Mirek sin elegir ${m0}° → ${m1}° · escala ${z0.toFixed(2)} → ${z1.toFixed(2)} → en vacío ${z2.toFixed(2)} px/m · historial ${n1 === n0 ? 'igual' : 'cambiado'} · armada: Bidón azul ${b0}° → ${b1}°, documento ${u1 === u0 ? 'igual' : 'cambiado'}`]];
  });

  // UX-45: la rueda encima de un campo numérico lo sube o lo baja
  await R26('UX-45 +', async p => {
    const what = 'UX-45 + con el ratón encima, la rueda sube la X de «Bidón azul» 0,1 m por paso hacia arriba, y con Mayús 1 m, en un solo cambio del historial, y el Rumbo 1° por paso';
    await dock(p);
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150);
    const n0 = await nHist(p), x0 = await val(p, '#f-x');
    await over(p, '#f-x'); await wheel(p, -100); await wheel(p, -100);
    const x1 = await val(p, '#f-x'); await wheel(p, -100, 'Shift');
    const x2 = await val(p, '#f-x'), n1 = await nHist(p);
    await over(p, '#f-yaw'); const r0 = await val(p, '#f-yaw'); await wheel(p, -100); const r1 = await val(p, '#f-yaw');
    const d1 = Math.round((x1 - x0) * 10) / 10, d2 = Math.round((x2 - x1) * 10) / 10;
    return [[what, d1 === 0.2 && d2 === 1 && n1 === n0 + 1 && turned(r0, r1) === 1, `X ${x0} → ${x1} (+${d1}) → con Mayús ${x2} (+${d2}) · historial ${n1 - n0 >= 0 ? '+' : ''}${n1 - n0} · Rumbo ${r0}° → ${r1}°`]];
  });
  await R26('UX-45 −', async p => {
    const what = 'UX-45 − una rueda que venía de fuera de los campos no cambia el campo que pasa por debajo, y con la toma armada los campos no cambian con la rueda';
    await dock(p);
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150);
    const x0 = await val(p, '#f-x'), n0 = await nHist(p);
    await over(p, '#colR .ph'); await p.mouse.wheel(0, 100); await p.waitForTimeout(40);
    const b = await p.locator('#f-x').boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await p.mouse.wheel(0, -100); await p.waitForTimeout(150);
    const x1 = await val(p, '#f-x'), n1 = await nHist(p);
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    if (!await p.locator('#f-x').count()) return [[what, false, 'Propiedades no enseña la X armada']];
    const a0 = await val(p, '#f-x'), dis = await p.locator('#f-x').isDisabled();
    await over(p, '#f-x'); await wheel(p, -100); const a1 = await val(p, '#f-x');
    return [[what, x1 === x0 && n1 === n0 && dis && a1 === a0, `desplazando: X ${x0} → ${x1}, historial ${n1 === n0 ? 'igual' : 'cambiado'} · armada: X ${dis ? 'apagada' : 'encendida'}, ${a0} → ${a1}`]];
  });

  // UX-30 con la decisión de §8.4: en Rodaje, el cursor de tiempo mueve a los actores como estimación rayada; clic en un gesto elige al actor
  await R26('UX-30 +', async p => {
    const what = 'UX-30 + en Rodaje, con el cursor de tiempo a 3 s, Mirek se pinta también rayado donde estaría, con «Mirek · estimado» a 12 px y 4,5:1 en todos los píxeles de su letra, y a 5 s ese rayado está más adelante; clic en su gesto «Señalar» lo elige';
    await p.keyboard.press('2'); await p.waitForTimeout(300);
    const look = async t => { await scrub(p, t); const f = await frame(p), e = f.texts.find(x => x.text === 'Mirek · estimado'); return { est: !!e && e.px >= 12 && e.n > 0 && !e.low, e, h: striped(f), any: hatched(f) }; };
    const a = await look(3), b = await look(5);
    const moved = a.h.length && b.h.length ? Math.round(Math.hypot(b.h[0].x - a.h[0].x, b.h[0].y - a.h[0].y)) : 0;
    const g = p.locator('.lane .gest', { hasText: 'Señalar' });
    if (!await g.count()) return [[what, false, 'no hay gesto «Señalar» en la línea de tiempo']];
    await g.click(); await p.waitForTimeout(200);
    const picked = await p.evaluate(() => { const ps = document.querySelectorAll('#colR .panel'), last = ps[ps.length - 1]; return !!last && /Mirek/.test(last.innerText) && !!last.querySelector('#f-x'); });
    return [[what, a.est && a.h.length === 1 && a.any.length === 1 && b.est && b.h.length === 1 && moved >= 3 && picked, `a 3 s: ${a.h.length} de ${a.any.length} patrones con rayas que se ven (${showStripes(a.any[0] && a.any[0].stripes)})${a.e ? ` y «Mirek · estimado» a ${a.e.px} px, ${a.e.low ? `${a.e.min}:1 en ${a.e.low} de ${a.e.n} px` : 'todo a 4,5:1 o más'}` : ', sin «estimado»'} · a 5 s: ${b.h.length} rayado, ${moved} px más allá · clic en «Señalar»: ${picked ? 'elige a Mirek' : 'no lo elige'}`]];
  });
  await R26('UX-30 −', async p => {
    const what = 'UX-30 − en Rodaje a 0 s, y rodando, no hay nada rayado ni «estimado» en el mapa; clic en un gesto no cambia el documento ni mueve el cursor de tiempo';
    await p.keyboard.press('2'); await p.waitForTimeout(300);
    const count = f => hatched(f).length + f.texts.filter(x => /estimado/.test(x.text)).length;
    const at0 = count(await frame(p));
    await scrub(p, 3); const t0 = await T(p, '#tlTime'), u0 = await p.getAttribute('#bUndo', 'title');
    const g = p.locator('.lane .gest', { hasText: 'Señalar' });
    if (!await g.count()) return [[what, false, 'no hay gesto «Señalar» en la línea de tiempo']];
    await g.click(); await p.waitForTimeout(200);
    const t1 = await T(p, '#tlTime'), u1 = await p.getAttribute('#bUndo', 'title');
    await p.keyboard.press('1'); await p.waitForTimeout(250);
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(1500);
    const live = count(await frame(p));
    return [[what, at0 === 0 && live === 0 && t0 === t1 && u0 === u1, `a 0 s: ${at0} rayados o «estimado» · rodando: ${live} · cursor de tiempo ${t0} → ${t1} · documento ${u0 === u1 ? 'igual' : 'cambiado'}`]];
  });

  // UX-46, la decisión de §8.3 (C-16): la tecla «Parar toma» del mod de cliente para la toma desde dentro del juego
  await R26('UX-46 +', async p => {
    const what = 'UX-46 + armada, la barra de la toma dice que también se para desde tu juego con «Parar toma» y su tecla; rodando, esa tecla la para: el aviso, Tomas y Actividad dicen que fue desde tu juego, y Parar deja la barra de arriba';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const slate = await T(p, '#slateWrap');
    if (!await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600); await p.click('#bSim'); await p.waitForTimeout(120);
    const item = p.locator('#menu [data-act="sim-gamestop"]');
    if (!await item.count()) { await p.click('#status', { position: { x: 3, y: 3 } }); return [[what, false, `armada: «${slate.slice(0, 90)}» · el simulador no tiene la tecla del juego`]]; }
    await item.click();
    const toast = await W(p, () => /desde tu juego/.test(document.querySelector('#toasts').innerText), null, 2000), top = await p.locator('#bTopStop').isVisible();
    await p.click('[data-act="ltab"][data-v="tomas"]'); await p.waitForTimeout(150); const takes = await T(p, '#colL');
    await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(150); const act = await T(p, '#dock');
    const named = /Parar toma/.test(slate) && /\bFin\b/.test(slate), log = /desde tu juego/.test(takes), op = /tecla «Parar toma»/.test(act);
    return [[what, named && toast && !top && log && op, `armada: ${named ? 'nombra «Parar toma» (Fin)' : 'no la nombra'} · aviso: ${toast ? 'desde tu juego' : 'no lo dice'} · Parar ${top ? 'sigue arriba' : 'deja la barra'} · Tomas: ${log ? 'desde tu juego' : 'no lo dice'} · Actividad: ${op ? 'tu juego · tecla «Parar toma»' : 'no lo dice'}`]];
  });
  await R26('UX-46 −', async p => {
    const what = 'UX-46 − Parar en la web y la tecla del juego casi a la vez, las dos pulsadas, dan una sola parada: una toma más en Tomas y una sola orden de esa toma en Actividad';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const tn = (await T(p, '#slateWrap .tn')) || 'Toma', count = () => p.evaluate(() => { const n = document.querySelector('[data-act="ltab"][data-v="tomas"] .n'); return n ? +n.textContent : -1; });
    const k0 = await count();
    if (!await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600);
    // Parar en la web y, en la misma tarea, la tecla del juego: la segunda llega mientras la web espera la confirmación
    const game = await p.evaluate(() => { document.querySelector('#bTopStop').click(); document.querySelector('#bSim').click(); const b = document.querySelector('#menu [data-act="sim-gamestop"]'), on = !!b && !b.disabled; if (on) b.click(); return on; });
    if (!game) await p.click('#status', { position: { x: 3, y: 3 } });
    await p.waitForTimeout(1200);
    const k1 = await count();
    await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(150);
    const ops = await p.evaluate(tn => [...document.querySelectorAll('#dock .qrow')].filter(r => r.innerText.includes(tn)).length, tn);
    return [[what, game && k1 === k0 + 1 && ops === 1, `${game ? 'web y juego' : 'solo la web: la tecla del juego no está o está apagada, así que no prueba nada'} · Tomas ${k0} → ${k1} · órdenes de la ${tn}: ${ops}`]];
  });

  // UX-47, la decisión de §8.5: Aplicar quita la otra escena y crea la nueva, y el aviso nombra la que quitó
  await R26('UX-47 +', async p => {
    const what = 'UX-47 + con «Amanecer en Stary Sobor» en el juego, aplicar una escena nueva la quita, y el aviso final dice «Se quitó «Amanecer en Stary Sobor» del juego»';
    await p.click('#docBtn'); await p.waitForTimeout(150);
    if (!await p.locator('#menu [data-act="m-new"]').count()) return [[what, false, 'no hay «Nueva escena»']];
    await p.click('#menu [data-act="m-new"]'); await p.waitForTimeout(300);
    const ok = await apply(p), msg = await T(p, '#toasts');
    return [[what, ok && /Se quitó «Amanecer en Stary Sobor» del juego/.test(msg), `aviso: «${msg.slice(-150)}»`]];
  });
  await R26('UX-47 −', async p => {
    const what = 'UX-47 − reaplicar la escena que ya está en el juego no dice que se quitara otra';
    const ok = await apply(p), msg = await T(p, '#toasts');
    return [[what, ok && /Escena aplicada y leída/.test(msg) && !/Se quitó/.test(msg), `aviso: «${msg.slice(-150)}»`]];
  });

  // --- Segunda revisión de Astra (ui/astra/2026-11-05-ui-revision2-astra.md): AR2-01 a AR2-07 ---
  // AR2-01: lo que se ve, también en el tema claro (en el oscuro lo miran UX-09 −, UX-30 + y AR-03 +), y la sonda no se deja engañar
  await R26('AR2-01 + claro', async p => {
    const what = 'AR2-01 + en tema claro, el borrador se pinta con un contorno discontinuo de huecos que se ven, la estimación de Mirek a 3 s con rayas que se ven, y aplicado y leído, el marcador es sólido';
    const id = await changedId(p);
    if (!id) return [[what, false, 'ninguna entidad cambiada en la Jerarquía']];
    const a = await glyphAt(p, id);
    await p.keyboard.press('Escape'); await p.keyboard.press('2'); await p.waitForTimeout(300); await scrub(p, 3);
    const f = await frame(p), h = hatched(f);
    await p.keyboard.press('1'); await p.waitForTimeout(250);
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const b = await glyphAt(p, id);
    return [[what, a.dashed > 0 && !a.filled && striped(f).length === 1 && h.length === 1 && b.filled > 0 && !b.nominal, `${id.slice(4)}: ${a.see} · estimación: ${showStripes(h[0] && h[0].stripes)} · aplicada: ${b.see}`]];
  }, 1600, 960, 'light');
  await R26('AR2-01 −', async p => {
    const res = [];
    // a mano sobre el mapa, como AR-03 −: lo que la sonda tiene que dar por malo, y el halo de verdad, que es lo único que deja pasar
    const r = await p.evaluate(() => {
      const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth, cv = window.__cv;
      Object.assign(cv, { texts: [], strokes: [], fills: [], images: [], on: true });
      g.save(); g.setTransform(d, 0, 0, d, 0, 0);
      const aux = (t, color, w = 100, h = 30) => { const q = document.createElement('canvas'); q.width = w; q.height = h; const x = q.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = color; x.fillText(t, 2, 15); return q; };
      g.drawImage(aux('6150', '#888'), 40, 40);                                              // un número como imagen pálida
      g.drawImage(aux('6250', '#fff', 60, 24), 40, 80); g.font = '500 12px monospace'; g.fillStyle = '#000'; g.fillText('6250', 42, 95);   // un halo y su letra dentro
      g.drawImage(aux('6350', '#fff', 60, 24), 40, 120); g.fillText('9999', 42, 135);         // un «halo» con otra letra
      const white = document.createElement('canvas'); white.width = white.height = 6; const wq = white.getContext('2d'); wq.fillStyle = '#fff'; wq.fillRect(0, 0, 6, 6);
      g.save(); g.translate(200, 60); g.beginPath(); g.arc(0, 0, 8.75, 0, Math.PI * 2); g.fillStyle = g.createPattern(white, 'repeat'); g.fill(); g.restore();   // patrón sin rayas
      const ring = (x, dash, cap) => { g.save(); g.translate(x, 120); g.beginPath(); g.arc(0, 0, 8.75, 0, Math.PI * 2); g.fillStyle = 'rgba(255,255,255,.6)'; g.fill(); g.setLineDash(dash); g.lineCap = cap; g.lineWidth = 1.9; g.strokeStyle = '#544d40'; g.stroke(); g.restore(); };
      ring(200, [10000, 0.001], 'butt'); ring(240, [3, 2], 'round'); ring(280, [3, 2], 'butt');   // guion nominal, huecos que se cierran, huecos de verdad
      g.restore(); cv.on = false; cv.finish();
      return { images: cv.images.map(i => ({ texts: i.texts, halo: i.halo, kind: i.kind })), fills: cv.fills.filter(f => f.pat).map(f => f.stripes), gaps: cv.strokes.filter(s => s.gaps).map(s => s.gaps) };
    });
    const [pale, halo, other] = r.images, [nominal, round, butt] = r.gaps;
    res.push(['AR2-01 − la sonda da por no medido un número pintado como imagen, y por halo solo la imagen con la misma letra pintada dentro justo después', !!pale && unmeasured(pale) && !!halo && !unmeasured(halo) && !!other && unmeasured(other), r.images.map(i => `«${i.texts.join('')}» ${unmeasured(i) ? 'sin medir' : 'halo'}`).join(' · ')]);
    res.push(['AR2-01 − un patrón de un solo color no cuenta como rayado', r.fills.length === 1 && !STRIPES(r.fills[0]), showStripes(r.fills[0])]);
    res.push(['AR2-01 − un guion más largo que el contorno y unos huecos que los extremos redondos cierran no cuentan como discontinuo; unos huecos de 2 px con extremos planos, sí', !!nominal && !GAPS(nominal) && !!round && !GAPS(round) && !!butt && GAPS(butt), r.gaps.map(g => `${g.comps} trozos, ${g.gapPx} px de hueco a ${g.ratio}:1`).join(' · ')]);
    // sin ningún texto en el mapa la vista no pasa en vacío
    await p.evaluate(() => { const P = CanvasRenderingContext2D.prototype, f = P.fillText; P.fillText = function () { if (this.canvas && this.canvas.id === 'map') return; return f.apply(this, arguments); }; });
    const v = await readable(p, ['Mirek', 'Linda']);
    res.push(['AR2-01 − si el mapa no pinta ningún texto, la vista no pasa en vacío', !v.ok && /^0 textos/.test(v.info), v.info]);
    return res;
  });

  // AR2-02: hasta 900 px la página se desplaza; Parar, «MCP apagado», los avisos y los menús se quedan dentro de la ventana (B5, CU-35)
  const seen = (p, sel, re) => p.evaluate(([s, r]) => {
    const el = [...document.querySelectorAll(s)].find(e => e.getClientRects().length && (!r || new RegExp(r).test(e.textContent)));
    if (!el) return { ok: false, at: 'no está' };
    const q = el.getBoundingClientRect(), hit = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2), on = !!hit && (hit === el || el.contains(hit));
    const whole = q.top >= -0.5 && q.left >= -0.5 && q.bottom <= innerHeight + 0.5 && q.right <= innerWidth + 0.5;
    return { ok: whole && on, at: `en ${Math.round(q.top)}…${Math.round(q.bottom)} px${whole ? '' : ', fuera de la ventana'}${on ? '' : ', tapado'}` };
  }, [sel, re ? re.source : '']);
  const scrollTo = (p, end) => p.evaluate(e => { const s = document.scrollingElement; s.scrollTop = e ? s.scrollHeight : 0; return Math.round(s.scrollTop); }, end);
  // Parar en la web y, en la misma tarea, se corta tu juego: Parando… espera la confirmación hasta 4 s y después queda sin confirmar
  const stopAndCut = (p, peer) => p.evaluate(v => { document.querySelector('#bTopStop').click(); document.querySelector('#bSim').click(); document.querySelector(`#menu [data-act="sim"][data-v="${v}"]`).click(); document.querySelector('#status').click(); }, peer);
  for (const w of [390, 768, 900, 901]) await R26(`AR2-02 + ${w}`, async p => {
    const what = `AR2-02 + a ${w} × 768, arriba y desplazada hasta el final, Parar se ve entero y se alcanza rodando, parando y con la parada sin confirmar, «MCP apagado» se ve entero, y el aviso y el menú de escena caen dentro de la ventana`;
    const bad = [], states = [];
    const both = async (state, extra = []) => {
      for (const end of [false, true]) {
        const y = await scrollTo(p, end); await p.waitForTimeout(60);
        for (const [n, sel, re] of [['Parar', '#bTopStop'], ['«MCP apagado»', '#stInfo > span', /MCP apagado/], ...extra]) { const r = await seen(p, sel, re); if (!r.ok) bad.push(`${state}, ${end ? `desplazada ${y} px` : 'arriba'}: ${n} ${r.at}`); }
      }
      states.push(state);
    };
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await both('rodando');
    await stopAndCut(p, 'director');
    if (await shows(p, '#bTopStop', /Parando/, 500)) await both('parando'); else bad.push('no se vio «Parando…»');
    if (!await shows(p, '#bTopStop', /sin confirmar/, 6000)) return [[what, false, `${bad.join(' · ')} · no llegó a «Parada sin confirmar»`]];
    await both('sin confirmar', [['el aviso', '#toasts .toast']]);
    await scrollTo(p, true); await p.click('#docBtn'); await p.waitForTimeout(150);
    const m = await seen(p, '#menu'); if (!m.ok) bad.push(`menú de escena, desplazada: ${m.at}`);
    await p.click('#status', { position: { x: 3, y: 3 } });
    return [[what, !bad.length, bad.length ? bad.slice(0, 6).join(' · ') : `todo a la vista ${states.join(', ')}, arriba y desplazada, y el menú también`]];
  }, w, 768);
  await R26('AR2-02 −', async p => {
    const res = [], what = 'AR2-02 − con la barra de arriba y la de estado otra vez en el flujo, a 390 px y rodando, la comprobación da Parar por perdido al desplazarse y «MCP apagado» por fuera de la ventana arriba';
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.addStyleTag({ content: '.top,.status{position:relative!important}' }); await p.waitForTimeout(100);
    await scrollTo(p, true); const stop = await seen(p, '#bTopStop'); await scrollTo(p, false); const mcp = await seen(p, '#stInfo > span', /MCP apagado/);
    res.push([what, !stop.ok && !mcp.ok, `Parar desplazada: ${stop.at} · «MCP apagado» arriba: ${mcp.at}`]);
    await p.evaluate(() => document.querySelectorAll('style').forEach(s => { if (/position:relative!important/.test(s.textContent)) s.remove(); })); await p.waitForTimeout(100);
    const last = await p.evaluate(() => {
      const s = document.scrollingElement; s.scrollTop = s.scrollHeight;
      const lp = [...document.querySelectorAll('#colR > .panel')].filter(e => e.getClientRects().length).pop(), st = document.querySelector('#status').getBoundingClientRect();
      if (!lp) return null;
      const q = lp.getBoundingClientRect(), hit = document.elementFromPoint(q.left + q.width / 2, q.bottom - 4);
      return { ok: q.bottom <= st.top + 0.5 && !!hit && lp.contains(hit), at: `acaba en ${Math.round(q.bottom)} px y la barra de estado empieza en ${Math.round(st.top)} px` };
    });
    res.push(['AR2-02 − con las barras fijas nada queda debajo de ellas: desplazada hasta el final a 390 px, el último panel acaba encima de la barra de estado y su borde de abajo responde', !!last && last.ok, last ? last.at : 'no hay panel']);
    await p.setViewportSize({ width: 1366, height: 768 }); await p.waitForTimeout(300);
    const desk = await p.evaluate(() => ({ h: document.scrollingElement.scrollHeight, v: innerHeight }));
    res.push(['AR2-02 − en escritorio la página no se desplaza: a 1366 × 768 cabe entera en la ventana', desk.h <= desk.v + 1, `alto ${desk.h} px para una ventana de ${desk.v} px`]);
    return res;
  }, 390, 768);

  // AR2-03: crear una escena es guardar un documento nuevo; sin backend no se puede, y abrir las de la lista sí (CU-37)
  const head = async p => (await T(p, '#docBtn')).replace(/ · guardado.*$/, '');
  const docsN = async p => { await p.click('#docBtn'); await p.waitForTimeout(150); const n = await p.locator('#menu [data-act="doc-open"]').count(); await p.keyboard.press('Escape'); await p.waitForTimeout(100); return n; };
  await R26('AR2-03 +', async p => {
    const what = 'AR2-03 + con backend, «Nueva escena» crea una vacía con su cámara y el juego sigue con la suya; sin backend, el menú la apaga y dice por qué, y «Abrir…» sigue sirviendo para consultar sin cambiar ninguna escena';
    await sceneMenu(p, 'm-new');
    const h0 = await head(p), ents = await p.locator('#colL [data-act="sel"][data-v^="ent:"]').count(), cams = await p.evaluate(() => [...document.querySelectorAll('#colL [data-act="sel"]')].filter(r => /^(cam|key):/.test(r.dataset.v)).length);
    await sim(p, 'backend');
    await p.click('#docBtn'); await p.waitForTimeout(150);
    const nb = p.locator('#menu [data-act="m-new"]'), off = (await nb.count()) > 0 && await nb.isDisabled(), note = await T(p, '#menu .note'), n0 = await p.locator('#menu [data-act="doc-open"]').count();
    const back = p.locator('#menu [data-act="doc-open"]', { hasText: 'Amanecer en Stary Sobor' }), can = (await back.count()) > 0 && await back.first().isEnabled();
    if (can) { await back.first().click(); await p.waitForTimeout(250); } else await p.keyboard.press('Escape');
    const h1 = await head(p), sub = await T(p, '#colL .ph .sub'), n1 = await docsN(p);
    return [[what, /Escena sin título/.test(h0) && /otra escena/i.test(h0) && !ents && cams > 0 && off && /Sin conexión con el backend/.test(note) && can && /Amanecer en Stary Sobor 2 cambios sin aplicar/.test(h1) && /35 entidades/.test(sub) && n0 === 2 && n1 === 2,
      `con backend: «${h0}», ${ents} entidades y ${cams} cámara · sin backend: Nueva escena ${off ? 'apagada' : 'encendida'}, nota «${note.slice(-118)}» · Abrir: «${h1}», ${sub} · escenas en la lista ${n0} → ${n1}`]];
  });
  await R26('AR2-03 −', async p => {
    const what = 'AR2-03 − sin backend, ni el botón ni la acción a la fuerza crean una escena: la lista sigue con una, la abierta es la misma, el historial no cambia y el aviso dice por qué';
    await dock(p); await sim(p, 'backend');
    const h0 = await head(p), u0 = await nHist(p);
    await p.click('#docBtn'); await p.waitForTimeout(150);
    if (!await p.locator('#menu [data-act="m-new"]').count()) return [[what, false, 'no hay «Nueva escena»']];
    await p.locator('#menu [data-act="m-new"]').click({ timeout: 800 }).catch(() => {}); await p.waitForTimeout(200);
    if (await p.locator('#menu').isHidden()) { await p.click('#docBtn'); await p.waitForTimeout(150); }
    await p.evaluate(() => { const b = document.querySelector('#menu [data-act="m-new"]'); if (b) { b.disabled = false; b.click(); } }); await p.waitForTimeout(250);
    const h1 = await head(p), u1 = await nHist(p), msg = await T(p, '#toasts'), n = await docsN(p);
    return [[what, n === 1 && h1 === h0 && u1 === u0 && /Sin conexión con el backend/.test(msg), `escenas en la lista: ${n} · «${h0}» → «${h1}» · historial ${u1 === u0 ? 'igual' : 'cambiado'} · aviso «${msg.slice(0, 96)}»`]];
  });

  // AR2-04: con Ctrl o Cmd la rueda amplía la página en el navegador; el mapa no la usa ni la cancela
  const wheelLog = p => p.evaluate(() => { window.__wp = []; addEventListener('wheel', e => window.__wp.push(e.defaultPrevented), { passive: true }); });
  await R26('AR2-04 +', async p => {
    const what = 'AR2-04 + la rueda sola sigue girando lo elegido 15° por paso, y con Alt 1°, y en un sitio vacío acerca y aleja; con Ctrl o con Cmd la rueda se deja al navegador, sin cancelarla';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.click('#bFit'); await p.waitForTimeout(250);
    const c = await center(p); await p.mouse.move(c[0], c[1]); await p.waitForTimeout(80);
    const y0 = await val(p, '#f-yaw'); await wheel(p, -100); const y1 = await val(p, '#f-yaw'); await wheel(p, -100, 'Alt'); const y2 = await val(p, '#f-yaw');
    await p.mouse.move(c[0] - 160, c[1] - 120); await p.waitForTimeout(80); const z0 = await zoomOf(p); await wheel(p, 100); const z1 = await zoomOf(p);
    await p.mouse.move(c[0], c[1]); await p.waitForTimeout(80); await wheelLog(p);
    await wheel(p, -100, 'Control'); await wheel(p, -100, 'Meta');
    const wp = await p.evaluate(() => window.__wp);
    return [[what, turned(y0, y1) === 15 && turned(y1, y2) === 1 && z1 < z0 && wp.length === 2 && wp.every(x => x === false), `rueda: ${y0}° → ${y1}° → con Alt ${y2}° · en vacío ${z0.toFixed(2)} → ${z1.toFixed(2)} px/m · con Ctrl y con Cmd: ${wp.map(x => x ? 'cancelada' : 'del navegador').join(' y ') || 'no llegó'}`]];
  });
  await R26('AR2-04 −', async p => {
    const what = 'AR2-04 − con Ctrl o con Cmd, la rueda encima de lo elegido no lo gira ni cambia el historial, y ni ahí ni en un sitio vacío acerca o aleja el mapa';
    await dock(p);
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.click('#bFit'); await p.waitForTimeout(250);
    const c = await center(p), y0 = await val(p, '#f-yaw'), n0 = await nHist(p), z0 = await zoomOf(p);
    await p.mouse.move(c[0], c[1]); await p.waitForTimeout(80); await wheel(p, -100, 'Control'); await wheel(p, -100, 'Meta');
    const y1 = await val(p, '#f-yaw'), z1 = await zoomOf(p);
    await p.mouse.move(c[0] - 160, c[1] - 120); await p.waitForTimeout(80); await wheel(p, 100, 'Control'); await wheel(p, 100, 'Meta');
    const z2 = await zoomOf(p), n1 = await nHist(p);
    return [[what, y1 === y0 && n1 === n0 && z1 === z0 && z2 === z0, `Bidón azul ${y0}° → ${y1}° · historial ${n1 === n0 ? 'igual' : 'cambiado'} · escala ${z0.toFixed(2)} → ${z1.toFixed(2)} → en vacío ${z2.toFixed(2)} px/m`]];
  });

  // AR2-05: la rueda en un campo junta los pasos de lo mismo; dos elegidos distintos son dos cambios con su nombre
  const stepOn = async (p, sel) => { const b = await p.locator(sel).boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await wheel(p, -100); };
  const pick = async (p, sel) => { await p.click(sel); await p.waitForTimeout(60); };
  await R26('AR2-05 +', async p => {
    const what = 'AR2-05 + tres pasos de la rueda en la X de «Bidón azul» son un solo cambio, y un paso justo después en la X de «Bidón verde» es otro, con su nombre';
    await dock(p); await pick(p, '#colL [data-act="sel"][data-v="ent:obj-13"]');
    const n0 = await nHist(p), a0 = await val(p, '#f-x');
    await over(p, '#f-x'); await wheel(p, -100); await wheel(p, -100); await wheel(p, -100);
    const a1 = await val(p, '#f-x'), n1 = await nHist(p);
    await pick(p, '#colL [data-act="sel"][data-v="ent:obj-14"]'); const b0 = await val(p, '#f-x'); await stepOn(p, '#f-x');
    const b1 = await val(p, '#f-x'), n2 = await nHist(p), u = await p.getAttribute('#bUndo', 'title');
    const da = Math.round((a1 - a0) * 10) / 10, db = Math.round((b1 - b0) * 10) / 10;
    return [[what, da === 0.3 && n1 === n0 + 1 && db === 0.1 && n2 === n1 + 1 && /Mover Bidón verde/.test(u || ''), `Bidón azul ${a0} → ${a1} (+${da}), historial +${n1 - n0} · Bidón verde ${b0} → ${b1} (+${db}), historial +${n2 - n1} · ${u}`]];
  });
  await R26('AR2-05 −', async p => {
    const what = 'AR2-05 − deshacer el paso de «Bidón verde» le devuelve su X y deja la de «Bidón azul» con el suyo, y Deshacer nombra entonces a «Bidón azul»; con K1 y K2 de una cámara, dos pasos seguidos también son dos cambios';
    await dock(p); await pick(p, '#colL [data-act="sel"][data-v="ent:obj-13"]');
    const a0 = await val(p, '#f-x'); await stepOn(p, '#f-x'); const a1 = await val(p, '#f-x');
    await pick(p, '#colL [data-act="sel"][data-v="ent:obj-14"]'); const b0 = await val(p, '#f-x'); await stepOn(p, '#f-x');
    await p.click('#bUndo'); await p.waitForTimeout(150);
    const b2 = await val(p, '#f-x'), u = await p.getAttribute('#bUndo', 'title');
    await pick(p, '#colL [data-act="sel"][data-v="ent:obj-13"]'); const a2 = await val(p, '#f-x'), k0 = await nHist(p);
    await p.keyboard.press('2'); await p.waitForTimeout(300); await pick(p, '#colL [data-act="sel"][data-v="cam:cam-travel"]');
    const keys = p.locator('#colR [data-act="sel"][data-v^="key:cam-travel:"]');
    if (await keys.count() < 2) return [[what, false, 'no hay K1 y K2 en Propiedades']];
    await keys.nth(0).click(); await p.waitForTimeout(60); await stepOn(p, '#k-x');
    await pick(p, '#colL [data-act="sel"][data-v="cam:cam-travel"]'); await keys.nth(1).click(); await p.waitForTimeout(60); await stepOn(p, '#k-x');
    const uk = await p.getAttribute('#bUndo', 'title'); await p.keyboard.press('1'); await p.waitForTimeout(300); const k1 = await nHist(p);
    return [[what, a1 !== a0 && a2 === a1 && b2 === b0 && /Mover Bidón azul/.test(u || '') && k0 >= 0 && k1 === k0 + 2 && /K2/.test(uk || ''), `deshecho Bidón verde: su X ${b2} (era ${b0}) · Bidón azul sigue en ${a2} (era ${a0}) · ${u} · K1 y K2: historial +${k1 - k0}, ${uk}`]];
  });

  // AR2-06: la tecla «Parar toma» del juego sigue los estados de la web
  const takesN = p => p.evaluate(() => { const n = document.querySelector('[data-act="ltab"][data-v="tomas"] .n'); return n ? +n.textContent : -1; });
  const gameKey = async p => { const on = await p.evaluate(() => { document.querySelector('#bSim').click(); const b = document.querySelector('#menu [data-act="sim-gamestop"]'), ok = !!b && !b.disabled; if (ok) b.click(); return ok; }); if (!on) await p.click('#status', { position: { x: 3, y: 3 } }); return on; };
  await R26('AR2-06 +', async p => {
    const what = 'AR2-06 + con la toma armada, la tecla «Parar toma» del juego la desarma sin sumar ninguna toma; conectado y rodando, la para una sola vez y dice que fue desde tu juego';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const k0 = await takesN(p), on = await gameKey(p);
    const idle = await W(p, () => document.querySelector('#bTopStop').hidden, null, 2000), msg = await T(p, '#toasts'), k1 = await takesN(p), st = await T(p, '#slateWrap .tstate');
    if (!await arm(p) || !await roll(p)) return [[what, false, `armada: tecla ${on ? 'disponible' : 'apagada'}, ${idle ? 'desarmó' : 'siguió armada'} · no llegó a rodar después`]];
    await p.waitForTimeout(600); const on2 = await gameKey(p);
    const stopped = await W(p, () => /desde tu juego/.test(document.querySelector('#toasts').innerText), null, 2000), k2 = await takesN(p);
    return [[what, on && idle && /desarmada desde tu juego/i.test(msg) && k1 === k0 && /Lista para preparar/.test(st) && on2 && stopped && k2 === k1 + 1, `armada: tecla ${on ? 'disponible' : 'apagada'}, ${idle ? 'desarma' : 'sigue armada'} («${msg.slice(0, 60)}»), Tomas ${k0} → ${k1}, «${st}» · rodando: ${stopped ? 'parada desde tu juego' : 'no se paró'}, Tomas ${k1} → ${k2}`]];
  });
  for (const [peer, name] of [['director', 'tu juego'], ['backend', 'el backend']]) await R26(`AR2-06 − ${name}`, async p => {
    const what = `AR2-06 − parando, con ${name} cortado, la tecla del juego no da la toma por parada: ni Parada ni Observado ni «leída hace 0 s»; sigue sin confirmar hasta volver la conexión, y entonces se confirma leyendo`;
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(600); await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(100);
    const tn = (await T(p, '#slateWrap .tn')) || 'Toma', k0 = await takesN(p);
    const op = () => p.evaluate(tn => { const r = [...document.querySelectorAll('#dock .qrow')].find(x => x.innerText.includes(tn)); return r ? { obs: !!r.querySelector('.chip.observado'), text: r.innerText.replace(/\s+/g, ' ') } : null; }, tn);
    const pressed = await p.evaluate(v => {
      document.querySelector('#bTopStop').click(); document.querySelector('#bSim').click(); document.querySelector(`#menu [data-act="sim"][data-v="${v}"]`).click();
      const b = document.querySelector('#menu [data-act="sim-gamestop"]'), on = !!b && !b.disabled; if (on) b.click(); else document.querySelector('#status').click(); return on;
    }, peer);
    await p.waitForTimeout(300);
    const st1 = await T(p, '#slateWrap .tstate'), o1 = await op(), k1 = await takesN(p);
    const fake = /Parada$/.test(st1) || !o1 || o1.obs || /Leída hace 0 s/i.test(o1.text);
    const unc = await shows(p, '#bTopStop', /sin confirmar/, 6000), o2 = await op();
    await sim(p, peer);
    const conf = await W(p, () => /Parada confirmada al leer el juego/.test(document.querySelector('#toasts').innerText), null, 4000), o3 = await op();
    return [[what, pressed && !fake && k1 === k0 && unc && !(o2 && o2.obs) && conf && !!o3 && o3.obs && /lectura al volver/.test(o3.text), `tecla ${pressed ? 'pulsada' : 'apagada'} · justo después: «${st1}», ${!o1 ? 'sin la fila de la toma' : `${o1.obs ? 'Observado' : 'sin Observado'}, ${(o1.text.match(/Leída hace \d+ s|Sin lectura/) || ['?'])[0]}`}, Tomas ${k0} → ${k1} · a los 4 s: ${unc ? 'sin confirmar' : 'otra cosa'} · al volver: ${conf ? 'confirmada leyendo' : 'sin confirmar'}${o3 ? ` («${o3.text.slice(0, 80)}»)` : ''}`]];
  });

  // AR2-07: la nota de la línea de tiempo, la leyenda y la Guía dicen qué hace la vista previa y qué es propio
  const about = p => p.evaluate(() => { const h = [...document.querySelectorAll('#guide h2')].find(x => /Acerca del diseño/.test(x.textContent)); let t = '', n = h && h.nextElementSibling; while (n && !/^H[23]$/.test(n.tagName)) { t += ' ' + n.textContent; n = n.nextElementSibling; } return t.replace(/\s+/g, ' ').trim(); });
  await R26('AR2-07 +', async p => {
    const what = 'AR2-07 + la nota de la línea de tiempo dice que la vista previa mueve la cámara y los actores estimados sin mover el juego, la leyenda separa lo estimado de lo leído, y la Guía separa lo que solo existe aquí de lo que se adapta, como la rueda';
    await p.keyboard.press('2'); await p.waitForTimeout(300);
    const note = await T(p, '.tlnote'); await p.click('#bLegend'); await p.waitForTimeout(150); const leg = await T(p, '#legend');
    await p.keyboard.press('1'); await p.waitForTimeout(200); await p.click('#bGuide'); await p.waitForTimeout(400); const g = await about(p);
    return [[what, /actores estimados/.test(note) && /no mueve el juego/i.test(note) && /estimación/.test(leg) && /en el juego y leído/.test(leg) && /solo existe aquí/.test(g) && /rueda/.test(g), `nota: «${note}» · leyenda: ${/estimación/.test(leg) ? 'el rayado es una estimación' : 'no dice qué es el rayado'}${/en el juego y leído/.test(leg) ? ', el relleno, leído' : ''} · Guía: «${g.slice(g.indexOf('Lo propio') >= 0 ? g.indexOf('Lo propio') : 0, (g.indexOf('Lo propio') >= 0 ? g.indexOf('Lo propio') : 0) + 150)}…»`]];
  });
  await R26('AR2-07 −', async p => {
    const what = 'AR2-07 − la nota no dice que solo se mueve la cámara ni que no se tocan los actores, y la Guía no dice que lo único propio es saber qué hay en el juego';
    await p.keyboard.press('2'); await p.waitForTimeout(300); const note = await T(p, '.tlnote');
    await p.keyboard.press('1'); await p.waitForTimeout(200); await p.click('#bGuide'); await p.waitForTimeout(400); const g = await about(p);
    return [[what, !!note && !/solo la cámara|ni los actores/.test(note) && !!g && !/Lo único propio/.test(g), `nota: «${note}» · Guía: ${/Lo único propio/.test(g) ? '«Lo único propio…»' : 'sin «Lo único propio»'}`]];
  });

  // --- Revisión visual (VIS): el aspecto, sin tocar lo decidido ---
  // VIS-01: la cabecera de toma es una sola franja que no cambia de alto con el estado; la acción va en la fila del reloj
  const slate = p => p.evaluate(() => {
    const t = document.querySelector('.takebar'); if (!t) return null;
    const mid = e => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; };
    const a = [...t.querySelectorAll('.tact .btn')].find(__r26.shown), c = t.querySelector('.tc'), f = t.querySelector('.tfix'), k = f && f.querySelector('kbd');
    return { h: Math.round(t.getBoundingClientRect().height), map: Math.round(document.querySelector('#mapwrap').getBoundingClientRect().top), row: !a || !c || Math.abs(mid(a) - mid(c)) <= 3,
      key: !k || (k.getBoundingClientRect().right <= f.getBoundingClientRect().right + 0.5 && f.scrollWidth <= f.clientWidth + 1) };
  });
  await R26('VIS-01 +', async p => {
    const what = 'VIS-01 + lista, armada, rodando, parada y con una comprobación que falla, la cabecera de toma no cambia de alto y el mapa no se mueve, a 1280, 1366 y 1440 px; a 1366 y 1440 es una sola franja de 48 px o menos, con la acción en la fila del reloj; y, armada o rodando, la tecla de «Parar toma» se ve entera';
    const sizes = [[1280, 800], [1366, 768], [1440, 900]], seen = { 1280: [], 1366: [], 1440: [] };
    const look = async st => { for (const [w, h] of sizes) { await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(150); seen[w].push({ st, ...((await slate(p)) || { h: 0, map: -1, row: false, key: false }) }); } };
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    await p.keyboard.press('2'); await p.waitForTimeout(300); await look('lista');
    if (!await arm(p)) return [[what, false, 'no llegó a armar']];
    await look('armada');
    if (!await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(300); await look('rodando');
    await p.keyboard.press('Escape'); await shows(p, '#slateWrap', /Reaplicar y preparar la/, 3000); await look('parada');
    await sim(p, 'director'); await p.click('[data-act="take-reapply"]');
    const blocked = await shows(p, '.takebar', /Falla «Tu juego conectado»/, 12000); await look('bloqueada');
    const ok = sizes.every(([w]) => { const l = seen[w], hs = l.map(x => x.h), one = w > 1280; return l.length === 5 && Math.max(...hs) - Math.min(...hs) <= 1 && (!one || (Math.max(...hs) <= 48 && l.every(x => x.row))) && new Set(l.map(x => x.map)).size === 1 && l.filter(x => /armada|rodando/.test(x.st)).every(x => x.key); });
    const out = sizes.map(([w]) => `${w} px: ` + seen[w].map(x => `${x.st} ${x.h} px${x.row || w <= 1280 ? '' : ', la acción en otra fila'}${x.key ? '' : ', tecla cortada'}`).join(' · ') + ` · mapa en ${[...new Set(seen[w].map(x => x.map))].join(' y ')}`);
    return [[what, blocked && ok, `${blocked ? '' : 'no llegó a la comprobación que falla · '}${out.join(' | ')}`]];
  }, 1366, 768);
  await R26('VIS-01 −', async p => {
    const what = 'VIS-01 − a 1600 × 960, armada, la cabecera dice entera «También para desde tu juego, con «Parar toma» (Fin)» y el estado es solo «Armada»; rodando, solo «Rodando»; y a 390 px de ancho la cabecera se parte en líneas sin salirse de la pantalla';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const s1 = await T(p, '#slateWrap'), st1 = await T(p, '#slateWrap .tstate'), whole = await p.evaluate(() => { const f = document.querySelector('.tfix'); return !!f && f.scrollWidth <= f.clientWidth + 1; });
    if (!await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(300); const st2 = await T(p, '#slateWrap .tstate');
    await p.keyboard.press('Escape'); await shows(p, '#slateWrap', /Reaplicar y preparar la/, 3000);
    await p.setViewportSize({ width: 390, height: 844 }); await p.waitForTimeout(300);
    const ph = await p.evaluate(() => { const t = document.querySelector('.takebar'); if (!t) return null; const kids = [...t.children].filter(e => e.getClientRects().length); return { lines: new Set(kids.map(e => { const q = e.getBoundingClientRect(); return Math.round((q.top + q.height / 2) / 8); })).size, inside: kids.every(e => { const q = e.getBoundingClientRect(); return q.left >= -0.5 && q.right <= innerWidth + 0.5; }) && t.scrollWidth <= t.clientWidth + 1 }; });
    const said = /También para desde tu juego, con «Parar toma» \(Fin\)/.test(s1);
    return [[what, said && whole && st1 === 'Armada' && st2 === 'Rodando' && !!ph && ph.lines > 1 && ph.inside, `armada: ${said ? 'la frase entera' : `«${s1.slice(0, 90)}»`}${whole ? '' : ', cortada'}, estado «${st1}» · rodando: «${st2}» · a 390 px: ${ph ? `${ph.lines} líneas, ${ph.inside ? 'dentro de la pantalla' : 'se sale'}` : 'sin cabecera'}`]];
  });

  // VIS-02: las cuatro pestañas de tipo de Añadir caben en el panel
  const cats = p => p.evaluate(() => {
    const c = document.querySelector('#colR .cats'); if (!c) return null;
    const r = c.getBoundingClientRect(), bs = [...c.querySelectorAll('button')];
    return { n: bs.length, out: bs.filter(b => { const q = b.getBoundingClientRect(); return q.left < r.left - 0.5 || q.right > r.right + 0.5; }).map(b => b.innerText.replace(/\s+/g, ' ').trim()), scroll: c.scrollWidth > c.clientWidth + 1 };
  });
  await R26('VIS-02 +', async p => {
    const what = 'VIS-02 + a 1366, 1440 y 1920 px, las cuatro pestañas de tipo de Añadir caben enteras en el panel y la tira no se desplaza';
    await p.click('[data-act="rtab"][data-v="add"]'); await p.waitForTimeout(200);
    const out = []; let ok = true;
    for (const [w, h] of [[1366, 768], [1440, 900], [1920, 1080]]) {
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(150);
      const c = await cats(p), good = !!c && c.n === 4 && !c.out.length && !c.scroll; ok = ok && good;
      out.push(`${w} px: ${!c ? 'sin pestañas' : c.out.length ? `se sale${c.out.length > 1 ? 'n' : ''} ${c.out.join(', ')}` : `las ${c.n} dentro`}${c && c.scroll ? ', la tira se desplaza' : ''}`);
    }
    return [[what, ok, out.join(' · ')]];
  }, 1366, 768);
  await R26('VIS-02 −', async p => {
    const what = 'VIS-02 − cada pestaña de tipo enseña su nombre y su cuenta enteros, a 12 px o más; «Animales» se puede elegir y la elegida lleva el subrayado ámbar';
    await p.click('[data-act="rtab"][data-v="add"]'); await p.waitForTimeout(200);
    await p.click('#colR .cats [data-act="lib-cat"][data-v="animal"]'); await p.waitForTimeout(200);
    const r = await p.evaluate(() => {
      const t = document.createElement('i'); t.style.color = 'var(--accent)'; document.body.appendChild(t); const amber = getComputedStyle(t).color; t.remove();
      const bs = [...document.querySelectorAll('#colR .cats button')], on = bs.find(b => b.getAttribute('aria-selected') === 'true');
      return { labels: bs.map(b => b.innerText.replace(/\s+/g, ' ').trim()), whole: bs.every(b => b.scrollWidth <= b.clientWidth + 1), px: Math.min(...bs.map(b => parseFloat(getComputedStyle(b).fontSize))), on: on ? on.innerText.replace(/\s+/g, ' ').trim() : '', under: !!on && getComputedStyle(on).borderBottomColor === amber };
    });
    const named = r.labels.length === 4 && r.labels.every(l => /^(Actores|Objetos|Infectados|Animales) \d+$/.test(l));
    return [[what, named && r.whole && r.px >= 12 && /^Animales/.test(r.on) && r.under, `${r.labels.join(' · ')} · ${r.whole ? 'enteras' : 'alguna cortada'} · ${r.px} px · elegida «${r.on}», ${r.under ? 'subrayada en ámbar' : 'sin el subrayado ámbar'}`]];
  });

  // VIS-03: barras de desplazamiento finas y en los colores del tema, tenues hasta que el ratón pasa por encima
  const sbar = (p, sel) => p.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const cs = getComputedStyle(e); return `${cs.scrollbarWidth} ${cs.scrollbarColor}`; }, sel);
  await R26('VIS-03 +', async p => {
    const what = 'VIS-03 + la Jerarquía, Propiedades, los menús y la Guía piden una barra de desplazamiento fina con los colores del tema, tenue, y la del panel que tiene el ratón encima se aviva';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150);
    const m = await p.locator('#map').boundingBox(); await p.mouse.move(m.x + m.width / 2, m.y + m.height / 2); await p.waitForTimeout(100);
    const l0 = await sbar(p, '#colL .pb'), r0 = await sbar(p, '#colR .pb');
    const l = await p.locator('#colL .pb').boundingBox(); await p.mouse.move(l.x + l.width / 2, l.y + l.height / 2); await p.waitForTimeout(100);
    const l1 = await sbar(p, '#colL .pb'), r1 = await sbar(p, '#colR .pb');
    await p.click('#bTools'); await p.waitForTimeout(150); const menu = await sbar(p, '#menu'); await p.keyboard.press('Escape'); await p.waitForTimeout(100);
    await p.click('#bGuide'); await p.waitForTimeout(400); const guide = await sbar(p, '#guide');
    const thin = [l0, r0, menu, guide].every(x => !!x && /^thin /.test(x) && !/auto/.test(x));
    return [[what, thin && l0 === r0 && l1 !== l0 && r1 === r0, `en reposo: Jerarquía «${l0}», Propiedades «${r0}» · con el ratón en la Jerarquía: «${l1}», Propiedades «${r1}» · menú «${menu}» · Guía «${guide}»`]];
  }, 1440, 900);
  await R26('VIS-03 −', async p => {
    const what = 'VIS-03 − a 1366 × 768 la Jerarquía se sigue desplazando, y las tiras de pestañas siguen sin barra';
    const r = await p.evaluate(() => { const pb = document.querySelector('#colL .pb'), can = pb.scrollHeight > pb.clientHeight; pb.scrollTop = 120; const moved = pb.scrollTop > 0; pb.scrollTop = 0; return { can, moved, tabs: [...document.querySelectorAll('.tabs')].map(e => getComputedStyle(e).scrollbarWidth) }; });
    await p.click('[data-act="rtab"][data-v="add"]'); await p.waitForTimeout(150);
    const cw = await p.evaluate(() => { const c = document.querySelector('#colR .cats'); return c ? getComputedStyle(c).scrollbarWidth : 'sin tira'; });
    return [[what, r.can && r.moved && r.tabs.length > 0 && r.tabs.every(x => x === 'none') && cw === 'none', `Jerarquía: ${r.can ? 'más larga que el panel' : 'cabe entera'}, ${r.moved ? 'se desplaza' : 'no se desplaza'} · pestañas: ${r.tabs.join(', ')} · tipos de Añadir: ${cw}`]];
  }, 1366, 768);

  // VIS-04: la cabecera y las pestañas de cada panel son una capa propia; la pestaña activa lleva el fondo del panel
  await R26('VIS-04 +', async p => {
    const what = 'VIS-04 + en oscuro, la cabecera de cada panel tiene un fondo distinto del cuerpo; la pestaña activa lleva el fondo del cuerpo y las demás, el de la cabecera';
    await dock(p);
    const l = await p.evaluate(() => {
      const bg = e => { for (; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (!/^(transparent|rgba\(0, 0, 0, 0\))$/.test(c)) return c; } return ''; };
      return [...document.querySelectorAll('.ph')].filter(__r26.shown).map(h => { const box = h.parentElement, b = box.querySelector(':scope > .pb') || box, on = h.querySelector('.tabs [aria-selected="true"]'), off = h.querySelector('.tabs [aria-selected="false"]');
        return { name: (on || h.querySelector('.pt') || h).innerText.replace(/\s+/g, ' ').trim().slice(0, 24), head: bg(h), body: bg(b), on: on ? bg(on) : null, off: off ? bg(off) : null }; });
    });
    const ok = l.length >= 3 && l.every(x => x.head !== x.body && (x.on === null || x.on === x.body) && (x.off === null || x.off === x.head));
    return [[what, ok, l.map(x => `«${x.name}»: cabecera ${x.head}, cuerpo ${x.body}${x.on ? `, activa ${x.on}` : ''}${x.off ? `, otra ${x.off}` : ''}`).join(' · ') || 'sin cabeceras']];
  }, 1440, 900);
  await R26('VIS-04 −', async p => {
    const what = 'VIS-04 − en claro, la pestaña activa sigue subrayada en ámbar, los paneles, sus cabeceras y sus pestañas siguen sin radio ni sombra, y el nombre de una pestaña sin elegir se lee a 4,5:1 o más sobre su cabecera';
    const r = await p.evaluate(() => {
      const t = document.createElement('i'); t.style.color = 'var(--accent)'; document.body.appendChild(t); const amber = getComputedStyle(t).color; t.remove();
      const on = document.querySelector('#colR .tabs [aria-selected="true"]'), off = document.querySelector('#colR .tabs [aria-selected="false"]'), cs = getComputedStyle(on);
      const flat = [...document.querySelectorAll('.panel, .ph, .tabs button')].filter(__r26.shown).every(e => { const s = getComputedStyle(e); return parseFloat(s.borderTopLeftRadius) === 0 && s.boxShadow === 'none'; });
      const bg = e => { for (; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (!/^(transparent|rgba\(0, 0, 0, 0\))$/.test(c)) return c; } return 'rgb(255, 255, 255)'; };
      const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; const [r, g, b] = c.match(/[\d.]+/g).map(Number); return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const a = lum(getComputedStyle(off).color), b = lum(bg(off));
      return { under: cs.borderBottomColor === amber && parseFloat(cs.borderBottomWidth) >= 2, flat, ratio: Math.round((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) * 100) / 100, off: off.innerText.trim() };
    });
    return [[what, r.under && r.flat && r.ratio >= 4.5, `${r.under ? 'subrayado ámbar' : 'sin el subrayado ámbar'} · ${r.flat ? 'sin radio ni sombra' : 'con radio o sombra'} · «${r.off}» a ${r.ratio}:1`]];
  }, 1440, 900, 'light');

  // VIS-05: la acción principal apagada se ve como cualquier botón apagado, no como un botón ámbar oscurecido
  const tops = p => p.evaluate(() => {
    const v = x => { const t = document.createElement('i'); t.style.cssText = `background:var(${x});color:var(${x})`; document.body.appendChild(t); const c = getComputedStyle(t).color; t.remove(); return c; };
    const a = document.querySelector('#bApply'), q = document.querySelector('#bReset');
    return { amber: v('--primary'), ink: v('--primary-ink'), apply: getComputedStyle(a).backgroundColor, color: getComputedStyle(a).color, reset: getComputedStyle(q).backgroundColor, disA: a.disabled, disQ: q.disabled, busy: a.classList.contains('busy'), txt: a.innerText.replace(/\s+/g, ' ').trim() };
  });
  await R26('VIS-05 +', async p => {
    const what = 'VIS-05 + sin backend, «Aplicar escena» apagado pierde el ámbar y se ve igual que «Quitar del juego» apagado';
    await sim(p, 'backend'); await p.waitForTimeout(300);
    const r = await tops(p);
    return [[what, r.disA && r.disQ && r.apply !== r.amber && r.apply === r.reset, `«${r.txt}» ${r.disA ? 'apagado' : 'encendido'}, fondo ${r.apply} (el ámbar es ${r.amber}) · «Quitar del juego» ${r.disQ ? 'apagado' : 'encendido'}, fondo ${r.reset}`]];
  }, 1440, 900);
  await R26('VIS-05 −', async p => {
    const what = 'VIS-05 − encendido, «Aplicar escena» sigue en ámbar con el texto oscuro, y mientras aplica también';
    const a0 = await tops(p);
    await p.locator('#map').hover(); await p.keyboard.press('Control+Enter');
    const busy = await W(p, () => { const a = document.querySelector('#bApply'); return a.disabled && a.classList.contains('busy'); }, null, 2000);
    const a1 = await tops(p); await free(p);
    return [[what, !a0.disA && a0.apply === a0.amber && a0.color === a0.ink && busy && a1.apply === a1.amber, `con cambios: «${a0.txt}», fondo ${a0.apply}, texto ${a0.color} · aplicando: ${busy ? `«${a1.txt}», fondo ${a1.apply}` : 'no llegó a aplicar'} · ámbar ${a0.amber}, texto oscuro ${a0.ink}`]];
  }, 1440, 900);

  // VIS-06: las órdenes de lo elegido van en dos columnas del mismo ancho, no en una nube de anchos distintos
  const orders = p => p.evaluate(() => {
    const f = document.querySelector('#colR [data-act="coords"]'), row = f && f.closest('.btnrow'); if (!row) return null;
    const t = document.createElement('i'); t.style.color = 'var(--st-fail)'; document.body.appendChild(t); const red = getComputedStyle(t).color; t.remove();
    const bs = [...row.querySelectorAll('.btn')].filter(__r26.shown), rs = bs.map(b => b.getBoundingClientRect()), del = bs.find(b => b.dataset.act === 'del');
    return { n: bs.length, ws: rs.map(r => Math.round(r.width)), cols: new Set(rs.map(r => Math.round(r.left))).size, rows: new Set(rs.map(r => Math.round(r.top))).size, hs: [...new Set(rs.map(r => Math.round(r.height)))],
      whole: bs.every(b => b.scrollWidth <= b.clientWidth + 1 && [...b.querySelectorAll('kbd')].every(k => k.getBoundingClientRect().right <= b.getBoundingClientRect().right + 0.5)), red: !!del && getComputedStyle(del).color === red, labels: bs.map(b => b.innerText.replace(/\s+/g, ' ').trim()) };
  });
  await R26('VIS-06 +', async p => {
    const what = 'VIS-06 + con un objeto elegido, sus cinco órdenes van en dos columnas del mismo ancho y en tres filas';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    const r = await orders(p);
    return [[what, !!r && r.n === 5 && Math.max(...r.ws) - Math.min(...r.ws) <= 1 && r.cols === 2 && r.rows === 3, r ? `${r.n} órdenes, anchos ${r.ws.join('/')} px, ${r.cols} columnas y ${r.rows} filas` : 'sin las órdenes']];
  }, 1440, 900);
  await R26('VIS-06 −', async p => {
    const what = 'VIS-06 − cada orden enseña su nombre y su tecla enteros, siguen con el alto de 26 px y «Borrar» sigue en rojo';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    const r = await orders(p);
    return [[what, !!r && r.n === 5 && r.whole && r.red && r.hs.length === 1 && r.hs[0] === 26, r ? `${r.labels.join(' · ')} · ${r.whole ? 'enteras' : 'alguna cortada'} · alto ${r.hs.join('/')} px · «Borrar» ${r.red ? 'en rojo' : 'sin el rojo'}` : 'sin las órdenes']];
  }, 1440, 900);

  // --- Revisión visual, segunda ronda (VIS-07 a VIS-13) ---
  // VIS-07: el archivo se pinta en modo estándar, como la página publicada, y la composición no se mueve
  await R26('VIS-07 +', async p => {
    const what = 'VIS-07 + el estudio abierto con file:// se pinta en modo estándar, como la página publicada';
    const m = await p.evaluate(() => document.compatMode);
    return [[what, m === 'CSS1Compat', `${m === 'CSS1Compat' ? 'modo estándar' : 'modo de compatibilidad'} (${m})`]];
  }, 1440, 900);
  // cada caja a la vista, por su sitio en el árbol; antes se igualan lo que cambia con el reloj (los «hace N s» y las animaciones) y se quitan los avisos, que van y vienen solos
  const boxes = p => p.evaluate(() => {
    document.getAnimations().forEach(a => a.cancel());
    document.querySelectorAll('[data-since]').forEach(e => { e.textContent = (e.dataset.fmt || '%').replace('%', '7 s'); e.removeAttribute('data-since'); });
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); for (let n; (n = tw.nextNode());) if (/hace \d/.test(n.textContent)) n.textContent = n.textContent.replace(/hace \d+ (s|min|h)\b/g, 'hace 7 s');
    const ts = document.querySelector('#toasts'); if (ts) ts.innerHTML = '';
    const key = e => { const k = []; for (; e && e !== document.body; e = e.parentElement) k.unshift(e.tagName.toLowerCase() + ':' + [...e.parentElement.children].indexOf(e)); return k.join('>'); };
    const name = e => e.id ? '#' + e.id : typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/)[0] : e.tagName.toLowerCase();
    const out = {};
    for (const e of document.querySelectorAll('body *')) { if (!e.getClientRects().length) continue; const r = e.getBoundingClientRect(); out[key(e)] = `${name(e)} [${[r.left, r.top, r.width, r.height].map(v => Math.round(v * 2) / 2).join(', ')}]`; }
    return out;
  });
  const layouts = async p => {
    const seen = {}, look = async n => { await p.mouse.move(2, 2); await p.waitForTimeout(250); seen[n] = await boxes(p); };
    await dock(p); await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200); await look('Escena con «Bidón azul» elegido y el panel de abajo abierto');
    if (!await apply(p) || !await arm(p)) return null;
    await p.waitForTimeout(200); await look('Rodaje con la toma armada');
    await sim(p, 'backend'); await p.waitForTimeout(300); await look('sin backend');
    return seen;
  };
  await R26('VIS-07 −', async p => {
    const what = 'VIS-07 − la composición no se mueve: en Escena con algo elegido y el panel de abajo abierto, en Rodaje con la toma armada y sin backend, cada caja está en el mismo sitio y con el mismo tamaño que con el mismo archivo en modo de compatibilidad';
    if (!/^file:/.test(URL)) return [[what, false, 'la copia en modo de compatibilidad se hace leyendo el archivo del disco: hace falta una dirección file://']];
    const fs = require('fs'), os = require('os'), { fileURLToPath, pathToFileURL } = require('url');
    const file = path.join(os.tmpdir(), `estudio-compatibilidad-${process.pid}.html`);
    fs.writeFileSync(file, fs.readFileSync(fileURLToPath(URL), 'utf8').replace(/^\s*<!doctype html>\s*/i, ''));
    const c = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
    try {
      const q = await c.newPage(); q.setDefaultTimeout(3000);
      q.on('pageerror', e => errors.push(`[pageerror] ${e.message}`)); q.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
      await q.goto(pathToFileURL(file).href); await q.waitForTimeout(900);
      const modes = [await q.evaluate(() => document.compatMode), await p.evaluate(() => document.compatMode)];
      const a = await layouts(q), b = await layouts(p);
      if (!a || !b) return [[what, false, 'no llegó a armar']];
      const diffs = [];
      for (const n of Object.keys(a)) for (const k of new Set([...Object.keys(a[n]), ...Object.keys(b[n])])) if (a[n][k] !== b[n][k]) diffs.push(`${n}: ${a[n][k] || 'no está'} → ${b[n][k] || 'no está'}`);
      return [[what, modes[0] === 'BackCompat' && diffs.length === 0, `${modes[1]} frente a ${modes[0]} · ${Object.keys(a).map(n => `${n}: ${Object.keys(a[n]).length} cajas`).join(' · ')} · ${diffs.length ? `${diffs.length} cambian: ${diffs.slice(0, 4).join(' | ')}` : 'ninguna cambia'}`]];
    } finally { await c.close().catch(() => {}); fs.rmSync(file, { force: true }); }
  }, 1440, 900);

  // VIS-08: la barra de arriba, a un solo alto, en una fila y entera a 1366 px
  const topbar = p => p.evaluate(() => {
    const t = document.querySelector('#top'), tr = t.getBoundingClientRect(), s = document.querySelector('#bTopStop');
    const items = [...t.children].filter(e => __r26.shown(e) && !e.classList.contains('grow') && !e.classList.contains('brand')), rs = items.map(e => e.getBoundingClientRect()), mids = rs.map(r => r.top + r.height / 2);
    const sr = s && __r26.shown(s) ? s.getBoundingClientRect() : null;
    return { hs: items.map((e, i) => `${e.id || e.className.split(' ')[0]} ${Math.round(rs[i].height * 2) / 2}`), spread: Math.max(...rs.map(r => r.height)) - Math.min(...rs.map(r => r.height)), bar: Math.round(tr.height), row: Math.max(...mids) - Math.min(...mids) <= 2 && rs.every(r => r.top >= tr.top - 0.5 && r.bottom <= tr.bottom + 0.5), fits: t.scrollWidth <= t.clientWidth + 1, stop: sr ? Math.round(sr.right) : null, inBar: !!sr && sr.top >= tr.top && sr.bottom <= tr.bottom };
  });
  const barStates = async p => {
    const seen = [], look = async st => { for (const [w, h] of [[1366, 768], [1440, 900]]) { await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(150); seen.push({ st, w, ...(await topbar(p)), free: await exposed(p) }); } };
    await look('Escena');
    if (!await apply(p) || !await arm(p)) return null;
    await p.mouse.move(700, 500); await look('armada');
    if (!await roll(p)) return null;
    await p.waitForTimeout(200); await look('rodando');
    return seen;
  };
  await R26('VIS-08 +', async p => {
    const what = 'VIS-08 + a 1366 y 1440 px, en Escena, armada y rodando, el documento, Escena y Rodaje, los botones y el grupo del prototipo de la barra de arriba miden lo mismo';
    const s = await barStates(p);
    if (!s) return [[what, false, 'no llegó a rodar']];
    return [[what, s.every(x => x.spread <= 0.5), s.map(x => `${x.st} a ${x.w} px: ${x.spread <= 0.5 ? `todo a ${x.hs[0].split(' ').pop()} px` : x.hs.join(', ')}`).join(' · ')]];
  }, 1366, 768);
  await R26('VIS-08 −', async p => {
    const what = 'VIS-08 − a 1366 y 1440 px, en Escena, armada y rodando, la barra sigue en una fila de 44 px y cabe entera; y Parar está en la barra, en el mismo sitio armada y rodando, y nada lo tapa (B5)';
    const s = await barStates(p);
    if (!s) return [[what, false, 'no llegó a rodar']];
    const stopAt = w => s.filter(x => x.w === w && x.st !== 'Escena').map(x => x.stop), same = [1366, 1440].every(w => { const l = stopAt(w); return l.length === 2 && l[0] !== null && l[0] === l[1]; });
    const ok = s.every(x => x.bar === 44 && x.row && x.fits) && s.filter(x => x.st !== 'Escena').every(x => x.inBar && x.free) && same;
    return [[what, ok, s.map(x => `${x.st} a ${x.w} px: ${x.bar} px, ${x.row ? 'una fila' : 'se parte'}, ${x.fits ? 'cabe' : 'no cabe'}${x.st === 'Escena' ? '' : `, Parar acaba en ${x.stop} px${x.inBar ? '' : ' fuera de la barra'}${x.free ? '' : ', tapado'}`}`).join(' · ')]];
  }, 1366, 768);

  // VIS-09: lo que flota arriba del mapa no tapa los números de la regla de X
  // las placas de los números de la regla de X, que el mapa pinta a 13 px de alto, en px de la página; se fuerza un fotograma cambiando 1 px la ventana
  const rulerX = async p => {
    await p.evaluate(() => {
      if (!window.__nx) { const P = CanvasRenderingContext2D.prototype, f = P.fillText; P.fillText = function (t, x, y, ...r) { if (this.canvas && this.canvas.id === 'map' && /^\d+$/.test(String(t)) && Math.abs(y - 13) < 0.01) { const T = this.getTransform(), d = this.canvas.width / this.canvas.clientWidth, w = this.measureText(String(t)).width, c = this.canvas.getBoundingClientRect(); window.__nx.push({ t: String(t), l: c.left + (T.a * (x - 2) + T.e) / d, r: c.left + (T.a * (x + w + 2) + T.e) / d, top: c.top + (T.d * (y - 11) + T.f) / d, b: c.top + (T.d * (y + 3) + T.f) / d }); } return f.call(this, t, x, y, ...r); }; }
      window.__nx = [];
    });
    const vs = p.viewportSize(); await p.setViewportSize({ width: vs.width, height: vs.height + 1 }); await p.waitForTimeout(150); await p.evaluate(() => { window.__nx = []; }); await p.setViewportSize(vs); await p.waitForTimeout(300);
    return p.evaluate(() => {
      const labs = [...new Map(window.__nx.map(n => [n.t + '@' + Math.round(n.l), n])).values()], name = e => e.id ? '#' + e.id : 'el grupo del zoom';
      const ov = [...document.querySelectorAll('#hint, .ovl.tr, #recBadge')].filter(__r26.shown), hits = [];
      for (const n of labs) for (const e of ov) { const r = e.getBoundingClientRect(); if (r.left < n.r && r.right > n.l && r.top < n.b && r.bottom > n.top) hits.push(`${n.t} bajo ${name(e)}`); }
      return { n: labs.length, over: ov.map(name), hits };
    });
  };
  await R26('VIS-09 +', async p => {
    const what = 'VIS-09 + a 1366 y 1440 px, con algo elegido y rodando, ni la ayuda del mapa, ni el grupo del zoom, ni «Rodando» tapan ningún número de la regla de X';
    const seen = [], look = async (st, sizes) => { for (const [w, h] of sizes) { await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(150); seen.push({ st, w, ...(await rulerX(p)) }); } };
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    await look('con «Bidón azul» elegido', [[1366, 768], [1440, 900]]);
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(200); await look('rodando', [[1440, 900], [1366, 768]]);
    return [[what, seen.every(x => x.n > 0 && !x.hits.length && x.over.length > 0), seen.map(x => `${x.st} a ${x.w} px: ${x.n} números, ${x.hits.length ? `tapados ${x.hits.slice(0, 4).join(', ')}${x.hits.length > 4 ? ` y ${x.hits.length - 4} más` : ''}` : `ninguno bajo ${x.over.join(', ')}`}`).join(' · ')]];
  }, 1366, 768);
  await R26('VIS-09 −', async p => {
    const what = 'VIS-09 − con algo elegido, la ayuda del mapa sigue diciendo cómo moverlo, a 10 px del borde izquierdo del mapa, el grupo del zoom sigue a 10 px del derecho y «Acercar» sigue acercando; y rodando, «Rodando» sigue a 10 px del borde izquierdo';
    const edges = () => p.evaluate(() => { const m = document.querySelector('#mapwrap').getBoundingClientRect(), g = s => { const e = document.querySelector(s); return e && __r26.shown(e) ? e.getBoundingClientRect() : null; }, h = g('#hint'), z = g('.ovl.tr'), r = g('#recBadge'); return { hint: h && Math.round(h.left - m.left), zoom: z && Math.round(m.right - z.right), rec: r && Math.round(r.left - m.left), text: document.querySelector('#hint').innerText.replace(/\s+/g, ' ').trim() }; });
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    // el foco se queda en «Acercar», y entonces Intro lo pulsaría en vez de rodar
    const e1 = await edges(), z0 = await zoomOf(p); await p.click('#bZin'); await p.waitForTimeout(300); const z1 = await zoomOf(p); await p.evaluate(() => document.activeElement.blur());
    if (!await apply(p) || !await arm(p) || !await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(200); const e2 = await edges(), rec = await T(p, '#recBadge');
    return [[what, /^Arrastra para mover/.test(e1.text) && e1.hint === 10 && e1.zoom === 10 && z1 > z0 && /^Rodando/.test(rec) && e2.rec === 10, `ayuda «${e1.text.slice(0, 48)}…» a ${e1.hint} px · zoom a ${e1.zoom} px · «Acercar»: ${z0.toFixed(2)} → ${z1.toFixed(2)} px/m · «${rec.slice(0, 16)}…» a ${e2.rec} px`]];
  }, 1440, 900);

  // VIS-10: dentro de un botón, de Escena y Rodaje o de un menú, la tecla va en texto tenue y sin caja
  // cada tecla a la vista con su caja (borde, fondo o relleno), su tamaño y su contraste: su color sobre los fondos de debajo, compuestos en un lienzo de 1 px
  const keysIn = (p, sel) => p.evaluate(s => {
    const g = document.createElement('canvas').getContext('2d'), px = () => [...g.getImageData(0, 0, 1, 1).data].slice(0, 3);
    const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    return [...document.querySelectorAll(s)].filter(__r26.shown).map(k => {
      const cs = getComputedStyle(k), host = k.closest('button') || k.parentElement, chain = [];
      for (let e = k; e; e = e.parentElement) chain.unshift(getComputedStyle(e).backgroundColor);
      g.clearRect(0, 0, 1, 1); g.fillStyle = '#fff'; g.fillRect(0, 0, 1, 1); chain.forEach(c => { g.fillStyle = c; g.fillRect(0, 0, 1, 1); }); const bg = px();
      g.fillStyle = cs.color; g.fillRect(0, 0, 1, 1); const a = lum(px()), b = lum(bg);
      return { key: k.textContent.trim(), host: (host.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 28), off: !!host.disabled, boxed: (cs.borderTopStyle !== 'none' && parseFloat(cs.borderTopWidth) > 0) || !/^(transparent|rgba\(0, 0, 0, 0\))$/.test(cs.backgroundColor) || parseFloat(cs.paddingLeft) > 0, px: parseFloat(cs.fontSize), ratio: Math.round((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) * 100) / 100 };
    });
  }, sel);
  const IN_BUTTONS = '.btn kbd, .seg kbd, .mi kbd';
  // al cambiar de tema, el fondo de los botones se funde en 0,12 s y el color de la tecla cambia de golpe: se lee cuando acaban esas transiciones,
  // que en una máquina cargada pueden seguir a medias pasados 150 ms (getAnimations aplica antes el cambio de estilo pendiente; como mucho 2 s)
  const settled = p => p.evaluate(() => Promise.race([Promise.all(document.getAnimations().filter(a => a instanceof CSSTransition).map(a => a.finished.catch(() => {}))), new Promise(r => setTimeout(r, 2000))]));
  // en Escena con algo elegido y con los dos menús abiertos, y en Rodaje con la toma armada; en el tema que toque
  const keyStates = async (p, themes) => {
    const all = [], take = async st => { for (const th of themes) { if (themes.length > 1) { await p.emulateMedia({ colorScheme: th }); await p.waitForTimeout(150); await settled(p); } (await keysIn(p, IN_BUTTONS)).forEach(k => all.push({ ...k, st, th })); } };
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200); await take('Escena');
    await p.click('#bTools'); await p.waitForTimeout(150); await take('Herramientas'); await p.keyboard.press('Escape'); await p.waitForTimeout(100);
    await p.click('#docBtn'); await p.waitForTimeout(150); await take('menú de la escena'); await p.keyboard.press('Escape'); await p.waitForTimeout(100);
    if (!await apply(p) || !await arm(p)) return null;
    await take('armada');
    return all;
  };
  await R26('VIS-10 +', async p => {
    const what = 'VIS-10 + las teclas dentro de los botones, de Escena y Rodaje y de los menús van sin caja: sin borde, sin fondo y sin relleno, también en «Rodar» y en «Desarmar»';
    const all = await keyStates(p, ['dark']);
    if (!all) return [[what, false, 'no llegó a armar']];
    const boxed = all.filter(k => k.boxed), hosts = ['Rodar', 'Desarmar', 'Escena', 'Guardar'].filter(h => all.some(k => k.host.startsWith(h)));
    return [[what, all.length > 0 && !boxed.length && hosts.length === 4, `${all.length} teclas en ${[...new Set(all.map(k => k.st))].join(', ')} · ${boxed.length ? `con caja: ${[...new Set(boxed.map(k => `«${k.key}» en «${k.host}»`))].slice(0, 5).join(', ')}` : 'ninguna con caja'}${hosts.length === 4 ? '' : ` · no se vieron teclas en ${['Rodar', 'Desarmar', 'Escena', 'Guardar'].filter(h => !hosts.includes(h)).join(', ')}`}`]];
  }, 1440, 900);
  await R26('VIS-10 −', async p => {
    const what = 'VIS-10 − en oscuro y en claro, cada tecla dentro de un botón encendido, de Escena y Rodaje o de un menú se lee a 4,5:1 o más sobre su fondo y a 12 px o más, también en «Rodar» y en «Desarmar»; y las teclas dentro del texto, en la ayuda del mapa y en la Guía, siguen en su caja';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    const hint = await keysIn(p, '#hint kbd');
    await p.click('#bGuide'); await p.waitForTimeout(400); const guide = await keysIn(p, '#guide kbd'); await p.click('#bGuideClose'); await p.waitForTimeout(300);
    const all = await keyStates(p, ['dark', 'light']);
    if (!all) return [[what, false, 'no llegó a armar']];
    const on = all.filter(k => !k.off), low = on.filter(k => k.ratio < 4.5), tiny = all.filter(k => k.px < 12), worst = th => { const l = on.filter(k => k.th === th); return l.length ? Math.min(...l.map(k => k.ratio)) : 0; };
    const seen = ['Rodar', 'Desarmar'].every(h => ['dark', 'light'].every(th => on.some(k => k.th === th && k.host.startsWith(h))));
    const prose = hint.length > 0 && guide.length > 0 && hint.every(k => k.boxed) && guide.every(k => k.boxed);
    return [[what, on.length > 0 && !low.length && !tiny.length && seen && prose, `${on.length} teclas en botones encendidos · la que menos, ${worst('dark')}:1 en oscuro y ${worst('light')}:1 en claro${low.length ? ` · por debajo: ${low.slice(0, 4).map(k => `«${k.key}» en «${k.host}» (${k.th}) ${k.ratio}:1`).join(', ')}` : ''} · ${tiny.length ? `${tiny.length} por debajo de 12 px` : 'todas a 12 px o más'}${seen ? '' : ' · faltan «Rodar» o «Desarmar»'} · en el texto: ${hint.length} en la ayuda y ${guide.length} en la Guía, ${prose ? 'en su caja' : 'alguna sin caja'}`]];
  }, 1440, 900);

  // VIS-11: los campos numéricos sin las flechas del navegador
  await R26('VIS-11 +', async p => {
    const what = 'VIS-11 + los campos numéricos de Propiedades piden el aspecto de un campo de texto, y con el ratón en el extremo derecho de la X no salen las flechas del navegador';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(200);
    const ap = await p.evaluate(() => [...document.querySelectorAll('#colR .nin input')].filter(__r26.shown).map(i => `${i.id} ${getComputedStyle(i).appearance}`));
    const b = await p.locator('#f-x').boundingBox(), clip = { x: b.x + b.width - 20, y: b.y + 2, width: 18, height: b.height - 4 };
    await p.mouse.move(2, 2); await p.waitForTimeout(150); const s0 = await p.screenshot({ clip });
    await p.mouse.move(b.x + b.width - 8, b.y + b.height / 2); await p.waitForTimeout(250); const s1 = await p.screenshot({ clip });
    const same = s0.equals(s1);
    return [[what, ap.length > 0 && ap.every(x => / textfield$/.test(x)) && same, `${ap.join(' · ')} · con el ratón encima, el extremo derecho de la X ${same ? 'no cambia' : 'cambia: salen las flechas'}`]];
  }, 1440, 900);
  await R26('VIS-11 −', async p => {
    const what = 'VIS-11 − con el foco en la X, la flecha arriba la sube 0,1 m en un solo cambio del historial y el borde del campo se pone en ámbar; y la rueda encima de la Z la sigue subiendo 0,1 m por paso';
    await dock(p); await p.click('#colL [data-act="sel"][data-v="ent:obj-13"]'); await p.waitForTimeout(150);
    const n0 = await nHist(p), x0 = await val(p, '#f-x');
    await p.click('#f-x'); await p.keyboard.press('ArrowUp'); await p.waitForTimeout(200);
    const x1 = await val(p, '#f-x'), n1 = await nHist(p);
    const ring = await p.evaluate(() => { const t = document.createElement('i'); t.style.color = 'var(--accent)'; document.body.appendChild(t); const a = getComputedStyle(t).color; t.remove(); const f = document.querySelector('#f-x'); return { on: document.activeElement === f, border: getComputedStyle(f.closest('.nin')).borderTopColor, accent: a }; });
    await over(p, '#f-z'); const z0 = await val(p, '#f-z'); await wheel(p, -100); const z1 = await val(p, '#f-z');
    const d1 = Math.round((x1 - x0) * 10) / 10, d2 = Math.round((z1 - z0) * 10) / 10;
    return [[what, d1 === 0.1 && n1 === n0 + 1 && ring.on && ring.border === ring.accent && d2 === 0.1, `X ${x0} → ${x1} (+${d1}), historial ${n1 - n0 >= 0 ? '+' : ''}${n1 - n0} · ${ring.on ? 'con el foco' : 'sin el foco'}, borde ${ring.border}${ring.border === ring.accent ? ', el ámbar' : ` (el ámbar es ${ring.accent})`} · rueda en la Z: ${z0} → ${z1} (+${d2})`]];
  }, 1440, 900);

  // VIS-12: los nombres largos de Cámaras van en una línea, con puntos suspensivos y enteros al pasar el ratón; «En la toma» no los parte
  const camList = p => p.evaluate(() => {
    const lines = e => { const r = document.createRange(); r.selectNodeContents(e); return new Set([...r.getClientRects()].filter(q => q.width > 0).map(q => Math.round(q.top))).size; };
    const mid = e => { const q = e.getBoundingClientRect(); return q.top + q.height / 2; };
    return [...document.querySelectorAll('#colL .camrow')].filter(__r26.shown).map(r => { const b = r.querySelector('b'), s = r.querySelector('small'), lv = r.querySelector('.live');
      return { v: r.dataset.v, name: b.textContent, sum: s.textContent, nl: lines(b), sl: lines(s), cut: b.scrollWidth > b.clientWidth + 1, ell: getComputedStyle(b).textOverflow === 'ellipsis', title: b.title, live: lv ? { text: lv.textContent, l: lines(lv), whole: lv.scrollWidth <= lv.clientWidth + 1, row: Math.abs(mid(lv) - mid(b)) <= 3 } : null }; });
  });
  const toCams = async p => { await p.keyboard.press('2'); await p.waitForTimeout(300); if (await p.locator('[data-act="ltab"][data-v="camaras"][aria-selected="false"]').count()) { await p.click('[data-act="ltab"][data-v="camaras"]'); await p.waitForTimeout(200); } };
  await R26('VIS-12 +', async p => {
    const what = 'VIS-12 + a 1366 y 1440 px, cada nombre y cada resumen de Cámaras va en una línea; el nombre cortado acaba en puntos suspensivos y se lee entero al pasar el ratón, y «En la toma» va en la línea del nombre';
    await toCams(p);
    const out = []; let ok = true;
    for (const [w, h] of [[1366, 768], [1440, 900]]) {
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(150);
      const l = await camList(p), good = l.length >= 3 && l.every(c => c.nl === 1 && c.sl === 1 && c.title === c.name && (!c.cut || c.ell) && (!c.live || c.live.row)) && l.some(c => c.live); ok = ok && good;
      out.push(`${w} px: ` + l.map(c => `«${c.name}» ${c.nl} línea${c.nl > 1 ? 's' : ''}${c.cut ? (c.ell ? ', con puntos suspensivos' : ', cortado a secas') : ''}${c.title === c.name ? '' : ', sin el nombre entero al pasar el ratón'}, resumen en ${c.sl}${c.live ? (c.live.row ? ', «En la toma» en su línea' : ', «En la toma» en otra línea') : ''}`).join(' · '));
    }
    return [[what, ok, out.join(' | ')]];
  }, 1366, 768);
  await R26('VIS-12 −', async p => {
    const what = 'VIS-12 − a 1366 px los nombres cortos no se cortan, «En la toma» se lee entero en una línea, los resúmenes siguen diciendo «Fija» o el camino con sus claves y sus segundos, y un clic en una cámara la elige';
    await toCams(p);
    const l = await camList(p), short = l.filter(c => /^(Plano general|Primer plano de Linda)$/.test(c.name)), live = l.find(c => c.live);
    const said = l.length >= 3 && l.every(c => /^(Fija|Camino · \d+ claves? · \d+,\d s)$/.test(c.sum));
    const pick = l.find(c => !c.live);
    if (pick) { await p.click(`#colL .camrow[data-v="${pick.v}"]`); await p.waitForTimeout(200); }
    const sel = pick ? await p.getAttribute(`#colL .camrow[data-v="${pick.v}"]`, 'aria-selected') : null;
    return [[what, short.length >= 2 && short.every(c => !c.cut) && !!live && live.live.whole && live.live.l === 1 && said && sel === 'true', `${short.map(c => `«${c.name}» ${c.cut ? 'cortado' : 'entero'}`).join(' · ')} · ${live ? `«${live.live.text}» ${live.live.whole && live.live.l === 1 ? 'entero en una línea' : 'cortado o partido'}` : 'sin «En la toma»'} · resúmenes: ${l.map(c => `«${c.sum}»`).join(', ')} · clic en «${pick ? pick.name : '?'}»: ${sel === 'true' ? 'elegida' : 'sin elegir'}`]];
  }, 1366, 768);

  // VIS-13: el aviso de la toma armada se va al rodar. Queda fuera del aspecto: lo pide la coordinación, porque rodando dice cómo desarmar
  const notes = p => p.evaluate(() => [...document.querySelectorAll('#toasts .toast')].filter(e => __r26.shown(e) && +getComputedStyle(e).opacity > 0.05).map(e => ({ text: e.innerText.replace(/\s+/g, ' ').trim(), fail: e.classList.contains('fail') })));
  const said = l => l.length ? l.map(x => `«${x.text}»`).join(' ') : 'ningún aviso';
  await R26('VIS-13 +', async p => {
    const what = 'VIS-13 + al rodar, el aviso «Toma NN armada…» ya no está a la vista, ni el que sale con Espacio y la toma armada';
    const armed = l => l.some(x => /^Toma \d+ armada/.test(x.text)), space = l => l.some(x => /^Espacio solo para una toma que rueda/.test(x.text));
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const t0 = await notes(p);
    if (!await roll(p)) return [[what, false, 'no llegó a rodar']];
    await p.waitForTimeout(150); const t1 = await notes(p);
    await p.keyboard.press('Escape');
    if (!await shows(p, '#slateWrap', /Reaplicar y preparar la/, 3000)) return [[what, false, `armada: ${said(t0)} → rodando: ${said(t1)} · no llegó a parar`]];
    await p.click('[data-act="take-reapply"]');
    if (!await shows(p, '#bTopStop', /Desarmar/, 15000)) return [[what, false, `armada: ${said(t0)} → rodando: ${said(t1)} · no llegó a armar otra vez`]];
    await p.evaluate(() => { if (document.activeElement) document.activeElement.blur(); }); await p.locator('#map').hover(); await p.keyboard.press('Space'); await p.waitForTimeout(150); const t2 = await notes(p);
    if (!await roll(p)) return [[what, false, 'no llegó a rodar la segunda vez']];
    await p.waitForTimeout(150); const t3 = await notes(p);
    return [[what, armed(t0) && !armed(t1) && space(t2) && !space(t3), `armada: ${said(t0)} → rodando: ${said(t1)} · armada otra vez, con Espacio: ${said(t2)} → rodando: ${said(t3)}`]];
  }, 1440, 900);
  await R26('VIS-13 −', async p => {
    const what = 'VIS-13 − armada, sigue saliendo «Toma NN armada. Intro para rodar y Esc para desarmar.»; y los demás avisos no cambian: sin backend sale «Backend parado…» con la franja de conexión, e Intro dice «Sin conexión con el backend: la toma no sale de la web.», no rueda y el aviso sigue a la vista un segundo después';
    if (!await apply(p) || !await arm(p)) return [[what, false, 'no llegó a armar']];
    const t0 = await notes(p);
    await sim(p, 'backend'); await p.waitForTimeout(300); const t1 = await notes(p), ban = await T(p, '#banner');
    await p.locator('#map').hover(); await p.keyboard.press('Enter'); await p.waitForTimeout(250); const t2 = await notes(p), st = await T(p, '#bTopStop');
    await p.waitForTimeout(1000); const t3 = await notes(p);
    const NO = 'Sin conexión con el backend: la toma no sale de la web.', gone = l => l.length === 1 && l[0].fail && l[0].text === NO;
    const ok = t0.length === 1 && /^Toma \d+ armada\. \S+ para rodar y \S+ para desarmar\.$/.test(t0[0].text) && t1.length === 1 && t1[0].fail && /^Backend parado/.test(t1[0].text) && /^Sin conexión con el backend/.test(ban) && gone(t2) && /^Desarmar/.test(st) && gone(t3);
    return [[what, ok, `armada: ${said(t0)} · sin backend: ${said(t1)}, franja «${ban.slice(0, 40)}…» · Intro: ${said(t2)}, Parar dice «${st}» · un segundo después: ${said(t3)}`]];
  }, 1440, 900);

  // --- Tercera revisión de Astra (ui/astra/2026-11-10-ui-revision3-astra.md): AR3-01 a AR3-05 ---
  // AR3-01: la sonda mide la letra en el fotograma acabado, sigue las copias de píxeles y los patrones, y pide franjas con dirección
  for (const scheme of ['dark', 'light']) await R26(`AR3-01 + ${scheme}`, async p => {
    const what = `AR3-01 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, en Rodaje con el cursor a 3 s, cada texto que se espera está pintado y todos los pintados llegan a 4,5:1 en cada píxel de su letra también en el fotograma acabado, cada halo tiene su letra legible encima, ninguna imagen ni patrón con texto queda sin medir, y la estimación de Mirek se ve en franjas con dirección`;
    await p.keyboard.press('2'); await p.waitForTimeout(300); await scrub(p, 3); await p.mouse.move(5, 5); await p.waitForTimeout(200);
    const r = await readable(p, ['Mirek', 'Linda', 'Mirek · estimado', 'Mirek · M1', 'Mirek · M2', 'Travelling del autobús · K1', 'Travelling del autobús · K2', 'Travelling del autobús · K3', 'trayectoria prevista']), f = r.f;
    const halos = f.images.filter(i => i.halo).length, lettered = f.texts.filter(t => t.halo && t.fin && t.fin.n > 0 && !t.fin.low).length;
    const fin = f.texts.filter(t => t.n > 0), minFin = Math.min(...fin.map(t => t.fin ? t.fin.min : 0)), h = hatched(f);
    return [[what, r.ok && halos > 0 && lettered === halos && fin.every(t => t.fin) && h.length === 1 && striped(f).length === 1, `${r.info} · ${halos} halos, ${lettered} con su letra legible al acabar · peor letra al acabar ${minFin}:1 · estimación: ${showStripes(h[0] && h[0].stripes)}`]];
  }, 1600, 960, scheme);
  await R26('AR3-01 −', async p => {
    // a mano sobre el mapa: cada ataque de Astra tiene que caer por su propiedad, no por faltar un texto del inventario
    const r = await p.evaluate(() => {
      const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth, cv = window.__cv;
      Object.assign(cv, { texts: [], strokes: [], fills: [], images: [], on: true });
      g.save(); g.setTransform(d, 0, 0, d, 0, 0);
      const plate = (t, x, y) => { g.font = '500 12px monospace'; g.fillStyle = 'rgb(200,197,182)'; g.fillRect(x - 2, y - 11, g.measureText(t).width + 4, 14); g.fillStyle = '#222116'; g.fillText(t, x, y); };
      const aux = (t, color, w = 100, h = 30, r = 0) => { const q = document.createElement('canvas'); q.width = w; q.height = h; const x = q.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = color; for (let u = -r; u <= r; u++) for (let v = -r; v <= r; v++) if (u * u + v * v <= r * r + 1) x.fillText(t, 2 + u, 15 + v); return q; };
      // 1. repintado pálido con putImageData después de la letra, como el mutante «texto-final»
      plate('6150', 44, 54);
      const b = g.getImageData(42 * d, 43 * d, 40 * d, 14 * d); for (let i = 0; i < b.data.length; i += 4) if (Math.max(b.data[i], b.data[i + 1], b.data[i + 2]) < 136) b.data[i] = b.data[i + 1] = b.data[i + 2] = 136; g.putImageData(b, 42 * d, 43 * d);
      // 2. un velo pálido encima, sin tocar píxeles a mano
      plate('6250', 44, 84); g.fillStyle = 'rgba(200,197,182,.75)'; g.fillRect(40, 70, 40, 18);
      // 3. halo con su letra pintada a opacidad 0, como «halo-sin-letra»
      g.drawImage(aux('6350', 'rgb(200,197,182)', 60, 24, 2), 40, 100); g.font = '500 12px monospace'; g.fillStyle = '#222116'; g.save(); g.filter = 'opacity(0)'; g.fillText('6350', 42, 115); g.restore();
      // 4. texto pálido pasado de un lienzo a otro con getImageData y putImageData, como «imagen-sin-tag»
      const ex = aux('SIN LECTURA', '#888', 150, 24), cp = document.createElement('canvas'); cp.width = 150; cp.height = 24; cp.getContext('2d').putImageData(ex.getContext('2d').getImageData(0, 0, 150, 24), 0, 0); g.drawImage(cp, 40, 130);
      // 5. texto dentro de un patrón
      g.fillStyle = g.createPattern(aux('6450', '#888', 40, 20), 'repeat'); g.fillRect(40, 160, 40, 20);
      // 6. un tablero de 2 px, como «ajedrez2», y el rayado de la página (su mismo azulejo), en un círculo cada uno
      const tile = draw => { const q = document.createElement('canvas'); q.width = q.height = 6; const h = q.getContext('2d'); draw(h); return g.createPattern(q, 'repeat'); };
      const chk = tile(h => { h.fillStyle = '#fff'; h.fillRect(0, 0, 6, 6); h.fillStyle = '#000'; for (let yy = 0; yy < 6; yy++) for (let xx = 0; xx < 6; xx++) if ((Math.floor(xx / 2) + Math.floor(yy / 2)) % 2 === 0) h.fillRect(xx, yy, 1, 1); });
      const hat = tile(h => { h.fillStyle = 'rgba(255,255,255,.8)'; h.fillRect(0, 0, 6, 6); h.strokeStyle = '#18191a'; h.lineWidth = 1.6; h.beginPath(); h.moveTo(-1, 7); h.lineTo(7, -1); h.moveTo(-1, 1); h.lineTo(1, -1); h.moveTo(5, 7); h.lineTo(7, 5); h.stroke(); });
      [[chk, 200], [hat, 240]].forEach(([pat, x]) => { g.save(); g.translate(x, 60); g.beginPath(); g.arc(0, 0, 8.75, 0, Math.PI * 2); g.fillStyle = pat; g.fill(); g.restore(); });
      // 7. control: un halo con su letra oscura dentro, que tiene que pasar
      g.drawImage(aux('6550', 'rgb(200,197,182)', 60, 24, 2), 40, 190); g.font = '500 12px monospace'; g.fillStyle = '#222116'; g.fillText('6550', 42, 205);
      g.restore(); cv.on = false; cv.finish();
      return { texts: cv.texts.map(t => ({ text: t.text, n: t.n, low: t.low, fin: t.fin, halo: !!t.halo })), images: cv.images.map(i => ({ kind: i.kind, texts: i.texts, halo: i.halo })), fills: cv.fills.filter(f => f.pat).map(f => f.stripes) };
    });
    const tx = t => r.texts.find(x => x.text === t), im = t => r.images.find(i => i.texts.includes(t)), see = t => t ? `«${t.text}» al pintar ${t.low} de ${t.n} px bajos, al acabar ${t.fin ? `${t.fin.low} (${t.fin.min}:1)` : 'sin medir'}` : 'no está';
    const late = t => !!t && t.n > 0 && t.low === 0 && !!t.fin && t.fin.low > 0;
    const [a, b, c, k] = ['6150', '6250', '6350', '6550'].map(tx), [chk, hat] = r.fills;
    return [
      ['AR3-01 − una letra legible al pintarla y repintada después con píxeles pálidos (putImageData) cae por su contraste en el fotograma acabado, y esos píxeles puestos en el mapa quedan además como imagen sin medir', late(a) && !!im('6150') && unmeasured(im('6150')) && im('6150').kind === 'píxeles', `${see(a)} · ${im('6150') ? im('6150').kind : 'sin imagen'}`],
      ['AR3-01 − un velo pálido encima de una letra ya pintada cae por su contraste en el fotograma acabado', late(b), see(b)],
      ['AR3-01 − un halo con su letra pintada a opacidad 0 cuenta como halo, pero su letra cae en el fotograma acabado', late(c) && c.halo, `${see(c)}${c && c.halo ? ', tras su halo' : ''}`],
      ['AR3-01 − un texto pasado de un lienzo a otro con getImageData y putImageData llega al mapa con su texto y queda sin medir; un patrón con texto, también', !!im('SIN LECTURA') && unmeasured(im('SIN LECTURA')) && !!im('6450') && im('6450').kind === 'patrón' && unmeasured(im('6450')), r.images.filter(i => i.texts.length).map(i => `${i.kind} «${i.texts.slice(0, 2).join('», «')}»${i.texts.length > 2 ? ` y ${i.texts.length - 2} textos más` : ''} ${unmeasured(i) ? 'sin medir' : 'halo'}`).join(' · ')],
      ['AR3-01 − un tablero de 2 px no cuenta como rayado; el azulejo del rayado de la página, sí', !!chk && !STRIPES(chk) && !!hat && STRIPES(hat), `tablero: ${showStripes(chk)} · rayado: ${showStripes(hat)}`],
      ['AR3-01 − el control, un halo con su letra oscura, pasa al pintarla y al acabar', !!k && k.halo && k.n > 0 && k.low === 0 && !!k.fin && k.fin.low === 0, see(k)]
    ];
  });
  // AR3-02: la lectura al volver solo vale si la conexión sigue igual cuando llega
  const flip = (p, v) => p.evaluate(v => { document.querySelector('#bSim').click(); document.querySelector(`#menu [data-act="sim"][data-v="${v}"]`).click(); document.querySelector('#status').click(); }, v);
  const lostTake = async p => {
    if (!await apply(p) || !await arm(p) || !await roll(p)) return null;
    await p.waitForTimeout(600); await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(100);
    return (await T(p, '#slateWrap .tn')) || 'Toma';
  };
  const takeRow = (p, tn) => p.evaluate(tn => { const r = [...document.querySelectorAll('#dock .qrow')].filter(x => x.innerText.includes(tn)).pop(); return r ? { obs: !!r.querySelector('.chip.observado'), text: r.innerText.replace(/\s+/g, ' ') } : null; }, tn);
  const confirmed = p => p.evaluate(() => /Parada confirmada al leer el juego/.test(document.querySelector('#toasts').innerText));
  await R26('AR3-02 +', async p => {
    const what = 'AR3-02 + cortado tu juego mientras rueda, la parada queda sin confirmar; al volver la conexión estable se confirma una vez, leyendo, con su origen y una edad nueva, sin sumar otra toma, y se quita la recuperación';
    const tn = await lostTake(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    await flip(p, 'director');
    if (!await shows(p, '#bTopStop', /sin confirmar/, 6000)) return [[what, false, 'no quedó sin confirmar']];
    // la toma cortada ya está en Tomas al quedar sin confirmar: la lectura al volver no tiene que sumar otra
    const k0 = await takesN(p); await flip(p, 'director');
    const conf = await W(p, () => /Parada confirmada al leer el juego/.test(document.querySelector('#toasts').innerText), null, 4000), o = await takeRow(p, tn), k1 = await takesN(p);
    const gone = await W(p, () => document.querySelector('#bTopStop').hidden, null, 2000);
    return [[what, conf && !!o && o.obs && /lectura al volver/.test(o.text) && /Leída hace [0-2] s/.test(o.text) && k1 === k0 && gone, `${conf ? 'confirmada' : 'sin confirmar'} · fila: «${o ? o.text.slice(0, 120) : 'no está'}» · Tomas ${k0} → ${k1} · recuperación ${gone ? 'quitada' : 'a la vista'}`]];
  });
  for (const [peer, name] of [['director', 'tu juego'], ['server', 'el servidor'], ['backend', 'el backend']]) await R26(`AR3-02 − ${name}`, async p => {
    const what = `AR3-02 − parada sin confirmar, ${name} vuelve y se corta otra vez a los 100 ms: a los 850 ms no hay Observado ni «lectura al volver» ni aviso de confirmada, y la recuperación sigue a la vista; al volver estable, se confirma una sola vez`;
    const tn = await lostTake(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    await flip(p, peer);
    if (!await shows(p, '#bTopStop', /sin confirmar/, 6000)) return [[what, false, 'no quedó sin confirmar']];
    await flip(p, peer); await p.waitForTimeout(100); await flip(p, peer); await p.waitForTimeout(850);
    const o1 = await takeRow(p, tn), c1 = await confirmed(p), st1 = await T(p, '#bTopStop');
    const fake = c1 || !/sin confirmar/.test(st1) || (!!o1 && (o1.obs || /lectura al volver/.test(o1.text)));
    await p.evaluate(() => { window.__nConf = 0; new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(x => { if (/Parada confirmada al leer el juego/.test(x.textContent)) window.__nConf++; }))).observe(document.querySelector('#toasts'), { childList: true }); });
    await flip(p, peer);
    const conf = await W(p, () => /Parada confirmada al leer el juego/.test(document.querySelector('#toasts').innerText), null, 4000);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(() => window.__nConf), o2 = await takeRow(p, tn);
    return [[what, !fake && conf && n === 1 && !!o2 && o2.obs && /lectura al volver/.test(o2.text), `a los 850 ms: ${c1 ? 'aviso de confirmada' : 'sin aviso'}, Parar «${st1.slice(0, 40)}», fila «${o1 ? o1.text.slice(0, 90) : 'no está'}» · al volver estable: ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar'}, fila «${o2 ? o2.text.slice(0, 90) : 'no está'}»`]];
  });
  // AR3-03: Guardar sin backend no dice «Guardado»
  const saveOut = async p => { await p.locator('#map').hover(); await p.keyboard.press('Control+s'); await p.waitForTimeout(250); return T(p, '#toasts'); };
  await R26('AR3-03 +', async p => {
    const what = 'AR3-03 + con conexión, Ctrl+S y Guardar del menú de la escena dicen «Guardado» y la escena sigue igual';
    const d0 = await T(p, '#docBtn'), m1 = await saveOut(p);
    await p.click('#docBtn'); await p.waitForTimeout(150); const dis = await p.locator('#menu [data-act="m-save"]').isDisabled();
    await p.evaluate(() => { document.querySelector('#toasts').innerHTML = ''; }); await p.click('#menu [data-act="m-save"]'); await p.waitForTimeout(250);
    const m2 = await T(p, '#toasts'), d1 = await T(p, '#docBtn');
    return [[what, /Guardado\./.test(m1) && !dis && /Guardado\./.test(m2) && d0.split('·')[0] === d1.split('·')[0], `Ctrl+S: «${m1.slice(-60)}» · menú: Guardar ${dis ? 'apagado' : 'encendido'}, «${m2.slice(-60)}» · escena «${d1}»`]];
  });
  await R26('AR3-03 −', async p => {
    const what = 'AR3-03 − sin backend, Ctrl+S y el menú no dicen «Guardado»: Ctrl+S explica que no se guarda y que la escena sigue como se guardó, Guardar sale apagado con ese motivo, y la escena y su edad no cambian';
    await sim(p, 'backend'); await p.waitForTimeout(300);
    const s0 = await p.getAttribute('#docBtn [data-since]', 'data-since'), d0 = await T(p, '#docBtn'), m1 = await saveOut(p);
    await p.click('#docBtn'); await p.waitForTimeout(150);
    const dis = await p.locator('#menu [data-act="m-save"]').isDisabled(), note = await T(p, '#menu .note');
    await p.evaluate(() => { document.querySelector('#toasts').innerHTML = ''; }); await p.click('#menu [data-act="m-save"]', { force: true, timeout: 1000 }).catch(() => {}); await p.waitForTimeout(250);
    const m2 = await T(p, '#toasts'), s1 = await p.getAttribute('#docBtn [data-since]', 'data-since'), d1 = await T(p, '#docBtn');
    return [[what, !/Guardado\./.test(m1) && /no se guarda/.test(m1) && /como se guardó la última vez/.test(m1) && dis && /Guardar tampoco/.test(note) && !/Guardado\./.test(m2) && s0 === s1 && d0.split('·')[0] === d1.split('·')[0], `Ctrl+S: «${m1.slice(-90)}» · menú: Guardar ${dis ? 'apagado' : 'encendido'}, nota ${/Guardar tampoco/.test(note) ? 'con el motivo' : 'sin el motivo'} · edad ${s0 === s1 ? 'igual' : 'cambiada'}`]];
  });
  // AR3-05: la nota de la línea de tiempo se lee. Lo que se ve de ella acaba donde acaba su caja, menos los puntos suspensivos (8 px)
  const tlnote = async p => { await p.keyboard.press('2'); await p.waitForTimeout(300); return p.evaluate(() => {
    const n = document.querySelector('.tlnote'); if (!n || !n.firstChild) return null;
    const t = n.firstChild, end = i => { const r = document.createRange(); r.setStart(t, 0); r.setEnd(t, i); return r.getBoundingClientRect().right; }, box = n.getBoundingClientRect(), cut = n.scrollWidth > n.clientWidth + 1;
    const k = t.textContent.search(/no mueve el juego/i), sees = k >= 0 && end(k + 17) <= box.right - (cut ? 8 : 0) + 0.5;
    const b = document.querySelector('[data-act="tl-play"]'), desc = b && b.getAttribute('aria-describedby') === n.id && !!n.id;
    return { text: t.textContent, cut, sees, title: n.title || '', desc, w: Math.round(box.width) };
  }); };
  const fullNote = n => /actores estimados/.test(n.title) && /no mueve nada en el juego/.test(n.title);
  for (const [w, h] of [[1280, 800], [1366, 768], [1440, 900]]) await R26(`AR3-05 + ${w}`, async p => {
    const n = await tlnote(p);
    return [[`AR3-05 + a ${w} × ${h}, en Rodaje se lee en la nota de la línea de tiempo que no mueve el juego, la frase entera, con la cámara y los actores estimados, sale al pasar el ratón, y la nota es la descripción de Previsualizar`, !!n && n.sees && fullNote(n) && n.desc, n ? `«${n.text}» en ${n.w} px${n.cut ? ', cortada' : ', entera'}; «no mueve el juego» ${n.sees ? 'a la vista' : 'cortado'} · al pasar el ratón: ${n.title ? '«' + n.title + '»' : 'nada'} · Previsualizar ${n.desc ? 'la tiene como descripción' : 'no la tiene'}` : 'no está']];
  }, w, h);
  await R26('AR3-05 −', async p => {
    const out = []; let ok = true;
    for (const w of [1024, 1100, 1200, 1280, 1366]) { await p.setViewportSize({ width: w, height: 800 }); await p.waitForTimeout(200); const n = await tlnote(p); const bad = !n || (n.cut && !fullNote(n)) || (w >= 1280 && !n.sees); ok = ok && !bad; out.push(`${w}: ${n ? `${n.cut ? (fullNote(n) ? 'cortada, con la frase entera al pasar el ratón' : 'cortada, sin la frase entera') : 'entera'}${n.sees ? '' : ', sin «no mueve el juego» a la vista'}` : 'no está'}`); }
    return [['AR3-05 − de 1024 a 1366 px, la nota nunca queda cortada sin su frase entera a mano, y desde 1280 px nunca corta «no mueve el juego»', ok, out.join(' · ')]];
  });

  // --- UX-48: cada objeto lleva el icono de su tipo, el mismo en el mapa y en las listas (petición de Guillermo) ---
  // el `d` de los iconos de las listas: el trazado de su svg en cada fila de objeto de la Jerarquía, en los botones de Añadir › Objetos
  // y en la cabecera de Propiedades
  const rowIcons = p => p.evaluate(() => [...document.querySelectorAll('#colL .row[data-v^="ent:obj-"]')].map(r => { const q = r.querySelector('svg.g path'); return { id: r.dataset.v, cls: (r.getAttribute('title') || '').split(' · ')[0], d: q ? q.getAttribute('d') : null }; }));
  const addIcons = async p => {
    await p.click('[data-act="rtab"][data-v="add"]'); await p.click('[data-act="lib-cat"][data-v="objeto"]'); await p.waitForTimeout(150);
    const r = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll('#colR [data-act="lib-item"]')].map(b => { const q = b.querySelector('svg.g path'); return [b.dataset.v, q ? q.getAttribute('d') : null]; })));
    await p.click('[data-act="rtab"][data-v="props"]'); await p.waitForTimeout(150);
    return r;
  };
  const propIcon = p => p.evaluate(() => { const q = document.querySelector('#colR .ident svg.g path'); return q ? q.getAttribute('d') : null; });
  // en el mapa, solo la capa de objetos: así ninguna etiqueta ni otro marcador les cae encima
  const onlyObjects = async p => {
    await p.click('#bLayers'); await p.waitForTimeout(150);
    for (const v of ['actor', 'infectado', 'animal', 'marcas', 'camaras']) { await p.click(`#menu [data-act="layer"][data-v="${v}"]`); await p.waitForTimeout(60); }
    await p.click('#status', { position: { x: 3, y: 3 } }); await p.waitForTimeout(150);
  };
  // el marcador de un objeto encuadrado con F: el último relleno con interior en el centro, por encima de su fantasma si lo tiene
  const objAt = async (p, id) => { const g = await glyphAt(p, id); return { g, m: g.fl[g.fl.length - 1] || null }; };
  const UX48T = [['Land_Wreck_Ikarus', 'autobús'], ['Land_Wreck_Volha_Police', 'coche'], ['Land_Wreck_V3S', 'camión'], ['Land_Container_1Bo', 'contenedor'], ['LargeTent', 'tienda'], ['CamoNet', 'red'], ['Fireplace', 'hoguera'], ['Barrel_Red', 'bidón'], ['WoodenCrate', 'caja'], ['Spotlight', 'foco'], ['PowerGenerator', 'generador']];
  await R26('UX-48 +', async p => {
    const res = [], add = await addIcons(p), rows = await rowIcons(p);
    await onlyObjects(p);
    const seen = [];
    for (const r of rows) { const { g, m } = await objAt(p, r.id); seen.push(Object.assign({}, r, { draft: g.nominal > 0, ic: m && m.icon, prop: await propIcon(p) })); }
    const pct = v => Math.round(v * 100);
    const inside = seen.filter(s => s.ic && s.ic.d && s.ic.out === 0 && s.ic.touched >= 0.15 * s.ic.n);
    res.push(['UX-48 + cada objeto del mapa lleva dentro de su cuadrado un icono, pintado con su trazado, que no se sale del interior', rows.length === 20 && inside.length === rows.length, `${inside.length} de ${rows.length} objetos con su icono dentro${seen.some(s => s.ic) ? ` · toca entre el ${pct(Math.min(...seen.filter(s => s.ic).map(s => s.ic.touched / s.ic.n)))} y el ${pct(Math.max(...seen.filter(s => s.ic).map(s => s.ic.touched / s.ic.n)))} % del interior y se sale ${Math.max(...seen.filter(s => s.ic).map(s => s.ic.out))} px como mucho` : ''}${seen.filter(s => !inside.includes(s)).slice(0, 3).map(s => ` · ${s.id.slice(4)}: ${s.ic ? `toca ${s.ic.touched} de ${s.ic.n} px y se sale ${s.ic.out}` : 'sin icono'}`).join('')}`]);
    const byCls = {}; seen.forEach(s => { if (s.ic && s.ic.d && !byCls[s.cls]) byCls[s.cls] = s.ic.d; });
    const ds = UX48T.map(([c]) => byCls[c]);
    res.push(['UX-48 + el autobús, el coche, el camión, el contenedor, la tienda, la red, la hoguera, el bidón, la caja, el foco y el generador llevan iconos distintos en el mapa', ds.every(Boolean) && new Set(ds).size === UX48T.length, `${new Set(ds.filter(Boolean)).size} iconos distintos para ${UX48T.length} tipos${UX48T.filter((_, i) => !ds[i]).length ? ` · sin icono: ${UX48T.filter((_, i) => !ds[i]).map(t => t[1]).join(', ')}` : ''}`]);
    const bad = seen.filter(s => !(s.ic && s.ic.d && s.ic.d === s.d && add[s.cls] === s.d && s.prop === s.d));
    res.push(['UX-48 + el icono que se pinta en el mapa para cada objeto es el mismo trazado que el de su fila de la Jerarquía, el de su botón de Añadir y el de la cabecera de sus Propiedades', rows.length === 20 && !bad.length, `${rows.length - bad.length} de ${rows.length} iguales${bad.slice(0, 3).map(s => ` · ${s.id.slice(4)}: mapa ${s.ic && s.ic.d ? (s.ic.d === s.d ? '=' : '≠') : 'sin icono'}, Jerarquía ${s.d ? 'con' : 'sin'} icono, Añadir ${add[s.cls] ? (add[s.cls] === s.d ? '=' : '≠') : 'sin icono'}, Propiedades ${s.prop ? (s.prop === s.d ? '=' : '≠') : 'sin icono'}`).join('')}`]);
    const sol = seen.filter(s => !s.draft && s.ic), dr = seen.filter(s => s.draft && s.ic), low = l => l.length ? Math.min(...l.map(s => s.ic.ratio)) : null;
    res.push(['UX-48 + el icono queda a 3:1 o más de su cuadrado, en sólido y en borrador', sol.length > 0 && dr.length > 0 && sol.length + dr.length === rows.length && seen.every(s => s.ic && s.ic.ratio >= 3), `sólidos: ${sol.length}, el más bajo a ${low(sol) || '?'}:1 · borradores: ${dr.length}, el más bajo a ${low(dr) || '?'}:1`]);
    return res;
  });
  await R26('UX-48 −', async p => {
    const res = [], ids = await p.evaluate(() => [...document.querySelectorAll('#colL .row[data-v^="ent:obj-"]')].filter(r => r.querySelector('.st svg')).map(r => r.dataset.v));
    await onlyObjects(p);
    const a = []; for (const id of ids) a.push([id, (await objAt(p, id)).g]);
    if (!await apply(p)) return [['UX-48 − aplicado y leído, el objeto sigue siendo un cuadrado y va sólido', false, 'no llegó a aplicar']];
    const b = []; for (const id of ids.concat('ent:obj-01')) b.push([id, (await objAt(p, id)).g]);
    const shape = l => l.map(([id, g]) => `${id.slice(4)} ${g.fl.map(x => x.shape ? `${x.shape.ratio} y ${x.shape.sym} px` : '?').join('/') || 'no visto'}`).join(', ');
    res.push(['UX-48 − el objeto sigue siendo un cuadrado: sin aplicar y aplicado, la misma distancia al borde a 90° y la mayor √2 veces la menor', a.length > 0 && a.concat(b).every(([, g]) => g.fl.length > 0 && g.fl.every(x => SQUARE(x.shape))), `sin aplicar: ${shape(a) || 'ningún objeto'} · aplicado: ${shape(b)}`]);
    res.push(['UX-48 − sin aplicar, el objeto va con contorno discontinuo, huecos que se ven y nada sólido', a.length > 0 && a.every(([, g]) => g.dashed > 0 && !g.solid && !g.filled), a.map(([id, g]) => `${id.slice(4)}: ${g.dashed} de ${g.nominal} contornos discontinuos con huecos que se ven y ${g.solid} sólidos (${g.see})`).join(' · ') || 'ningún objeto sin aplicar']);
    res.push(['UX-48 − aplicado y leído, va sólido con la regla nueva: el 85 % de lo que deja ver el icono es del color del relleno, y eso es al menos la mitad del interior', b.every(([, g]) => g.solid > 0 && g.filled > 0 && !g.nominal), b.map(([id, g]) => `${id.slice(4)}: ${g.solid} sólidos y ${g.nominal} discontinuos (${g.see})`).join(' · ')]);
    // una clase que no está en el catálogo: en una copia de la página, dos objetos con clases que no están
    const what = 'UX-48 − una clase que no está en el catálogo lleva el icono genérico: el mismo para dos clases así, distinto del de cada tipo, igual en la Jerarquía, en Propiedades y en el mapa, y sin errores';
    if (!/^file:/.test(URL)) return res.concat([[what, false, 'la copia se hace leyendo el archivo del disco: hace falta una dirección file://']]);
    const fs = require('fs'), os = require('os'), { fileURLToPath, pathToFileURL } = require('url');
    const html = fs.readFileSync(fileURLToPath(URL), 'utf8').replace(/E\('obj-17', 'objeto', '[^']+'/, "E('obj-17', 'objeto', 'Land_Prueba_SinCatalogo'").replace(/E\('obj-15', 'objeto', '[^']+'/, "E('obj-15', 'objeto', 'Prueba_OtraClase'");
    if (!/Land_Prueba_SinCatalogo/.test(html) || !/Prueba_OtraClase/.test(html)) return res.concat([[what, false, 'no se encontraron obj-15 y obj-17 en el archivo para cambiarles la clase']]);
    const file = path.join(os.tmpdir(), `estudio-sin-catalogo-${process.pid}.html`); fs.writeFileSync(file, html);
    const c = await browser.newContext({ viewport: { width: 1600, height: 960 }, colorScheme: 'dark' });
    try {
      await c.addInitScript(LIB); await c.addInitScript(PROBE);
      const q = await c.newPage(), errs = []; q.setDefaultTimeout(3000);
      q.on('pageerror', e => { errs.push(e.message); errors.push(`[pageerror] ${e.message}`); }); q.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
      await q.goto(pathToFileURL(file).href); await q.waitForTimeout(900);
      const add = await addIcons(q), rows = await rowIcons(q), r17 = rows.find(r => r.id === 'ent:obj-17'), r15 = rows.find(r => r.id === 'ent:obj-15');
      await onlyObjects(q);
      const { m } = await objAt(q, 'ent:obj-17'), prop = await propIcon(q), types = new Set(Object.values(add).filter(Boolean)), gen = r17 && r17.d;
      const ok = !!gen && !!r15 && r15.d === gen && types.size === UX48T.length && !types.has(gen) && !!m && !!m.icon && m.icon.d === gen && prop === gen && !errs.length;
      return res.concat([[what, ok, `${r17 ? `«${r17.cls}» ${gen ? 'con icono' : 'sin icono'} en la Jerarquía${r15 && gen ? `, ${r15.d === gen ? 'el mismo' : 'otro'} que «${r15.cls}»` : ''}` : 'obj-17 no está'} · ${types.size} iconos de tipo en Añadir, ${gen && types.has(gen) ? 'y el suyo es uno de ellos' : 'ninguno es el suyo'} · mapa: ${m && m.icon ? (m.icon.d === gen ? 'el mismo' : 'otro') : 'sin icono'} · Propiedades: ${prop ? (prop === gen ? 'el mismo' : 'otro') : 'sin icono'} · ${errs.length ? `errores: ${errs.slice(0, 2).join(' | ')}` : 'sin errores'}`]]);
    } finally { await c.close().catch(() => {}); fs.rmSync(file, { force: true }); }
  });

  // --- UX-49: vista previa al escoger en Añadir, y la planta del objeto bajo el cursor al colocarlo (petición de Guillermo) ---
  const BUS = '#colR [data-act="lib-item"][data-v="Land_Wreck_Ikarus"]';
  // un sitio libre entre los objetos, para poder colocar: se borra el bidón amarillo
  const freeObj = async p => { await p.click('#colL [data-act="sel"][data-v="ent:obj-20"]'); await p.focus('#map'); await p.keyboard.press('Delete'); await p.waitForTimeout(200); };
  const openObjs = async p => { await p.click('[data-act="rtab"][data-v="add"]'); await p.click('[data-act="lib-cat"][data-v="objeto"]'); await p.waitForTimeout(150); };
  // lo que enseña la vista previa, como se ve: su texto, el `d` de su icono, el tamaño de su planta y la escala de su barra. La planta y la
  // barra se miden por su caja, y la caja es la planta solo si ni ella ni nada por encima la gira, la inclina, la escala ni la lleva por un
  // trazado (un transform que no sea solo moverla, rotate, scale, offset-path), y si sus lados están donde dice la caja: un punto a 1 px por
  // dentro de cada lado, a 1/10, 1/2 y 9/10 de él, da en la planta, y no en algo que la tapa ni en lo que queda fuera de un recorte (AR5-04).
  // Y desde la sexta revisión (AR6-02), lo que se ve de las dos en una captura de su fila de la vista previa, sin fiarse de sus cajas. Tinta
  // es lo que se aparta del fondo (el color que más se repite) al menos la mitad que lo más apartado. De la planta, fuera de lo de la escala:
  // la caja de su tinta, el tramo más largo de cada lado sin tinta (el discontinuo deja huecos de 2 o 3 px), los píxeles de tinta que hay
  // dentro, a 3 px de sus lados o más, y el contraste con el fondo de su píxel más apartado de él; de la barra, a 2 px de su caja o menos, el
  // largo de su tinta y el mismo contraste. Desde la séptima (AR7-01), también el contraste de cada tramo de tinta de sus lados, sin
  // redondear, porque el de un solo píxel no dice nada de los demás lados
  const look = async p => {
    const r = await p.evaluate(() => { const q = s => { const e = document.querySelector('#libPrev ' + s); if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; }; return { plan: q('.pv-plan'), sc: q('.pv-sc'), bar: q('.pv-sc .scale i') }; });
    if (!r.plan || !r.sc || !r.bar) return null;
    const x0 = Math.floor(r.plan[0]), y0 = Math.floor(r.plan[1]);
    const shot = () => p.screenshot({ clip: { x: x0, y: y0, width: Math.ceil(r.plan[2]) - x0, height: Math.ceil(r.plan[3]) - y0 } });
    // la cobertura de cada píxel (AR8-01): lo de dentro de la fila de la planta se pinta otra vez todo en negro y todo en blanco, con
    // el mismo fondo, y la diferencia entre las dos capturas es cuánto de cada píxel cubre lo pintado (255 = entero), sea cual sea su color
    const paint = c => p.evaluate(c => { let s = document.getElementById('__r26cov'); if (!c) { if (s) s.remove(); return; } if (!s) { s = document.createElement('style'); s.id = '__r26cov'; document.head.appendChild(s); } s.textContent = `#libPrev .pv-plan *, #libPrev .pv-plan *::before, #libPrev .pv-plan *::after { filter: ${c} !important; transition: none !important; animation: none !important; }`; }, c);
    const png = await shot(); await paint('brightness(0)'); const pk = await shot(); await paint('brightness(0) invert(1)'); const pw = await shot(); await paint(null);
    return p.evaluate(async ([u, uk, uw, r, x0, y0]) => {
      const data = async s => { const im = new Image(); im.src = s; await im.decode(); const o = new OffscreenCanvas(im.naturalWidth, im.naturalHeight), g = o.getContext('2d'); g.drawImage(im, 0, 0); return [im.naturalWidth, im.naturalHeight, g.getImageData(0, 0, im.naturalWidth, im.naturalHeight).data]; };
      const [W, H, D] = await data(u), K = (await data(uk))[2], Wh = (await data(uw))[2], px = (x, y) => [D[4 * (y * W + x)], D[4 * (y * W + x) + 1], D[4 * (y * W + x) + 2]];
      // cobertura de 0 a 1: la menor de las tres diferencias blanco − negro; entero, desde COVER_FULL
      const cov = (x, y) => { const i = 4 * (y * W + x); return Math.min(Wh[i] - K[i], Wh[i + 1] - K[i + 1], Wh[i + 2] - K[i + 2]) / 255; }, COVER_FULL = 0.95;
      const n = new Map(); for (let i = 0; i < W * H; i++) { const k = D[4 * i] << 16 | D[4 * i + 1] << 8 | D[4 * i + 2]; n.set(k, (n.get(k) || 0) + 1); }
      const k0 = [...n].sort((a, b) => b[1] - a[1])[0][0], bg = [k0 >> 16, k0 >> 8 & 255, k0 & 255], far = q => Math.max(...q.map((v, i) => Math.abs(v - bg[i])));
      const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }, lum = q => 0.2126 * lin(q[0]) + 0.7152 * lin(q[1]) + 0.0722 * lin(q[2]);
      const cr = q => { const a = lum(q), b = lum(bg); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
      // la tinta en lo que deja `keep` de la captura: si un píxel lo es, su caja y el contraste del más apartado del fondo
      const ink = keep => {
        let top = 0, c = null; for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (keep(x, y)) { const f = far(px(x, y)); if (f > top) { top = f; c = px(x, y); } }
        const is = (x, y) => top > 0 && x >= 0 && y >= 0 && x < W && y < H && keep(x, y) && far(px(x, y)) >= top / 2;
        let l = W, t = H, rr = -1, b = -1; for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (is(x, y)) { l = Math.min(l, x); t = Math.min(t, y); rr = Math.max(rr, x); b = Math.max(b, y); }
        return rr < 0 ? null : { is, keep, l, t, r: rr, b, cr: cr(c) };
      };
      const inSc = (x, y) => x + x0 >= r.sc[0] && x + x0 < r.sc[2] && y + y0 >= r.sc[1] && y + y0 < r.sc[3];
      const f = ink((x, y) => !inSc(x, y)), b = ink((x, y) => inSc(x, y) && x + x0 >= r.bar[0] - 2 && x + x0 < r.bar[2] + 2 && y + y0 >= Math.floor(r.bar[1]) && y + y0 < r.bar[3] + 2);
      if (!f) return null;
      const gap = (len, at) => { let m = 0, c = 0; for (let i = 0; i < len; i++) { c = at(i) ? 0 : c + 1; m = Math.max(m, c); } return m; };
      // cada lado, como una franja de 2 px a lo largo de su caja de tinta: su largo y, en cada posición, sus dos píxeles
      const strips = (k, top) => [[k.r - k.l + 1, i => [[k.l + i, k.b], [k.l + i, k.b - 1]]], [k.b - k.t + 1, i => [[k.l, k.t + i], [k.l + 1, k.t + i]]], [k.b - k.t + 1, i => [[k.r, k.t + i], [k.r - 1, k.t + i]]]].concat(top ? [[k.r - k.l + 1, i => [[k.l + i, k.t], [k.l + i, k.t + 1]]]] : []);
      // el contraste del tramo más bajo (AR7-01): un tramo son las posiciones seguidas de un lado con tinta. Desde la octava (AR8-01) no se
      // aparta ningún píxel por estar en el extremo del tramo: cuentan todos los píxeles de tinta cubiertos enteros (los que la captura en
      // negro y en blanco da por cubiertos del todo), cada uno por su contraste, y uno cubierto solo en parte es antialias y no cuenta. Un
      // tramo sin ningún píxel cubierto entero no se acredita (cuenta como 0). Así un color débil opaco no se salva por su sitio, ni por
      // tener al lado, en la misma posición, un píxel fuerte de otro lado (una esquina). Y en la franja cuenta también todo píxel que lo
      // pintado cubre entero aunque se aparte del fondo menos de la mitad que lo más apartado: si no, un extremo débil y opaco no sería
      // tinta, y quedaría como un hueco de 1 px dentro del ±1 px del largo
      const on = (k, x, y) => x >= 0 && y >= 0 && x < W && y < H && k.keep(x, y) && (k.is(x, y) || cov(x, y) >= COVER_FULL);
      const low = (k, top) => { let lo = Infinity; for (const [len, at] of strips(k, top)) { let run = []; const end = () => { if (run.length) { const full = run.filter(v => v !== null); lo = Math.min(lo, full.length ? Math.min(...full) : 0); } run = []; }; for (let i = 0; i < len; i++) { const q = at(i).filter(([x, y]) => on(k, x, y)); if (!q.length) { end(); continue; } const f = q.filter(([x, y]) => cov(x, y) >= COVER_FULL).map(([x, y]) => cr(px(x, y))); run.push(f.length ? Math.min(...f) : null); } end(); } return lo; };
      const w = f.r - f.l + 1, h = f.b - f.t + 1;
      const sides = strips(f, true).map(([len, at]) => gap(len, i => at(i).some(([x, y]) => f.is(x, y))));
      let inner = 0; for (let y = f.t + 3; y <= f.b - 3; y++) for (let x = f.l + 3; x <= f.r - 3; x++) if (f.is(x, y)) inner++;
      return { w, h, sides, inner, cr: f.cr, lo: low(f, true), bar: b ? b.r - b.l + 1 : 0, barCr: b ? b.cr : 0, barLo: b ? low(b, false) : 0 };
    }, [png, pk, pw].map(b => 'data:image/png;base64,' + b.toString('base64')).concat([r, x0, y0]));
  };
  const preview = async p => { const v = await p.evaluate(() => {
    const el = document.querySelector('#libPrev');
    if (!el || !__r26.shown(el)) return null;
    const ic = el.querySelector('svg path'), fp = el.querySelector('.pv-fp'), bar = el.querySelector('.scale'), bi = bar && bar.querySelector('i'), m = bar ? parseFloat(bar.innerText.replace(',', '.')) : NaN;
    const f = fp && fp.getBoundingClientRect(), bent = new Set();
    for (const x of [fp, bi]) for (let e = x; e; e = e.parentElement) { const c = getComputedStyle(e); for (const k of ['transform', 'rotate', 'scale', 'offsetPath']) if (c[k] !== 'none' && !(k === 'transform' && /^matrix\(1, 0, 0, 1, [^,]+, [^,]+\)$/.test(c[k]))) bent.add(`${k} en ${e.id ? '#' + e.id : e.classList[0] ? '.' + e.classList[0] : e.tagName.toLowerCase()}`); }
    const miss = f ? [0.1, 0.5, 0.9].flatMap(t => [[f.left + t * f.width, f.top + 1], [f.left + t * f.width, f.bottom - 1], [f.left + 1, f.top + t * f.height], [f.right - 1, f.top + t * f.height]]).filter(([x, y]) => document.elementFromPoint(x, y) !== fp).length : 0;
    return { text: el.innerText.replace(/\s+/g, ' ').trim(), d: ic ? ic.getAttribute('d') : null, fp: f ? [f.width, f.height] : null, s: bi && m > 0 ? bi.getBoundingClientRect().width / m : null, bw: bi ? bi.getBoundingClientRect().width : null, bent: [...bent], miss };
  }); if (v && v.fp) v.seen = await look(p); return v; };
  // la planta de la vista previa, a escala en los dos ejes: el largo a lo ancho y el ancho a lo alto, cada uno a ±1 px de su medida a la
  // escala de la barra (AR4-02). Las medidas las pone la prueba, las del catálogo de muestra, y no las lee de la página
  const r1 = x => Math.round(x * 10) / 10;
  const planFits0 = (v, L, Wd) => !!v && !!v.fp && !!v.s && Math.abs(v.fp[0] - L * v.s) <= 1 && Math.abs(v.fp[1] - Wd * v.s) <= 1;
  const planFits5 = (v, L, Wd) => planFits0(v, L, Wd) && !v.bent.length && !v.miss;
  // y como se ve (AR6-02): su tinta mide eso mismo a ±1 px en cada eje, ningún tramo de un lado se queda sin tinta más de 4 px, ningún píxel
  // clasificado como tinta queda dentro, y la barra se ve del largo de su caja, a ±1 px
  const planGeom = (v, L, Wd) => !!v && !!v.seen && !!v.s && Math.abs(v.seen.w - L * v.s) <= 1 && Math.abs(v.seen.h - Wd * v.s) <= 1 && Math.max(...v.seen.sides) <= 4 && !v.seen.inner && Math.abs(v.seen.bar - v.bw) <= 1;
  // el criterio de la sexta, solo para decir en los − si lo daba por bueno: además, el píxel más apartado del fondo de la planta y el de la
  // barra a 3:1 o más, con la razón redondeada a dos decimales
  const planSeen6 = (v, L, Wd) => planGeom(v, L, Wd) && Math.round(v.seen.cr * 100) / 100 >= 3 && Math.round(v.seen.barCr * 100) / 100 >= 3;
  // y desde la séptima (AR7-01), cada tramo de tinta de sus cuatro lados y de los tres de la barra a 3:1 o más del fondo (lo que pide WCAG 2.1,
  // 1.4.11, a lo que no es texto), sin redondear la razón
  const planSeen = (v, L, Wd) => planGeom(v, L, Wd) && v.seen.lo >= 3 && v.seen.barLo >= 3;
  const planFits = (v, L, Wd) => planFits5(v, L, Wd) && planSeen(v, L, Wd);
  // una razón de contraste, para leerla: truncada a dos decimales, que una por debajo de 3 no salga como 3,00
  const ratio2 = x => (Math.floor(x * 100) / 100).toFixed(2).replace('.', ',');
  const showPlan = (v, L, Wd) => !v ? 'sin vista previa' : `planta ${v.fp ? v.fp.map(r1).join(' × ') + ' px' : 'ninguna'}${v.s ? `, a ${r1(v.s)} px/m de su barra${L ? `: ${String(L).replace('.', ',')} × ${String(Wd).replace('.', ',')} m son ${r1(L * v.s)} × ${r1(Wd * v.s)} px` : ''}` : ', sin barra de escala'}${v.bent.length ? ` · su caja no es la planta: ${v.bent.join(', ')}` : ''}${v.miss ? ` · ${v.miss} de los 12 puntos junto a sus lados no ${v.miss === 1 ? 'da' : 'dan'} en ella` : ''}${v.fp ? ` · ${!v.seen ? 'en la captura no se ve' : `en la captura se ve de ${v.seen.w} × ${v.seen.h} px, con ${Math.max(...v.seen.sides)} px seguidos sin tinta en un lado como mucho${v.seen.inner ? `, ${v.seen.inner} px de tinta dentro` : ''}, su tramo más bajo a ${ratio2(v.seen.lo)}:1 (su píxel más apartado del fondo, a ${ratio2(v.seen.cr)}:1), y la barra de ${v.seen.bar} px (su caja, ${r1(v.bw)}), su tramo más bajo a ${ratio2(v.seen.barLo)}:1 (${ratio2(v.seen.barCr)}:1)`}` : ''}`;
  // la del autobús: su nombre y su tamaño, 11,4 × 2,5 m, el icono de su fila y su planta a escala en los dos ejes
  const busPrev = (v, d) => {
    if (!v) return { ok: false, info: 'sin vista previa' };
    const m = v.text.match(/(\d+(?:,\d+)?) × (\d+(?:,\d+)?) m/), L = m ? parseFloat(m[1].replace(',', '.')) : NaN, Wd = m ? parseFloat(m[2].replace(',', '.')) : NaN;
    return { L, Wd, ok: /Autobús Ikarus/.test(v.text) && L === 11.4 && Wd === 2.5 && !!d && v.d === d && planFits(v, 11.4, 2.5),
      info: `«${v.text.slice(0, 90)}» · icono ${v.d ? (v.d === d ? 'el de su fila' : 'otro') : 'ninguno'} · ${showPlan(v, 11.4, 2.5)}` };
  };
  await R26('UX-49 +', async p => {
    const res = [];
    await freeObj(p); await openObjs(p);
    const d = await p.evaluate(s => { const q = document.querySelector(s + ' svg path'); return q ? q.getAttribute('d') : null; }, BUS), tree = (await rowIcons(p)).find(r => r.cls === 'Land_Wreck_Ikarus');
    await p.hover(BUS); await p.waitForTimeout(150);
    const a = busPrev(await preview(p), d);
    res.push(['UX-49 + con el ratón sobre el autobús en Añadir › Objetos, la vista previa dice «Autobús Ikarus» y su tamaño, 11,4 × 2,5 m, y lleva el mismo icono que su fila y su planta a escala en los dos ejes: el largo a lo ancho y el ancho a lo alto, a ±1 px de su medida a la escala de la barra (AR4-02)', a.ok && !!tree && tree.d === d, a.info]);
    // con el teclado: Tab con el mapa activo abre Añadir con el foco en la búsqueda, y el Tab siguiente llega al primero de la lista
    await p.mouse.move(2, 2); await p.focus('#map'); await p.keyboard.press('Tab'); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    const on = await p.evaluate(s => document.activeElement === document.querySelector(s), BUS), b = busPrev(await preview(p), d);
    res.push(['UX-49 + con el teclado, al llegar al autobús la vista previa enseña lo mismo', on && b.ok, `${on ? 'el foco, en el autobús' : 'el foco no llega al autobús'} · ${b.info}`]);
    // al colocarlo, bajo el cursor, un rectángulo discontinuo de largo × ancho a la escala del mapa (la de su barra)
    await p.click(BUS); await p.waitForTimeout(150);
    const box = await p.locator('#map').boundingBox(), cx = Math.round(box.width / 2), cy = Math.round(box.height / 2);
    await p.mouse.move(box.x + cx - 40, box.y + cy - 30); await p.mouse.move(box.x + cx, box.y + cy, { steps: 4 }); await p.waitForTimeout(150);
    const f = await frame(p), sc = await p.evaluate(() => [document.querySelector('#scaleTxt').textContent, document.querySelector('#scaleBar').getBoundingClientRect().width]);
    const s = sc[1] / (parseFloat(sc[0].replace(',', '.')) * (/km/.test(sc[0]) ? 1000 : 1)), want = [a.Wd * s, a.L * s].sort((u, v) => u - v);
    const err = r => { const z = [r.ext.w, r.ext.h].sort((u, v) => u - v); return Math.max(Math.abs(z[0] - want[0]), Math.abs(z[1] - want[1])); };
    const fp = f.strokes.filter(r => r.ext && Math.abs(r.x - cx) <= 2 && Math.abs(r.y - cy) <= 2).sort((u, v) => err(u) - err(v))[0], r1 = x => Math.round(x * 10) / 10;
    res.push(['UX-49 + al colocarlo, el mapa lleva bajo el cursor un rectángulo discontinuo de largo·s × ancho·s px, ±1,5 px, con huecos que se ven', !!a.L && !!fp && err(fp) <= 1.5 && GAPS(fp.gaps), `${a.L ? `escala del mapa ${r1(s)} px/m: se esperan ${want.map(r1).join(' × ')} px` : 'sin el tamaño de la vista previa, nada con que comparar'} · ${fp ? `bajo el cursor, uno de ${fp.ext.w} × ${fp.ext.h} px, ${fp.gaps ? `en ${fp.gaps.comps} trozos, ${fp.gaps.gapPx} px de hueco a ${fp.gaps.ratio}:1 de los guiones` : 'sin guiones medidos'}` : 'ningún trazo discontinuo bajo el cursor'}`]);
    return res;
  });
  await R26('UX-49 −', async p => {
    const res = [];
    await freeObj(p);
    const mapAt = () => p.evaluate(() => { const r = document.querySelector('#map').getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round).join(', '); });
    const m0 = await mapAt();
    await openObjs(p); await p.hover(BUS); await p.waitForTimeout(150);
    const r = await p.evaluate(() => {
      const el = document.querySelector('#libPrev'), col = document.querySelector('#colR'), seen = el && __r26.shown(el);
      const url = [col, ...col.querySelectorAll('*')].filter(x => [null, '::before', '::after'].some(ps => { const c = getComputedStyle(x, ps); return /url\(/.test(c.backgroundImage + c.content + (c.maskImage || '') + c.listStyleImage + c.borderImageSource); }));
      const m = document.querySelector('#map').getBoundingClientRect(), b = seen ? el.getBoundingClientRect() : null;
      return { text: seen ? el.innerText.replace(/\s+/g, ' ').trim() : '', imgs: col.querySelectorAll('img, picture, video, iframe, object, embed, image').length, url: url.length, over: !!b && b.left < m.right && b.right > m.left && b.top < m.bottom && b.bottom > m.top };
    });
    const m1 = await mapAt(), mt = await p.evaluate(() => __r26.metrics());
    res.push(['UX-49 − sin captura del juego, la vista previa dice que no la hay y no pinta ninguna imagen (ni <img> ni fondo con url())', /sin captura/i.test(r.text) && !r.imgs && !r.url, `${r.text ? `«${r.text.slice(0, 90)}»` : 'sin vista previa'} · en el panel, ${r.imgs} imágenes y ${r.url} fondos con url()`]);
    res.push(['UX-49 − la vista previa no tapa el mapa: va fuera de él, y el mapa sigue en el mismo sitio y del mismo tamaño', !r.over && m0 === m1, `${r.text ? (r.over ? 'encima del mapa' : 'fuera del mapa') : 'sin vista previa'} · mapa en ${m0} → ${m1}`]);
    res.push(['UX-49 − con la vista previa a la vista, ninguna letra baja de 12 px (UX-10)', mt.small === 0, `${mt.small} textos por debajo de 12 px${mt.small ? ': ' + mt.smallEj.join(' | ') : ''}`]);
    // Esc cancela la colocación; e Intro pone el objeto en el centro del mapa, el que dice la coordenada bajo el ratón allí
    await p.click(BUS); await p.waitForTimeout(150);
    const armed = await p.locator('[data-act="place-cancel"]').count();
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const after = await p.locator('[data-act="place-cancel"]').count();
    await p.click(BUS); await p.waitForTimeout(150);
    const box = await p.locator('#map').boundingBox(); await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 3 }); await p.waitForTimeout(100);
    const xy = (await T(p, '#cursorXY')).match(/X ([\d.,-]+) · Z ([\d.,-]+)/), es = t => parseFloat(t.replace(/\./g, '').replace(',', '.'));
    await p.keyboard.press('Enter'); await p.waitForTimeout(250);
    const put = await p.evaluate(() => ({ name: (document.querySelector('#f-name') || {}).value || '', x: parseFloat((document.querySelector('#f-x') || {}).value), z: parseFloat((document.querySelector('#f-z') || {}).value) }));
    const centred = !!xy && Math.abs(put.x - es(xy[1])) <= 0.6 && Math.abs(put.z - es(xy[2])) <= 0.6;
    res.push(['UX-49 − Intro sigue poniendo el objeto en el centro del mapa, y Esc cancela la colocación', armed > 0 && after === 0 && put.name === 'Autobús Ikarus' && centred, `Esc: ${armed ? (after ? 'sigue colocando' : 'cancela') : 'no llegó a colocar'} · Intro: ${put.name ? `«${put.name}» en ${put.x} · ${put.z}` : 'nada'}${xy ? `, el centro del mapa en ${es(xy[1])} · ${es(xy[2])}` : ''}`]);
    // con Propiedades y Añadir a la vez, el panel de Añadir es más bajo: la lista sigue a la vista y el presupuesto, entero
    await p.click('#bTools'); await p.waitForTimeout(120); await p.click('#menu [data-act="pan"][data-v="both"]'); await p.click('#status', { position: { x: 3, y: 3 } }); await p.waitForTimeout(150);
    await p.click('[data-act="lib-cat"][data-v="objeto"]'); await p.waitForTimeout(150);
    const sp = await p.evaluate(() => { const it = document.querySelector('#colR .items'), pb = it && it.parentElement, bg = document.querySelector('#colR .budget'), pan = bg && bg.parentElement, r = x => x.getBoundingClientRect(); return pb && bg ? { list: Math.round(r(pb).height), cut: Math.max(0, Math.round(r(bg).bottom - r(pan).bottom)) } : null; });
    res.push(['UX-49 − con Propiedades y Añadir a la vez, la lista sigue a la vista, con tres filas o más (90 px), y el presupuesto se ve entero', !!sp && sp.list >= 90 && sp.cut === 0, sp ? `lista de ${sp.list} px · presupuesto cortado ${sp.cut} px` : 'sin la lista de Añadir']);
    return res;
  });

  // --- UX-50: ningún texto del mapa tapado ni cortado (lo que se vio en las capturas de UX-48 y UX-49, y ya pasaba en 7a047bf) ---
  // Lo que el lienzo no ve: cada texto del mapa, menos los nombres de los pueblos, que van con el mapa, cabe en él y no cae debajo de lo que
  // flota encima (el grupo del zoom, la escala y la leyenda, la ayuda y «Rodando»). Lo que sí ve, un marcador o una etiqueta pintados encima
  // de un número o de otra etiqueta, lo mide el fotograma acabado (AR3-01).
  const hidden = (p, f) => p.evaluate(texts => {
    const m = document.querySelector('#map').getBoundingClientRect(), name = e => e.id === 'hint' ? 'la ayuda' : e.id === 'recBadge' ? '«Rodando»' : e.id === 'legend' ? 'la leyenda' : e.classList.contains('tr') ? 'el grupo del zoom' : 'la escala y la leyenda';
    const ov = [...document.querySelectorAll('#mapwrap .ovl, #legend, #hint, #recBadge')].filter(__r26.shown).map(e => { const b = e.getBoundingClientRect(); return { n: name(e), l: b.left - m.left, t: b.top - m.top, r: b.right - m.left, b: b.bottom - m.top }; });
    return texts.map(([t, b]) => { const under = ov.filter(o => o.l < b[2] && o.r > b[0] && o.t < b[3] && o.b > b[1]).map(o => o.n); return b[0] < 0 || b[1] < 0 || b[2] > m.width || b[3] > m.height ? `«${t}» cortada por el borde` : under.length ? `«${t}» bajo ${under.join(' y ')}` : ''; }).filter(Boolean);
  }, f.texts.filter(t => t.box && !TOWNS.some(w => w[0] === t.text)).map(t => [t.text, t.box]));
  // las tres vistas de las capturas, a 1440 × 900: la escena recién abierta acercada dos veces, de cerca el autobús y los bidones, y colocando el autobús
  const VIEWS50 = [
    ['escena', async p => { for (let i = 0; i < 2; i++) { await p.click('#bZin'); await p.waitForTimeout(150); } }],
    ['de cerca', async p => {
      await p.click('#colL [data-act="sel"][data-v="ent:obj-01"]');
      for (const id of ['obj-12', 'obj-13', 'obj-14', 'obj-20']) { await p.keyboard.down('Control'); await p.click(`#colL [data-act="sel"][data-v="ent:${id}"]`); await p.keyboard.up('Control'); }
      await p.focus('#map'); await p.keyboard.press('f'); await p.waitForTimeout(250); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    }],
    ['colocando', async p => {
      await freeObj(p); for (let i = 0; i < 2; i++) { await p.click('#bZin'); await p.waitForTimeout(150); }
      await openObjs(p); await p.click(BUS); await p.waitForTimeout(150);
      const b = await p.locator('#map').boundingBox(); await p.mouse.move(b.x + b.width * 0.66, b.y + b.height * 0.62, { steps: 4 }); await p.waitForTimeout(150);
    }]
  ];
  for (const scheme of ['dark', 'light']) {
    await R26(`UX-50 + ${scheme}`, async p => {
      const out = []; let ok = true;
      for (const [n, go] of VIEWS50) {
        if (out.length) { await p.goto(URL); await p.waitForTimeout(900); }
        await go(p);
        const r = await readable(p, ['Mirek', 'Linda']), h = await hidden(p, r.f);
        ok = ok && r.ok && !h.length; out.push(`${n}: ${r.info}${h.length ? ', ' + h.slice(0, 3).join(', ') : ''}`);
      }
      return [[`UX-50 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, a 1440 × 900, en la escena recién abierta acercada dos veces, de cerca sobre el autobús y los bidones, y colocando el autobús, cada texto que se espera está pintado, cada píxel de su letra llega a 4,5:1 también al acabar, y ninguno queda debajo de lo que flota encima del mapa ni cortado por su borde`, ok, out.join(' · ')]];
    }, 1440, 900, scheme);
  }
  await R26('UX-50 + regla', async p => {
    const what = 'UX-50 + Linda junto al borde izquierdo, a la altura de un número de la regla de Y: el número se lee entero encima de su marcador, a 4,5:1 también al acabar, y su nombre sale sin pisarlo';
    // Linda a 14 px del borde izquierdo del mapa y justo en una línea de la rejilla del centro, puesta con sus campos de posición
    const f = await toScreen(p), r = await p.locator('#map').boundingBox();
    if (!f) return [[what, false, 'sin lectura del cursor']];
    const [ax, az] = f(6000, 7600), [bx, bz] = f(6100, 7700), kx = (bx - ax) / 100, kz = (bz - az) / 100;
    const sp = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000].find(m => m * Math.abs(kx) >= 70) || 5000, z = Math.round((7600 + (r.y + r.height / 2 - az) / kz) / sp) * sp, x = 6000 + (r.x + 14 - ax) / kx;
    await p.click('#colL [data-act="sel"][data-v="ent:act-linda"]'); await p.waitForTimeout(150);
    await p.fill('#f-x', x.toFixed(1)); await p.keyboard.press('Tab'); await p.fill('#f-z', z.toFixed(1)); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
    await p.focus('#map'); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const at = f(x, z), rd = await readable(p, ['Linda']), h = await hidden(p, rd.f), n = rd.f.texts.find(t => t.text === String(z)), l = rd.f.texts.find(t => t.text === 'Linda');
    const over = !!n && !!l && n.box[0] < l.box[2] && l.box[0] < n.box[2] && n.box[1] < l.box[3] && l.box[1] < n.box[3];
    const near = Math.abs(at[0] - r.x - 14) <= 2 && Math.abs(at[1] - r.y - r.height / 2) <= sp * Math.abs(kz) / 2 + 1;
    return [[what, rd.ok && !h.length && near && !!n && n.n > 0 && !!n.fin && n.fin.low === 0 && !!l && !over, `Linda en ${Math.round(at[0] - r.x)} · ${Math.round(at[1] - r.y)} px del mapa, en la línea de ${z} · ${rd.info}${h.length ? ', ' + h.slice(0, 3).join(', ') : ''} · «${z}» ${n ? (n.fin ? `al acabar ${n.fin.low} de ${n.fin.n} px bajos` : 'sin medir al acabar') : 'no está'} · «Linda» ${l ? (over ? 'encima del número' : 'sin pisarlo') : 'no está'}`]];
  }, 1440, 900);
  await R26('UX-50 −', async p => {
    // a mano sobre el mapa: la prueba ve una etiqueta bajo la escala, una cortada por el borde y un número con un marcador encima, y deja pasar una libre
    const r = await p.evaluate(() => {
      const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth, cv = window.__cv, m = c.getBoundingClientRect(), bl = document.querySelector('#mapwrap .ovl.bl').getBoundingClientRect();
      Object.assign(cv, { texts: [], strokes: [], fills: [], images: [], on: true });
      g.save(); g.setTransform(d, 0, 0, d, 0, 0);
      const tag = (t, x, y) => { g.font = '600 12px sans-serif'; g.fillStyle = 'rgb(200,197,182)'; g.fillRect(x - 2, y - 11, g.measureText(t).width + 4, 14); g.fillStyle = '#222116'; g.fillText(t, x, y); };
      tag('Bajo la escala', bl.left - m.left + 8, bl.top - m.top + 16);
      tag('Cortada por el borde', c.clientWidth - 40, 200);
      tag('6650', 60, 300); g.beginPath(); g.moveTo(70, 289); g.lineTo(92, 299); g.lineTo(70, 309); g.closePath(); g.fillStyle = '#c0392b'; g.fill(); g.lineWidth = 2; g.strokeStyle = '#fff'; g.stroke();
      tag('Libre', 200, 300);
      g.restore(); cv.on = false; cv.finish();
      return cv.texts.map(t => ({ text: t.text, n: t.n, low: t.low, fin: t.fin, box: t.box }));
    });
    const h = await hidden(p, { texts: r }), tx = t => r.find(x => x.text === t), says = t => h.find(x => x.startsWith(`«${t}»`)) || '';
    const num = tx('6650'), free = tx('Libre');
    return [
      ['UX-50 − una etiqueta pintada debajo de la escala y la leyenda cuenta como tapada', /bajo la escala/.test(says('Bajo la escala')), says('Bajo la escala') || 'no la ve tapada'],
      ['UX-50 − una etiqueta que se sale por el borde del mapa cuenta como cortada', /cortada por el borde/.test(says('Cortada por el borde')), says('Cortada por el borde') || 'no la ve cortada'],
      ['UX-50 − un número de la regla con un marcador pintado encima cae por su contraste en el fotograma acabado', !!num && num.n > 0 && num.low === 0 && !!num.fin && num.fin.low > 0, num ? `«6650» al pintar ${num.low} de ${num.n} px bajos, al acabar ${num.fin ? `${num.fin.low} (${num.fin.min}:1)` : 'sin medir'}` : 'no está'],
      ['UX-50 − el control, una etiqueta libre, ni tapada ni cortada, pasa al pintarla y al acabar', !!free && !says('Libre') && free.n > 0 && free.low === 0 && !!free.fin && free.fin.low === 0, free ? `«Libre» ${says('Libre') || 'ni tapada ni cortada'}, al acabar ${free.fin ? `${free.fin.low} de ${free.fin.n}` : '?'} px bajos` : 'no está']
    ];
  });

  // --- AR4: los arreglos de la cuarta revisión de Astra (ui/astra/2026-11-11-ui-revision4-astra.md) ---
  // AR4-01: lo que se le escapaba a la sonda del mapa. El +: con la sonda nueva, las vistas de la página se leen en los dos temas, y la
  // comparación con la pantalla no es vacía: mira los píxeles de todos los textos (desde AR5-02; antes, de 8 de cada 10 o más)
  for (const scheme of ['dark', 'light']) await R26(`AR4-01 + ${scheme}`, async p => {
    const r = await readable(p, ['Mirek', 'Linda']), withN = r.f.texts.filter(t => t.n > 0), seen = withN.filter(t => t.comp && t.comp.n > 0);
    return [[`AR4-01 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, la escena recién abierta se lee con la sonda nueva (letra con su fondo cercano, huecos sin rellenar, procedencia de cada imagen y pantalla igual al lienzo), y la pantalla se compara en los píxeles de todos sus textos`, r.ok && withN.length > 0 && seen.length === withN.length, `${r.info} · en pantalla, ${seen.length} de ${withN.length} textos comparados, ${seen.reduce((a, t) => a + t.comp.n, 0)} px`]];
  }, 1600, 960, scheme);
  // El −: cada ataque cae por su propiedad. En la pantalla, lo que CSS hace después del lienzo; a mano sobre el mapa, lo demás
  await R26('AR4-01 − pantalla', async p => {
    const res = [];
    for (const [how, say] of [['filtro', 'un filtro de CSS en el mapa, contrast(0.15)'], ['opacidad', 'lo que contiene el mapa a opacidad 0,3'], ['velo', 'un velo blanco al 50 % encima del mapa, que deja pasar el ratón']]) {
      if (res.length) { await p.goto(URL); await p.waitForTimeout(900); }
      await p.evaluate(how => {
        const m = document.querySelector('#map');
        if (how === 'filtro') m.style.filter = 'contrast(0.15)';
        if (how === 'opacidad') m.parentElement.style.opacity = '0.3';
        if (how === 'velo') { const v = document.createElement('div'); v.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,.5);pointer-events:none;z-index:3'; m.parentElement.appendChild(v); }
      }, how);
      const r = await readable(p, ['Mirek', 'Linda']), w = r.why, only = !w.miss.length && !w.low.length && !w.img.length && !w.fill.length;
      res.push([`AR4-01 − con ${say}, la vista no se lee, y solo porque en pantalla sus textos no son los del lienzo`, !r.ok && only && w.scr.length > 0, `${w.scr.length} de ${r.f.texts.filter(t => t.n > 0).length} textos distintos en pantalla · ${r.info}`]);
    }
    return res;
  });
  await R26('AR4-01 −', async p => {
    const r = await p.evaluate(async () => {
      const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth, cv = window.__cv;
      // antes de grabar: un texto pálido que llega por un ImageBitmap, puesto con bitmaprenderer o hecho con createImageBitmap; uno que pasa
      // por una imagen <img> (toDataURL) a otro lienzo; un lienzo con WebGL, y uno limpio, sin texto
      const pale = t => { const o = new OffscreenCanvas(150, 24), x = o.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = '#888'; x.fillText(t, 2, 15); return o; };
      const br = document.createElement('canvas'); br.width = 150; br.height = 24; br.getContext('bitmaprenderer').transferFromImageBitmap(pale('SIN LECTURA').transferToImageBitmap());
      const cb = await createImageBitmap(pale('SIN LEER'));
      const src = document.createElement('canvas'); src.width = 90; src.height = 20; { const x = src.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = '#888'; x.fillText('SIN MEDIR', 2, 15); }
      const im = new Image(); im.src = src.toDataURL(); await im.decode();
      const viaImg = document.createElement('canvas'); viaImg.width = 90; viaImg.height = 20; viaImg.getContext('2d').drawImage(im, 0, 0);
      const gl = document.createElement('canvas'); gl.width = 40; gl.height = 20; gl.getContext('webgl');
      const clean = document.createElement('canvas'); clean.width = 40; clean.height = 20; { const x = clean.getContext('2d'); x.fillStyle = '#c0392b'; x.fillRect(0, 0, 40, 20); }
      const aux = (t, color, w, h, rr) => { const q = document.createElement('canvas'); q.width = w; q.height = h; const x = q.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = color; for (let u = -rr; u <= rr; u++) for (let v = -rr; v <= rr; v++) if (u * u + v * v <= rr * rr + 1) x.fillText(t, 2 + u, 15 + v); return q; };
      const halo = aux('6550', 'rgb(200,197,182)', 60, 24, 2);
      const tile = draw => { const q = document.createElement('canvas'); q.width = q.height = 6; const h = q.getContext('2d'); draw(h); return g.createPattern(q, 'repeat'); };
      const hat = tile(h => { h.fillStyle = 'rgba(255,255,255,.8)'; h.fillRect(0, 0, 6, 6); h.strokeStyle = '#18191a'; h.lineWidth = 1.6; h.beginPath(); h.moveTo(-1, 7); h.lineTo(7, -1); h.moveTo(-1, 1); h.lineTo(1, -1); h.moveTo(5, 7); h.lineTo(7, 5); h.stroke(); });
      Object.assign(cv, { texts: [], strokes: [], fills: [], images: [], on: true });
      g.save(); g.setTransform(d, 0, 0, d, 0, 0);
      const plate = (t, x, y) => { g.font = '500 12px monospace'; g.fillStyle = 'rgb(200,197,182)'; g.fillRect(x - 2, y - 11, g.measureText(t).width + 4, 14); g.fillStyle = '#222116'; g.fillText(t, x, y); return g.measureText(t); };
      // 1. un bloque de su misma tinta sobre la primera cifra, como el mutante «dígito tapado»: «6050» se ve «▮050»; y en «6400», un píxel de
      // su misma tinta en el hueco de la letra más lejos de ella, como el ojo de una cifra, sea cual sea la fuente: no toca el fondo de alrededor
      { const m = plate('6050', 44, 54); g.fillStyle = '#222116'; g.fillRect(44, 54 - m.actualBoundingBoxAscent, g.measureText('6').width, m.actualBoundingBoxAscent + m.actualBoundingBoxDescent); }
      {
        const m = plate('6400', 44, 240), q = new OffscreenCanvas(80, 24), x = q.getContext('2d'); x.font = '500 12px monospace'; x.fillText('6400', 2, 18);
        const a = x.getImageData(0, 0, 80, 24).data, ink = (u, v) => a[4 * (v * 80 + u) + 3] > 0, X0 = Math.floor(2 - m.actualBoundingBoxLeft), X1 = Math.ceil(2 + m.actualBoundingBoxRight), Y0 = Math.floor(18 - m.actualBoundingBoxAscent), Y1 = Math.ceil(18 + m.actualBoundingBoxDescent);
        let far = [0, 0, 0];
        for (let v = Y0; v < Y1; v++) for (let u = X0; u < X1; u++) { if (ink(u, v)) continue; let k = 1; while (k < 6 && ![...Array(2 * k + 1).keys()].some(i => ink(u - k + i, v - k) || ink(u - k + i, v + k) || ink(u - k, v - k + i) || ink(u + k, v - k + i))) k++; if (k > far[2]) far = [u, v, k]; }
        g.fillStyle = '#222116'; g.fillRect(44 - 2 + far[0], 240 - 18 + far[1], 1, 1);
      }
      // 2. el fondo de la mitad izquierda de un texto, oscurecido después de pintarlo y sin tocar su tinta
      { plate('6250', 44, 84); g.save(); g.globalCompositeOperation = 'darken'; g.fillStyle = 'rgb(60,58,50)'; g.fillRect(42, 72, 16, 16); g.restore(); }
      // 3 a 6. las imágenes: bitmaprenderer, createImageBitmap, la que pasó por <img> y la de WebGL; y el lienzo limpio, que vale
      g.drawImage(br, 40, 100); g.drawImage(cb, 40, 130); g.drawImage(viaImg, 200, 100); g.drawImage(gl, 200, 130); g.drawImage(clean, 200, 160);
      // 7. un bloque oscuro solo, y puntos alargados en columnas, en un círculo; y el rayado de la página, girado 0, 5, 20 y 40°
      const disc = (x, y, fn) => { g.save(); g.translate(x, y); g.beginPath(); g.arc(0, 0, 8.75, 0, Math.PI * 2); g.fillStyle = 'rgb(200,197,182)'; g.fill(); g.fillStyle = '#222116'; fn(); g.restore(); };
      disc(300, 60, () => g.fillRect(-2.5, -9, 5, 18));
      disc(340, 60, () => { for (const x of [-6, -2, 2, 6]) for (const y of [-8, -4, 0, 4]) g.fillRect(x - 1, y, 2, 3); });
      [0, 5, 20, 40].forEach((deg, i) => { g.save(); g.translate(380 + 40 * i, 60); g.rotate(deg * Math.PI / 180); g.beginPath(); g.arc(0, 0, 8.75, 0, Math.PI * 2); g.fillStyle = hat; g.fill(); g.restore(); });
      // 8. los controles: una cifra intacta en su placa, y un texto con su halo de otro lienzo y su letra dentro
      plate('6150', 44, 160); g.drawImage(halo, 40, 190); g.font = '500 12px monospace'; g.fillStyle = '#222116'; g.fillText('6550', 42, 205);
      g.restore(); cv.on = false; cv.finish();
      return { texts: cv.texts.map(t => ({ text: t.text, n: t.n, low: t.low, fin: t.fin, halo: !!t.halo })), images: cv.images.map(i => ({ kind: i.kind, texts: i.texts, unknown: !!i.unknown, halo: i.halo })), fills: cv.fills.filter(f => f.stripes).map(f => ({ x: f.x, s: f.stripes })) };
    });
    const tx = t => r.texts.find(x => x.text === t), fin = t => t && t.fin ? `al acabar ${t.fin.low} de ${t.fin.n} px bajos (${t.fin.min}:1), ${t.fin.filled} de ${t.fin.holes} huecos con tinta` : 'sin medir';
    const [ibr, icb, iimg, igl, iclean, ihalo] = r.images, st = x => (r.fills.find(f => f.x === x) || {}).s;
    const showImg = i => i ? `${i.kind}${i.texts.length ? ` con «${i.texts.join('», «')}»` : ''}${i.unknown ? ', de procedencia desconocida' : ''}${i.halo ? ', halo de su letra' : ''}: ${unmeasured(i) ? 'sin medir' : 'medida'}` : 'no está';
    const blk = tx('6050'), bar = tx('6400'), dk = tx('6250'), ok1 = tx('6150'), ok2 = tx('6550'), hats = [380, 420, 460, 500].map(st);
    return [
      ['AR4-01 − una cifra tapada con un bloque de su misma tinta, como el mutante «dígito tapado», pasaba al pintarla y cae al acabar: por sus huecos, rellenos de tinta, o por su letra, sin contraste con el fondo que tiene cerca', !!blk && blk.n > 0 && blk.low === 0 && !!blk.fin && (blk.fin.filled > 0 || blk.fin.low > 0), `«6050» al pintar ${blk ? `${blk.low} de ${blk.n}` : '?'} px bajos, ${fin(blk)}`],
      ['AR4-01 − un píxel de su misma tinta en el ojo de una cifra cae solo por sus huecos, rellenos de tinta: cada píxel de su letra sigue a su contraste con el fondo que tiene cerca', !!bar && bar.n > 0 && bar.low === 0 && !!bar.fin && bar.fin.low === 0 && bar.fin.filled > 0, `«6400» al pintar ${bar ? `${bar.low} de ${bar.n}` : '?'} px bajos, ${fin(bar)}`],
      ['AR4-01 − un texto con el fondo de su mitad izquierda oscurecido después de pintarlo cae por su contraste con el fondo que tiene cerca', !!dk && dk.n > 0 && !!dk.fin && dk.fin.low > 0, `«6250» ${fin(dk)}`],
      ['AR4-01 − un texto que llega al mapa en un lienzo con bitmaprenderer, desde un ImageBitmap de otro lienzo, llega con su texto y queda sin medir', !!ibr && ibr.texts.includes('SIN LECTURA') && unmeasured(ibr), showImg(ibr)],
      ['AR4-01 − un texto que llega al mapa en un ImageBitmap hecho con createImageBitmap llega con su texto y queda sin medir', !!icb && icb.texts.includes('SIN LEER') && unmeasured(icb), showImg(icb)],
      ['AR4-01 − un lienzo que lleva una imagen <img>, o uno con WebGL, es de procedencia desconocida y queda sin medir', !!iimg && iimg.unknown && unmeasured(iimg) && !!igl && igl.unknown && unmeasured(igl), `${showImg(iimg)} · ${showImg(igl)}`],
      ['AR4-01 − un bloque oscuro solo dentro de un círculo no cuenta como rayado, aunque el criterio de antes lo diera por bueno', !STRIPES(st(300)), `${showStripes(st(300))} · el criterio de antes ${STRIPES0(st(300)) ? 'lo daba por rayado' : 'tampoco lo daba por rayado'}`],
      ['AR4-01 − unos puntos alargados en columnas no cuentan como rayado, aunque el criterio de antes los diera por buenos', !STRIPES(st(340)), `${showStripes(st(340))} · el criterio de antes ${STRIPES0(st(340)) ? 'los daba por rayado' : 'tampoco los daba por rayado'}`],
      ['AR4-01 − el control: el rayado de la página sigue contando como rayado, y girado 0, 5, 20 y 40° el criterio nuevo da lo mismo que el de antes', STRIPES(hats[0]) && hats.every(h => !!h && STRIPES(h) === STRIPES0(h)), hats.map((h, i) => `${[0, 5, 20, 40][i]}°: ${STRIPES(h) ? 'rayado' : 'no'}, antes ${STRIPES0(h) ? 'rayado' : 'no'} (${showStripes(h)})`).join(' · ')],
      ['AR4-01 − el control: una cifra intacta en su placa, un texto con su halo y un lienzo limpio pasan: letra a su contraste, huecos sin tinta y la imagen medida', [ok1, ok2].every(t => !!t && t.n > 0 && t.low === 0 && !!t.fin && t.fin.low === 0 && t.fin.filled === 0) && ok2.halo && !!ihalo && !unmeasured(ihalo) && !!iclean && !unmeasured(iclean), `«6150» ${fin(ok1)} · «6550» ${fin(ok2)} · ${showImg(ihalo)} · ${showImg(iclean)}`]
    ];
  });
  // AR4-02: la planta de la vista previa, a escala en los dos ejes. El + mira dos objetos que no son cuadrados, de escalas distintas; el −,
  // que el criterio falla si se toca un solo eje, si se cambian entre sí o si cambia solo la escala, sobre la vista previa ya pintada
  const PLAN4 = [['Land_Wreck_Ikarus', 'Autobús Ikarus', 11.4, 2.5], ['PowerGenerator', 'Generador', 1.2, 0.8]];
  await R26('AR4-02 +', async p => {
    await openObjs(p);
    const out = []; let ok = true;
    for (const [cls, name, L, Wd] of PLAN4) {
      await p.hover(`#colR [data-act="lib-item"][data-v="${cls}"]`); await p.waitForTimeout(100);
      const v = await preview(p); ok = ok && !!v && v.text.includes(name) && planFits(v, L, Wd); out.push(`${name}: ${showPlan(v, L, Wd)}`);
    }
    return [['AR4-02 + la planta de la vista previa va a escala en los dos ejes en el autobús (11,4 × 2,5 m) y en el generador (1,2 × 0,8 m): el largo a lo ancho y el ancho a lo alto, cada uno a ±1 px de su medida a la escala de su barra', ok, out.join(' · ')]];
  });
  await R26('AR4-02 −', async p => {
    await openObjs(p); await p.hover(BUS); await p.waitForTimeout(100);
    const v0 = await preview(p), res = [['AR4-02 − el control: la planta del autobús sin tocar cumple el criterio', planFits(v0, 11.4, 2.5), showPlan(v0, 11.4, 2.5)]];
    for (const [how, say] of [['ancho', 'solo el ancho, a la quinta parte'], ['largo', 'solo el largo, a la mitad'], ['cambiados', 'el largo y el ancho cambiados entre sí'], ['barra', 'solo la escala de la barra, al 80 %'], ['planta', 'solo la escala de la planta, al 80 % en los dos ejes']]) {
      await p.evaluate(how => {
        const el = document.querySelector('#libPrev'), fp = el.querySelector('.pv-fp'), bi = el.querySelector('.scale i'), w = parseFloat(fp.style.width), h = parseFloat(fp.style.height);
        window.__pv = el.innerHTML;
        if (how === 'ancho') fp.style.height = h / 5 + 'px';
        if (how === 'largo') fp.style.width = w / 2 + 'px';
        if (how === 'cambiados') { fp.style.width = h + 'px'; fp.style.height = w + 'px'; }
        if (how === 'barra') bi.style.width = parseFloat(bi.style.width) * 0.8 + 'px';
        if (how === 'planta') { fp.style.width = w * 0.8 + 'px'; fp.style.height = h * 0.8 + 'px'; }
      }, how);
      const v = await preview(p), old = !!v && !!v.fp && !!v.s && Math.abs(Math.max(...v.fp) - 11.4 * v.s) <= 1;
      await p.evaluate(() => { document.querySelector('#libPrev').innerHTML = window.__pv; });
      res.push([`AR4-02 − con ${say}, la planta del autobús ya no cumple el criterio`, !planFits(v, 11.4, 2.5), `${showPlan(v, 11.4, 2.5)} · el criterio de antes, solo con el lado largo, ${old ? 'la daba por buena' : 'también la rechazaba'}`]);
    }
    return res;
  });

  // AR4-03: el servidor se reinicia mientras rueda. A la vuelta, en el mundo nuevo ya no queda nada de la toma, y eso confirma la parada;
  // ninguna lectura del mundo de antes, ni tocar la profundidad de campo, la confirma
  const reboot = p => p.evaluate(() => { document.querySelector('#bSim').click(); document.querySelector('#menu [data-act="sim-reboot"]').click(); });
  const lostByReboot = async p => {
    if (!await apply(p) || !await arm(p) || !await roll(p)) return null;
    await p.waitForTimeout(600); await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(100);
    const tn = (await T(p, '#slateWrap .tn')) || 'Toma';
    await reboot(p);
    return await shows(p, '#bTopStop', /sin confirmar/, 3000) ? tn : null;
  };
  const countConf = p => p.evaluate(() => { window.__nConf = 0; new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(x => { if (/Parada confirmada/.test(x.textContent)) window.__nConf++; }))).observe(document.querySelector('#toasts'), { childList: true }); });
  const anyConf = p => p.evaluate(() => /Parada confirmada/.test(document.querySelector('#toasts').innerText));
  const newWorldRow = o => !!o && o.obs && /mundo nuevo/.test(o.text) && !/lectura al volver/.test(o.text);
  await R26('AR4-03 +', async p => {
    const what = 'AR4-03 + reiniciado el servidor mientras rueda, sin tocar nada más: al volver, la parada se confirma una vez con el mundo nuevo, con su origen y una edad nueva, sin sumar otra toma, se quita la recuperación, la toma queda desarmada y se puede aplicar otra vez';
    const tn = await lostByReboot(p); if (!tn) return [[what, false, 'no quedó sin confirmar al reiniciar']];
    const k0 = await takesN(p); await countConf(p);
    const conf = await W(p, () => /Parada confirmada/.test(document.querySelector('#toasts').innerText), null, 5000);
    await p.waitForTimeout(1200);
    const o = await takeRow(p, tn), k1 = await takesN(p), n = await p.evaluate(() => window.__nConf);
    const st = await p.evaluate(() => { const s = document.querySelector('#bTopStop'), a = document.querySelector('#bApply'); return { stop: s.hidden ? '' : s.innerText.replace(/\s+/g, ' ').trim(), apply: !a.disabled && !a.hidden }; });
    return [[what, conf && n === 1 && newWorldRow(o) && /Leída hace [0-2] s/.test(o.text) && k1 === k0 && !st.stop && st.apply, `${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar a los 5 s de reiniciar'} · fila: «${o ? o.text.slice(0, 150) : 'no está'}» · Tomas ${k0} → ${k1} · Parar ${st.stop ? `«${st.stop}»` : 'quitado'} · Aplicar ${st.apply ? 'disponible' : 'apagado'}`]];
  });
  await R26('AR4-03 − tu juego', async p => {
    const what = 'AR4-03 − reiniciado el servidor mientras rueda, a los 100 ms de volver el servidor se corta tu juego y se toca dos veces la profundidad de campo: a los 950 ms no hay Observado, ni edad nueva, ni aviso de confirmada, y la recuperación sigue a la vista; al volver tu juego estable, se confirma una sola vez y con el mundo nuevo, nunca con la lectura del mundo de antes';
    const tn = await lostByReboot(p); if (!tn) return [[what, false, 'no quedó sin confirmar al reiniciar']];
    const back = await W(p, () => /se ha reiniciado/.test(document.querySelector('#banner').innerText), null, 4000);
    await p.waitForTimeout(100); await flip(p, 'director'); await flip(p, 'dof'); await flip(p, 'dof'); await p.waitForTimeout(950);
    const o1 = await takeRow(p, tn), c1 = await anyConf(p), st1 = await T(p, '#bTopStop');
    const fake = c1 || !/sin confirmar/.test(st1) || !o1 || o1.obs || !/Sin lectura/.test(o1.text);
    await countConf(p); await flip(p, 'director');
    const conf = await W(p, () => /Parada confirmada/.test(document.querySelector('#toasts').innerText), null, 4000);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(() => window.__nConf), o2 = await takeRow(p, tn);
    return [[what, back && !fake && conf && n === 1 && newWorldRow(o2), `${back ? 'volvió el servidor' : 'sin aviso de mundo nuevo'} · a los 950 ms: ${c1 ? 'aviso de confirmada' : 'sin aviso'}, Parar «${st1.slice(0, 40)}», fila «${o1 ? o1.text.slice(0, 100) : 'no está'}» · al volver estable: ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar'}, fila «${o2 ? o2.text.slice(0, 120) : 'no está'}»`]];
  });
  await R26('AR4-03 − mundo de antes', async p => {
    const what = 'AR4-03 − cortado tu juego mientras rueda, vuelve y a los 200 ms se reinicia el servidor: la lectura que iba a confirmar la parada en el mundo de antes no llega, ni con el servidor caído ni al volver; al volver, se confirma una sola vez y con el mundo nuevo';
    const tn = await lostTake(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    await flip(p, 'director');
    if (!await shows(p, '#bTopStop', /sin confirmar/, 6000)) return [[what, false, 'no quedó sin confirmar']];
    await countConf(p); await flip(p, 'director'); await p.waitForTimeout(200); await reboot(p); await p.waitForTimeout(900);
    const o1 = await takeRow(p, tn), n1 = await p.evaluate(() => window.__nConf), st1 = await T(p, '#bTopStop');
    const fake = n1 > 0 || !/sin confirmar/.test(st1) || !o1 || o1.obs || !/Sin lectura/.test(o1.text);
    const conf = await W(p, () => /Parada confirmada/.test(document.querySelector('#toasts').innerText), null, 5000);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(() => window.__nConf), o2 = await takeRow(p, tn);
    return [[what, !fake && conf && n === 1 && newWorldRow(o2), `con el servidor caído: ${n1 ? 'aviso de confirmada' : 'sin aviso'}, Parar «${st1.slice(0, 40)}», fila «${o1 ? o1.text.slice(0, 100) : 'no está'}» · al volver: ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar'}, fila «${o2 ? o2.text.slice(0, 120) : 'no está'}»`]];
  });

  // AR4-04: una entrada del catálogo sin medidas, o con medidas que no valen. El script de la página va dentro de una función y no se
  // alcanza desde fuera: el catálogo se lee de su archivo, y cada caso sin medidas es una copia de la página con la entrada del autobús cambiada
  const fs = require('fs'), os = require('os'), { fileURLToPath, pathToFileURL } = require('url');
  const catalogOf = () => { const m = fs.readFileSync(fileURLToPath(URL), 'utf8').match(/const CATALOG = (\{[\s\S]*?\n\});/); return m ? Function('return ' + m[1])() : null; };
  // la copia se abre en un contexto aparte, con la sonda; sus errores cuentan como los de cualquier otra página
  const withCopy = async (name, edit, fn) => {
    const src = fs.readFileSync(fileURLToPath(URL), 'utf8'), html = edit(src);
    if (html === src) return null;
    const file = path.join(os.tmpdir(), `estudio-${name}-${process.pid}.html`); fs.writeFileSync(file, html);
    const c = await browser.newContext({ viewport: { width: 1600, height: 960 }, colorScheme: 'dark' });
    try {
      await c.addInitScript(LIB); await c.addInitScript(PROBE);
      const q = await c.newPage(), errs = []; q.setDefaultTimeout(3000);
      q.on('pageerror', e => { errs.push(e.message); errors.push(`[pageerror] ${e.message}`); }); q.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
      await q.goto(pathToFileURL(file).href); await q.waitForTimeout(900);
      return await fn(q, errs);
    } finally { await c.close().catch(() => {}); fs.rmSync(file, { force: true }); }
  };
  const es1 = x => x.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  await R26('AR4-04 +', async p => {
    const what = 'AR4-04 + con sus medidas, cada entrada de Añadir, en las cuatro categorías, enseña en la vista previa su nombre, su clase y sus medidas, y cada objeto su planta a escala en los dos ejes';
    if (!/^file:/.test(URL)) return [[what, false, 'el catálogo se lee del archivo del disco: hace falta una dirección file://']];
    const cat = catalogOf(); if (!cat) return [[what, false, 'no se encontró el catálogo en el archivo']];
    await p.click('[data-act="rtab"][data-v="add"]'); await p.waitForTimeout(100); await p.mouse.move(2, 2);
    const bad = []; let n = 0;
    for (const k of ['objeto', 'infectado', 'animal', 'actor']) {
      await p.click(`[data-act="lib-cat"][data-v="${k}"]`); await p.waitForTimeout(100);
      for (const c of cat[k]) {
        const [l, w, h] = c[c.length - 1]; n++;
        await p.hover(`#colR [data-act="lib-item"][data-v="${c[0]}"]`); await p.waitForTimeout(40);
        const v = await preview(p), want = (k === 'objeto' ? [`${es1(l)} × ${es1(w)} m`] : k === 'animal' ? [`${es1(l)} m de largo`] : []).concat(`${es1(h)} m de alto`);
        if (!(!!v && v.text.includes(c[1]) && v.text.includes(c[0]) && want.every(t => v.text.includes(t)) && !/sin tamaño/i.test(v.text) && (k !== 'objeto' || planFits(v, l, w)))) bad.push(`${c[1]}: ${v ? `«${v.text.slice(0, 70)}»${k === 'objeto' ? ', ' + showPlan(v, l, w) : ''}` : 'sin vista previa'}`);
      }
    }
    return [[what, n > 40 && !bad.length, `${n - bad.length} de ${n} bien${bad.length ? ' · ' + bad.slice(0, 3).join(' · ') : ''}`]];
  });
  const BUS4 = "['Land_Wreck_Ikarus', 'Autobús Ikarus', 'autobus', [11.4, 2.5, 3.1]]", VOLGA = '#colR [data-act="lib-item"][data-v="Land_Wreck_Volha_Police"]';
  const SIZES4 = [['null', 'con el tamaño a null', "['Land_Wreck_Ikarus', 'Autobús Ikarus', 'autobus', null]"], ['sin', 'sin tamaño', "['Land_Wreck_Ikarus', 'Autobús Ikarus', 'autobus']"], ['dos', 'con dos medidas de las tres', "['Land_Wreck_Ikarus', 'Autobús Ikarus', 'autobus', [11.4, 2.5]]"]];
  await R26('AR4-04 −', async p => {
    const res = [];
    if (!/^file:/.test(URL)) return [['AR4-04 − sin medidas', false, 'la copia se hace leyendo el archivo del disco: hace falta una dirección file://']];
    for (const [how, say, entry] of SIZES4) {
      const what = `AR4-04 − ${say}, la vista previa del autobús dice que no tiene tamaño en el catálogo, no se inventa ninguna medida ni planta, sigue con su nombre, su clase, su icono y el aviso de que no hay captura, y no hay ningún error`;
      const r = await withCopy(`sin-medidas-${how}`, src => src.replace(BUS4, entry), async (q, errs) => {
        await freeObj(q); await openObjs(q); await q.mouse.move(2, 2);
        const d = await q.evaluate(s => { const x = document.querySelector(s + ' svg path'); return x ? x.getAttribute('d') : null; }, BUS);
        await q.hover(VOLGA); await q.waitForTimeout(60); await q.hover(BUS); await q.waitForTimeout(100);
        const v = await preview(q), e1 = errs.length;
        const ok = !!v && /Autobús Ikarus/.test(v.text) && /Land_Wreck_Ikarus/.test(v.text) && /Sin captura del juego/.test(v.text) && /Sin tamaño en el catálogo/.test(v.text) && !/×|m de alto|m de largo|NaN|undefined|null|Planta a escala/.test(v.text) && !v.fp && !!d && v.d === d && !e1;
        const out = [[what, ok, `${v ? `«${v.text.slice(0, 120)}»${v.fp ? ', con planta' : ''}` : 'sin vista previa'} · ${e1 ? `${e1} errores: ${errs.slice(0, 2).join(' | ')}` : 'sin errores'}`]];
        if (how !== 'null') return out;
        // con el tamaño a null: el teclado sigue recorriendo la lista, y el autobús se escoge, se lleva sobre el mapa y se pone en el centro con Intro
        await q.mouse.move(2, 2); await q.focus(BUS); await q.keyboard.press('Tab'); await q.waitForTimeout(100);
        const nav = await preview(q);
        await q.click(BUS); await q.waitForTimeout(100);
        const box = await q.locator('#map').boundingBox(); await q.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 3 }); await q.waitForTimeout(150);
        await q.keyboard.press('Enter'); await q.waitForTimeout(250);
        const put = await q.evaluate(() => (document.querySelector('#f-name') || {}).value || '');
        return out.concat([['AR4-04 − con el tamaño a null, el teclado sigue recorriendo Añadir (la fila siguiente enseña su vista previa) y el autobús se escoge, se lleva sobre el mapa y se pone en el centro con Intro, sin errores', !!nav && /Volga de policía/.test(nav.text) && /4,7 × 1,8 m/.test(nav.text) && put === 'Autobús Ikarus' && !errs.length, `la fila siguiente: ${nav ? `«${nav.text.slice(0, 60)}»` : 'sin vista previa'} · Intro: ${put ? `«${put}»` : 'nada'} · ${errs.length ? `${errs.length} errores: ${errs.slice(0, 2).join(' | ')}` : 'sin errores'}`]]);
      });
      res.push(...(r || [[what, false, 'no se encontró la entrada del autobús en el archivo']]));
    }
    return res;
  });

  // AR4-05: Añadir con el presupuesto lleno se recorre con el teclado para ver cada vista previa, sin colocar nada; y el foco del teclado
  // sigue donde estaba, o donde se fue, al rehacer el panel
  const focusOf = p => p.evaluate(() => { const a = document.activeElement, ok = !!a && a !== document.body; return { tag: a ? a.tagName : '', act: ok && a.dataset ? a.dataset.act || '' : '', v: ok && a.dataset ? a.dataset.v || '' : '', vis: ok && a.matches(':focus-visible') }; });
  const showFocus = f => f.act ? `${f.act} ${f.v}${f.vis ? '' : ', sin foco visible'}` : f.tag === 'BODY' ? 'en la página (BODY)' : f.tag;
  const objN = p => p.evaluate(() => document.querySelectorAll('#colL .row[data-v^="ent:obj-"]').length);
  const placing = p => p.locator('[data-act="place-cancel"]').count();
  const firstItems = p => p.evaluate(() => [...document.querySelectorAll('#colR [data-act="lib-item"]')].slice(0, 4).map(b => [b.dataset.v, b.querySelector('.nm').textContent]));
  await R26('AR4-05 + al tope', async p => {
    await openObjs(p); await p.mouse.move(2, 2); await p.focus('#libq');
    const items = await firstItems(p), seen = [];
    for (let i = 0; i < 4; i++) { await p.keyboard.press('Tab'); await p.waitForTimeout(80); seen.push([await focusOf(p), await preview(p)]); }
    const n = await objN(p), pl0 = await placing(p);
    const ok = seen.every(([f, v], i) => f.act === 'lib-item' && f.v === items[i][0] && f.vis && !!v && v.text.includes(items[i][1])) && n === 20 && !pl0;
    return [['AR4-05 + con 20 de 20 objetos, el teclado recorre Añadir › Objetos fila a fila, con el foco a la vista, y la vista previa enseña cada una, sin crear nada ni ponerse a colocar', ok, `${seen.map(([f, v]) => `${showFocus(f)}: ${v ? `«${v.text.slice(0, 32)}»` : 'sin vista previa'}`).join(' · ')} · ${n} objetos${pl0 ? ', colocando' : ''}`]];
  });
  await R26('AR4-05 + con hueco', async p => {
    await freeObj(p); await openObjs(p); await p.mouse.move(2, 2); await p.focus('#libq');
    const items = await firstItems(p); await p.keyboard.press('Tab'); await p.keyboard.press('Tab'); await p.waitForTimeout(80);
    const [cls, name] = items[1], at = f => f.act === 'lib-item' && f.v === cls && f.vis;
    await p.keyboard.press('Space'); await p.waitForTimeout(150);
    const a1 = await placing(p), f1 = await focusOf(p), v1 = await preview(p);
    await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    const a2 = await placing(p), f2 = await focusOf(p);
    await p.keyboard.press('Enter'); await p.waitForTimeout(150);
    const a3 = await placing(p), f3 = await focusOf(p);
    await p.keyboard.press('Enter'); await p.waitForTimeout(250);
    const f4 = await focusOf(p), put = await p.evaluate(() => (document.querySelector('#f-name') || {}).value || ''), n = await objN(p);
    return [[`AR4-05 + con 19 de 20, el ${name.toLowerCase()} se escoge con Espacio y el foco sigue, visible, en su fila, con su vista previa; Esc cancela y el foco sigue en ella; Intro lo escoge otra vez e Intro lo pone en el centro, y el foco pasa, visible, a la pestaña de Propiedades`, a1 > 0 && at(f1) && !!v1 && v1.text.includes(name) && !a2 && at(f2) && a3 > 0 && at(f3) && put === name && n === 20 && f4.act === 'rtab' && f4.v === 'props' && f4.vis,
      `Espacio: ${a1 ? 'colocando' : 'sin colocar'}, foco ${showFocus(f1)}, vista previa ${v1 ? `«${v1.text.slice(0, 30)}»` : 'ninguna'} · Esc: ${a2 ? 'sigue colocando' : 'cancela'}, foco ${showFocus(f2)} · Intro: ${a3 ? 'colocando' : 'sin colocar'}, foco ${showFocus(f3)} · Intro: ${put ? `«${put}»` : 'nada'}, ${n} objetos, foco ${showFocus(f4)}`]];
  });
  await R26('AR4-05 − tope', async p => {
    await openObjs(p);
    await p.click(BUS, { force: true, timeout: 1000 }).catch(() => {}); await p.waitForTimeout(150);
    const a1 = await placing(p), t1 = await T(p, '#toasts');
    await p.evaluate(() => { document.querySelector('#toasts').innerHTML = ''; });
    await p.focus(BUS).catch(() => {}); await p.keyboard.press('Enter'); await p.waitForTimeout(150);
    const a2 = await placing(p), t2 = await T(p, '#toasts'), box = await p.locator('#map').boundingBox();
    await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2); await p.waitForTimeout(150);
    const n1 = await objN(p);
    // con un hueco, colocando con Ctrl + clic: el primero cabe y el segundo ya no
    await freeObj(p); await openObjs(p); await p.click(BUS); await p.waitForTimeout(100);
    await p.evaluate(() => { document.querySelector('#toasts').innerHTML = ''; });
    await p.keyboard.down('Control'); await p.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.5); await p.waitForTimeout(150); await p.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.5); await p.waitForTimeout(150); await p.keyboard.up('Control');
    const n2 = await objN(p), t3 = await T(p, '#toasts'), cap = /Tope de objetos alcanzado/;
    return [['AR4-05 − con 20 de 20, ni el clic ni Intro en una fila de Añadir se ponen a colocar, y el clic en el mapa no crea nada; con 19 de 20, colocando con Ctrl + clic, el primero cabe y el segundo no pasa del tope; las tres veces avisa del tope', !a1 && !a2 && n1 === 20 && n2 === 20 && cap.test(t1) && cap.test(t2) && cap.test(t3),
      `clic: ${a1 ? 'colocando' : 'sin colocar'}${cap.test(t1) ? ', avisa del tope' : ', sin aviso'} · Intro: ${a2 ? 'colocando' : 'sin colocar'}${cap.test(t2) ? ', avisa del tope' : ', sin aviso'} · ${n1} objetos · Ctrl + clic dos veces: ${n2} objetos${cap.test(t3) ? ', avisa del tope' : ', sin aviso'}`]];
  });
  await R26('AR4-05 − foco', async p => {
    await freeObj(p); await openObjs(p); await p.mouse.move(2, 2); await p.focus('#libq');
    const items = await firstItems(p); for (let i = 0; i < 3; i++) await p.keyboard.press('Tab'); await p.waitForTimeout(80);
    const [cls, name] = items[2], at = f => f.act === 'lib-item' && f.v === cls && f.vis, f0 = await focusOf(p);
    // Aplicar rehace el panel varias veces mientras dura
    await p.keyboard.press('Control+Enter'); await W(p, () => document.querySelector('#bApply').disabled, null, 2000); await free(p); await p.waitForTimeout(80);
    const f1 = await focusOf(p), v1 = await preview(p);
    await p.keyboard.press('Control+a'); await p.waitForTimeout(150);
    const f2 = await focusOf(p), v2 = await preview(p), sel = await p.evaluate(() => document.querySelectorAll('#colL [role="treeitem"][aria-selected="true"]').length);
    await p.focus('[data-act="lib-cat"][data-v="infectado"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(150);
    const f3 = await focusOf(p), v3 = await preview(p);
    return [['AR4-05 − con el foco del teclado en una fila de Añadir, al aplicar con Ctrl + Intro, que rehace el panel, y al seleccionar todo con Ctrl + A el foco sigue, visible, en esa fila, y la vista previa la enseña a ella; al cambiar de categoría con Intro, el foco sigue, visible, en la categoría elegida y la vista previa no enseña ninguna fila de antes; nunca queda en la página', at(f0) && at(f1) && !!v1 && v1.text.includes(name) && at(f2) && !!v2 && v2.text.includes(name) && sel > 1 && f3.act === 'lib-cat' && f3.v === 'infectado' && f3.vis && !!v3 && !v3.text.includes(name),
      `al empezar: ${showFocus(f0)} · al aplicar: ${showFocus(f1)}, ${v1 ? `«${v1.text.slice(0, 30)}»` : 'sin vista previa'} · Ctrl + A: ${sel} seleccionados, ${showFocus(f2)}, ${v2 ? `«${v2.text.slice(0, 30)}»` : 'sin vista previa'} · categoría: ${showFocus(f3)}, ${v3 ? `«${v3.text.slice(0, 40)}»` : 'sin vista previa'}`]];
  });

  // AR4-06: una clase que no está en el catálogo, en Propiedades: obj-17 con una clase así, en una copia de la página
  const clsSel = p => p.evaluate(() => { const s = document.querySelector('#f-cls'), o = s && s.selectedOptions[0]; return s ? { value: s.value, text: o ? o.textContent : '' } : null; });
  const showCls = x => x ? `«${x.text}» (${x.value})` : 'sin selector';
  const unknown17 = src => src.replace(/E\('obj-17', 'objeto', '[^']+'/, "E('obj-17', 'objeto', 'Land_Prueba_SinCatalogo'");
  const histN = async p => { await dock(p); return p.evaluate(() => { const n = document.querySelector('#dock [data-act="dtab"][data-v="historial"] .n'); return n ? +n.textContent : -1; }); };
  await R26('AR4-06 +', async p => {
    const what = 'AR4-06 + una clase que no está en el catálogo sale elegida en Propiedades tal cual, con su identificador a la vista y el icono de su fila';
    await p.click('#colL [data-act="sel"][data-v="ent:obj-01"]'); await p.waitForTimeout(120);
    const k = await clsSel(p), row1 = (await rowIcons(p)).find(r => r.id === 'ent:obj-01'), ic1 = await propIcon(p), cat = /^file:/.test(URL) && catalogOf(), name1 = cat && row1 && (cat.objeto.find(x => x[0] === row1.cls) || [])[1];
    const res = [['AR4-06 + una clase del catálogo sale elegida en Propiedades con su nombre, y con el icono de su fila', !!k && !!row1 && k.value === row1.cls && !!name1 && k.text === name1 && !!ic1 && ic1 === row1.d, `${showCls(k)} para ${row1 ? row1.cls : '?'}, que en el catálogo es «${name1 || '?'}» · icono ${ic1 ? (row1 && ic1 === row1.d ? 'el de su fila' : 'otro') : 'ninguno'}`]];
    if (!/^file:/.test(URL)) return res.concat([[what, false, 'la copia se hace leyendo el archivo del disco: hace falta una dirección file://']]);
    const r = await withCopy('clase-ajena', unknown17, async (q, errs) => {
      await q.click('#colL [data-act="sel"][data-v="ent:obj-17"]'); await q.waitForTimeout(120);
      const u = await clsSel(q), row = (await rowIcons(q)).find(x => x.id === 'ent:obj-17'), ic = await propIcon(q);
      return [[what, !!u && u.value === 'Land_Prueba_SinCatalogo' && u.text.includes('Land_Prueba_SinCatalogo') && !!row && row.cls === 'Land_Prueba_SinCatalogo' && !!ic && ic === row.d && ic !== ic1 && !errs.length, `${showCls(u)} · icono ${ic ? (row && ic === row.d ? 'el de su fila' : 'otro') : 'ninguno'}${ic && ic === ic1 ? ', el mismo que el del autobús' : ''} · ${errs.length ? `errores: ${errs.slice(0, 2).join(' | ')}` : 'sin errores'}`]];
    });
    return res.concat(r || [[what, false, 'no se encontró obj-17 en el archivo para cambiarle la clase']]);
  });
  await R26('AR4-06 −', async p => {
    const what = 'AR4-06 − con una clase que no está en el catálogo, al abrir sus Propiedades, al enfocar el selector, al salir de él sin cambiarlo y al volver a ella, el selector nunca enseña la primera clase del catálogo, la entidad sigue con la suya y no hay ningún cambio que deshacer';
    if (!/^file:/.test(URL)) return [[what, false, 'la copia se hace leyendo el archivo del disco: hace falta una dirección file://']];
    const first = catalogOf().objeto[0];
    const r = await withCopy('clase-ajena', unknown17, async (q, errs) => {
      const h0 = await histN(q);
      await q.click('#colL [data-act="sel"][data-v="ent:obj-17"]'); await q.waitForTimeout(120);
      const a = await clsSel(q); await q.focus('#f-cls'); await q.waitForTimeout(60);
      const b = await clsSel(q); await q.keyboard.press('Tab'); await q.waitForTimeout(120);
      await q.click('#colL [data-act="sel"][data-v="ent:obj-01"]'); await q.click('#colL [data-act="sel"][data-v="ent:obj-17"]'); await q.waitForTimeout(120);
      const c = await clsSel(q), row = (await rowIcons(q)).find(x => x.id === 'ent:obj-17'), h1 = await histN(q);
      const firstOne = x => !x || x.value === first[0] || x.text === first[1];
      return [[what, !firstOne(a) && !firstOne(b) && !firstOne(c) && !!row && row.cls === 'Land_Prueba_SinCatalogo' && h0 >= 0 && h1 === h0 && !errs.length,
        `al abrir ${showCls(a)} · al enfocar ${showCls(b)} · al volver ${showCls(c)} · la entidad con ${row ? row.cls : '?'} · Historial ${h0} → ${h1}${errs.length ? ` · errores: ${errs.slice(0, 2).join(' | ')}` : ''}`]];
    });
    return r || [[what, false, 'no se encontró obj-17 en el archivo para cambiarle la clase']];
  });

  // --- AR5: los arreglos de la quinta revisión de Astra (ui/astra/2026-11-11-ui-revision5-astra.md) ---
  // AR5-01: en la pantalla, cada píxel de cada texto es el suyo del lienzo, y no uno cualquiera entre el más claro y el más oscuro de sus
  // vecinos. El + mira la escena recién abierta a 1600 × 960, con el mapa de 855,6 px de alto en CSS, y a 1366 × 768, de alto entero; el −,
  // un filtro de CSS que dilata lo claro 1 px (feMorphology), su ataque: borra las cifras y deja cada canal entre los de sus vecinos
  const allSeen = r => { const t = r.f.texts.filter(x => x.n > 0); return { n: t.length, ok: t.length > 0 && t.every(x => x.comp && x.comp.g > 0 && !x.comp.cut && !x.comp.diff), at: [...new Set(t.filter(x => x.comp).map(x => x.comp.at.join(', ')))].join(' y ') || 'ninguno' }; };
  await R26('AR5-01 +', async p => {
    const res = [];
    for (const [w, h, say] of [[1600, 960, 'a 1600 × 960, con el mapa de 855,6 px de alto en CSS'], [1366, 768, 'a 1366 × 768, con el mapa de alto entero']]) {
      if (res.length) { await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(400); }
      const r = await readable(p, ['Mirek', 'Linda']), a = allSeen(r);
      res.push([`AR5-01 + ${say}, la escena recién abierta se lee, y en pantalla cada texto es el lienzo píxel a píxel: todos sus píxeles a la vista, a 8 de 255 o menos`, r.ok && a.ok, `${a.n} textos, con la captura desplazada ${a.at} px para casar con el lienzo · ${r.info}`]);
    }
    return res;
  });
  await R26('AR5-01 −', async p => {
    const res = [];
    for (const [w, h, on, say] of [[1366, 768, '#map', 'a 1366 × 768, en el mapa'], [1600, 960, '#map', 'a 1600 × 960, en el mapa'], [1600, 960, '#mapwrap', 'a 1600 × 960, en lo que contiene el mapa']]) {
      if (res.length) await p.goto(URL);
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(900);
      await p.evaluate(on => {
        document.body.insertAdjacentHTML('beforeend', '<svg width="0" height="0" style="position:absolute"><filter id="ar5dil"><feMorphology operator="dilate" radius="1"/></filter></svg>');
        document.querySelector(on).style.filter = 'url(#ar5dil)';
      }, on);
      await p.waitForTimeout(150);
      const r = await readable(p, ['Mirek', 'Linda']), x = r.why, only = !x.miss.length && !x.low.length && !x.img.length && !x.fill.length;
      res.push([`AR5-01 − con un filtro de CSS que dilata lo claro 1 px ${say}, la vista no se lee, y solo porque en pantalla sus textos no son los del lienzo`, !r.ok && only && x.scr.length > 0, `${x.scr.length} de ${r.f.texts.filter(t => t.n > 0).length} textos distintos en pantalla · ${r.info}`]);
    }
    return res;
  });
  // AR5-02: no se aparta de la comparación nada más que lo que tapa lo que flota encima del mapa. El +: a 1600 × 960, las cifras de la regla
  // de arriba junto a los controles (6250, 6275 y 6300), que caen en su sombra y antes no se miraban, se miran y se leen. El −: tapadas en
  // pantalla sin tocar ni los controles ni el lienzo, con un bloque negro, como en su ataque, o con uno del color de su placa al 80 %; con una
  // sombra de los controles tan oscura que ya no se leen; y con un aviso encima que tapa una entera, que se queda sin ningún píxel a la vista
  const nearTop = r => r.f.texts.filter(t => t.n > 0 && t.comp && t.comp.dark > 0 && t.box[1] < 20);
  await R26('AR5-02 +', async p => {
    const r = await readable(p, ['Mirek', 'Linda']), q = nearTop(r);
    return [['AR5-02 + a 1600 × 960, las cifras de la regla de arriba que caen en la sombra de los controles se comparan en pantalla y se leen, con la sombra: todos sus píxeles a la vista, a 4,5:1 o más', r.ok && q.length === 3 && q.every(t => t.comp.g > 0 && !t.comp.diff && !t.comp.low),
      `${q.map(t => `«${t.text}» ${t.comp.dark} de ${t.comp.n} px en la sombra, ${t.comp.diff} distintos, ${t.comp.min}:1 en pantalla`).join(' · ') || 'ninguna en la sombra'} · ${r.info}`]];
  }, 1600, 960);
  await R26('AR5-02 −', async p => {
    const res = [];
    for (const [how, say] of [['negro', 'bajo un bloque negro que deja pasar el ratón'], ['placa', 'bajo un bloque del color de su placa al 80 %'], ['sombra', 'bajo una sombra de los controles de 30 px de extensión, negra al 95 %'], ['aviso', 'y un aviso encima que tapa entera la de 6275']]) {
      if (res.length) { await p.goto(URL); await p.waitForTimeout(900); }
      const r0 = await readable(p, ['Mirek', 'Linda']), q0 = nearTop(r0), names = q0.map(t => t.text);
      await p.evaluate(([how, boxes, one]) => {
        const c = document.querySelector('#map'), m = c.getBoundingClientRect(), d = c.width / c.clientWidth, g = c.getContext('2d');
        const u = boxes.reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])]), at = (b, pad) => `left:${m.left + b[0] - pad}px;top:${m.top + b[1] - pad}px;width:${b[2] - b[0] + 2 * pad}px;height:${b[3] - b[1] + 2 * pad}px`;
        if (how === 'negro') document.body.insertAdjacentHTML('beforeend', `<div style="position:fixed;${at(u, 4)};background:#000;pointer-events:none;z-index:50"></div>`);
        if (how === 'placa') { const k = g.getImageData(Math.round((u[0] - 1) * d), Math.round((u[1] + 1) * d), 1, 1).data; document.body.insertAdjacentHTML('beforeend', `<div style="position:fixed;${at(u, 4)};background:rgba(${k[0]},${k[1]},${k[2]},.8);pointer-events:none;z-index:50"></div>`); }
        if (how === 'sombra') document.querySelector('#mapwrap .ovl.tr').style.boxShadow = '0 0 40px 30px rgba(0,0,0,.95)';
        // el aviso, en la pila de avisos, que se mueve con su transform: se pone en 0, 0 y se lleva a su sitio por lo que se ve
        if (how === 'aviso' && one) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = 'Aviso'; t.style.cssText = `position:fixed;${at(one, 6)};padding:0;margin:0`; document.querySelector('#toasts').appendChild(t); const r = t.getBoundingClientRect(); t.style.left = 2 * parseFloat(t.style.left) - r.left + 'px'; t.style.top = 2 * parseFloat(t.style.top) - r.top + 'px'; }
      }, [how, q0.map(t => t.box), (q0.find(t => t.text === '6275') || {}).box || null]);
      await p.waitForTimeout(150);
      const r = await readable(p, ['Mirek', 'Linda']), x = r.why, only = !x.miss.length && !x.low.length && !x.img.length && !x.fill.length, hit = x.scr.filter(t => names.includes(t.text)).map(t => t.text);
      res.push([`AR5-02 − con las cifras de la regla de arriba junto a los controles ${say}, la vista no se lee, y solo porque en pantalla ${how === 'aviso' ? 'esa no se ve' : 'no son las del lienzo o no se leen'}`, names.length === 3 && !r.ok && only && (how === 'aviso' ? hit.includes('6275') : hit.length === 3),
        `en la sombra de los controles: ${names.join(', ') || 'ninguna'} · en pantalla, mal: ${hit.join(', ') || 'ninguna de ellas'} · ${r.info}`]);
    }
    return res;
  });

  // AR5-03: cambiarle el tamaño a un lienzo borra lo que tenía pintado, pero no que pinte con WebGL. El + mira que un lienzo 2D que llevó
  // una imagen <img>, vaciado al cambiarle el tamaño y pintado de un color, vale como limpio; el −, que uno con WebGL sigue de procedencia
  // desconocida antes y después de cambiarle el tamaño con su contexto ya pedido, y lo mismo lo que llega de un OffscreenCanvas con WebGL
  await R26('AR5-03', async p => {
    const r = await p.evaluate(async () => {
      const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth, cv = window.__cv;
      const src = document.createElement('canvas'); src.width = 90; src.height = 20; { const x = src.getContext('2d'); x.font = '500 12px monospace'; x.fillStyle = '#888'; x.fillText('SIN MEDIR', 2, 15); }
      const im = new Image(); im.src = src.toDataURL(); await im.decode();
      const two = document.createElement('canvas'); two.width = 90; two.height = 20; const tx = two.getContext('2d'); tx.drawImage(im, 0, 0); two.width = 40; tx.fillStyle = '#c0392b'; tx.fillRect(0, 0, 40, 20);
      // unos bloques pálidos, como cifras, pintados con scissor y clear: en uno sin cambiarle el tamaño, y en otro y en un OffscreenCanvas
      // con el tamaño cambiado después de pedir el contexto, que es lo que le quitaba la marca
      const pale = q => { q.enable(q.SCISSOR_TEST); q.clearColor(0.53, 0.53, 0.53, 1); for (let i = 0; i < 4; i++) { q.scissor(4 + 10 * i, 6, 6, 12); q.clear(q.COLOR_BUFFER_BIT); } };
      const gl0 = document.createElement('canvas'); gl0.width = 60; gl0.height = 24; pale(gl0.getContext('webgl', { preserveDrawingBuffer: true }));
      const gl1 = document.createElement('canvas'), q1 = gl1.getContext('webgl', { preserveDrawingBuffer: true }); gl1.width = 60; gl1.height = 24; pale(q1);
      const o = new OffscreenCanvas(10, 10), q2 = o.getContext('webgl'); o.width = 60; o.height = 24; pale(q2);
      const br = document.createElement('canvas'); br.width = 60; br.height = 24; br.getContext('bitmaprenderer').transferFromImageBitmap(o.transferToImageBitmap());
      Object.assign(cv, { texts: [], strokes: [], fills: [], images: [], on: true });
      g.save(); g.setTransform(d, 0, 0, d, 0, 0); g.drawImage(two, 200, 100); g.drawImage(gl0, 200, 130); g.drawImage(gl1, 200, 160); g.drawImage(br, 200, 190); g.restore();
      cv.on = false; cv.finish();
      return cv.images.map(i => ({ kind: i.kind, texts: i.texts, unknown: !!i.unknown, halo: i.halo }));
    });
    const [i2d, gl0, gl1, ibr] = r, say = i => i ? `${i.kind}${i.unknown ? ', de procedencia desconocida' : ''}: ${unmeasured(i) ? 'sin medir' : 'medido'}` : 'no está';
    return [
      ['AR5-03 + un lienzo 2D que llevó una imagen <img>, vaciado al cambiarle el tamaño y pintado de un color, vale como limpio y se mide', !!i2d && !i2d.unknown && !unmeasured(i2d), say(i2d)],
      ['AR5-03 − un lienzo con WebGL es de procedencia desconocida antes de cambiarle el tamaño, y lo sigue siendo después, vuelto a pintar con su mismo contexto; y lo que llega por un ImageBitmap de un OffscreenCanvas con WebGL al que se le cambió el tamaño', [gl0, gl1, ibr].every(i => !!i && i.unknown && unmeasured(i)), `sin cambiar: ${say(gl0)} · cambiado: ${say(gl1)} · el del OffscreenCanvas: ${say(ibr)}`]
    ];
  });

  // AR5-04: la planta de la vista previa se mide por sus lados, no por la caja que la envuelve. El + mira las del autobús y el generador
  // sin tocar, y una movida solo de sitio, que se ve igual; el −, cada forma de dejar la misma caja con otra planta: estrecharla y girarla
  // 5°, girarla 0,4° sin tocarla, estrecharla y girar lo que la contiene, y recortarle el pie. Todas las daba por buenas el criterio de AR4-02
  const bend = (p, how) => p.evaluate(how => {
    const el = document.querySelector('#libPrev'), fp = el.querySelector('.pv-fp'), r = fp.getBoundingClientRect(), t = 5 * Math.PI / 180, c = Math.cos(t), s = Math.sin(t), k = Math.cos(2 * t);
    window.__pv = el.innerHTML;
    // los lados que, girados 5°, dejan la misma caja: el autobús pasa de 114 × 25 a 113,1 × 15,2 px
    const narrow = () => { fp.style.width = (r.width * c - r.height * s) / k + 'px'; fp.style.height = (r.height * c - r.width * s) / k + 'px'; };
    if (how === 'girada') { narrow(); fp.style.transform = 'rotate(5deg)'; }
    if (how === 'giro') fp.style.rotate = '0.4deg';
    if (how === 'contenedor') { narrow(); el.querySelector('.pv-plan').style.transform = 'rotate(5deg)'; }
    if (how === 'recorte') fp.style.clipPath = 'inset(0 0 40% 0)';
    if (how === 'movida') fp.style.transform = 'translate(3px, -2px)';
    // los de la sexta revisión (AR6-02): sin su borde y con un contorno discontinuo 10 px por dentro; una muesca de 3 px de hondo en cada lado,
    // entre los puntos que se miran; y la barra recortada a un 80 % de su largo
    if (how === 'contorno') { fp.style.border = '0'; fp.style.outline = '1.5px dashed var(--g-obj)'; fp.style.outlineOffset = '-10px'; }
    if (how === 'muescas') fp.style.clipPath = 'polygon(0 0, 20% 0, 20% 3px, 40% 3px, 40% 0, 100% 0, 100% 20%, calc(100% - 3px) 20%, calc(100% - 3px) 40%, 100% 40%, 100% 100%, 80% 100%, 80% calc(100% - 3px), 60% calc(100% - 3px), 60% 100%, 0 100%, 0 80%, 3px 80%, 3px 60%, 0 60%)';
    if (how === 'barra') el.querySelector('.scale i').style.clipPath = 'inset(0 20% 0 0)';
    // los de la séptima (AR7-01), con los colores de su ataque en cada tema, flojo y fuerte: en oscuro #666 y #999, en claro #aaa y #666. Los
    // tres lados flojos y el de arriba fuerte; en un borde sólido, un tramo flojo del 40 al 60 % de los lados de arriba y de abajo; la línea de
    // abajo de la barra floja y sus lados fuertes; y la planta toda de un gris a 2,999:1 del fondo, que redondeado daba 3,00
    const dk = (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark', [weak, strong] = dk ? ['#666', '#999'] : ['#aaa', '#666'];
    if (how === 'lados') { fp.style.borderColor = weak; fp.style.borderTopColor = strong; }
    if (how === 'tramo') fp.style.borderImage = `linear-gradient(90deg, ${strong} 40%, ${weak} 40% 60%, ${strong} 60%) 1`;
    if (how === 'barra-baja') { const i = el.querySelector('.scale i'); i.style.borderColor = strong; i.style.borderBottomColor = weak; }
    if (how === 'redondeo') fp.style.borderColor = dk ? '#68686a' : '#909092';
  }, how);
  const unbend = p => p.evaluate(() => { document.querySelector('#libPrev').innerHTML = window.__pv; });
  await R26('AR5-04 +', async p => {
    await openObjs(p);
    const out = []; let ok = true;
    for (const [cls, name, L, Wd] of PLAN4) {
      await p.hover(`#colR [data-act="lib-item"][data-v="${cls}"]`); await p.waitForTimeout(100);
      const v = await preview(p); ok = ok && !!v && v.text.includes(name) && planFits(v, L, Wd); out.push(`${name}: ${showPlan(v, L, Wd)}${v && !v.bent.length && !v.miss ? ', nada la gira y sus 12 puntos dan en ella' : ''}`);
    }
    await p.hover(BUS); await p.waitForTimeout(100); await bend(p, 'movida');
    const v = await preview(p); await unbend(p);
    return [['AR5-04 + la planta del autobús y la del generador, sin tocar, cumplen el criterio por sus lados: nada la gira, ni a su barra, y los 12 puntos junto a sus lados dan en ella', ok, out.join(' · ')],
      ['AR5-04 + movida 3 px a un lado y 2 px arriba con un transform, la planta del autobús se ve igual y sigue cumpliéndolo', planFits(v, 11.4, 2.5), showPlan(v, 11.4, 2.5)]];
  });
  await R26('AR5-04 −', async p => {
    await openObjs(p); await p.hover(BUS); await p.waitForTimeout(100);
    const res = [];
    for (const [how, say] of [['girada', 'estrechada a 113,1 × 15,2 px y girada 5°, con la misma caja de 114 × 25 px'], ['giro', 'girada 0,4° sin tocarla'], ['contenedor', 'estrechada igual y girado 5° lo que la contiene, con su barra'], ['recorte', 'recortada con un clip-path que le quita el 40 % de abajo']]) {
      await bend(p, how); const v = await preview(p); await unbend(p);
      res.push([`AR5-04 − ${say}, la planta del autobús ya no cumple el criterio`, !planFits(v, 11.4, 2.5), `${showPlan(v, 11.4, 2.5)} · el criterio de AR4-02, solo con la caja, ${planFits0(v, 11.4, 2.5) ? 'la daba por buena' : 'también la rechazaba'}`]);
    }
    return res;
  });

  // AR5-05: Parar y, mientras dice «Parando…», un corte o un reinicio del servidor. La confirmación que venía en camino ya no vale: la
  // parada se confirma leyendo el juego, como la de una toma cortada, y en su mundo; nunca con «Control devuelto» ni con el mundo de antes
  const stopThen = (p, act) => p.evaluate(a => { document.querySelector('#bTopStop').click(); document.querySelector('#bSim').click(); document.querySelector(a === 'reboot' ? '#menu [data-act="sim-reboot"]' : `#menu [data-act="sim"][data-v="${a}"]`).click(); if (a !== 'reboot') document.querySelector('#status').click(); }, act);
  const rolling = async p => {
    if (!await apply(p) || !await arm(p) || !await roll(p)) return null;
    await p.waitForTimeout(600); await dock(p); await p.click('[data-act="rdtab"][data-v="actividad"]'); await p.waitForTimeout(100);
    return (await T(p, '#slateWrap .tn')) || 'Toma';
  };
  const ctlBack = (p, tn) => p.evaluate(tn => /Control devuelto/.test(document.querySelector('#toasts').innerText) || [...document.querySelectorAll('#dock .qrow')].some(r => r.innerText.includes(tn) && /Control devuelto/.test(r.innerText)), tn);
  const stopState = p => p.evaluate(() => { const s = document.querySelector('#bTopStop'), a = document.querySelector('#bApply'); return { stop: s.hidden ? '' : s.innerText.replace(/\s+/g, ' ').trim(), apply: !a.disabled && !a.hidden }; });
  await R26('AR5-05 + conectado', async p => {
    const what = 'AR5-05 + Parar sin ningún corte confirma como siempre: una vez, con «Control devuelto» y su tiempo, y la toma Observada con lo leído en el servidor y tu juego';
    const tn = await rolling(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    const k0 = await takesN(p);
    await p.click('#bTopStop');
    const back = await W(p, () => /Control devuelto en [\d,]+ s/.test(document.querySelector('#toasts').innerText), null, 2500);
    await p.waitForTimeout(400);
    const o = await takeRow(p, tn), k1 = await takesN(p), st = await stopState(p);
    return [[what, back && !!o && o.obs && /servidor y tu juego/.test(o.text) && !/mundo nuevo|lectura al volver|Reconciliada/.test(o.text) && k1 === k0 + 1 && !st.stop,
      `${back ? '«Control devuelto» a la vista' : 'sin «Control devuelto»'} · fila: «${o ? o.text.slice(0, 150) : 'no está'}» · Tomas ${k0} → ${k1} · Parar ${st.stop ? `«${st.stop}»` : 'quitado'}`]];
  });
  await R26('AR5-05 + reinicio', async p => {
    const what = 'AR5-05 + Parar y reiniciar el servidor enseguida, mientras dice «Parando…»: al volver, la parada se confirma una vez con el mundo nuevo, con su origen y una edad nueva, sin «Control devuelto» ni otra toma; se quita la recuperación y se puede aplicar otra vez';
    const tn = await rolling(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    const k0 = await takesN(p); await countConf(p);
    await stopThen(p, 'reboot');
    const parando = await shows(p, '#bTopStop', /Parando/, 500);
    const conf = await W(p, () => /Parada confirmada/.test(document.querySelector('#toasts').innerText), null, 6000);
    await p.waitForTimeout(1200);
    const o = await takeRow(p, tn), k1 = await takesN(p), n = await p.evaluate(() => window.__nConf), back = await ctlBack(p, tn), st = await stopState(p);
    return [[what, parando && conf && n === 1 && newWorldRow(o) && /Leída hace [0-2] s/.test(o.text) && !back && k1 === k0 + 1 && !st.stop && st.apply,
      `${parando ? '«Parando…» a la vista' : 'sin «Parando…»'} · ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar a los 6 s'} · ${back ? '«Control devuelto» a la vista' : 'sin «Control devuelto»'} · fila: «${o ? o.text.slice(0, 150) : 'no está'}» · Tomas ${k0} → ${k1} · Parar ${st.stop ? `«${st.stop}»` : 'quitado'} · Aplicar ${st.apply ? 'disponible' : 'apagado'}`]];
  });
  await R26('AR5-05 − tu juego', async p => {
    const what = 'AR5-05 − Parar y reiniciar enseguida; a los 100 ms de volver el servidor se corta tu juego y se toca dos veces la profundidad de campo: a los 950 ms no hay Observado, ni edad nueva, ni aviso de confirmada, ni «Control devuelto», y la recuperación sigue a la vista; al volver tu juego estable, se confirma una sola vez y con el mundo nuevo';
    const tn = await rolling(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    await stopThen(p, 'reboot');
    const srv = await W(p, () => /se ha reiniciado/.test(document.querySelector('#banner').innerText), null, 4000);
    await p.waitForTimeout(100); await flip(p, 'director'); await flip(p, 'dof'); await flip(p, 'dof'); await p.waitForTimeout(950);
    const o1 = await takeRow(p, tn), c1 = await anyConf(p), st1 = await T(p, '#bTopStop'), b1 = await ctlBack(p, tn);
    const fake = c1 || b1 || !/sin confirmar/.test(st1) || !o1 || o1.obs || !/Sin lectura/.test(o1.text);
    await countConf(p); await flip(p, 'director');
    const conf = await W(p, () => /Parada confirmada/.test(document.querySelector('#toasts').innerText), null, 4000);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(() => window.__nConf), o2 = await takeRow(p, tn);
    return [[what, srv && !fake && conf && n === 1 && newWorldRow(o2),
      `${srv ? 'volvió el servidor' : 'sin aviso de mundo nuevo'} · a los 950 ms: ${c1 ? 'aviso de confirmada' : 'sin aviso'}${b1 ? ', «Control devuelto»' : ''}, Parar «${st1.slice(0, 40)}», fila «${o1 ? o1.text.slice(0, 100) : 'no está'}» · al volver estable: ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar'}, fila «${o2 ? o2.text.slice(0, 120) : 'no está'}»`]];
  });
  await R26('AR5-05 − corte', async p => {
    const what = 'AR5-05 − Parar y cortar tu juego mientras dice «Parando…», y que vuelva a los 300 ms: la parada no se da por confirmada con «Control devuelto» ni Observada sin leer el juego; se confirma una sola vez al leerlo, con la lectura al volver';
    const tn = await rolling(p); if (!tn) return [[what, false, 'no llegó a rodar']];
    await countConf(p);
    await stopThen(p, 'director'); await p.waitForTimeout(300); await flip(p, 'director'); await p.waitForTimeout(300);
    const o1 = await takeRow(p, tn), b1 = await ctlBack(p, tn), early = (!!o1 && o1.obs) || b1;
    const conf = await W(p, () => /Parada confirmada al leer el juego/.test(document.querySelector('#toasts').innerText), null, 4000);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(() => window.__nConf), o2 = await takeRow(p, tn), b2 = await ctlBack(p, tn);
    return [[what, !early && conf && n === 1 && !!o2 && o2.obs && /lectura al volver/.test(o2.text) && !b2,
      `a los 300 ms de volver: ${early ? `ya Observada o con «Control devuelto» («${o1 ? o1.text.slice(0, 100) : 'no está'}»)` : 'sin confirmar'} · al leer: ${conf ? `confirmada (${n} aviso${n === 1 ? '' : 's'})` : 'sin confirmar'}, fila «${o2 ? o2.text.slice(0, 120) : 'no está'}»${b2 ? ' · «Control devuelto» a la vista' : ''}`]];
  });

  // --- AR6: los arreglos de la sexta revisión de Astra (ui/astra/2026-11-12-ui-revision6-astra.md) ---
  // AR6-01: lo que flota encima del mapa con un recorte se compara, y un texto comparado a medias no se da por leído (dicho así desde AR7-02).
  // Un aviso recortado con clip-path apartaba su caja entera, también lo que no pinta, y un velo debajo de eso tapaba parte de 6275 sin que se
  // comparase: con lo que quedaba comparado, la cifra contaba como leída. El +: a 1600 × 960, en los dos temas, la escena recién abierta, con
  // la sombra de los controles, se lee, y cada texto pintado se compara entero, sin ningún píxel de su letra ni de sus huecos en la caja de lo
  // que flota encima. El −, en 6275, la cifra de la regla de arriba junto a los controles: un aviso que solo pinta su décima parte de la derecha
  // (clip-path) encima de sus tres primeras cifras, y debajo, un velo del color de la placa (su ataque); y un aviso entero encima de sus tres
  // primeras cifras, que deja la última a la vista. Que lo tape entera sigue en AR5-02 −
  const whole = r => { const t = r.f.texts.filter(x => x.n > 0); return { n: t.length, ok: t.length > 0 && t.every(x => x.comp && x.comp.g > 0 && !x.comp.cut) }; };
  for (const scheme of ['dark', 'light']) await R26(`AR6-01 + ${scheme}`, async p => {
    const r = await readable(p, ['Mirek', 'Linda']), a = whole(r), q = nearTop(r);
    return [[`AR6-01 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, a 1600 × 960, la escena recién abierta se lee y cada texto pintado se compara entero en pantalla, también las cifras de arriba que caen en la sombra de los controles`, r.ok && a.ok && q.length === 3,
      `${a.n} textos, ${r.f.texts.filter(x => x.n > 0 && x.comp && !x.comp.cut).length} comparados enteros · en la sombra: ${q.map(t => t.text).join(', ') || 'ninguna'} · ${r.info}`]];
  }, 1600, 960, scheme);
  await R26('AR6-01 −', async p => {
    const res = [];
    for (const [how, say] of [['recortado', 'un aviso que solo pinta su décima parte de la derecha encima de sus tres primeras cifras, y debajo de lo que no pinta, un velo del color de la placa'], ['tres', 'un aviso entero encima de sus tres primeras cifras, con la última a la vista']]) {
      if (res.length) { await p.goto(URL); await p.waitForTimeout(900); }
      const r0 = await readable(p, ['Mirek', 'Linda']), one = (nearTop(r0).find(t => t.text === '6275') || {}).box || null;
      await p.evaluate(([how, one]) => {
        const c = document.querySelector('#map'), m = c.getBoundingClientRect(), d = c.width / c.clientWidth, g = c.getContext('2d');
        const b = [one[0] - 2, one[1] - 2, one[0] + (one[2] - one[0]) * 0.75, one[3] + 2], at = `left:${m.left + b[0]}px;top:${m.top + b[1]}px;width:${b[2] - b[0]}px;height:${b[3] - b[1]}px`;
        if (how === 'recortado') { const k = g.getImageData(Math.round((one[0] - 1) * d), Math.round((one[1] + 1) * d), 1, 1).data; document.body.insertAdjacentHTML('beforeend', `<div style="position:fixed;${at};background:rgb(${k[0]},${k[1]},${k[2]});pointer-events:none;z-index:50"></div>`); }
        // el aviso, en la pila de avisos, que se mueve con su transform: se pone en 0, 0 y se lleva a su sitio por lo que se ve
        const t = document.createElement('div'); t.className = 'toast'; t.textContent = 'Aviso'; t.style.cssText = `position:fixed;${at};padding:0;margin:0;overflow:hidden${how === 'recortado' ? ';clip-path:inset(0 0 0 90%)' : ''}`;
        document.querySelector('#toasts').appendChild(t); const r = t.getBoundingClientRect(); t.style.left = 2 * parseFloat(t.style.left) - r.left + 'px'; t.style.top = 2 * parseFloat(t.style.top) - r.top + 'px';
      }, [how, one]);
      await p.waitForTimeout(150);
      const r = await readable(p, ['Mirek', 'Linda']), x = r.why, only = !x.miss.length && !x.low.length && !x.img.length && !x.fill.length, t = x.scr.find(u => u.text === '6275'), c = t && t.comp;
      res.push([`AR6-01 − en 6275, la cifra de la regla de arriba junto a los controles, con ${say}, la vista no se lee, y solo porque esa cifra ${how === 'recortado' ? 'no se ve como en el lienzo: lo que el aviso no pinta se compara' : 'se compara a medias: lo que se queda sin comparar no se da por leído'}`,
        !!one && !r.ok && only && !!c && (how === 'recortado' ? c.diff > 0 : c.cut > 0 && c.g > 0 && !c.diff),
        `${one ? (c ? `6275: ${c.g} px de su letra comparados, ${c.cut} sin comparar, ${c.diff} distintos` : '6275 se da por leída') : 'no está 6275 junto a los controles'} · ${r.info}`]);
    }
    return res;
  });

  // AR6-02: la planta de la vista previa se mide por lo que se ve, no por su caja. Sin su borde y con un contorno 10 px por dentro
  // (outline-offset) quedaban la caja de 114 × 25 px, la barra a 10 px/m, ningún giro y los 12 puntos, con una planta mucho más pequeña a la
  // vista; y un recorte entre los puntos tampoco se veía. El + mira la planta del autobús y la del generador con su borde, y la del autobús
  // movida solo de sitio, en los dos temas; el −, el contorno por dentro, las muescas entre los puntos y la barra recortada. El giro con la
  // planta estrechada, un eje solo y la barra de otro largo siguen en AR4-02 − y AR5-04 −
  for (const scheme of ['dark', 'light']) await R26(`AR6-02 + ${scheme}`, async p => {
    await openObjs(p);
    const out = []; let ok = true;
    for (const [cls, name, L, Wd] of PLAN4) {
      await p.hover(`#colR [data-act="lib-item"][data-v="${cls}"]`); await p.waitForTimeout(100);
      const v = await preview(p); ok = ok && !!v && v.text.includes(name) && planFits(v, L, Wd); out.push(`${name}: ${showPlan(v, L, Wd)}`);
    }
    await p.hover(BUS); await p.waitForTimeout(100); await bend(p, 'movida');
    const v = await preview(p), tema = scheme === 'dark' ? 'oscuro' : 'claro'; await unbend(p);
    return [[`AR6-02 + en tema ${tema}, la planta del autobús y la del generador se ven de su medida a la escala de la barra, a ±1 px, con sus cuatro lados enteros, ningún píxel de tinta dentro y cada tramo de sus lados a 3:1 o más, y la barra se ve del largo de su caja`, ok, out.join(' · ')],
      [`AR6-02 + en tema ${tema}, movida 3 px a un lado y 2 px arriba con un transform, la planta del autobús se ve igual`, planFits(v, 11.4, 2.5), showPlan(v, 11.4, 2.5)]];
  }, 1600, 960, scheme);
  await R26('AR6-02 −', async p => {
    await openObjs(p); await p.hover(BUS); await p.waitForTimeout(100);
    const res = [];
    for (const [how, say] of [['contorno', 'sin su borde y con un contorno discontinuo 10 px por dentro (outline-offset), con la misma caja de 114 × 25 px'], ['muescas', 'con una muesca de 3 px de hondo en cada lado, entre los puntos que se miran'], ['barra', 'con su barra recortada a un 80 % de su largo con un clip-path, con la misma caja']]) {
      await bend(p, how); const v = await preview(p); await unbend(p);
      res.push([`AR6-02 − ${say}, la planta del autobús ya no cumple el criterio`, !planFits(v, 11.4, 2.5), `${showPlan(v, 11.4, 2.5)} · el criterio de AR5-04, sin la captura, ${planFits5(v, 11.4, 2.5) ? 'la daba por buena' : 'también la rechazaba'}`]);
    }
    return res;
  });

  // AR6-03: los números de la regla no se pisan entre sí. Abierta a 1600 × 960 y encogida a 1440 × 900, el mapa conserva su escala y la
  // placa de Z = 7750 se pintaba encima de X = 6050, en la esquina de arriba a la izquierda. El + mira la escena abierta directamente a
  // 1600 × 960 y a 1440 × 900, y encogida de 1600 × 960 a cada vista que fallaba en su barrido (1440 × 900, 1440 × 901 y 1280 × 720), en
  // los dos temas: se lee, y ninguna letra de un número de la regla cae encima de la de otro. Se lee ido ya el aviso de bienvenida: a 1280 ×
  // 720 tapa entera la etiqueta «Plano general», y que las etiquetas no se aparten de los avisos es un límite declarado de UX-50. El −, en
  // mutantes.js: volver a pintarlos uno encima de otro, y quitar el de X en vez del de Z, que deja sin pintar un número que se espera
  const rulerHits = f => {
    const n = f.texts.filter(t => t.n > 0 && t.box && /^\d+$/.test(t.text)), out = [];
    n.forEach((a, i) => n.slice(i + 1).forEach(b => { if (a.box[0] < b.box[2] && b.box[0] < a.box[2] && a.box[1] < b.box[3] && b.box[1] < a.box[3]) out.push(`«${a.text}» y «${b.text}»`); }));
    return out;
  };
  for (const scheme of ['dark', 'light']) await R26(`AR6-03 + ${scheme}`, async p => {
    const res = [];
    for (const [w, h, from, say] of [[1600, 960, 0, 'abierta a 1600 × 960'], [1440, 900, 1600, 'abierta a 1600 × 960 y encogida a 1440 × 900'], [1440, 900, 0, 'abierta a 1440 × 900'], [1440, 901, 1600, 'abierta a 1600 × 960 y encogida a 1440 × 901'], [1280, 720, 1600, 'abierta a 1600 × 960 y encogida a 1280 × 720']]) {
      if (res.length) { await p.setViewportSize(from ? { width: 1600, height: 960 } : { width: w, height: h }); await p.goto(URL); await p.waitForTimeout(900); }
      if (from) { await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(400); }
      await W(p, () => !document.querySelector('#toasts .toast'), null, 6000);
      const r = await readable(p, ['Mirek', 'Linda']), hits = rulerHits(r.f);
      res.push([`AR6-03 + ${say}, en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, la escena se lee y ningún número de la regla queda encima de otro`, r.ok && !hits.length,
        `${hits.length ? 'uno encima de otro: ' + hits.join(', ') : 'ninguno encima de otro'} · ${r.info}`]);
    }
    return res;
  }, 1600, 960, scheme);

  // --- AR7: los arreglos de la séptima revisión de Astra (ui/astra/2026-11-12-ui-revision7-astra.md) ---
  // AR7-01: el contraste de la planta de la vista previa era el de su píxel más apartado del fondo, y uno solo valía por los cuatro lados. Con
  // el de arriba fuerte y los otros tres flojos pasaba, a 5,85:1 en oscuro con tres lados a 2,90:1, y a 5,40:1 en claro con tres a 2,19:1; y la
  // razón se redondeaba antes de compararla con 3. Ahora cuenta cada tramo de tinta de sus lados y de los de la barra, sin redondear. El +: en
  // los dos temas, la planta del autobús y la del generador, sin tocar y movidas solo de sitio. El −, en los dos temas: su ataque; un tramo
  // flojo en medio de dos lados; la línea de abajo de la barra floja; y la planta a 2,999:1, que redondeada daba 3,00. Todas cumplen lo demás
  for (const scheme of ['dark', 'light']) await R26(`AR7-01 + ${scheme}`, async p => {
    await openObjs(p);
    const tema = scheme === 'dark' ? 'oscuro' : 'claro', res = [];
    for (const moved of [false, true]) {
      const out = []; let ok = true;
      for (const [cls, name, L, Wd] of PLAN4) {
        await p.hover(`#colR [data-act="lib-item"][data-v="${cls}"]`); await p.waitForTimeout(100);
        if (moved) await bend(p, 'movida');
        const v = await preview(p); if (moved) await unbend(p);
        ok = ok && !!v && v.text.includes(name) && planFits(v, L, Wd); out.push(`${name}: ${showPlan(v, L, Wd)}`);
      }
      res.push([`AR7-01 + en tema ${tema}, ${moved ? 'movidas 3 px a un lado y 2 px arriba con un transform' : 'sin tocar'}, la planta del autobús y la del generador cumplen el criterio, con cada tramo de sus cuatro lados y de los tres de su barra a 3:1 o más, sin redondear`, ok, out.join(' · ')]);
    }
    return res;
  }, 1600, 960, scheme);
  for (const scheme of ['dark', 'light']) await R26(`AR7-01 − ${scheme}`, async p => {
    await openObjs(p); await p.hover(BUS); await p.waitForTimeout(100);
    const dk = scheme === 'dark', res = [];
    for (const [how, say] of [['lados', `con el lado de arriba ${dk ? '#999' : '#666'} y los otros tres ${dk ? '#666' : '#aaa'}, como en su ataque`], ['tramo', `con un borde sólido ${dk ? '#999' : '#666'} y un tramo ${dk ? '#666' : '#aaa'} del 40 al 60 % de los lados de arriba y de abajo`], ['barra-baja', `con su barra de lados ${dk ? '#999' : '#666'} y la línea de abajo ${dk ? '#666' : '#aaa'}`], ['redondeo', `toda de ${dk ? '#68686a' : '#909092'}, a 2,999:1 del fondo, que redondeado daba 3,00`]]) {
      await bend(p, how); const v = await preview(p); await unbend(p);
      res.push([`AR7-01 − en tema ${dk ? 'oscuro' : 'claro'}, la planta del autobús ${say}, ya no cumple el criterio, y solo por su contraste`, !planFits(v, 11.4, 2.5) && planFits5(v, 11.4, 2.5) && planGeom(v, 11.4, 2.5),
        `${showPlan(v, 11.4, 2.5)} · el criterio de AR6-02 ${planSeen6(v, 11.4, 2.5) ? 'la daba por buena' : 'también la rechazaba'}`]);
    }
    return res;
  }, 1600, 960, scheme);

  // AR7-02: lo que se aparta de la comparación es la caja de lo que flota encima, recortada por lo que la contiene, aunque no la pinte entera,
  // como un fondo transparente o unas esquinas redondeadas. Eso no lo hace invisible: lo deja sin comparar, y un texto con algo sin comparar
  // no se da por leído. El +: a 1600 × 960, la escena recién abierta se lee y sus 29 textos se comparan enteros. El −: una caja sin fondo, borde
  // ni sombra encima de las tres primeras cifras de 6275 no cambia lo que se ve, y la vista no se lee porque esa cifra queda en parte sin
  // comparar, y así se dice
  await R26('AR7-02 +', async p => {
    const r = await readable(p, ['Mirek', 'Linda']), a = whole(r);
    return [['AR7-02 + a 1600 × 960, la escena recién abierta se lee, y sus 29 textos se comparan enteros, sin ningún píxel de su letra ni de sus huecos sin comparar', r.ok && a.ok && a.n === 29, `${a.n} textos, ${a.ok ? 'todos' : 'no todos'} comparados enteros · ${r.info}`]];
  }, 1600, 960);
  await R26('AR7-02 −', async p => {
    const r0 = await readable(p, ['Mirek', 'Linda']), one = (nearTop(r0).find(t => t.text === '6275') || {}).box || null;
    if (one) await p.evaluate(one => {
      // una caja vacía en la pila de avisos, que se mueve con su transform: se pone en 0, 0 y se lleva a su sitio por lo que se ve
      const m = document.querySelector('#map').getBoundingClientRect(), b = [one[0] - 2, one[1] - 2, one[0] + (one[2] - one[0]) * 0.75, one[3] + 2];
      const t = document.createElement('div'); t.style.cssText = `position:fixed;left:${m.left + b[0]}px;top:${m.top + b[1]}px;width:${b[2] - b[0]}px;height:${b[3] - b[1]}px;pointer-events:none`;
      document.querySelector('#toasts').appendChild(t); const r = t.getBoundingClientRect(); t.style.left = 2 * parseFloat(t.style.left) - r.left + 'px'; t.style.top = 2 * parseFloat(t.style.top) - r.top + 'px';
    }, one);
    await p.waitForTimeout(150);
    const r = await readable(p, ['Mirek', 'Linda']), x = r.why, only = !x.miss.length && !x.low.length && !x.img.length && !x.fill.length, t = x.scr.find(u => u.text === '6275'), c = t && t.comp;
    return [['AR7-02 − una caja sin fondo, borde ni sombra encima de las tres primeras cifras de 6275 no cambia lo que se ve, y la vista no se lee solo porque esa cifra se queda en parte sin comparar, y así se dice: sin comparar, no que no se vea',
      !!one && !r.ok && only && x.scr.length === 1 && !!c && c.cut > 0 && c.g > 0 && !c.diff && /«6275» comparado a medias, con \d+ px de su letra o de sus huecos sin comparar/.test(r.info) && !/a la vista|no se ven/.test(r.info),
      `${one ? (c ? `6275: ${c.g} px de su letra comparados, ${c.cut} sin comparar, ${c.diff} distintos` : '6275 se da por leída') : 'no está 6275 junto a los controles'} · ${r.info}`]];
  }, 1600, 960);

  expect(external.length === 0, 'ninguna petición sale de la página: ' + (external.slice(0, 3).join(' ') || 'ninguna'));
  expect(errors.length === 0, 'sin errores de JavaScript en la página');
  errors.forEach(e => console.log(e));
  console.log(`RESULT ${passes} pass, ${fails} fail`);
  await browser.close();
  process.exitCode = fails ? 1 : 0;
})();
