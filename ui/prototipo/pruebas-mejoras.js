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
// Desde la segunda revisión de Astra (AR2-01) mira también lo que se ve, no solo las órdenes de dibujo:
// - las imágenes que se componen en el mapa. Se apunta qué textos se pintan en cada lienzo, también en los auxiliares y en los que reciben
//   la imagen de otro, y una imagen con texto solo vale si es el halo de la letra que el mapa pinta justo después dentro de ella. Cualquier
//   otra imagen con texto, o una imagen que no sea un lienzo, queda como no medida. No sigue el texto metido en un patrón o en putImageData:
//   si fuera un texto que se espera, lo echa en falta el inventario de la prueba;
// - en cada relleno centrado en su origen, como los marcadores, los píxeles de su interior (a 2 px de CSS del borde) en el fotograma ya
//   acabado: si alternan dos tonos, como un rayado, o si son del color del relleno, opaco;
// - en cada contorno discontinuo de un marcador, sus guiones y sus huecos, sacados de su propio trazo pintado con y sin discontinuo, en
//   cuántos trozos se parte, y en el fotograma acabado el color de los guiones frente al de los huecos.
// Solo graba cuando __cv.on, y se queda con el último fotograma entero del mapa, que empieza pintando el mar en todo el lienzo.
const PROBE = () => {
  const P = CanvasRenderingContext2D.prototype, OP = window.OffscreenCanvasRenderingContext2D ? OffscreenCanvasRenderingContext2D.prototype : null;
  const stroke0 = P.stroke, fill0 = P.fill, fillRect0 = P.fillRect;
  const cv = window.__cv = { on: false, texts: [], strokes: [], fills: [], images: [] }, cache = {};
  const rgba = c => cache[c] || (cache[c] = (() => { const o = new OffscreenCanvas(1, 1).getContext('2d'); o.fillStyle = c; o.fillRect(0, 0, 1, 1); return Array.from(o.getImageData(0, 0, 1, 1).data); })());
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const mine = ctx => cv.on && ctx.canvas && ctx.canvas.id === 'map';
  const dprOf = ctx => ctx.canvas.width / ctx.canvas.clientWidth;
  // qué textos lleva cada lienzo; cambiarle el tamaño lo borra, y con él sus textos
  const TXT = new WeakMap(), tag = (c, t) => { if (!c) return; let s = TXT.get(c); if (!s) TXT.set(c, s = new Set()); s.add(String(t)); };
  [window.HTMLCanvasElement, window.OffscreenCanvas].filter(Boolean).forEach(C => ['width', 'height'].forEach(k => {
    const d = Object.getOwnPropertyDescriptor(C.prototype, k);
    Object.defineProperty(C.prototype, k, { configurable: true, enumerable: d.enumerable, get: d.get, set(v) { TXT.delete(this); d.set.call(this, v); } });
  }));
  // la imagen con texto que espera su letra: la siguiente orden de dibujo del mapa decide si era su halo
  let pending = null;
  const probe = (ctx, draw, style, args) => {
    const t = String(args[0]), x = args[1], y = args[2], T = ctx.getTransform(), m = ctx.measureText(t), dpr = dprOf(ctx);
    const rec = { text: t, px: Math.round(parseFloat((ctx.font.match(/([\d.]+)px/) || [0, 0])[1]) * T.a / dpr * 10) / 10, n: 0, low: 0, min: null };
    if (pending) {
      const b = pending.box, g = [T.a * (x - m.actualBoundingBoxLeft) + T.e, T.d * (y - m.actualBoundingBoxAscent) + T.f, T.a * (x + m.actualBoundingBoxRight) + T.e, T.d * (y + m.actualBoundingBoxDescent) + T.f];
      pending.halo = pending.texts.every(s => s === t) && g[0] >= b[0] - 1 && g[1] >= b[1] - 1 && g[2] <= b[2] + 1 && g[3] <= b[3] + 1; pending = null;
    }
    const pad = Math.ceil(ctx.lineWidth * Math.abs(T.a)) + 2;
    const x0 = Math.max(0, Math.floor(T.a * (x - m.actualBoundingBoxLeft) + T.e) - pad), y0 = Math.max(0, Math.floor(T.d * (y - m.actualBoundingBoxAscent) + T.f) - pad);
    const w = Math.min(ctx.canvas.width, Math.ceil(T.a * (x + m.actualBoundingBoxRight) + T.e) + pad) - x0, h = Math.min(ctx.canvas.height, Math.ceil(T.d * (y + m.actualBoundingBoxDescent) + T.f) + pad) - y0;
    if (w > 0 && h > 0) {
      const under = ctx.getImageData(x0, y0, w, h), bg = under.data;
      ctx.save(); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.shadowColor = 'transparent'; ctx.filter = 'none';
      ctx[style] = '#fff'; draw.apply(ctx, args); const wh = ctx.getImageData(x0, y0, w, h).data; ctx.putImageData(under, x0, y0);
      ctx[style] = '#000'; draw.apply(ctx, args); const bk = ctx.getImageData(x0, y0, w, h).data; ctx.putImageData(under, x0, y0);
      ctx.restore();
      const ink = rgba(String(ctx[style])), a = ink[3] / 255 * ctx.globalAlpha;
      let min = 99;
      for (let i = 0; i < bg.length; i += 4) {
        if (wh[i] - bk[i] + wh[i + 1] - bk[i + 1] + wh[i + 2] - bk[i + 2] < 383) continue;
        const b = [bg[i], bg[i + 1], bg[i + 2]], r = ratio([0, 1, 2].map(k => ink[k] * a + b[k] * (1 - a)), b);
        rec.n++; if (r < 4.5) rec.low++; if (r < min) min = r;
      }
      if (rec.n) rec.min = Math.round(min * 100) / 100;
    }
    cv.texts.push(rec);
  };
  [P, OP].filter(Boolean).forEach(Q => {
    const fillText0 = Q.fillText, strokeText0 = Q.strokeText, drawImage0 = Q.drawImage;
    Q.fillText = function () { tag(this.canvas, arguments[0]); if (mine(this)) probe(this, fillText0, 'fillStyle', arguments); return fillText0.apply(this, arguments); };
    Q.strokeText = function () { tag(this.canvas, arguments[0]); if (mine(this)) probe(this, strokeText0, 'strokeStyle', arguments); return strokeText0.apply(this, arguments); };
    Q.drawImage = function (src) {
      const s = TXT.get(src);
      if (s) s.forEach(t => tag(this.canvas, t));
      if (mine(this)) {
        const a = arguments, T = this.getTransform(), sw = src.width || 0, sh = src.height || 0;
        const [dx, dy, dw, dh] = a.length === 3 ? [a[1], a[2], sw, sh] : a.length === 5 ? [a[1], a[2], a[3], a[4]] : [a[5], a[6], a[7], a[8]], xs = [], ys = [];
        [[dx, dy], [dx + dw, dy], [dx, dy + dh], [dx + dw, dy + dh]].forEach(([u, v]) => { xs.push(T.a * u + T.c * v + T.e); ys.push(T.b * u + T.d * v + T.f); });
        const kind = src instanceof HTMLCanvasElement || (window.OffscreenCanvas && src instanceof OffscreenCanvas) ? 'canvas' : (src && src.constructor && src.constructor.name) || 'imagen';
        const rec = { kind, texts: s ? [...s] : [], box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], halo: false };
        cv.images.push(rec); pending = rec.texts.length ? rec : null;
      }
      return drawImage0.apply(this, arguments);
    };
  });
  P.fillRect = function (x, y, w, h) {
    if (mine(this)) {
      pending = null;
      const T = this.getTransform(), c = this.canvas;
      if (!T.b && !T.c && T.a * x + T.e <= 0.5 && T.d * y + T.f <= 0.5 && T.a * (x + w) + T.e >= c.width - 1 && T.d * (y + h) + T.f >= c.height - 1) Object.assign(cv, { texts: [], strokes: [], fills: [], images: [] });
    }
    return fillRect0.apply(this, arguments);
  };
  const at = (ctx, kind) => { const T = ctx.getTransform(), dpr = dprOf(ctx); return { kind, x: Math.round(T.e / dpr), y: Math.round(T.f / dpr), dash: ctx.getLineDash().join(','), lw: ctx.lineWidth }; };
  // caja de px del lienzo alrededor del origen, de r px de CSS de radio
  const around = (ctx, T, r) => { const R = Math.ceil(r * dprOf(ctx)), cx = Math.round(T.e), cy = Math.round(T.f), x0 = Math.max(0, cx - R), y0 = Math.max(0, cy - R); return [x0, y0, Math.min(ctx.canvas.width, cx + R) - x0, Math.min(ctx.canvas.height, cy + R) - y0]; };
  // cuánto cubre el propio trazo cada píxel de la caja: se pinta en blanco y en negro solo dentro de ella, y se devuelve el fondo
  const cover = (ctx, T, [x0, y0, w, h], dash) => {
    const under = ctx.getImageData(x0, y0, w, h), clip = new Path2D(); clip.rect(x0, y0, w, h);
    const paint = c => { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clip(clip); ctx.setTransform(T); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.shadowColor = 'transparent'; ctx.filter = 'none'; if (dash) ctx.setLineDash(dash); ctx.strokeStyle = c; stroke0.call(ctx); ctx.restore(); const d = ctx.getImageData(x0, y0, w, h).data; ctx.putImageData(under, x0, y0); return d; };
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
  P.stroke = function () {
    if (!mine(this)) return stroke0.apply(this, arguments);
    pending = null;
    const rec = at(this, 'stroke'), T = this.getTransform();
    // el contorno discontinuo de un marcador: su trazo rodea su origen
    const box = around(this, T, 13);
    if (!arguments.length && rec.dash && box[2] > 0 && box[3] > 0 && this.isPointInPath(T.e, T.f)) {
      const [x0, y0, w, h] = box, dash = cover(this, T, box, null), full = cover(this, T, box, []), on = [], off = [];
      for (let i = 0; i < w * h; i++) { const q = [x0 + i % w, y0 + Math.floor(i / w)]; if (dash[i] >= 0.75) on.push(q); else if (full[i] >= 0.75 && dash[i] <= 0.1) off.push(q); }
      rec.raw = { on, off }; rec.gaps = { comps: pieces(dash, w, h), gapPx: off.length, dashPx: on.length };
    }
    cv.strokes.push(rec);
    return stroke0.apply(this, arguments);
  };
  P.fill = function () {
    if (!mine(this)) return fill0.apply(this, arguments);
    pending = null;
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
      rec.raw = { px };
    }
    cv.fills.push(rec);
    return r;
  };
  // Al cerrar el fotograma: de cada interior, los dos tonos (se separan por luminancia), qué parte es de cada uno, su contraste y cuántas
  // veces cambia de tono cada fila de 6 px o más; y la parte del color del relleno, si es opaco. De cada contorno discontinuo, el contraste
  // entre el color mediano de sus guiones y el de sus huecos.
  cv.finish = () => {
    const c = document.querySelector('#map'), W = c.width, D = c.getContext('2d').getImageData(0, 0, W, c.height).data;
    const col = ([x, y]) => { const i = 4 * (y * W + x); return [D[i], D[i + 1], D[i + 2]]; };
    const med = cs => { if (!cs.length) return null; const s = cs.slice().sort((a, b) => lum(a) - lum(b)); return s[s.length >> 1]; };
    const r2 = v => Math.round(v * 100) / 100;
    cv.fills.forEach(f => {
      if (!f.raw) return;
      const px = f.raw.px, cs = px.map(col), L = cs.map(lum); delete f.raw;
      if (!cs.length) return;
      const lo = Math.min(...L), hi = Math.max(...L); let thr = (lo + hi) / 2;
      for (let k = 0; k < 12; k++) { let a = 0, na = 0, b = 0, nb = 0; L.forEach(v => { if (v < thr) { a += v; na++; } else { b += v; nb++; } }); if (!na || !nb) break; thr = (a / na + b / nb) / 2; }
      const light = L.map(v => hi - lo > 1e-4 && v >= thr), nl = light.filter(Boolean).length;
      const mean = sel => { const q = cs.filter((_, i) => light[i] === sel); return q.length ? [0, 1, 2].map(k => q.reduce((s, x) => s + x[k], 0) / q.length) : null; };
      const ml = mean(true), md = mean(false), rows = {};
      px.forEach(([x, y], i) => (rows[y] = rows[y] || []).push([x, light[i]]));
      let alt = 0, nr = 0;
      Object.values(rows).forEach(r => { if (r.length < 6) return; r.sort((a, b) => a[0] - b[0]); for (let k = 1; k < r.length; k++) if (r[k][0] === r[k - 1][0] + 1 && r[k][1] !== r[k - 1][1]) alt++; nr++; });
      f.stripes = { n: cs.length, light: r2(nl / cs.length), dark: r2(1 - nl / cs.length), ratio: ml && md ? r2(ratio(ml, md)) : 1, alt: nr ? r2(alt / nr) : 0 };
      if (f.ink) f.solid = { share: f.ink[3] < 0.99 ? 0 : r2(cs.filter(x => Math.max(...[0, 1, 2].map(k => Math.abs(x[k] - f.ink[k]))) <= 24).length / cs.length) };
    });
    cv.strokes.forEach(s => {
      if (!s.raw) return;
      const on = med(s.raw.on.map(col)), off = med(s.raw.off.map(col)); delete s.raw;
      s.gaps.ratio = on && off ? r2(ratio(on, off)) : 1;
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
  // contraste de lo pintado en el mapa: cada texto, con todos los píxeles de su letra a 4,5:1 o más
  const lowTexts = f => f.texts.filter(t => t.low > 0);
  const showLow = l => l.slice(0, 4).map(t => `«${t.text}» ${t.min}:1 en ${t.low} de ${t.n} px`).join(' · ');
  const mapPct = p => p.evaluate(() => { const r = document.querySelector('#map').getBoundingClientRect(); return Math.round(r.width * r.height / (innerWidth * innerHeight) * 100); });
  const hatched = f => f.fills.filter(x => x.pat);
  // Lo que se ve en el fotograma acabado (AR2-01). Rayado: dos tonos a 3:1 o más entre sí, cada uno en al menos un 15 % del interior,
  // que alternan a lo ancho (más de un cambio de tono por fila, de media). Huecos de un contorno discontinuo: se parte en tres trozos o más,
  // hay huecos de verdad (6 px o más) y su color se distingue del de los guiones (1,5:1 o más). Sólido: el 85 % del interior es del color
  // del relleno, opaco.
  const STRIPES = s => !!s && s.light >= 0.15 && s.dark >= 0.15 && s.ratio >= 3 && s.alt > 1;
  const GAPS = g => !!g && g.comps >= 3 && g.gapPx >= 6 && g.ratio >= 1.5;
  const SOLID = s => !!s && s.share >= 0.85;
  const striped = f => hatched(f).filter(x => STRIPES(x.stripes));
  const showStripes = s => s ? `${Math.round(s.light * 100)} % claro y ${Math.round(s.dark * 100)} % oscuro a ${s.ratio}:1, ${s.alt} cambios por fila` : 'sin interior';

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
    const n = await p.locator('#colR .item').count(), off = await p.locator('#colR .item[disabled]').count(), tot = await T(p, '#colR .btotal');
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
    const near = s => Math.abs(s.x - c[0]) <= 3 && Math.abs(s.y - c[1]) <= 3, g = f.strokes.filter(near), fl = f.fills.filter(near), d = g.find(s => s.gaps);
    return { nominal: g.filter(s => s.dash).length, dashed: g.filter(s => s.dash && GAPS(s.gaps)).length, solid: g.filter(s => !s.dash && s.lw >= 3).length, filled: fl.filter(x => SOLID(x.solid)).length,
      see: `${d ? `contorno en ${d.gaps.comps} trozos, ${d.gaps.gapPx} px de hueco a ${d.gaps.ratio}:1 de los guiones` : 'sin contorno discontinuo'}, interior ${fl.map(x => x.solid ? Math.round(x.solid.share * 100) + ' % del relleno' : '?').join('/') || 'no visto'}` };
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
    const kx = (b[0] - a[0]) / (wb[0] - wa[0]), kz = (b[1] - a[1]) / (wb[1] - wa[1]), s = Math.abs(kx);
    const u = x => a[0] - r.x + (x - wa[0]) * kx, v = z => a[1] - r.y + (z - wa[1]) * kz, wx = q => wa[0] + (q + r.x - a[0]) / kx, wz = q => wa[1] + (q + r.y - a[1]) / kz;
    const sp = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000].find(m => m * s >= 70) || 5000, want = [...names];
    const [x0, x1] = [wx(0), wx(r.width)].sort((m, n) => m - n), [z0, z1] = [wz(0), wz(r.height)].sort((m, n) => m - n);
    for (let x = Math.ceil(x0 / sp) * sp; x <= x1; x += sp) if (x >= 0 && x <= 15360 && u(x) >= 6 && u(x) <= r.width - 56) want.push(String(x));
    for (let z = Math.ceil(z0 / sp) * sp; z <= z1; z += sp) if (z >= 0 && z <= 15360 && v(z) >= 36 && v(z) <= r.height - 6) want.push(String(z));
    if (s < 1.2) TOWNS.forEach(([t, x, z]) => { if (u(x) >= 70 && u(x) <= r.width - 70 && v(z) >= 24 && v(z) <= r.height - 12) want.push(t); });
    return want;
  };
  // Una vista del mapa se lee si cada texto esperado está pintado, con su letra medida; si cada texto pintado llega a 4,5:1 en todos los
  // píxeles de su letra, y si ninguna imagen con texto se queda sin medir. Sin textos, o sin inventario, no pasa.
  const unmeasured = i => i.kind !== 'canvas' || (i.texts.length > 0 && !i.halo);
  const missing = (want, seen) => { const c = {}; seen.forEach(t => { c[t] = (c[t] || 0) + 1; }); return want.filter(t => c[t] > 0 ? (c[t]--, false) : true); };
  const readable = async (p, names = []) => {
    const want = await inventory(p, names), f = await frame(p), low = lowTexts(f), img = f.images.filter(unmeasured);
    const miss = want ? missing(want, f.texts.filter(t => t.n > 0).map(t => t.text)) : [];
    return { ok: !!want && want.length > 0 && f.texts.length > 0 && !miss.length && !low.length && !img.length,
      info: `${f.texts.length} textos, ${want ? want.length : 'sin'} esperados${miss.length ? `, faltan ${miss.slice(0, 4).map(t => '«' + t + '»').join(', ')}` : ''}${low.length ? ', bajos ' + showLow(low) : ''}${img.length ? `, ${img.length} imágenes sin medir${img[0].texts.length ? ' con «' + img[0].texts.slice(0, 2).join('», «') + '»' : ''}` : ''}` };
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
    return [[what, /actores estimados/.test(note) && /no mueve el juego/.test(note) && /estimación/.test(leg) && /en el juego y leído/.test(leg) && /solo existe aquí/.test(g) && /rueda/.test(g), `nota: «${note}» · leyenda: ${/estimación/.test(leg) ? 'el rayado es una estimación' : 'no dice qué es el rayado'}${/en el juego y leído/.test(leg) ? ', el relleno, leído' : ''} · Guía: «${g.slice(g.indexOf('Lo propio') >= 0 ? g.indexOf('Lo propio') : 0, (g.indexOf('Lo propio') >= 0 ? g.indexOf('Lo propio') : 0) + 150)}…»`]];
  });
  await R26('AR2-07 −', async p => {
    const what = 'AR2-07 − la nota no dice que solo se mueve la cámara ni que no se tocan los actores, y la Guía no dice que lo único propio es saber qué hay en el juego';
    await p.keyboard.press('2'); await p.waitForTimeout(300); const note = await T(p, '.tlnote');
    await p.keyboard.press('1'); await p.waitForTimeout(200); await p.click('#bGuide'); await p.waitForTimeout(400); const g = await about(p);
    return [[what, !!note && !/solo la cámara|ni los actores/.test(note) && !!g && !/Lo único propio/.test(g), `nota: «${note}» · Guía: ${/Lo único propio/.test(g) ? '«Lo único propio…»' : 'sin «Lo único propio»'}`]];
  });

  expect(external.length === 0, 'ninguna petición sale de la página: ' + (external.slice(0, 3).join(' ') || 'ninguna'));
  expect(errors.length === 0, 'sin errores de JavaScript en la página');
  errors.forEach(e => console.log(e));
  console.log(`RESULT ${passes} pass, ${fails} fail`);
  await browser.close();
  process.exitCode = fails ? 1 : 0;
})();
