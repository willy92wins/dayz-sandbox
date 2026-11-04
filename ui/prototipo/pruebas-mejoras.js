// Criterios R26 de las mejoras de noviembre (ui/2026-11-04-ui-mejoras-consolidado.md §2: AHORA y la segunda pasada): un caso + y uno − por mejora.
// Uso: node ui/prototipo/pruebas-mejoras.js (necesita Playwright con Chromium). Cada caso abre una página nueva.
// Contra el prototipo de antes (ESTUDIO_URL=file://… con `git show de37c03:ui/prototipo/estudio.html`) los + tienen que fallar;
// un − que ya se cumplía antes pasa también allí. El contraste de CU-38 en los dos temas sigue en pruebas.js; el del mapa, aquí (AR-03).
// Los casos AR-xx son los arreglos de la revisión de Astra (ui/astra/2026-11-04-ui-revision-astra.md). Lo que se pinta en el mapa
// se mira con una sonda del lienzo, no con contadores de la propia página (AR-04); mutantes.js comprueba que esas pruebas fallan
// cuando el dibujo se rompe. SOLO=<expresión> pasa solo los casos cuyo nombre encaje.
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
// Sonda del lienzo del mapa: cada texto pintado con su tamaño en px de CSS y el contraste de cada píxel de la letra contra lo que ya
// estaba pintado debajo; y cada trazo y relleno con su posición, su discontinuo y su grosor. Solo graba cuando __cv.on.
const PROBE = () => {
  const P = CanvasRenderingContext2D.prototype, fillText0 = P.fillText, stroke0 = P.stroke, fill0 = P.fill;
  const cv = window.__cv = { on: false, texts: [], strokes: [], fills: [] }, cache = {};
  const rgba = c => cache[c] || (cache[c] = (() => { const o = new OffscreenCanvas(1, 1).getContext('2d'); o.fillStyle = c; o.fillRect(0, 0, 1, 1); return Array.from(o.getImageData(0, 0, 1, 1).data); })());
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const mine = ctx => cv.on && ctx.canvas && ctx.canvas.id === 'map';
  P.fillText = function (txt, x, y) {
    if (mine(this)) {
      const t = String(txt), T = this.getTransform(), m = this.measureText(t), dpr = this.canvas.width / this.canvas.clientWidth;
      const rec = { text: t, px: Math.round(parseFloat((this.font.match(/([\d.]+)px/) || [0, 0])[1]) * T.a / dpr * 10) / 10, n: 0, low: 0, min: null };
      const x0 = Math.max(0, Math.floor(T.a * (x - m.actualBoundingBoxLeft) + T.e)), y0 = Math.max(0, Math.floor(T.d * (y - m.actualBoundingBoxAscent) + T.f));
      const w = Math.min(this.canvas.width, Math.ceil(T.a * (x + m.actualBoundingBoxRight) + T.e)) - x0, h = Math.min(this.canvas.height, Math.ceil(T.d * (y + m.actualBoundingBoxDescent) + T.f)) - y0;
      if (w > 0 && h > 0) {
        const oc = new OffscreenCanvas(w, h).getContext('2d');
        oc.setTransform(T.a, T.b, T.c, T.d, T.e - x0, T.f - y0); oc.font = this.font; oc.textAlign = this.textAlign; oc.textBaseline = this.textBaseline; oc.fillText(t, x, y);
        const mask = oc.getImageData(0, 0, w, h).data, bg = this.getImageData(x0, y0, w, h).data, ink = rgba(String(this.fillStyle)), a = ink[3] / 255;
        let min = 99;
        for (let i = 0; i < mask.length; i += 4) {
          if (mask[i + 3] < 200) continue;
          const b = [bg[i], bg[i + 1], bg[i + 2]], r = ratio([0, 1, 2].map(k => ink[k] * a + b[k] * (1 - a)), b);
          rec.n++; if (r < 4.5) rec.low++; if (r < min) min = r;
        }
        if (rec.n) rec.min = Math.round(min * 100) / 100;
      }
      cv.texts.push(rec);
    }
    return fillText0.apply(this, arguments);
  };
  const at = (ctx, kind) => { const T = ctx.getTransform(), dpr = ctx.canvas.width / ctx.canvas.clientWidth; return { kind, x: Math.round(T.e / dpr), y: Math.round(T.f / dpr), dash: ctx.getLineDash().join(','), lw: ctx.lineWidth }; };
  P.stroke = function () { if (mine(this)) cv.strokes.push(at(this, 'stroke')); return stroke0.apply(this, arguments); };
  P.fill = function () { if (mine(this)) cv.fills.push(at(this, 'fill')); return fill0.apply(this, arguments); };
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
    await p.evaluate(() => { Object.assign(window.__cv, { texts: [], strokes: [], fills: [], on: true }); });
    await p.setViewportSize(vs); await p.waitForTimeout(300);
    return p.evaluate(() => { const cv = window.__cv; cv.on = false; return { texts: cv.texts, strokes: cv.strokes, fills: cv.fills }; });
  };
  // contraste de lo pintado en el mapa: cada texto, con al menos el 98 % de los píxeles de su letra a 4,5:1 o más
  const lowTexts = f => f.texts.filter(t => t.n && t.low / t.n > 0.02);
  const showLow = l => l.slice(0, 4).map(t => `«${t.text}» ${t.min}:1 en ${t.low} de ${t.n} px`).join(' · ');
  const mapPct = p => p.evaluate(() => { const r = document.querySelector('#map').getBoundingClientRect(); return Math.round(r.width * r.height / (innerWidth * innerHeight) * 100); });

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
  await R26('UX-09 −', async p => {
    const what = 'UX-09 − lo que está sin aplicar se pinta como documento (contorno discontinuo) y pasa a sólido solo tras aplicar y leer';
    // la entidad cambiada se busca por su icono en la Jerarquía, se encuadra con F y se mira el glifo pintado en el centro del mapa
    const id = await p.evaluate(() => { const r = [...document.querySelectorAll('#colL .row[data-v^="ent:"]')].find(r => r.querySelector('.st svg')); return r ? r.dataset.v : null; });
    if (!id) return [[what, false, 'ninguna entidad cambiada en la Jerarquía']];
    const center = async () => {
      await p.click(`#colL [data-v="${id}"]`); await p.focus('#map'); await p.keyboard.press('f'); await p.waitForTimeout(250);
      const f = await frame(p), c = await p.evaluate(() => { const m = document.querySelector('#map'); return [m.clientWidth / 2, m.clientHeight / 2]; });
      const g = f.strokes.filter(s => Math.abs(s.x - c[0]) <= 3 && Math.abs(s.y - c[1]) <= 3);
      return { dashed: g.filter(s => s.dash).length, solid: g.filter(s => !s.dash && s.lw >= 3).length };
    };
    const a = await center();
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const b = await center();
    return [[what, a.dashed > 0 && !a.solid && !b.dashed && b.solid > 0, `${id.slice(4)} con un cambio: ${a.dashed} trazos discontinuos y ${a.solid} sólidos · aplicada y leída: ${b.dashed} y ${b.solid}`]];
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
  // UX-33: las zonas de la barra no se pisan ni se salen del borde, con el cursor en cualquier punto del mapa; «MCP apagado» se ve entero (CU-35)
  const zones = p => p.evaluate(() => {
    const st = document.querySelector('#status'), sr = st.getBoundingClientRect(), cs = getComputedStyle(st);
    const lo = sr.left + parseFloat(cs.paddingLeft) - 0.5, hi = sr.right - parseFloat(cs.paddingRight) + 0.5;
    const els = [...st.children, ...document.querySelector('#stInfo').children].filter(e => e.id !== 'stInfo' && !e.classList.contains('ssep') && !e.classList.contains('grow') && e.getClientRects().length && e.textContent.trim());
    const z = els.map(e => { const r = document.createRange(); r.selectNodeContents(e); const q = r.getBoundingClientRect(); return { t: e.textContent.replace(/\s+/g, ' ').trim().slice(0, 24), l: q.left, r: q.right, y: q.top + q.height / 2 }; });
    const bad = z.filter(a => a.l < lo || a.r > hi).map(a => `«${a.t}» se sale`);
    z.forEach(a => z.forEach(b => { if (a !== b && Math.abs(a.y - b.y) < 6 && b.l >= a.l && b.l - a.r < 6) bad.push(`«${a.t}» y «${b.t}» a ${Math.round(b.l - a.r)} px`); }));
    const m = z.find(a => /MCP apagado/.test(a.t));
    return { bad, h: Math.round(sr.height), mcp: !!m && m.r <= hi };
  });
  const sweep = async p => {
    const b = await p.locator('#map').boundingBox(), bad = new Set(), hs = new Set(); let mcp = true;
    for (let i = 0; i < 6; i++) for (let j = 0; j < 4; j++) {
      await p.mouse.move(b.x + b.width * (0.05 + i * 0.18), b.y + b.height * (0.08 + j * 0.28)); await p.waitForTimeout(25);
      const r = await zones(p); r.bad.forEach(x => bad.add(x)); hs.add(r.h); mcp = mcp && r.mcp;
    }
    return { bad: [...bad], hs: [...hs], mcp };
  };
  await R26('UX-33 + barra', async p => {
    const out = []; let ok = true;
    for (const [w, h] of [[1280, 800], [1366, 768]]) {
      await p.setViewportSize({ width: w, height: h }); await p.waitForTimeout(200);
      const r = await sweep(p); ok = ok && !r.bad.length && r.mcp && r.hs.length === 1 && r.hs[0] <= 30;
      out.push(`${w} px: alto ${r.hs.join('/')} px · ${r.bad.length ? r.bad.slice(0, 3).join(' · ') : 'nada se pisa'} · MCP apagado ${r.mcp ? 'entero' : 'cortado'}`);
    }
    return [['UX-33 + a 1280 × 800 y 1366 × 768, con el cursor en 24 puntos del mapa, la barra de estado es una línea que no cambia de alto, sus zonas no se pisan y «MCP apagado» se ve entero', ok, out.join(' · ')]];
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
  for (const scheme of ['dark', 'light']) {
    await R26(`AR-03 + ${scheme}`, async p => {
      const out = [], bad = [];
      const look = async n => { const f = await frame(p), l = lowTexts(f); bad.push(...l); out.push(`${n}: ${f.texts.length} textos${l.length ? ', bajos ' + showLow(l) : ''}`); };
      await look('inicio');
      await p.click('#colL [data-act="sel"][data-v="ent:act-mirek"]'); await p.waitForTimeout(200); await look('Mirek');
      for (let i = 0; i < 4; i++) { await p.click('#bZout'); await p.waitForTimeout(120); } await look('alejado');
      await p.keyboard.press('Escape'); await p.keyboard.press('2'); await p.waitForTimeout(300); await look('Rodaje');
      return [[`AR-03 + en tema ${scheme === 'dark' ? 'oscuro' : 'claro'}, a 1366 × 768, cada texto pintado en el mapa (números de la rejilla, pueblos y etiquetas) llega a 4,5:1 en al menos el 98 % de los píxeles de su letra`, !bad.length, out.join(' · ')]];
    }, 1366, 768, scheme);
  }
  await R26('AR-03 −', async p => {
    // la sonda no da por bueno lo que fallaba: el número pintado como antes (tinta translúcida sobre el gris de un edificio) sale por debajo de 4,5:1
    const r = await p.evaluate(() => { const c = document.querySelector('#map'), g = c.getContext('2d'), d = c.width / c.clientWidth; window.__cv.texts = []; window.__cv.on = true; g.save(); g.setTransform(d, 0, 0, d, 0, 0); g.fillStyle = 'rgb(88,83,74)'; g.fillRect(40, 40, 60, 20); g.font = '500 12px monospace'; g.fillStyle = 'rgba(25,25,15,.8)'; g.fillText('6150', 44, 54); g.restore(); window.__cv.on = false; return window.__cv.texts[0]; });
    return [['AR-03 − la sonda detecta un número de la rejilla pintado como antes, sin placa, sobre un edificio', !!r && r.n > 0 && r.min < 4.5 && r.low === r.n, r ? `«${r.text}» ${r.min}:1 en ${r.low} de ${r.n} px` : 'la sonda no vio el texto']];
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

  expect(external.length === 0, 'ninguna petición sale de la página: ' + (external.slice(0, 3).join(' ') || 'ninguna'));
  expect(errors.length === 0, 'sin errores de JavaScript en la página');
  errors.forEach(e => console.log(e));
  console.log(`RESULT ${passes} pass, ${fails} fail`);
  await browser.close();
  process.exitCode = fails ? 1 : 0;
})();
