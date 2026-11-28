"use strict";
// Guion de F5 parte 1 (brief plans/2026-11-28-m1-f5-tomas-1-brief.md §6): el panel Tomas.
// Lo corre app/tests/e2e_studio.py con DSBX_GUION=tomas. Cada fila imprime «TMn OK».
// /api/take* se simula con page.route: el arnés no tiene mod.
const { chromium } = require("playwright");
const readline = require("readline");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
if (!BASE || !HUMAN_KEY) {
  console.error("FALLO: faltan DSBX_URL o DSBX_HUMAN_KEY");
  process.exit(2);
}

const ROW_ORDER = ["TM1", "TM2", "TM3", "TM4", "TM5", "TM6"];
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
  const ops = (snap.doc.entities || []).map((e) => ({ name: "entity.delete", target: e.id, args: {} }))
    .concat((snap.doc.cameras || []).map((c) => ({ name: "camera.delete", target: c.id, args: {} })));
  if (ops.length) {
    const r = await cmd({ cmd: "ai_ops", label: "Limpiar escena", ops });
    assert(r && r.ok, "limpiar: " + JSON.stringify(r));
  }
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


async function activatePanel(page, panelId) {
  const panel = page.locator('[data-panel="' + panelId + '"]');
  if ((await panel.count()) > 0 && (await panel.first().isVisible().catch(() => false))) return panel.first();
  await page.locator('.dv-tab[data-tab-panel-id="' + panelId + '"]').first().click();
  await panel.first().waitFor({ state: "visible", timeout: 5000 });
  return panel.first();
}

async function switchMode(page, modeName) {
  const re = modeName === "rodaje" ? /^Rodaje\b/ : /^Escena\b/;
  await page.locator('[data-testid="barra-superior"] [role="group"] button', { hasText: re }).first().click();
  await page.waitForFunction((src) => {
    const rx = new RegExp(src);
    const b = Array.from(document.querySelectorAll('[data-testid="barra-superior"] [role="group"] button'))
      .find((el) => rx.test((el.textContent || "").trim()));
    return !!b && b.getAttribute("aria-pressed") === "true";
  }, re.source, { timeout: 5000 });
}

// Compara sin depender del orden de las claves de los objetos.
function canon(v) {
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  if (v && typeof v === "object") return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
  return JSON.stringify(v);
}

const KEY = (o) => Object.assign({ t: 0, x: 6100, y: 2, z: 7600, yaw: 10, pitch: 0, fov: 40, focus: 5 }, o || {});
const CAMINO = [KEY({ t: 0 }), KEY({ t: 3, x: 6110, yaw: 20 }), KEY({ t: 6, x: 6120, yaw: -12, fov: 30 })];

// Crea cámaras por la IA y devuelve sus ids en orden.
async function seedCameras(list) {
  const ops = list.map((c) => ({ name: "camera.add", args: { name: c.name, keys: c.keys } }));
  const r = await cmd({ cmd: "ai_ops", label: "Sembrar cámaras", ops });
  assert(r && r.ok, "sembrar: " + JSON.stringify(r));
  const snap = await cmd({ cmd: "snapshot" });
  return snap.doc.cameras.map((c) => c.id);
}

async function camOf(id) {
  const snap = await cmd({ cmd: "snapshot" });
  return snap.doc.cameras.find((c) => c.id === id);
}

// Simula /api/take*: guarda los POST y contesta con lo que diga `fake`.
function routeTake(context, fake) {
  fake.posts = [];
  fake.gets = 0;
  return context.route("**/api/take**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "GET" && path === "/api/take") {
      fake.gets += 1;
      return route.fulfill({ status: 200, json: fake.state });
    }
    let body = null;
    try {
      body = JSON.parse(req.postData() || "null");
    } catch {
      body = null;
    }
    fake.posts.push({ path, body });
    const r = fake.reply || { status: 200, json: { ok: true, take_id: "tk-s-1" } };
    return route.fulfill({ status: r.status, json: r.json });
  });
}

const IDLE = { ok: true, take: null };
function TAKE(o) {
  return {
    ok: true,
    take: Object.assign({ take_id: "tk-s-1", doc_id: "d", rev: 1, cam_id: "cam-x", state: "armada", origin: null,
      reason: null, bad: [], t_ms: 0, dur_ms: 6000 }, o || {}),
  };
}

async function takesPanel(page) {
  await switchMode(page, "rodaje");
  return activatePanel(page, "tomas");
}

async function estadoText(page) {
  return (await page.locator("[data-take-estado]").first().innerText()).replace(/\s+/g, " ").trim();
}

async function waitEstado(page, re, desc) {
  const deadline = Date.now() + 5000;
  let last = "";
  while (Date.now() < deadline) {
    last = await estadoText(page).catch(() => "");
    if (re.test(last)) return last;
    await sleep(100);
  }
  throw new Error(desc + ": [data-take-estado] = '" + last + "'");
}

async function disabled(loc) {
  return loc.isDisabled();
}

// Espera a que el panel haya leído al menos una vez el estado nuevo.
async function settle(fake) {
  const g = fake.gets;
  const deadline = Date.now() + 3000;
  while (fake.gets < g + 2 && Date.now() < deadline) await sleep(50);
  await sleep(100);
}

// --- TM1 el select de cámaras ----------------------------------------------------
async function TM1(browser) {
  await clearScene();
  const fake = { state: IDLE };
  let { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    let panel = await takesPanel(page);
    assert((await panel.locator("[data-hueco]").count()) === 0, "TM1(+): el panel sigue siendo un hueco");
    assert((await panel.locator("[data-take-vacio]").innerText()).includes("Crea una cámara con un camino para rodar."),
      "TM1(-): sin cámaras no lo dice");
    assert(await disabled(panel.locator("#take-cam")), "TM1(-): select activo sin cámaras");
    assert(await disabled(panel.locator("#take-prepare")), "TM1(-): Preparar activo sin cámaras");
    await context.close();
    const ids = await seedCameras([{ name: "Plano general", keys: [KEY()] }, { name: "Travelling", keys: CAMINO },
      { name: "Dolly", keys: [KEY(), KEY({ t: 2 })] }]);
    ({ context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake)));
    panel = await takesPanel(page);
    const opts = await panel.locator("#take-cam option").evaluateAll((els) =>
      els.filter((e) => e.value).map((e) => [e.value, (e.textContent || "").trim()]));
    assert(canon(opts) === canon([[ids[1], "Travelling"], [ids[2], "Dolly"]]), "TM1(+): opciones " + JSON.stringify(opts));
    assert((await panel.locator("[data-take-vacio]").count()) === 0, "TM1(+): texto de vacío con cámaras");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- TM2 Preparar y los botones ---------------------------------------------------
async function TM2(browser) {
  await clearScene();
  const [, id] = await seedCameras([{ name: "Plano general", keys: [KEY()] }, { name: "Travelling", keys: CAMINO }]);
  const snap = await cmd({ cmd: "snapshot" });
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    const panel = await takesPanel(page);
    const prep = panel.locator("#take-prepare");
    const go = panel.locator("#take-go");
    const stop = panel.locator("#take-stop");
    await panel.locator("#take-cam").selectOption(id);
    await settle(fake);
    assert(!(await disabled(prep)) && (await disabled(go)) && (await disabled(stop)), "TM2: botones sin toma");
    await prep.click();
    await sleep(300);
    assert(canon(fake.posts) === canon([{ path: "/api/take/prepare", body: { doc_id: snap.doc_id, cam_id: id } }]),
      "TM2(+): POST " + JSON.stringify(fake.posts));
    const want = {
      preparando: [true, true, false],
      armada: [true, false, false],
      rodando: [true, true, false],
      terminada: [false, true, true],
      parada: [false, true, true],
      fallida: [false, true, true],
    };
    for (const [state, [p, g, s]] of Object.entries(want)) {
      fake.state = TAKE({ cam_id: id, state, origin: state === "parada" ? "web" : null, reason: state === "fallida" ? "x" : null,
        t_ms: state === "terminada" ? 6000 : 0 });
      await settle(fake);
      const got = [await disabled(prep), await disabled(go), await disabled(stop)];
      assert(canon(got) === canon([p, g, s]), "TM2: " + state + " desactivados " + JSON.stringify(got));
    }
    assert(fake.gets >= 1, "TM2(+): el panel no leyó GET /api/take");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- TM3 Rodar y Parar -------------------------------------------------------------
async function TM3(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: TAKE({ take_id: "tk-abc-7", cam_id: id, state: "armada" }) };
  const { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    const panel = await takesPanel(page);
    await settle(fake);
    await panel.locator("#take-go").click();
    await sleep(200);
    fake.state = TAKE({ take_id: "tk-abc-7", cam_id: id, state: "rodando", t_ms: 1200 });
    await settle(fake);
    await panel.locator("#take-stop").click();
    await sleep(300);
    const want = [
      { path: "/api/take/go", body: { take_id: "tk-abc-7" } },
      { path: "/api/take/stop", body: { take_id: "tk-abc-7" } },
    ];
    assert(canon(fake.posts) === canon(want), "TM3(+): POST " + JSON.stringify(fake.posts));
  } finally {
    await context.close().catch(() => {});
  }
}

// --- TM4 los estados ------------------------------------------------------------------
async function TM4(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    await takesPanel(page);
    await waitEstado(page, /^Sin tomas todavía$/, "TM4 sin toma");
    const rows = [
      [{ state: "preparando" }, /^Preparando Travelling$/],
      [{ state: "armada" }, /^Lista para rodar Travelling$/],
      [{ state: "rodando", t_ms: 1200 }, /^Rodando Travelling · 1,2 \/ 6,0 s$/],
      [{ state: "rodando", t_ms: 1200, cam_id: "cam-99" }, /^Rodando cam-99 · 1,2 \/ 6,0 s$/],
      [{ state: "terminada", t_ms: 6000 }, /^Terminada$/],
      [{ state: "parada", origin: "web", t_ms: 3000 }, /^Parada desde la web$/],
      [{ state: "parada", origin: "juego", t_ms: 3000 }, /^Parada con la tecla del juego$/],
      [{ state: "parada", origin: "hombre_muerto", t_ms: 3000 }, /^Parada por hombre muerto$/],
    ];
    for (const [o, re] of rows) {
      fake.state = TAKE(Object.assign({ cam_id: id }, o));
      await waitEstado(page, re, "TM4 " + JSON.stringify(o));
    }
  } finally {
    await context.close().catch(() => {});
  }
}

// --- TM5 errores y fallidas -------------------------------------------------------------
async function TM5(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    const panel = await takesPanel(page);
    await panel.locator("#take-cam").selectOption(id);
    for (const [reply, re] of [
      [{ status: 409, json: { ok: false, code: "no_director", pointer: "", msg: "x" } }, /^Tu juego no está conectado$/],
      [{ status: 409, json: { ok: false, code: "scene_not_observed", pointer: "", msg: "x" } }, /^Aplica la escena antes de preparar$/],
      [{ status: 409, json: { ok: false, code: "take_busy", pointer: "", msg: "x" } }, /^Ya hay una toma en curso$/],
      [{ status: 422, json: { ok: false, code: "invalid", pointer: "/cameras/0/keys", msg: "Sin camino" } }, /^No se pudo: Sin camino$/],
    ]) {
      fake.reply = reply;
      await panel.locator("#take-prepare").click();
      await waitEstado(page, re, "TM5 error " + reply.json.code);
      await sleep(1100);
      assert(re.test(await estadoText(page)), "TM5: el error " + reply.json.code + " no se quedó tras un GET");
    }
    fake.reply = null;
    await panel.locator("#take-prepare").click();
    await waitEstado(page, /^Sin tomas todavía$/, "TM5 el 200 borra el error");
    fake.state = TAKE({ cam_id: id, state: "fallida", reason: "checks", bad: ["scene", "marks", "wardrobe", "env", "director"] });
    await waitEstado(page, /^No está lista: escena distinta, actores fuera de marca, vestuario distinto, hora o clima distintos, sin director$/, "TM5 checks");
    fake.state = TAKE({ cam_id: id, state: "fallida", reason: "checks", bad: ["env"] });
    await waitEstado(page, /^No está lista: hora o clima distintos$/, "TM5 checks env");
    fake.state = TAKE({ cam_id: id, state: "fallida", reason: "mundo_reiniciado" });
    await waitEstado(page, /^Falló \(mundo_reiniciado\)$/, "TM5 otro motivo");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- TM6 texto hostil -------------------------------------------------------------------
async function TM6(browser) {
  await clearScene();
  const hostile = '<img src=x onerror="window.__x=1">';
  const [id] = await seedCameras([{ name: hostile, keys: CAMINO }]);
  const fake = { state: TAKE({ cam_id: id, state: "armada" }) };
  const { context, page } = await openStudio(browser, (ctx) => routeTake(ctx, fake));
  try {
    const panel = await takesPanel(page);
    await waitEstado(page, new RegExp("^Lista para rodar " + hostile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$"), "TM6 estado");
    fake.state = TAKE({ cam_id: id, state: "fallida", reason: '<b id="y">r</b>' });
    await waitEstado(page, /^Falló \(<b id="y">r<\/b>\)$/, "TM6 motivo");
    const bad = await panel.evaluate((el) => el.querySelectorAll('img[src="x"], b#y').length);
    assert(bad === 0, "TM6(-): elementos inyectados: " + bad);
    assert((await page.evaluate(() => typeof window.__x)) === "undefined", "TM6(-): window.__x definido");
  } finally {
    await context.close().catch(() => {});
  }
}

const RUNNERS = { TM1, TM2, TM3, TM4, TM5, TM6 };

async function main() {
  const rows = resolveSelectedRows();
  const browser = await chromium.launch({ headless: true });
  try {
    for (const id of rows) {
      await RUNNERS[id](browser);
      console.log(id + " OK");
    }
    assert(pageErrors.length === 0, "TM6(-): errores de JS: " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "TM6(-): violación de CSP en consola"
    );
    console.log("TOMAS E2E OK (" + rows.join(",") + ")");
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
