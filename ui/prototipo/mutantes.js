// Sensibilidad de las pruebas que miran el dibujo del mapa (revisión de Astra, AR-04; el rayado de lo estimado, UX-30).
// Cada mutante rompe una sola cosa de lo que se pinta, sin tocar los data-* de la página, y su caso de pruebas-mejoras.js
// tiene que fallar. Antes se pasan los mismos casos contra el prototipo sin tocar: tienen que pasar.
// Del sexto al octavo son los que Astra dejó vivos en su segunda revisión (AR2-01), copiados de su informe. Los cuatro siguientes son los de
// su tercera (AR3-01), copiados de su generador (ui/astra/2026-11-10-ui-revision3-astra.md, §5.1); el halo sin letra y la imagen sin
// etiqueta van con el punto de la página donde ahora se pintan las etiquetas, al final del fotograma. Los dos siguientes son los de los
// iconos de los objetos (UX-48); los cuatro siguientes, los de la vista previa de Añadir y la planta del objeto al colocarlo (UX-49), y los
// cuatro últimos, los de los textos del mapa: los números de la regla encima de los marcadores, y nada debajo de lo que flota encima del
// mapa ni cortado por su borde (UX-50).
// Uso: node ui/prototipo/mutantes.js (necesita Playwright con Chromium, como pruebas-mejoras.js).
const fs = require('fs'), os = require('os'), path = require('path'), { spawnSync } = require('child_process');
const SRC = fs.readFileSync(path.join(__dirname, 'estudio.html'), 'utf8');
const TEST = path.join(__dirname, 'pruebas-mejoras.js');
const MUTANTES = [
  { name: 'los borradores se pintan sólidos', solo: '^UX-09 −$', cambios: [["drawGlyph(g, kind, x, y, yw === null ? e.yaw : yw, draft ? 'draft' : 'solid', e.cls);", "drawGlyph(g, kind, x, y, yw === null ? e.yaw : yw, 'solid', e.cls);"]] },
  { name: 'la letra del mapa baja a 8 px', solo: '^UX-10 −$', cambios: [['${strong ? 600 : 500} 12px ${FONT_UI}', '${strong ? 600 : 500} 8px ${FONT_UI}'], ['600 12px ${FONT_UI}', '600 8px ${FONT_UI}'], ["'500 12px ' + FONT_MONO", "'500 8px ' + FONT_MONO"]] },
  { name: 'las marcas del seleccionado pierden su etiqueta «Mirek · M1»', solo: '^UX-09 \\+$', cambios: [['if (!dim) label(g, `${a.name} · M${i + 1}`, x + 10, y - 7, true);', '']] },
  { name: 'el actor estimado se pinta sin rayado', solo: '^UX-30 \\+$', cambios: [["drawGlyph(g, kind, qx, qy, e.yaw, 'est');", "drawGlyph(g, kind, qx, qy, e.yaw, 'solid');"]] },
  { name: 'los números de la rejilla vuelven a pintarse sin placa', solo: '^AR-03 \\+ dark$', cambios: [['g.fillStyle = P.halo; g.fillRect(x - 2, y - 11, g.measureText(t).width + 4, 14); g.fillStyle = P.label;', "g.fillStyle = 'rgba(25,25,15,.8)';"]] },
  { name: 'los números de la rejilla se pintan pálidos en una imagen aparte', solo: '^AR-03 \\+ ', cambios: [['g.fillStyle = P.label; g.fillText(t, x, y); });', "const c = document.body.appendChild(document.createElement('canvas')); c.hidden = true; c.width = 100; c.height = 30; const q = c.getContext('2d'); q.font = g.font; q.fillStyle = '#888'; q.fillText(t, 2, 15); g.drawImage(c, x - 2, y - 15); c.remove(); });"]] },
  { name: 'el rayado del actor estimado es un blanco sin rayas', solo: '^UX-30 \\+$', cambios: [["h.fillStyle = 'rgba(255,255,255,.8)';", "h.fillStyle = '#fff';"], ['h.lineTo(7, 5); h.stroke();', 'h.lineTo(7, 5);']] },
  { name: 'el contorno del borrador lleva un guion más largo que él', solo: '^UX-09 −$', cambios: [['g.setLineDash([3, 2]);', 'g.setLineDash([10000, 0.001]);']] },
  { name: 'los números de la rejilla se repintan pálidos con putImageData después de pintarlos', solo: '^AR-03 \\+ ', cambios: [['g.fillStyle = P.label; g.fillText(t, x, y); });', "g.fillStyle = P.label; g.fillText(t, x, y); const d = V.dpr, ix = Math.max(0, Math.floor((x - 1) * d)), iy = Math.max(0, Math.floor((y - 11) * d)), iw = Math.min(g.canvas.width - ix, Math.ceil((g.measureText(t).width + 2) * d)), ih = Math.min(g.canvas.height - iy, Math.ceil(14 * d)); if (iw > 0 && ih > 0) { const im = g.getImageData(ix, iy, iw, ih); for (let j = 0; j < im.data.length; j += 4) if (Math.max(im.data[j], im.data[j + 1], im.data[j + 2]) < 136) im.data[j] = im.data[j + 1] = im.data[j + 2] = 136; g.putImageData(im, ix, iy); } });"]] },
  { name: 'un texto pálido llega al mapa copiado de un lienzo a otro con getImageData y putImageData', solo: '^AR-03 \\+ ', cambios: [['ruler(); drawLabels(g);', "ruler(); drawLabels(g); const extra = document.createElement('canvas'); extra.width = 150; extra.height = 24; const ex = extra.getContext('2d'); ex.fillStyle = P.halo; ex.fillRect(0, 0, 150, 24); ex.font = '12px sans-serif'; ex.fillStyle = '#888'; ex.fillText('SIN LECTURA', 4, 16); const copy = document.createElement('canvas'); copy.width = 150; copy.height = 24; copy.getContext('2d').putImageData(ex.getImageData(0, 0, 150, 24), 0, 0); g.drawImage(copy, 80, V.h - 110);"]] },
  { name: 'las etiquetas pintan su halo y su letra a opacidad 0', solo: '^AR-03 \\+ ', cambios: [['halo(g, txt, lx, ly); g.fillStyle = P.label; g.fillText(txt, lx, ly);', "halo(g, txt, lx, ly); g.fillStyle = P.label; g.save(); g.filter = 'opacity(0)'; g.fillText(txt, lx, ly); g.restore();"]] },
  { name: 'el rayado del actor estimado es un tablero de 2 px', solo: '^UX-30 \\+$|^AR2-01 \\+ claro$', cambios: [['h.beginPath(); h.moveTo(-1, 7); h.lineTo(7, -1); h.moveTo(-1, 1); h.lineTo(1, -1); h.moveTo(5, 7); h.lineTo(7, 5); h.stroke();', "h.fillStyle = '#fff'; h.fillRect(0, 0, 6, 6); h.fillStyle = '#000'; for (let yy = 0; yy < 6; yy++) for (let xx = 0; xx < 6; xx++) if ((Math.floor(xx / 2) + Math.floor(yy / 2)) % 2 === 0) h.fillRect(xx, yy, 1, 1);"]] },
  { name: 'los objetos pierden el icono', solo: '^UX-48 \\+$', cambios: [["if (kind === 'objeto') { g.scale(0.7, 0.7); g.fillStyle = style === 'draft' ? col : 'rgba(255,255,255,.95)'; g.fill(objPath(cls), 'evenodd'); }", '']] },
  { name: 'el icono tapa todo el cuadrado', solo: '^UX-48 −$', cambios: [["g.scale(0.7, 0.7); g.fillStyle = style === 'draft'", "g.scale(1.6, 1.6); g.fillStyle = style === 'draft'"]] },
  { name: 'la planta del fantasma va a un tamaño fijo', solo: '^UX-49 \\+$', cambios: [['const fw = d[1] * V.s, fl = d[0] * V.s;', 'const fw = 12, fl = 24;']] },
  { name: 'la vista previa sale sin planta', solo: '^UX-49 \\+$', cambios: [['<span class="pv-cls">${esc(c[0])}</span>${size}</div>${plan}`;', '<span class="pv-cls">${esc(c[0])}</span>${size}</div>`;']] },
  { name: 'la vista previa no sigue al teclado', solo: '^UX-49 \\+$', cambios: [['v = libHover || (f && f.dataset.v);', 'v = libHover;']] },
  { name: 'la vista previa no se aparta cuando falta sitio', solo: '^UX-49 −$', cambios: [['@container (max-height:560px){.prev{display:none}}', '']] },
  { name: 'los números de la regla vuelven a pintarse debajo de los marcadores', solo: '^UX-50 \\+ regla$', cambios: [["floating(g.canvas); drawScene(g); g.font = '500 12px ' + FONT_MONO; g.textAlign = 'left'; ruler(); drawLabels(g);", "floating(g.canvas); g.font = '500 12px ' + FONT_MONO; g.textAlign = 'left'; ruler(); drawScene(g); drawLabels(g);"]] },
  { name: 'la placa de los números no cuenta como ocupada para las etiquetas', solo: '^UX-50 \\+ regla$', cambios: [['if (!inMap(b)) return; LBL.push(b); ', 'if (!inMap(b)) return; ']] },
  { name: 'las etiquetas vuelven a ir debajo de lo que flota encima del mapa y cortadas por su borde', solo: '^UX-50 \\+ dark$', cambios: [['inMap(at(q)) && ', ''], [' || !inMap(at([0, 0]))', '']] },
  { name: 'los números de la regla se pintan también debajo de lo que flota encima del mapa y cortados por su borde', solo: '^UX-50 \\+ dark$', cambios: [['if (!inMap(b)) return; LBL.push(b); ', 'LBL.push(b); ']] }
];
const run = (file, solo) => {
  const r = spawnSync(process.execPath, [TEST], { env: Object.assign({}, process.env, { ESTUDIO_URL: 'file://' + file, SOLO: solo }), encoding: 'utf8', timeout: 300000 });
  const out = (r.stdout || '') + (r.stderr || '');
  return { fails: out.split('\n').filter(l => /^FAIL /.test(l)), result: (out.match(/RESULT \d+ pass, \d+ fail/) || ['sin RESULT'])[0] };
};
let vivos = 0, muertos = 0;
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsbx-mutantes-'));
const control = path.join(dir, 'control.html'); fs.writeFileSync(control, SRC);
const c = run(control, MUTANTES.map(m => '(' + m.solo + ')').join('|'));
console.log(`${c.fails.length ? 'FAIL' : 'PASS'} control: los casos de los mutantes pasan con el prototipo sin tocar · ${c.result}`);
MUTANTES.forEach((m, i) => {
  let html = SRC;
  for (const [a, b] of m.cambios) { if (!html.includes(a)) { console.log(`FAIL mutante «${m.name}»: no se encontró «${a.slice(0, 50)}» en estudio.html`); vivos++; return; } html = html.split(a).join(b); }
  const file = path.join(dir, `mutante-${i + 1}.html`); fs.writeFileSync(file, html);
  const r = run(file, m.solo), killed = r.fails.length > 0;
  if (killed) muertos++; else vivos++;
  console.log(`${killed ? 'PASS' : 'FAIL'} mutante «${m.name}»: ${killed ? 'su caso falla' : 'SOBREVIVE'} · ${r.result}${killed ? ' · ' + r.fails[0].slice(5, 170) : ''}`);
});
fs.rmSync(dir, { recursive: true, force: true });
console.log(`RESULT ${muertos} mutantes detectados, ${vivos} sin detectar${c.fails.length ? ', y el control falla' : ''}`);
process.exitCode = vivos || c.fails.length ? 1 : 0;
