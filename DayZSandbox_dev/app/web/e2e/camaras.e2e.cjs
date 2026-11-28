"use strict";
// Guion de F4-web (brief plans/2026-11-28-m1-f4-web-camaras-brief.md §4): las cámaras en el estudio.
// Lo corre app/tests/e2e_studio.py con DSBX_GUION=camaras. Cada fila imprime «CMn OK».
// /api/camera* se simula con page.route: el arnés no tiene mod.
const { chromium } = require("playwright");
const readline = require("readline");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
if (!BASE || !HUMAN_KEY) {
  console.error("FALLO: faltan DSBX_URL o DSBX_HUMAN_KEY");
  process.exit(2);
}

const ROW_ORDER = ["CM1", "CM2", "CM3", "CM4", "CM5", "CM6", "CM7", "CM8"];
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

// Simula /api/camera*: guarda los POST y contesta con lo que diga `fake`.
function routeCamera(context, fake) {
  fake.posts = [];
  fake.gets = 0;
  return context.route("**/api/camera**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "GET" && path === "/api/camera") {
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
    const r = fake.reply || { status: 200, json: { ok: true, op_id: "rd-" + fake.posts.length } };
    return route.fulfill({ status: r.status, json: r.json });
  });
}

const IDLE = { ok: true, cam: null, age_ms: null, last: null, in_flight: null };

async function camerasPanel(page) {
  await switchMode(page, "rodaje");
  return activatePanel(page, "camaras");
}

async function selectCamera(page, id) {
  const panel = await camerasPanel(page);
  await panel.locator('[data-cam="' + id + '"]').click();
  const props = await activatePanel(page, "propiedades");
  await props.locator("#f-cam-name").waitFor({ state: "visible", timeout: 5000 });
  return props;
}

async function juegoText(page) {
  return (await page.locator("[data-cam-juego]").first().innerText()).replace(/\s+/g, " ").trim();
}

async function waitJuego(page, re, desc) {
  const deadline = Date.now() + 5000;
  let last = "";
  while (Date.now() < deadline) {
    last = await juegoText(page).catch(() => "");
    if (re.test(last)) return last;
    await sleep(100);
  }
  throw new Error(desc + ": [data-cam-juego] = '" + last + "'");
}

// --- CM1 panel y Jerarquía -----------------------------------------------------
async function CM1(browser) {
  await clearScene();
  const fake = { state: IDLE };
  let { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const panel = await camerasPanel(page);
    assert((await panel.locator("[data-hueco]").count()) === 0, "CM1(+): el panel sigue siendo un hueco");
    assert((await panel.innerText()).includes("Todavía no hay cámaras."), "CM1(-): sin cámaras no lo dice");
    await context.close();
    const ids = await seedCameras([{ name: "Plano general", keys: [KEY()] }, { name: "Travelling", keys: CAMINO }]);
    ({ context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake)));
    const p2 = await camerasPanel(page);
    const rows = await p2.locator("[data-cam]").evaluateAll((els) => els.map((e) => e.getAttribute("data-cam")));
    assert(JSON.stringify(rows) === JSON.stringify(ids), "CM1(+): filas " + JSON.stringify(rows));
    const r0 = (await p2.locator('[data-cam="' + ids[0] + '"]').innerText()).replace(/\s+/g, " ");
    const r1 = (await p2.locator('[data-cam="' + ids[1] + '"]').innerText()).replace(/\s+/g, " ");
    assert(r0.includes("Plano general") && r0.includes("Fija"), "CM1(+): fila 0 = " + r0);
    assert(r1.includes("Travelling") && r1.includes("Camino · 3 claves · 6,0 s"), "CM1(+): fila 1 = " + r1);
    await p2.locator('[data-cam="' + ids[1] + '"]').click();
    const props = await activatePanel(page, "propiedades");
    await props.locator("#f-cam-name").waitFor({ state: "visible", timeout: 5000 });
    assert((await props.locator("#f-cam-name").inputValue()) === "Travelling", "CM1(+): Propiedades no enseña la cámara");
    assert((await props.locator('[data-section="claves"] [data-key]').count()) === 3, "CM1(+): no hay 3 claves");
    await activatePanel(page, "camaras");
    assert((await p2.locator('[data-cam="' + ids[1] + '"]').getAttribute("aria-selected")) === "true", "CM1(+): fila no seleccionada");
    // Jerarquía, en Escena
    await switchMode(page, "escena");
    const tree = await activatePanel(page, "jerarquia");
    const items = await tree.locator('[role="treeitem"][data-cam-id]').evaluateAll((els) => els.map((e) => e.getAttribute("data-cam-id")));
    assert(JSON.stringify(items) === JSON.stringify(ids), "CM1(+): Jerarquía " + JSON.stringify(items));
    assert(!(await tree.innerText()).includes("Llegan con F4"), "CM1(-): la Jerarquía sigue diciendo Llegan con F4");
    await tree.locator('[role="treeitem"][data-cam-id="' + ids[0] + '"]').click();
    const props2 = await activatePanel(page, "propiedades");
    await props2.locator("#f-cam-name").waitFor({ state: "visible", timeout: 5000 });
    assert((await props2.locator("#f-cam-name").inputValue()) === "Plano general", "CM1(+): Jerarquía no selecciona");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM2 nueva cámara ----------------------------------------------------------
async function CM2(browser) {
  await clearScene();
  const fake = { state: IDLE };
  const before = await cmd({ cmd: "snapshot" });
  const n = before.doc.next.cam;
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const panel = await camerasPanel(page);
    const ops = countOps(page);
    await panel.locator("#cam-new").click();
    const snap = await waitForSnap((s) => s.doc.cameras.length === 1, "CM2(+): cámara creada");
    await sleep(300);
    ops.stop();
    assert(ops.n === 1, "CM2(+): POST != 1: " + ops.n);
    const sent = ops.bodies[0].ops;
    const want = { name: "Cámara " + n, keys: [{ t: 0, x: 7680, y: 2, z: 7680, yaw: 0, pitch: 0, fov: 50, focus: 10 }] };
    assert(sent.length === 1 && sent[0].name === "camera.add", "CM2(+): ops " + JSON.stringify(sent));
    assert(canon(sent[0].args) === canon(want), "CM2(+): args " + JSON.stringify(sent[0].args));
    const id = snap.doc.cameras[0].id;
    await activatePanel(page, "camaras");
    await page.waitForFunction((q) => {
      const el = document.querySelector(q);
      return !!el && el.getAttribute("aria-selected") === "true";
    }, '[data-cam="' + id + '"]', { timeout: 5000 });
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM3 editar una clave --------------------------------------------------------
async function CM3(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const props = await selectCamera(page, id);
    assert((await props.locator("#f-key-1-t").getAttribute("readonly")) !== null, "CM3(+): t de la clave 1 no es readonly");
    const ops = countOps(page);
    assert(!(await typeAndEnter(page, "#f-key-2-fov", 33)), "CM3(+): fov 33 marcado inválido");
    const cam = await (async () => {
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        const c = await camOf(id);
        if (c.keys[1].fov === 33) return c;
        await sleep(100);
      }
      throw new Error("CM3(+): el fov no llegó al documento");
    })();
    await sleep(300);
    assert(ops.n === 1, "CM3(+): POST != 1: " + ops.n);
    const sent = ops.bodies[0].ops;
    const want = CAMINO.map((k, i) => (i === 1 ? Object.assign({}, k, { fov: 33 }) : k));
    assert(sent.length === 1 && sent[0].name === "camera.set" && sent[0].target === id, "CM3(+): ops " + JSON.stringify(sent));
    assert(JSON.stringify(Object.keys(sent[0].args)) === '["keys"]', "CM3(+): args " + JSON.stringify(sent[0].args));
    assert(canon(sent[0].args.keys) === canon(want), "CM3(+): keys " + JSON.stringify(sent[0].args.keys));
    assert(canon(cam.keys) === canon(want), "CM3(+): documento " + JSON.stringify(cam.keys));
    // negativas: ninguna manda nada
    for (const [sel, val] of [["#f-key-2-t", 7], ["#f-key-3-t", 3], ["#f-key-2-x", 20000], ["#f-key-2-z", -1],
      ["#f-key-2-yaw", 360], ["#f-key-2-pitch", 91], ["#f-key-2-fov", 0], ["#f-key-2-fov", 180], ["#f-key-2-focus", 0]]) {
      assert(await typeAndEnter(page, sel, val), "CM3(-): " + sel + "=" + val + " no quedó aria-invalid");
      await page.locator(sel).press("Escape").catch(() => {});
    }
    await sleep(300);
    ops.stop();
    assert(ops.n === 1, "CM3(-): las negativas mandaron " + (ops.n - 1) + " POST");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM4 añadir y quitar clave ----------------------------------------------------
async function CM4(browser) {
  await clearScene();
  const [id, fixed] = await seedCameras([{ name: "Travelling", keys: CAMINO }, { name: "Fija", keys: [KEY()] }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    let props = await selectCamera(page, id);
    const ops = countOps(page);
    await props.locator("#cam-key-add").click();
    let c = null;
    const d1 = Date.now() + 5000;
    while (Date.now() < d1 && !(c && c.keys.length === 4)) { c = await camOf(id); await sleep(100); }
    assert(c.keys.length === 4, "CM4(+): no se añadió la clave");
    assert(canon(c.keys[3]) === canon(Object.assign({}, CAMINO[2], { t: 7 })), "CM4(+): clave añadida " + JSON.stringify(c.keys[3]));
    await props.locator('[data-key="4"]').waitFor({ state: "visible", timeout: 5000 });
    await props.locator('[data-key-del="1"]').click();
    const d2 = Date.now() + 5000;
    while (Date.now() < d2 && c.keys.length !== 3) { c = await camOf(id); await sleep(100); }
    const want = [Object.assign({}, CAMINO[1], { t: 0 }), Object.assign({}, CAMINO[2], { t: 3 }), Object.assign({}, CAMINO[2], { t: 4 })];
    assert(canon(c.keys) === canon(want), "CM4(+): tras quitar la 1: " + JSON.stringify(c.keys));
    await sleep(300);
    ops.stop();
    assert(ops.n === 2, "CM4(+): POST != 2: " + ops.n);
    assert(ops.bodies.every((b) => b.ops.length === 1 && b.ops[0].name === "camera.set"), "CM4(+): ops " + JSON.stringify(ops.bodies));
    // negativa: con una sola clave, quitar está desactivado
    props = await selectCamera(page, fixed);
    const del = props.locator('[data-key-del="1"]');
    const dis = await del.evaluate((el) => !!(el.disabled || el.getAttribute("aria-disabled") === "true"));
    assert(dis, "CM4(-): quitar la única clave no está desactivado");
    const ops2 = countOps(page);
    await del.click({ force: true }).catch(() => {});
    await sleep(500);
    ops2.stop();
    assert(ops2.n === 0, "CM4(-): quitar la única clave mandó " + ops2.n + " POST");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM5 reproducir, parar e ir a una pose ------------------------------------------
async function CM5(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const snap = await cmd({ cmd: "snapshot" });
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const panel = await camerasPanel(page);
    const play = panel.locator("#cam-play");
    const dis = await play.evaluate((el) => !!(el.disabled || el.getAttribute("aria-disabled") === "true"));
    assert(dis, "CM5(-): Reproducir activo sin selección");
    await play.click({ force: true }).catch(() => {});
    await sleep(300);
    assert(fake.posts.length === 0, "CM5(-): sin selección se mandó " + JSON.stringify(fake.posts));
    const props = await selectCamera(page, id);
    await props.locator('[data-key-goto="2"]').click();
    await activatePanel(page, "camaras");
    await panel.locator("#cam-play").click();
    await panel.locator("#cam-stop").click();
    await sleep(500);
    const want = [
      { path: "/api/camera/play", body: { doc_id: snap.doc_id, cam_id: id, key: 1 } },
      { path: "/api/camera/play", body: { doc_id: snap.doc_id, cam_id: id } },
      { path: "/api/camera/stop", body: {} },
    ];
    assert(canon(fake.posts) === canon(want), "CM5(+): POST " + JSON.stringify(fake.posts));
    assert(fake.gets >= 1, "CM5(+): el panel no leyó GET /api/camera");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM6 el estado del juego ---------------------------------------------------------
async function CM6(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  const cam = (o) => Object.assign({ active: 1, playing: 0, cam_id: id, t_ms: 0, dur_ms: 6000, pose: [1, 2, 3, 4, 5, 6] }, o);
  const last = (status, reason) => ({ op_id: "rd-1", verb: "camera.play", status, reason });
  try {
    const panel = await camerasPanel(page);
    await waitJuego(page, /^Sin cámara del estudio en el juego$/, "CM6 nulo");
    fake.state = Object.assign({}, IDLE, { cam: cam({ playing: 1, t_ms: 1234 }), last: last("done", null) });
    await waitJuego(page, /^Reproduciendo Travelling · 1,2 \/ 6,0 s$/, "CM6 reproduciendo");
    fake.state = Object.assign({}, IDLE, { cam: cam({ t_ms: 6000 }), last: last("done", null) });
    await waitJuego(page, /^Quieta en Travelling$/, "CM6 quieta");
    fake.state = Object.assign({}, IDLE, { cam: cam({ cam_id: "cam-99" }), last: last("done", null) });
    await waitJuego(page, /^Quieta en cam-99$/, "CM6 id desconocido");
    fake.state = Object.assign({}, IDLE, { cam: cam({}), last: last("rejected", "busy") });
    await waitJuego(page, /^El juego no la aceptó \(busy\)$/, "CM6 rechazada");
    fake.state = Object.assign({}, IDLE, { cam: cam({}), last: last("dropped", "sin_resultado") });
    await waitJuego(page, /^La orden no llegó al juego$/, "CM6 descartada");
    fake.state = Object.assign({}, IDLE, { cam: Object.assign({}, cam({}), { active: 0, cam_id: "", dur_ms: 0, pose: [0, 0, 0, 0, 0, 0] }), last: last("done", null) });
    await waitJuego(page, /^Sin cámara del estudio en el juego$/, "CM6 inactiva");
    await panel.locator('[data-cam="' + id + '"]').click();
    await activatePanel(page, "camaras");
    for (const [reply, re] of [
      [{ status: 409, json: { ok: false, code: "client_not_in_game", pointer: "", msg: "x" } }, /^Tu juego no está conectado$/],
      [{ status: 409, json: { ok: false, code: "camera_busy", pointer: "", msg: "x" } }, /^Hay una orden de cámara en curso$/],
      [{ status: 422, json: { ok: false, code: "out_of_map", pointer: "/cameras/0/keys/1/x", msg: "Fuera del mapa" } }, /^No se pudo: Fuera del mapa$/],
    ]) {
      fake.reply = reply;
      await panel.locator("#cam-play").click();
      await waitJuego(page, re, "CM6 error " + reply.json.code);
      await sleep(1300);
      assert(re.test(await juegoText(page)), "CM6: el error " + reply.json.code + " no se quedó tras un GET");
    }
    fake.reply = null;
    await panel.locator("#cam-stop").click();
    await waitJuego(page, /^Sin cámara del estudio en el juego$/, "CM6 el 200 borra el error");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM7 nombre y borrar ---------------------------------------------------------------
async function CM7(browser) {
  await clearScene();
  const [id] = await seedCameras([{ name: "Travelling", keys: CAMINO }]);
  const fake = { state: IDLE };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const props = await selectCamera(page, id);
    const ops = countOps(page);
    assert(await typeAndEnter(page, "#f-cam-name", "   "), "CM7(-): nombre vacío no quedó aria-invalid");
    await page.locator("#f-cam-name").press("Escape").catch(() => {});
    await sleep(300);
    assert(ops.n === 0, "CM7(-): el nombre vacío mandó " + ops.n + " POST");
    assert(!(await typeAndEnter(page, "#f-cam-name", "Dolly")), "CM7(+): Dolly marcado inválido");
    await waitForSnap((s) => s.doc.cameras[0].name === "Dolly", "CM7(+): nombre en el documento");
    assert(ops.bodies[0].ops[0].name === "camera.set" && JSON.stringify(ops.bodies[0].ops[0].args) === '{"name":"Dolly"}', "CM7(+): ops " + JSON.stringify(ops.bodies[0]));
    await props.locator("#cam-delete").click();
    await waitForSnap((s) => s.doc.cameras.length === 0, "CM7(+): borrada");
    await sleep(300);
    ops.stop();
    assert(ops.bodies[ops.bodies.length - 1].ops[0].name === "camera.delete", "CM7(+): no fue camera.delete");
    assert((await page.locator("#f-cam-name").count()) === 0, "CM7(+): Propiedades sigue enseñando la cámara");
  } finally {
    await context.close().catch(() => {});
  }
}

// --- CM8 texto hostil ----------------------------------------------------------------
async function CM8(browser) {
  await clearScene();
  const hostile = '<img src=x onerror="window.__x=1">';
  const [id] = await seedCameras([{ name: hostile, keys: CAMINO }]);
  const fake = { state: Object.assign({}, IDLE, { cam: { active: 1, playing: 0, cam_id: id, t_ms: 0, dur_ms: 0, pose: [1, 2, 3, 4, 5, 6] } }) };
  const { context, page } = await openStudio(browser, (ctx) => routeCamera(ctx, fake));
  try {
    const panel = await camerasPanel(page);
    assert((await panel.innerText()).includes(hostile), "CM8(+): el nombre hostil no se ve literal en Cámaras");
    await waitJuego(page, new RegExp("^Quieta en " + hostile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$"), "CM8 estado");
    const props = await selectCamera(page, id);
    assert((await props.locator("#f-cam-name").inputValue()) === hostile, "CM8(+): nombre en Propiedades");
    for (const root of [panel, props]) {
      const bad = await root.evaluate((el) => el.querySelectorAll('img[src="x"]').length);
      assert(bad === 0, "CM8(-): elementos inyectados: " + bad);
    }
    assert((await page.evaluate(() => typeof window.__x)) === "undefined", "CM8(-): window.__x definido");
  } finally {
    await context.close().catch(() => {});
  }
}

const RUNNERS = { CM1, CM2, CM3, CM4, CM5, CM6, CM7, CM8 };

async function main() {
  const rows = resolveSelectedRows();
  const browser = await chromium.launch({ headless: true });
  try {
    for (const id of rows) {
      await RUNNERS[id](browser);
      console.log(id + " OK");
    }
    assert(pageErrors.length === 0, "CM8(-): errores de JS: " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "CM8(-): violación de CSP en consola"
    );
    console.log("CAMARAS E2E OK (" + rows.join(",") + ")");
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
