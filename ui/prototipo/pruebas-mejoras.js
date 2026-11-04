// Criterios R26 de las mejoras de noviembre (ui/2026-11-04-ui-mejoras-consolidado.md §2, AHORA): un caso + y uno − por mejora.
// Uso: node ui/prototipo/pruebas-mejoras.js (necesita Playwright con Chromium). Cada caso abre una página nueva.
// Contra el prototipo de antes (ESTUDIO_URL=file://… con `git show de37c03:ui/prototipo/estudio.html`) los + tienen que fallar;
// un − que ya se cumplía antes pasa también allí. El contraste de CU-38 en los dos temas sigue en pruebas.js.
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
const TOWN = /^(Chernogorsk|Elektrozavodsk|Berezino|Solnichniy|Kamyshovo|Zelenogorsk|Stary Sobor|Novy Sobor|Vybor|Gorka|Balota|Komarovo|Kabanino|Prigorodki|Svetlojarsk|Krasnostav|Severograd|Novodmitrovsk|Lopatino|Pustoshka)$/i;

(async () => {
  const browser = await chromium.launch();
  const errors = [], external = [];
  const fresh = async (w = 1600, h = 960) => {
    const c = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: 'dark' });
    await c.addInitScript(LIB);
    const p = await c.newPage(); p.setDefaultTimeout(3000);
    p.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
    p.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
    await p.goto(URL); await p.waitForTimeout(900);
    return p;
  };
  // cada caso devuelve una lista de [qué se comprueba, si se cumple, lo que se vio]; si se corta a medias, cuenta como fallo
  const R26 = async (name, fn, w, h) => {
    let p;
    try { p = await fresh(w, h); for (const [what, ok, info] of await fn(p)) expect(ok, what + (info ? ' · ' + info : '')); }
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

  // --- UX-09: mapa ---
  await R26('UX-09 +', async p => {
    const labels = () => p.evaluate(() => (document.querySelector('#map').dataset.etiquetas || '').split('|').filter(Boolean));
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
    const what = 'UX-09 − lo que está sin aplicar se dibuja como documento, no como observado';
    const a = await p.evaluate(() => document.querySelector('#map').dataset.borrador);
    if (!await apply(p)) return [[what, false, 'no llegó a aplicar']];
    const b = await p.evaluate(() => document.querySelector('#map').dataset.borrador);
    return [[what, a === '2' && b === '0', `dibujadas como documento: ${a} con 2 cambios, ${b} con todo aplicado`]];
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
    return [['UX-10 − ningún texto de uso baja de 12 px en Escena, Rodaje y sus paneles', bad === 0, out.join(' · ')], ['UX-10 − la cámara elegida no lleva el verde de lo leído en el juego', green === 0, `${green} marcas verdes en sus propiedades`]];
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

  expect(external.length === 0, 'ninguna petición sale de la página: ' + (external.slice(0, 3).join(' ') || 'ninguna'));
  expect(errors.length === 0, 'sin errores de JavaScript en la página');
  errors.forEach(e => console.log(e));
  console.log(`RESULT ${passes} pass, ${fails} fail`);
  await browser.close();
  process.exitCode = fails ? 1 : 0;
})();
