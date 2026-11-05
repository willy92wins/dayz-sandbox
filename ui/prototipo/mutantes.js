// Sensibilidad de las pruebas que miran el dibujo del mapa (revisión de Astra, AR-04; el rayado de lo estimado, UX-30).
// Cada mutante rompe una sola cosa de lo que se pinta, sin tocar los data-* de la página, y su caso de pruebas-mejoras.js
// tiene que fallar. Antes se pasan los mismos casos contra el prototipo sin tocar: tienen que pasar.
// Los tres últimos son los que Astra dejó vivos en su segunda revisión (AR2-01), copiados de su informe.
// Uso: node ui/prototipo/mutantes.js (necesita Playwright con Chromium, como pruebas-mejoras.js).
const fs = require('fs'), os = require('os'), path = require('path'), { spawnSync } = require('child_process');
const SRC = fs.readFileSync(path.join(__dirname, 'estudio.html'), 'utf8');
const TEST = path.join(__dirname, 'pruebas-mejoras.js');
const MUTANTES = [
  { name: 'los borradores se pintan sólidos', solo: '^UX-09 −$', cambios: [["drawGlyph(g, kind, x, y, yw === null ? e.yaw : yw, draft ? 'draft' : 'solid');", "drawGlyph(g, kind, x, y, yw === null ? e.yaw : yw, 'solid');"]] },
  { name: 'la letra del mapa baja a 8 px', solo: '^UX-10 −$', cambios: [['${strong ? 600 : 500} 12px ${FONT_UI}', '${strong ? 600 : 500} 8px ${FONT_UI}'], ['600 12px ${FONT_UI}', '600 8px ${FONT_UI}'], ["'500 12px ' + FONT_MONO", "'500 8px ' + FONT_MONO"]] },
  { name: 'las marcas del seleccionado pierden su etiqueta «Mirek · M1»', solo: '^UX-09 \\+$', cambios: [['if (!dim) label(g, `${a.name} · M${i + 1}`, x + 10, y - 7, true);', '']] },
  { name: 'el actor estimado se pinta sin rayado', solo: '^UX-30 \\+$', cambios: [["drawGlyph(g, kind, qx, qy, e.yaw, 'est');", "drawGlyph(g, kind, qx, qy, e.yaw, 'solid');"]] },
  { name: 'los números de la rejilla vuelven a pintarse sin placa', solo: '^AR-03 \\+ dark$', cambios: [['g.fillStyle = P.halo; g.fillRect(x - 2, y - 11, g.measureText(t).width + 4, 14); g.fillStyle = P.label;', "g.fillStyle = 'rgba(25,25,15,.8)';"]] },
  { name: 'los números de la rejilla se pintan pálidos en una imagen aparte', solo: '^AR-03 \\+ ', cambios: [['g.fillStyle = P.label; g.fillText(t, x, y); });', "const c = document.body.appendChild(document.createElement('canvas')); c.hidden = true; c.width = 100; c.height = 30; const q = c.getContext('2d'); q.font = g.font; q.fillStyle = '#888'; q.fillText(t, 2, 15); g.drawImage(c, x - 2, y - 15); c.remove(); });"]] },
  { name: 'el rayado del actor estimado es un blanco sin rayas', solo: '^UX-30 \\+$', cambios: [["h.fillStyle = 'rgba(255,255,255,.8)';", "h.fillStyle = '#fff';"], ['h.lineTo(7, 5); h.stroke();', 'h.lineTo(7, 5);']] },
  { name: 'el contorno del borrador lleva un guion más largo que él', solo: '^UX-09 −$', cambios: [['g.setLineDash([3, 2]);', 'g.setLineDash([10000, 0.001]);']] }
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
