// Pruebas del prototipo consolidado (Claude + Astra). Sin backend: todo simulado en la página.
// Uso: node ui/prototipo/pruebas.js (necesita Playwright con Chromium). CAPTURAS=<carpeta> guarda capturas.
// Comprueban lo que enseña la interfaz con datos falsos; los efectos en el juego son de F6 y de los gates (consolidado §6).
const path = require('path');
const { chromium } = require('playwright');
const URL = process.env.ESTUDIO_URL || 'file://' + path.resolve(__dirname, 'estudio.html');
const CAPTURAS = process.env.CAPTURAS;
let fails = 0, passes = 0;
const expect = (c, m) => { if (c) { passes++; console.log('PASS', m); } else { fails++; console.log('FAIL', m); } };
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 960 }, colorScheme: 'dark' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(`[console] ${m.text()}`); });
  page.on('pageerror', e => errors.push(`[pageerror] ${e.message} :: ${(e.stack || '').split('\n').slice(0, 3).join(' | ')}`));
  const shot = async (n, full) => { if (CAPTURAS) await page.screenshot({ path: path.join(CAPTURAS, n + '.png'), fullPage: !!full }); };
  const external = [];
  page.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) external.push(r.url()); });
  const txt = async sel => (await page.locator(sel).first().innerText().catch(() => '')).replace(/\s+/g, ' ');
  const waitTxt = async (sel, re, ms = 15000) => { try { await page.waitForFunction(([s, r]) => { const el = document.querySelector(s); return el && new RegExp(r).test(el.innerText); }, [sel, re.source], { timeout: ms }); return true; } catch (e) { return false; } };
  const toasts = async () => (await page.locator('#toasts').innerText().catch(() => '')).replace(/\s+/g, ' ');
  const sim = async v => { await page.click('#bSim'); await page.waitForTimeout(120); await page.click(`#menu [data-act="sim"][data-v="${v}"]`); await page.keyboard.press('Escape'); await page.waitForTimeout(150); };
  const mapBox = async () => page.locator('#map').boundingBox();
  const selEnt = async id => { await page.click(`#colL [data-act="sel"][data-v="ent:${id}"]`); await page.waitForTimeout(150); await page.locator('#map').hover(); await page.keyboard.press('f'); await page.waitForTimeout(250); };

  await page.goto(URL); await page.waitForTimeout(1200);
  await shot('01-escena');
  expect(await page.locator('#peerBk').isVisible() && await page.locator('#peerSrv').isVisible() && await page.locator('#peerCli').isVisible(), 'tres luces de conexión: Backend, Servidor y Director');
  expect(/r14 editada · r12 en el juego/.test(await txt('#docBtn')), 'revisión editada frente a la aplicada en la cabecera');
  const total = await txt('.meter.total');
  expect(/35 entidades \+ 9 prendas = 44/.test(total) && /S-perf/.test(total), 'presupuesto total combinado: ' + total);

  // --- Aplicar con Ctrl+Intro ---
  await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#bApply', /Volver a aplicar/), 'Ctrl+Intro aplica y termina en observado');
  expect(/observado/i.test(await txt('#dock .qrow')), 'la orden de aplicar acaba Observado');

  // --- Mayús + arrastrar gira (Eden) ---
  await selEnt('obj-12');
  let b = await mapBox(); const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
  const yaw0 = await page.inputValue('#f-yaw');
  await page.keyboard.down('Shift');
  await page.mouse.move(cx, cy - 5); await page.mouse.down();
  await page.mouse.move(cx + 30, cy - 10, { steps: 4 }); await page.mouse.move(cx + 60, cy, { steps: 6 });
  await shot('02-girando');
  await page.mouse.up(); await page.keyboard.up('Shift'); await page.waitForTimeout(200);
  const yaw1 = await page.inputValue('#f-yaw');
  expect(yaw0 === '0' && yaw1 === '90', `Mayús + arrastrar gira con rejilla de 15°: ${yaw0} → ${yaw1}`);
  await page.click('[data-act="dtab"][data-v="historial"]'); await page.waitForTimeout(100);
  expect(/Girar Bidón rojo/.test(await txt('#dock')), 'el giro queda en el historial como «Girar Bidón rojo»');
  await page.click('[data-act="dtab"][data-v="consola"]');

  // --- Mayús + clic sin mover: selección seguida (DayZ Editor) ---
  await page.keyboard.down('Shift'); await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.up(); await page.keyboard.up('Shift'); await page.waitForTimeout(150);
  expect(/Bidón rojo/.test(await txt('#colR')), 'Mayús + clic sin mover no gira (sigue seleccionado)');

  // --- Rejilla: mover a saltos de 1 m ---
  await page.click('#bGrid'); await page.waitForTimeout(120);
  expect(/Rejilla de movimiento/.test(await txt('#menu')) && /Rejilla de giro/.test(await txt('#menu')), 'menú de rejillas de movimiento y de giro');
  await page.click('#menu [data-act="grid-step"][data-v="m:1"]'); await page.keyboard.press('Escape');
  await selEnt('obj-12'); b = await mapBox();
  const x0 = parseFloat((await page.inputValue('#f-x')).replace(',', '.'));
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx + 25, cy, { steps: 3 }); await page.mouse.move(cx + 57, cy + 2, { steps: 5 }); await page.mouse.up(); await page.waitForTimeout(200);
  const x1 = parseFloat((await page.inputValue('#f-x')).replace(',', '.'));
  expect(x1 > x0 && Math.abs((x1 - x0) - Math.round(x1 - x0)) < 1e-6, `arrastrar con rejilla de 1 m mueve metros enteros: ${x0} → ${x1}`);
  await page.locator('#map').hover(); await page.keyboard.press('ArrowRight'); await page.waitForTimeout(150);
  const x2 = parseFloat((await page.inputValue('#f-x')).replace(',', '.'));
  expect(Math.abs(x2 - x1 - 1) < 1e-6, `flecha con rejilla de 1 m: ${x1} → ${x2}`);
  await page.keyboard.press('Alt+ArrowRight'); await page.waitForTimeout(150);
  const x3 = parseFloat((await page.inputValue('#f-x')).replace(',', '.'));
  expect(Math.abs(x3 - x2 - 0.1) < 1e-6, `Alt + flecha mueve 0,1 m: ${x2} → ${x3}`);

  // --- Botón derecho y arrastrar mueve el mapa (Eden) ---
  await page.mouse.move(cx + 100, cy + 60); const before = await txt('#cursorXY');
  await page.mouse.down({ button: 'right' }); await page.mouse.move(cx + 200, cy + 60, { steps: 5 }); await page.mouse.up({ button: 'right' });
  await page.mouse.move(cx + 101, cy + 60); await page.mouse.move(cx + 100, cy + 60); const after = await txt('#cursorXY');
  expect(before !== after, `botón derecho y arrastrar desplaza el mapa: ${before} → ${after}`);

  // --- Colocar: lectura del suelo automática (#27) ---
  await selEnt('obj-20'); await page.keyboard.press('Delete'); await page.waitForTimeout(150);
  await page.click('[data-act="lib-item"]'); b = await mapBox();
  await page.mouse.click(b.x + b.width * 0.7, b.y + b.height * 0.3); await page.waitForTimeout(150);
  expect(await waitTxt('#dock', /Leer el suelo/, 3000), 'colocar lanza «Leer el suelo» en la consola');
  expect(await waitTxt('#colR', /Suelo a [\d.,]+ m, leído en el servidor/, 4000), 'las propiedades enseñan el suelo leído con su edad');
  await shot('03-suelo');

  // --- out_of_map ---
  await page.fill('#f-x', '99999'); await page.keyboard.press('Tab'); await page.waitForTimeout(150);
  await page.click('[data-act="dtab"][data-v="validacion"]'); await page.waitForTimeout(100);
  expect(/out_of_map/.test(await txt('#dock')), 'una posición fuera del mapa da out_of_map');
  expect(await page.locator('#bApply').isDisabled(), 'con errores no se puede aplicar');
  await page.click('#bUndo'); await page.waitForTimeout(150);
  await page.click('[data-act="dtab"][data-v="consola"]');

  // --- D2: se pierde la respuesta después de entregar -> Parcial hasta reconciliar ---
  await page.locator('#map').hover(); await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#dock', /Creando por lotes/, 6000), 'aplicar llega a «Creando por lotes»');
  await sim('server');
  expect(await waitTxt('#dock .qrow', /Parcial[\s\S]*Falta confirmar el resultado/, 3000), 'corte tras la entrega: la orden pasa a Parcial, «Falta confirmar el resultado»');
  await shot('04-parcial-corte');
  await page.waitForTimeout(800); await sim('server');
  expect(await waitTxt('#dock .qrow', /Observado[\s\S]*Reconciliada tras el corte/, 9000), 'al volver la conexión se reconcilia: Observado, «Reconciliada tras el corte»');
  expect(await waitTxt('#bApply', /Volver a aplicar/, 3000), 'termina con todo aplicado');

  // --- D2: sin conexión antes de entregar -> Pendiente y luego Fallido «No se entregó» ---
  await page.locator('#map').hover(); await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(100);
  await sim('server'); await page.locator('#map').hover(); await page.keyboard.press('Control+Enter'); await page.waitForTimeout(800);
  expect(/Pendiente/.test(await txt('#dock .qrow')) && /caduca sin haberse hecho/.test(await txt('#dock .qrow')), 'sin servidor la orden queda Pendiente y avisa de que caduca');
  expect(await waitTxt('#dock .qrow', /Fallido[\s\S]*No se entregó/, 12000), 'a los 10 s pasa a Fallido: «No se entregó»');
  await sim('server');
  await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#bApply', /Volver a aplicar/, 9000), 'con el servidor de vuelta se aplica');

  // --- Backend parado ---
  await sim('backend');
  expect(/hace/.test(await txt('#peerSrv')) && /última noticia/.test(await page.getAttribute('#peerSrv', 'title')) && await page.locator('#peerSrv.stale').count() === 1 && await page.locator('#peerCli.stale').count() === 1, 'sin backend, Servidor y Director enseñan «hace X» sin color y la última noticia en el título');
  expect(/Sin conexión con el backend/.test(await txt('#banner')), 'aviso «Sin conexión con el backend»');
  expect(await page.locator('#bApply').isDisabled(), 'sin backend Aplicar está desactivado');
  expect(/esto es lo último que se supo/.test(await txt('#dock')), 'la consola dice que es lo último que se supo');
  await selEnt('obj-13'); await page.keyboard.press('ArrowUp'); await page.waitForTimeout(150);
  expect(/no se puede guardar ningún cambio/.test(await toasts()), 'sin backend no se guarda ningún cambio');
  expect(await page.locator('#colR fieldset.lockf[disabled]').count() === 1, 'sin backend las propiedades quedan bloqueadas');
  await shot('05-sin-backend');
  await sim('backend');
  expect(!(await page.locator('#banner').isVisible()), 'con el backend de vuelta desaparece el aviso');

  // --- Toma: Mayús+F9, Intro, Esc con «Parando…» ---
  await page.keyboard.press('2'); await page.waitForTimeout(300);
  expect(/Preparar toma Mayús\+F9/.test(await txt('#slateWrap')), 'el botón de preparar enseña Mayús+F9');
  await page.keyboard.press('Shift+F9');
  expect(await waitTxt('#slateWrap', /Desarmar/, 6000), 'Mayús+F9 prepara y la toma queda armada');
  expect(/Rodar Intro/.test(await txt('#slateWrap')), 'Rodar enseña Intro');
  expect(await page.locator('#colR fieldset.lockf[disabled]').count() === 1, 'con la toma armada las propiedades se bloquean');
  await page.keyboard.press('Control+z'); await page.waitForTimeout(150);
  expect(/Durante la toma no se edita/.test(await toasts()), 'Ctrl+Z durante la toma se rechaza con el motivo');
  await page.keyboard.press('Space'); await page.waitForTimeout(150);
  expect(/Espacio solo para una toma que rueda/.test(await toasts()) && /Desarmar/.test(await txt('#slateWrap')), 'Espacio con la toma armada no rueda: avisa');
  await shot('06-armada');
  await page.keyboard.press('Enter');
  expect(await waitTxt('#slateWrap', /Parar/, 1500), 'Intro rueda la toma armada');
  expect(await page.locator('#recBadge').isVisible() && /RODANDO/.test(await txt('#recBadge')) && /OBS/.test(await txt('#recBadge')), 'insignia «RODANDO» que dice que el vídeo lo graba OBS');
  const stopFree = await page.evaluate(() => { const b = document.querySelector('#bTopStop'); if (!b || b.hidden) return false; const r = b.getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!el && (el === b || b.contains(el)); });
  expect(stopFree, 'rodando, Parar está en la barra de arriba y nada lo tapa (B5)');
  await page.waitForTimeout(1500); await shot('07-rodando');
  await page.keyboard.press('Escape'); await page.waitForTimeout(60);
  expect(/Parando…/.test(await txt('#slateWrap')), 'Esc deja la toma en «Parando…» hasta que confirma el cliente');
  await shot('08-parando');
  expect(await waitTxt('#slateWrap', /Reaplicar y preparar la/, 2000), 'después queda Parada y ofrece «Reaplicar y preparar»');
  await page.click('[data-act="ltab"][data-v="tomas"]'); await page.waitForTimeout(100);
  expect(/Control devuelto en \d+,\d\d s/.test(await txt('#colL')), 'la lista de tomas mide el control devuelto');
  expect(await page.locator('#colL .tk.parada').count() >= 1, 'las tomas llevan su propia etiqueta, no un estado D2');

  // --- Toma que pierde al director: Fallida y la orden Parcial hasta reconciliar ---
  await page.click('[data-act="take-reapply"]');
  expect(await waitTxt('#slateWrap', /Desarmar/, 12000), '«Reaplicar y preparar» aplica y vuelve a armar');
  await page.keyboard.press('Enter'); await page.waitForTimeout(900);
  await sim('director');
  expect(await waitTxt('#slateWrap', /Fallida/, 2000), 'perder al director falla la toma');
  await page.click('[data-act="rdtab"][data-v="consola"]'); await page.waitForTimeout(100);
  expect(/Parcial[\s\S]*hombre muerto/.test(await txt('#dock .qrow')), 'la orden de la toma queda Parcial y cita el hombre muerto (F5)');
  await sim('director');
  expect(await waitTxt('#dock .qrow', /Observado[\s\S]*Reconciliada tras el corte: el mod paró/, 3000), 'al volver el director se reconcilia la orden');
  await shot('09-toma-reconciliada');

  // --- Casos del simulador: sin Expansion, fallo a mitad, DOF apagada, sin director y mundo nuevo ---
  await page.keyboard.press('1'); await page.waitForTimeout(300);
  await sim('expansion'); await page.click('[data-act="dtab"][data-v="validacion"]'); await page.waitForTimeout(200);
  const val = await txt('#dock');
  expect(/expansion_unavailable/.test(val) && /\/entities\/\d+/.test(val) && await page.locator('#bApply').isDisabled(), 'sin Expansion: expansion_unavailable con su ruta y Aplicar desactivado (C5)');
  await sim('expansion'); await page.click('[data-act="dtab"][data-v="consola"]');
  await sim('fault'); await page.locator('#map').hover(); await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#dock .qrow', /Parcial[\s\S]*Falló al crear la entidad[\s\S]*Se borró todo lo que había creado esta orden/, 12000), 'fallo a mitad: Parcial, nombra la entidad y dice que se borró lo de esa orden (#9)');
  await page.locator('#map').hover(); await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#bApply', /Volver a aplicar/, 12000), 'el fallo simulado es de una vez: aplicar otra vez termina aplicado');
  await page.keyboard.press('2'); await page.waitForTimeout(300);
  await sim('dof');
  expect(/profundidad de campo de vídeo está apagada/i.test(await txt('#banner')), 'con la DOF apagada sale el aviso de B3');
  await sim('dof');
  await sim('director'); await page.keyboard.press('Shift+F9');
  expect(await waitTxt('#colR', /No se puede armar[\s\S]*no_director/, 10000) && /No se puede armar/.test(await txt('#colR')) && !(await page.locator('#recBadge').isVisible()), 'sin director: no_director y la toma no se arma (#4)');
  await sim('director');
  await page.keyboard.press('1'); await page.waitForTimeout(200);
  const world0 = await txt('#status');
  await page.click('#bSim'); await page.waitForTimeout(150); await page.click('#menu [data-act="sim-reboot"]'); await page.keyboard.press('Escape');
  expect(await waitTxt('#banner', /mundo nuevo/, 5000) && (await txt('#status')) !== world0, 'reinicio del servidor: aviso de mundo nuevo y otro epoch en la barra de estado (#10)');
  await page.locator('#map').hover(); await page.keyboard.press('Control+Enter');
  expect(await waitTxt('#bApply', /Volver a aplicar/, 12000) && !(await page.locator('#banner').isVisible()), 'aplicar en el mundo nuevo quita el aviso');

  // --- Atajos: conflicto con una de D4 y Reemplazar ---
  await page.click('#bKeys'); await page.waitForTimeout(120);
  await page.click('[data-act="key-set"][data-v="apply"]'); await page.keyboard.press('Enter'); await page.waitForTimeout(100);
  expect(/no puede quedarse sin tecla/.test(await txt('#kconf')), 'una tecla de D4 no se puede quitar');
  await page.click('#kconf [data-act="key-cancel"]');
  await page.click('[data-act="key-set"][data-v="coords"]'); await page.keyboard.press('l'); await page.waitForTimeout(100);
  expect(/Reemplazar/.test(await txt('#kconf')) && /Cancelar/.test(await txt('#kconf')), 'conflicto normal: Reemplazar o Cancelar');
  await shot('10-atajos');
  await page.click('#kconf [data-act="key-conf"]'); await page.waitForTimeout(100);
  const dlg = await txt('.dialog');
  expect(/Copiar coordenadas[^]*?L Cambiar/.test(dlg) && /Bloquear[^]*?sin tecla/.test(dlg), 'Reemplazar pasa L a Copiar coordenadas y deja Bloquear sin tecla');
  await page.click('[data-act="keys-reset"]'); await page.keyboard.press('Escape');

  // --- Guía ---
  await page.click('#bGuide'); await page.waitForTimeout(500);
  const rows = await page.locator('#refTable tr').count(), cols = await page.locator('#refTable tr:first-child td').count();
  expect(rows >= 50 && cols === 5, `tabla de referentes: ${rows} filas con ${cols} columnas`);
  const guide = await txt('#guide');
  expect(!/Foundry/.test(guide), 'Foundry VTT ya no aparece (no está en la lista de referentes)');
  const props = await page.locator('#refTable tr td:nth-child(5)').allInnerTexts();
  const tally = props.reduce((o, p) => (o[p] = (o[p] || 0) + 1, o), {});
  console.log('INFO propuso:', JSON.stringify(tally));
  console.log('INFO fuentes:', (await page.locator('#refTable tr td:nth-child(4)').allInnerTexts()).filter((v, i, a) => a.indexOf(v) === i).join(' | '));
  await shot('11-guia', true);
  await page.click('#bGuideClose'); await page.waitForTimeout(200);

  expect(external.length === 0, 'ninguna petición sale de la página (sin teselas ni servicios externos): ' + (external.slice(0, 3).join(' ') || 'ninguna'));
  expect(errors.length === 0, 'sin errores de JavaScript en la página');
  errors.forEach(e => console.log(e));
  console.log(`RESULT ${passes} pass, ${fails} fail`);
  await browser.close();
  process.exitCode = fails ? 1 : 0;
})();
