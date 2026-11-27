"use strict";
// Guion de F3-web (brief plans/2026-11-27-m1-f3-web-actores-brief.md §5.2): actores en Añadir y Propiedades.
// Lo corre app/tests/e2e_studio.py con DSBX_GUION=actores. Cada fila imprime «ACn OK».
const { chromium } = require("playwright");
const readline = require("readline");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
if (!BASE || !HUMAN_KEY) {
  console.error("FALLO: faltan DSBX_URL o DSBX_HUMAN_KEY");
  process.exit(2);
}

const ROW_ORDER = ["AC1", "AC2", "AC3", "AC4", "AC5", "AC6", "AC7", "AC8"];
function resolveSelectedRows() {
  const raw = process.env.DSBX_ONLY;
  if (!raw || !raw.trim()) return ROW_ORDER.slice();
  const parts = raw.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  for (const p of parts) if (!ROW_ORDER.includes(p)) throw new Error("DSBX_ONLY: fila desconocida " + p);
  return ROW_ORDER.filter((r) => parts.includes(r));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rl = readline.createInterface({ input: process.stdin });
const waiters = [];
const ready = [];
rl.on("line", (line) => {
  let obj;
  try {
    obj = JSON.parse(line);
  } catch {
    return;
  }
  if (waiters.length) waiters.shift()(obj);
  else ready.push(obj);
});
function cmd(obj) {
  return new Promise((resolve) => {
    while (ready.length) ready.shift();
    waiters.push(resolve);
    process.stdout.write(JSON.stringify(obj) + "\n");
  });
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const consoleTexts = [];
const pageErrors = [];
function track(page) {
  page.on("console", (m) => consoleTexts.push(m.text()));
  page.on("pageerror", (err) => pageErrors.push(err && err.message ? err.message : String(err)));
}

// Peticiones POST /api/scene/ops de la página, con su cuerpo.
function countOps(page) {
  const c = { n: 0, bodies: [] };
  const fn = (req) => {
    if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") {
      c.n += 1;
      try {
        c.bodies.push(JSON.parse(req.postData() || "null"));
      } catch {
        c.bodies.push(null);
      }
    }
  };
  page.on("request", fn);
  c.stop = () => page.off("request", fn);
  return c;
}

// Backend nuevo (sin leases vivas de la fila anterior) sobre el mismo almacén, y escena vacía.
async function clearScene() {
  assert((await cmd({ cmd: "stop_backend" })).ok, "stop_backend");
  assert((await cmd({ cmd: "start_backend" })).ok, "start_backend");
  const snap = await cmd({ cmd: "snapshot" });
  const ops = (snap.doc.entities || []).map((e) => ({ name: "entity.delete", target: e.id, args: {} }));
  if (ops.length) {
    const r = await cmd({ cmd: "ai_ops", label: "Limpiar escena", ops });
    assert(r && r.ok, "limpiar: " + JSON.stringify(r));
  }
}

const ACTOR_BASE = {
  kind: "actor",
  cls: "SurvivorM_Mirek",
  name: "Mirek",
  x: 6176,
  z: 7632,
  yaw: 35,
  wardrobe: "partisano",
  behaviour: "HOLD",
  roam: 15,
  marks: [],
  gestures: [],
};

// Crea actores por la IA y devuelve sus ids.
async function seedActors(list) {
  const ops = list.map((a) => ({ name: "entity.add", args: Object.assign({}, ACTOR_BASE, a) }));
  const r = await cmd({ cmd: "ai_ops", label: "Sembrar actores", ops });
  assert(r && r.ok, "sembrar: " + JSON.stringify(r));
  const snap = await cmd({ cmd: "snapshot" });
  return snap.doc.entities.filter((e) => e.kind === "actor").map((e) => e.id);
}

async function actorOf(id) {
  const snap = await cmd({ cmd: "snapshot" });
  return { snap, ent: snap.doc.entities.find((e) => e.id === id) };
}

async function waitForSnap(predicate, desc, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await cmd({ cmd: "snapshot" });
    if (last && last.ok && predicate(last)) return last;
    await sleep(100);
  }
  throw new Error("timeout esperando snapshot (" + desc + "): " + JSON.stringify(last && last.doc && last.doc.entities));
}

async function openStudio(browser, before) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, colorScheme: "dark" });
  if (before) await before(context);
  const page = await context.newPage();
  track(page);
  await page.goto(BASE + "/");
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (await page.getByText("Conectado", { exact: true }).isVisible().catch(() => false)) break;
    if (await page.locator("#human-key").isVisible().catch(() => false)) {
      await page.locator("#human-key").fill(HUMAN_KEY);
      await page.getByRole("button", { name: "Entrar" }).click();
      break;
    }
    await sleep(100);
  }
  await page.getByText("Conectado", { exact: true }).waitFor({ state: "visible", timeout: 15000 });
  return { context, page };
}

// Cambia el catálogo que ve la web, no el del backend.
function routeCatalog(target, edit) {
  return target.route("**/api/catalog", async (route) => {
    const resp = await route.fetch();
    const body = await resp.json();
    edit(body);
    await route.fulfill({ response: resp, json: body });
  });
}

async function activatePanel(page, panelId) {
  const panel = page.locator('[data-panel="' + panelId + '"]');
  if ((await panel.count()) > 0 && (await panel.first().isVisible().catch(() => false))) return panel.first();
  await page.locator('.dv-tab[data-tab-panel-id="' + panelId + '"]').first().click();
  await panel.first().waitFor({ state: "visible", timeout: 5000 });
  return panel.first();
}

async function selectEntity(page, id) {
  await activatePanel(page, "jerarquia");
  const item = page.locator('[data-panel="jerarquia"] [role="treeitem"][data-entity-id="' + id + '"]');
  await item.waitFor({ state: "visible", timeout: 5000 });
  await item.click();
  const props = await activatePanel(page, "propiedades");
  await props.locator("#f-wardrobe").waitFor({ state: "visible", timeout: 5000 });
  return props;
}

async function actoresTab(page) {
  const anadir = await activatePanel(page, "anadir");
  const tab = anadir.locator('[role="tablist"][aria-label="Tipo"]').locator('[role="tab"], button', { hasText: /^Actores\b/ }).first();
  return { anadir, tab };
}

// Un select del inspector ignora el cambio hasta que llega la lease del campo (F6-web 1, como `cls`).
async function selectWithLease(page, sel, value) {
  const f = page.locator(sel);
  await f.focus();
  await page.waitForFunction((q) => {
    const el = document.querySelector(q);
    return !!el && !el.disabled && el.getAttribute("aria-readonly") !== "true";
  }, sel, { timeout: 5000 });
  await f.selectOption(value);
}

async function isAriaInvalid(loc) {
  return (await loc.getAttribute("aria-invalid")) === "true";
}

// Escribe un valor y confirma con Intro; devuelve si quedó aria-invalid.
async function typeAndEnter(page, sel, value) {
  const f = page.locator(sel);
  await f.click();
  await f.fill(String(value));
  await f.press("Enter");
  await sleep(300);
  return isAriaInvalid(f);
}

async function catalogFromApi(page) {
  return page.evaluate(async () => (await fetch("/api/catalog", { credentials: "same-origin" })).json());
}

// --- AC1 colocar -------------------------------------------------------------
async function AC1(browser) {
  await clearScene();
  let { context, page } = await openStudio(browser);
  try {
    const cat = await catalogFromApi(page);
    const { anadir, tab } = await actoresTab(page);
    const st = await tab.evaluate((el) => ({
      disabled: !!(el.disabled || el.getAttribute("aria-disabled") === "true"),
      title: el.getAttribute("title") || "",
    }));
    assert(!st.disabled && !/Llega con F3/.test(st.title), "AC1(+): pestaña Actores desactivada: " + JSON.stringify(st));
    await tab.click();
    const rows = await anadir.locator("[data-cls]").evaluateAll((els) => els.map((e) => e.getAttribute("data-cls")));
    assert(JSON.stringify(rows) === JSON.stringify(cat.classes.actor), "AC1(+): filas != classes.actor: " + JSON.stringify(rows));

    const ops = countOps(page);
    await anadir.locator('[data-cls="SurvivorF_Linda"]').click();
    await page.keyboard.press("Enter");
    const snap = await waitForSnap((s) => s.doc.entities.some((e) => e.kind === "actor"), "AC1(+): actor colocado");
    await sleep(300);
    ops.stop();
    assert(ops.n === 1, "AC1(+): POST /api/scene/ops != 1: " + ops.n);
    const sent = ops.bodies[0] && ops.bodies[0].ops;
    assert(Array.isArray(sent) && sent.length === 1 && sent[0].name === "entity.add", "AC1(+): ops enviadas: " + JSON.stringify(sent));
    const want = {
      kind: "actor", cls: "SurvivorF_Linda", name: "SurvivorF_Linda", x: 7680, z: 7680, yaw: 0,
      wardrobe: cat.wardrobes[0], behaviour: "HOLD", roam: 15, marks: [], gestures: [],
    };
    const keys = Object.keys(want).sort();
    assert(JSON.stringify(Object.keys(sent[0].args).sort()) === JSON.stringify(keys), "AC1(+): claves de args: " + JSON.stringify(sent[0].args));
    for (const k of keys) {
      assert(JSON.stringify(sent[0].args[k]) === JSON.stringify(want[k]), "AC1(+): args." + k + " = " + JSON.stringify(sent[0].args[k]));
    }
    const ent = snap.doc.entities.find((e) => e.kind === "actor");
    for (const k of keys) assert(JSON.stringify(ent[k]) === JSON.stringify(want[k]), "AC1(+): snapshot." + k);
    // Colocar enseña Propiedades; el medidor vive en Añadir.
    await activatePanel(page, "anadir");
    assert(/1\s*\/\s*2/.test(await page.locator('[data-budget="actor"]').first().innerText()), "AC1(+): medidor != 1 / 2");

    // Negativa: al tope (2), la fila no coloca.
    await seedActors([{ name: "Otro" }]);
    await waitForSnap((s) => s.doc.entities.filter((e) => e.kind === "actor").length === 2, "AC1(-): dos actores");
    await sleep(500);
    const row = anadir.locator('[data-cls="SurvivorM_Boris"]');
    assert((await row.getAttribute("aria-disabled")) === "true", "AC1(-): fila no aria-disabled al tope");
    const ops2 = countOps(page);
    await row.click({ force: true });
    await row.press("Enter").catch(() => {});
    await page.keyboard.press("Enter");
    await sleep(800);
    ops2.stop();
    assert(ops2.n === 0, "AC1(-): al tope se mandaron " + ops2.n + " POST");
    await context.close();

    // Negativa: catálogo sin vestuarios.
    await clearScene();
    ({ context, page } = await openStudio(browser, (ctx) => routeCatalog(ctx, (b) => { b.wardrobes = []; b.wardrobe_items = {}; })));
    const t2 = await actoresTab(page);
    await t2.tab.click();
    const row2 = t2.anadir.locator('[data-cls="SurvivorF_Linda"]');
    await row2.waitFor({ state: "visible", timeout: 5000 });
    assert((await row2.getAttribute("aria-disabled")) === "true", "AC1(-): sin vestuarios la fila no está aria-disabled");
    assert(/El catálogo no tiene vestuarios/.test(await t2.anadir.innerText()), "AC1(-): falta la nota sin vestuarios");
    const ops3 = countOps(page);
    await row2.click({ force: true });
    await page.keyboard.press("Enter");
    await sleep(800);
    ops3.stop();
    assert(ops3.n === 0, "AC1(-): sin vestuarios se mandaron " + ops3.n + " POST");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC2 vestuario -----------------------------------------------------------
async function AC2(browser) {
  await clearScene();
  const [id] = await seedActors([{}]);
  let { context, page } = await openStudio(browser);
  try {
    const cat = await catalogFromApi(page);
    const props = await selectEntity(page, id);
    const opts = await props.locator("#f-wardrobe option").evaluateAll((els) => els.map((e) => e.value));
    assert(JSON.stringify(opts) === JSON.stringify(cat.wardrobes), "AC2(+): opciones de vestuario: " + JSON.stringify(opts));
    const items = async () => props.locator("[data-wardrobe-items] li").evaluateAll((els) => els.map((e) => e.textContent.trim()));
    assert(JSON.stringify(await items()) === JSON.stringify(cat.wardrobe_items.partisano), "AC2(+): prendas de partisano");

    // La IA cambia el vestuario: las prendas siguen al documento.
    const r = await cmd({ cmd: "ai_ops", label: "IA viste", ops: [{ name: "entity.set", target: id, args: { wardrobe: "cazador" } }] });
    assert(r && r.ok, "AC2: ai_ops " + JSON.stringify(r));
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline && JSON.stringify(await items()) !== JSON.stringify(cat.wardrobe_items.cazador)) await sleep(100);
    assert(JSON.stringify(await items()) === JSON.stringify(cat.wardrobe_items.cazador), "AC2(+): las prendas no siguen al vestuario del documento");

    const ops = countOps(page);
    await selectWithLease(page, "#f-wardrobe", "medica");
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).wardrobe === "medica", "AC2(+): wardrobe medica");
    await sleep(300);
    ops.stop();
    assert(ops.n === 1, "AC2(+): POST != 1: " + ops.n);
    const sent = ops.bodies[0].ops;
    assert(sent.length === 1 && sent[0].name === "entity.set" && JSON.stringify(sent[0].args) === '{"wardrobe":"medica"}',
      "AC2(+): op enviada: " + JSON.stringify(sent));
    while (Date.now() < deadline + 5000 && JSON.stringify(await items()) !== JSON.stringify(cat.wardrobe_items.medica)) await sleep(100);
    assert(JSON.stringify(await items()) === JSON.stringify(cat.wardrobe_items.medica), "AC2(+): prendas de medica");
    await context.close();

    // Negativa: el vestuario sin prendas en el catálogo que ve la web.
    ({ context, page } = await openStudio(browser, (ctx) => routeCatalog(ctx, (b) => { b.wardrobe_items.medica = []; })));
    const props2 = await selectEntity(page, id);
    const li = await props2.locator("[data-wardrobe-items] li").evaluateAll((els) => els.map((e) => e.textContent.trim()));
    assert(JSON.stringify(li) === JSON.stringify(["Sin prendas en el catálogo"]), "AC2(-): sin prendas: " + JSON.stringify(li));
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC3 comportamiento y radio ---------------------------------------------
async function AC3(browser) {
  await clearScene();
  const [id] = await seedActors([{}]);
  const { context, page } = await openStudio(browser);
  try {
    const props = await selectEntity(page, id);
    const opts = await props.locator("#f-behaviour option").evaluateAll((els) => els.map((e) => e.value));
    assert(JSON.stringify(opts) === JSON.stringify(["HOLD", "ONCE", "LOOP", "ROAM"]), "AC3(+): opciones: " + JSON.stringify(opts));
    await selectWithLease(page, "#f-behaviour", "ROAM");
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).behaviour === "ROAM", "AC3(+): ROAM");
    assert(!(await typeAndEnter(page, "#f-roam", 30)), "AC3(+): 30 marcado inválido");
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).roam === 30, "AC3(+): roam 30");

    for (const bad of ["0", "-5", ""]) {
      const ops = countOps(page);
      const inv = await typeAndEnter(page, "#f-roam", bad);
      await page.locator("#f-roam").press("Tab").catch(() => {});
      await sleep(400);
      ops.stop();
      assert(inv || (await isAriaInvalid(page.locator("#f-roam"))), "AC3(-): roam «" + bad + "» sin aria-invalid");
      assert(ops.n === 0, "AC3(-): roam «" + bad + "» mandó " + ops.n + " POST");
      await page.locator("#f-roam").press("Escape").catch(() => {});
    }
    const { ent } = await actorOf(id);
    assert(ent.roam === 30, "AC3(-): el radio cambió: " + ent.roam);
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC4 marcas --------------------------------------------------------------
async function AC4(browser) {
  await clearScene();
  const [id] = await seedActors([{}]);
  const { context, page } = await openStudio(browser);
  try {
    const props = await selectEntity(page, id);
    const sec = props.locator('[data-section="marcas"]');
    assert(/Sin marcas/.test(await sec.innerText()), "AC4(+): falta «Sin marcas»");
    const ops = countOps(page);
    await sec.getByRole("button", { name: "Añadir marca" }).click();
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).marks.length === 1, "AC4(+): 1 marca");
    await sec.getByRole("button", { name: "Añadir marca" }).click();
    let snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).marks.length === 2, "AC4(+): 2 marcas");
    await sleep(300);
    ops.stop();
    assert(ops.n === 2, "AC4(+): POST != 2: " + ops.n);
    for (const b of ops.bodies) {
      assert(b.ops.length === 1 && b.ops[0].name === "entity.marks" && b.ops[0].target === id, "AC4(+): op: " + JSON.stringify(b.ops));
    }
    let ent = snap.doc.entities.find((e) => e.id === id);
    assert(JSON.stringify(ent.marks) === JSON.stringify([{ x: 6176, z: 7632 }, { x: 6176, z: 7632 }]), "AC4(+): marcas: " + JSON.stringify(ent.marks));
    await props.locator('[data-mark="2"]').waitFor({ state: "visible", timeout: 5000 });

    const ops2 = countOps(page);
    assert(!(await typeAndEnter(page, "#f-mark-2-x", 6200)), "AC4(+): 6200 inválido");
    snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).marks[1].x === 6200, "AC4(+): x de la marca 2");
    await sleep(300);
    ops2.stop();
    ent = snap.doc.entities.find((e) => e.id === id);
    assert(JSON.stringify(ent.marks) === JSON.stringify([{ x: 6176, z: 7632 }, { x: 6200, z: 7632 }]), "AC4(+): marcas tras editar: " + JSON.stringify(ent.marks));
    assert(ops2.n === 1 && JSON.stringify(ops2.bodies[0].ops[0].args.marks) === JSON.stringify(ent.marks),
      "AC4(+): editar no mandó la lista entera: " + JSON.stringify(ops2.bodies));

    const ops3 = countOps(page);
    const inv = await typeAndEnter(page, "#f-mark-1-z", 20000);
    await sleep(300);
    ops3.stop();
    assert(inv, "AC4(-): z = 20000 sin aria-invalid");
    assert(ops3.n === 0, "AC4(-): z = 20000 mandó " + ops3.n + " POST");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC5 quitar marca --------------------------------------------------------
async function AC5(browser) {
  await clearScene();
  const marks = [{ x: 6180, z: 7630 }, { x: 6190, z: 7640 }, { x: 6200, z: 7650 }];
  const [id] = await seedActors([{ marks, gestures: [{ emote: "EmotePoint", at: 3 }] }]);
  const { context, page } = await openStudio(browser);
  try {
    const props = await selectEntity(page, id);
    const sec = props.locator('[data-section="marcas"]');
    const ops = countOps(page);
    await sec.getByRole("button", { name: "Quitar marca 1" }).click();
    const snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).marks.length === 2, "AC5(+): 2 marcas");
    await sleep(300);
    ops.stop();
    assert(ops.n === 1, "AC5(+): POST != 1: " + ops.n);
    const names = ops.bodies[0].ops.map((o) => o.name);
    assert(JSON.stringify(names) === '["entity.marks","entity.gestures"]', "AC5(+): ops: " + JSON.stringify(names));
    const ent = snap.doc.entities.find((e) => e.id === id);
    assert(JSON.stringify(ent.marks) === JSON.stringify(marks.slice(1)), "AC5(+): marcas: " + JSON.stringify(ent.marks));
    assert(JSON.stringify(ent.gestures) === JSON.stringify([{ emote: "EmotePoint", at: 2 }]), "AC5(+): gestos: " + JSON.stringify(ent.gestures));

    // Negativa: la marca 2 la usa el gesto 1.
    const btn = sec.getByRole("button", { name: "Quitar marca 2" });
    await btn.waitFor({ state: "visible", timeout: 5000 });
    assert((await btn.getAttribute("aria-disabled")) === "true", "AC5(-): Quitar marca 2 no aria-disabled");
    assert(/La usa el gesto 1/.test(await sec.innerText()), "AC5(-): falta «La usa el gesto 1»");
    const before = await cmd({ cmd: "snapshot" });
    const ops2 = countOps(page);
    await btn.click({ force: true });
    await btn.focus();
    await page.keyboard.press("Enter");
    await sleep(800);
    ops2.stop();
    assert(ops2.n === 0, "AC5(-): mandó " + ops2.n + " POST");
    const after = await cmd({ cmd: "snapshot" });
    assert(after.hash === before.hash, "AC5(-): el documento cambió");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC6 gestos --------------------------------------------------------------
async function AC6(browser) {
  await clearScene();
  const [id] = await seedActors([{}]);
  const { context, page } = await openStudio(browser);
  try {
    const cat = await catalogFromApi(page);
    const props = await selectEntity(page, id);
    const sec = props.locator('[data-section="gestos"]');
    assert(/Sin gestos/.test(await sec.innerText()), "AC6(+): falta «Sin gestos»");
    const ops = countOps(page);
    await sec.getByRole("button", { name: "Añadir gesto" }).click();
    let snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).gestures.length === 1, "AC6(+): 1 gesto");
    await sleep(300);
    ops.stop();
    assert(ops.n === 1 && ops.bodies[0].ops.length === 1 && ops.bodies[0].ops[0].name === "entity.gestures", "AC6(+): op de añadir");
    let ent = snap.doc.entities.find((e) => e.id === id);
    assert(JSON.stringify(ent.gestures) === JSON.stringify([{ emote: cat.emotes[0], t: 0 }]), "AC6(+): gesto nuevo: " + JSON.stringify(ent.gestures));

    // Sin marcas, «En la marca» desactivada.
    await props.locator("#f-gesture-1-when").waitFor({ state: "visible", timeout: 5000 });
    const atDisabled = await props.locator('#f-gesture-1-when option[value="at"]').evaluate((o) => o.disabled);
    assert(atDisabled, "AC6(-): opción at activa sin marcas");
    const opsT = countOps(page);
    const invT = await typeAndEnter(page, "#f-gesture-1-value", -1);
    await sleep(300);
    opsT.stop();
    assert(invT && opsT.n === 0, "AC6(-): t = -1 aceptado (" + opsT.n + " POST)");
    await page.locator("#f-gesture-1-value").press("Escape").catch(() => {});

    // Una marca, después emote, «cuándo» y valor.
    // La marca la pone la persona: con la lease de gestos en sus manos, la IA no puede tocar marks.
    await props.locator('[data-section="marcas"]').getByRole("button", { name: "Añadir marca" }).click();
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).marks.length === 1, "AC6: 1 marca");
    await page.waitForFunction(() => {
      const o = document.querySelector('#f-gesture-1-when option[value="at"]');
      return o && !o.disabled;
    }, null, { timeout: 5000 });
    await selectWithLease(page, "#f-gesture-1-emote", "EmoteSalute");
    await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).gestures[0].emote === "EmoteSalute", "AC6(+): EmoteSalute");
    await selectWithLease(page, "#f-gesture-1-when", "at");
    snap = await waitForSnap((s) => "at" in s.doc.entities.find((e) => e.id === id).gestures[0], "AC6(+): at");
    assert(!(await typeAndEnter(page, "#f-gesture-1-value", 1)), "AC6(+): valor 1 inválido");
    await sleep(300);
    ent = (await actorOf(id)).ent;
    assert(JSON.stringify(ent.gestures) === JSON.stringify([{ emote: "EmoteSalute", at: 1 }]), "AC6(+): gesto final: " + JSON.stringify(ent.gestures));

    for (const bad of ["2", "0", "1.5"]) {
      const o = countOps(page);
      const inv = await typeAndEnter(page, "#f-gesture-1-value", bad);
      await sleep(300);
      o.stop();
      assert(inv && o.n === 0, "AC6(-): at = " + bad + " aceptado (" + o.n + " POST)");
      await page.locator("#f-gesture-1-value").press("Escape").catch(() => {});
    }
    ent = (await actorOf(id)).ent;
    assert(JSON.stringify(ent.gestures) === JSON.stringify([{ emote: "EmoteSalute", at: 1 }]), "AC6(-): el gesto cambió: " + JSON.stringify(ent.gestures));
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC7 quitar gesto y deshacer --------------------------------------------
async function AC7(browser) {
  await clearScene();
  const gestures = [{ emote: "EmoteGreeting", t: 1.5 }, { emote: "EmoteHeart", t: 3 }];
  const [id] = await seedActors([{ gestures }]);
  const { context, page } = await openStudio(browser);
  try {
    const props = await selectEntity(page, id);
    const before = await cmd({ cmd: "snapshot" });
    const sec = props.locator('[data-section="gestos"]');
    await sec.getByRole("button", { name: "Quitar gesto 1" }).click();
    let snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).gestures.length === 1, "AC7(+): 1 gesto");
    const ent = snap.doc.entities.find((e) => e.id === id);
    assert(JSON.stringify(ent.gestures) === JSON.stringify([gestures[1]]), "AC7(+): quedó " + JSON.stringify(ent.gestures));
    await page.locator('[data-testid="barra-superior"]').getByRole("button", { name: /^Deshacer/ }).click();
    snap = await waitForSnap((s) => s.doc.entities.find((e) => e.id === id).gestures.length === 2, "AC7(+): deshacer");
    assert(JSON.stringify(snap.doc.entities.find((e) => e.id === id).gestures) === JSON.stringify(gestures), "AC7(+): gestos tras deshacer");
    assert(snap.hash === before.hash, "AC7(+): hash tras deshacer != antes");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- AC8 texto hostil y catálogo raro ---------------------------------------
async function AC8(browser) {
  await clearScene();
  const hostile = '<img src=x onerror="window.__x=1">';
  const [id] = await seedActors([{ name: hostile, gestures: [{ emote: "EmoteSalute", t: 1 }] }]);
  const edit = (b) => {
    b.emotes = b.emotes.filter((e) => e !== "EmoteSalute").concat(["<b>x</b>"]);
    b.wardrobe_items.partisano = (b.wardrobe_items.partisano || []).concat(["<i>y</i>"]);
  };
  const { context, page } = await openStudio(browser, (ctx) => routeCatalog(ctx, edit));
  try {
    const props = await selectEntity(page, id);
    const text = await props.innerText();
    assert(text.includes(hostile), "AC8(+): el nombre hostil no se ve literal");
    const sel = props.locator("#f-gesture-1-emote");
    assert((await sel.inputValue()) === "EmoteSalute", "AC8(+): el select no enseña EmoteSalute: " + (await sel.inputValue()));
    const optTexts = await sel.locator("option").evaluateAll((els) => els.map((e) => e.textContent));
    assert(optTexts.includes("<b>x</b>"), "AC8(+): la opción hostil no es literal: " + JSON.stringify(optTexts));
    const li = await props.locator("[data-wardrobe-items] li").evaluateAll((els) => els.map((e) => e.textContent.trim()));
    assert(li.includes("<i>y</i>"), "AC8(+): la prenda hostil no es literal: " + JSON.stringify(li));
    const bad = await props.evaluate((el) => el.querySelectorAll('img[src="x"], b, i').length);
    assert(bad === 0, "AC8(-): elementos inyectados en Propiedades: " + bad);
    assert((await page.evaluate(() => typeof window.__x)) === "undefined", "AC8(-): window.__x definido");
  } finally {
    await context.close().catch(() => {});
  }
}

const RUNNERS = { AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8 };

async function main() {
  const rows = resolveSelectedRows();
  const browser = await chromium.launch({ headless: true });
  try {
    for (const id of rows) {
      await RUNNERS[id](browser);
      console.log(id + " OK");
    }
    assert(pageErrors.length === 0, "AC8(-): errores de JS: " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "AC8(-): violación de CSP en consola"
    );
    console.log("ACTORES E2E OK (" + rows.join(",") + ")");
  } finally {
    await browser.close().catch(() => {});
  }
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error("FALLO: " + (err && err.message ? err.message : String(err)));
    process.exit(1);
  }
);
