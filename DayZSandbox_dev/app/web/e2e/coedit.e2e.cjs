"use strict";
// Guion de F6-web parte 2 (brief §8.2): la IA en la web, el Historial y Deshacer tanda.
// Lo corre app/tests/e2e_studio.py con DSBX_GUION=coedit. Cada fila imprime «Cn OK».
const { chromium } = require("playwright");
const readline = require("readline");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
if (!BASE || !HUMAN_KEY) {
  console.error("FALLO: faltan DSBX_URL o DSBX_HUMAN_KEY");
  process.exit(2);
}

// C7 va primero: necesita las pilas de la persona vacías, y el almacén dura toda la corrida.
// C10 deja la clave de la IA revocada hasta reiniciar el backend; las demás filas empiezan con uno nuevo.
const ROW_ORDER = ["C7", "C1", "C2", "C3", "C4", "C5", "C6", "C8", "C9", "C10"];
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
const externalRequests = [];
const seenCsrf = new Set();
const seenCookies = new Set();
function track(page) {
  page.on("console", (m) => consoleTexts.push(m.text()));
  page.on("pageerror", (err) => pageErrors.push(err && err.message ? err.message : String(err)));
  page.on("request", (req) => {
    const u = req.url();
    if (u === "about:blank") return;
    if (!u.startsWith(BASE + "/") && u !== BASE) externalRequests.push(u);
  });
}

async function rememberSecrets(context, page) {
  const csrf = await page.evaluate(() => localStorage.getItem("csrf")).catch(() => null);
  if (csrf) seenCsrf.add(csrf);
  for (const c of await context.cookies().catch(() => [])) {
    if (c.name.startsWith("dsbx_session_") && c.value) seenCookies.add(c.value);
  }
}

// Backend nuevo (pausa y última llamada de la IA a cero) sobre el mismo almacén, y escena vacía.
async function freshBackend() {
  assert((await cmd({ cmd: "stop_backend" })).ok, "stop_backend");
  assert((await cmd({ cmd: "start_backend" })).ok, "start_backend");
  const snap = await cmd({ cmd: "snapshot" });
  const ops = (snap.doc.entities || []).map((e) => ({ name: "entity.delete", target: e.id, args: {} }));
  if (ops.length) {
    const r = await cmd({ cmd: "ai_ops", label: "Limpiar escena", ops });
    assert(r && r.ok, "limpiar: " + JSON.stringify(r));
  }
}

async function openStudio(browser, before, noSse = false) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, colorScheme: "dark" });
  if (before) await before(context);
  const page = await context.newPage();
  track(page);
  await page.goto(BASE + "/");
  if (noSse) {
    // Sin SSE nunca dice «Conectado»: basta con el estudio a la vista, como en C6.
    await login(context, page).catch(() => {});
    await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: 10000 });
  } else {
    await login(context, page);
  }
  return { context, page };
}

async function login(context, page) {
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
  await page.locator('[data-testid="luz-ia"]').waitFor({ state: "visible", timeout: 5000 });
  await rememberSecrets(context, page);
}

// C8 (W2-09): el almacenamiento se audita en cada contexto, tras sus acciones y antes de cerrarlo.
const storageLeaks = [];
async function closeAudited(context) {
  for (const page of context.pages()) {
    await rememberSecrets(context, page);
    const store = await page
      .evaluate(() => ({
        local: Object.keys(localStorage).filter((k) => k !== "csrf").map((k) => localStorage.getItem(k)),
        session: Object.keys(sessionStorage).map((k) => sessionStorage.getItem(k)),
      }))
      .catch(() => ({ local: [], session: [] }));
    const secrets = [HUMAN_KEY, ...seenCookies, ...seenCsrf];
    if ([...store.local, ...store.session].some((v) => secrets.some((x) => x && v && v.includes(x)))) {
      storageLeaks.push(page.url());
    }
  }
  await context.close();
}

// Retiene las respuestas de una ruta: la petición llega al backend en su momento, la respuesta
// se entrega al soltar. Con first, solo la primera petición tras armarlo.
async function hold(target, pattern, first = false) {
  const h = { held: [], seen: 0, open: false };
  const fn = async (route) => {
    if (h.open || (first && h.seen > 0)) return route.continue();
    h.seen += 1;
    const resp = await route.fetch();
    h.held.push(() => route.fulfill({ response: resp }));
  };
  await target.route(pattern, fn);
  h.waitHeld = async (desc, timeoutMs = 7000) => {
    const deadline = Date.now() + timeoutMs;
    while (h.held.length === 0 && Date.now() < deadline) await sleep(50);
    assert(h.held.length > 0, "timeout (" + desc + "): no llegó la petición retenida");
  };
  h.release = async () => {
    h.open = true;
    for (const f of h.held.splice(0)) await f();
    await target.unroute(pattern, fn);
  };
  return h;
}

async function activatePanel(page, panelId) {
  const panel = page.locator('[data-panel="' + panelId + '"]');
  if ((await panel.count()) > 0 && (await panel.first().isVisible().catch(() => false))) return panel.first();
  await page.locator('.dv-tab[data-tab-panel-id="' + panelId + '"]').first().click();
  await panel.first().waitFor({ state: "visible", timeout: 5000 });
  return panel.first();
}

async function waitText(locator, re, desc, timeoutMs = 7000) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    last = ((await locator.first().innerText().catch(() => "")) || "").replace(/\s+/g, " ").trim();
    if (re.test(last)) return last;
    await sleep(100);
  }
  throw new Error("timeout (" + desc + "): «" + last + "»");
}

async function waitForSnap(predicate, desc, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await cmd({ cmd: "snapshot" });
    if (last && last.ok && predicate(last)) return last;
    await sleep(100);
  }
  throw new Error("timeout esperando snapshot (" + desc + ")");
}

async function waitEditable(page, selector) {
  await page.waitForFunction(
    (sel) => {
      const el = document.querySelector(sel);
      return !!el && !el.readOnly && !el.disabled;
    },
    selector,
    { timeout: 5000 }
  );
}

function addOp(name, x, z) {
  return { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name, x, z, yaw: 0 } };
}

async function addEntity(name, x, z, who = "ai_ops") {
  const r = await cmd({ cmd: who, label: "Colocar " + name, ops: [addOp(name, x, z)] });
  assert(r && r.ok && r.created && r.created.length === 1, "addEntity: " + JSON.stringify(r));
  return r.created[0];
}

const light = (page) => page.locator('[data-testid="luz-ia"]');
const iaPanel = (page) => page.locator('[data-panel="ia"]');

function countPosts(page, pathname) {
  const counter = { n: 0, bodies: [] };
  const fn = (req) => {
    if (req.method() === "POST" && new URL(req.url()).pathname === pathname) {
      counter.n += 1;
      counter.bodies.push(req.postData());
    }
  };
  page.on("request", fn);
  counter.stop = () => page.off("request", fn);
  return counter;
}

// --- C1 luz de la IA ---------------------------------------------------------
async function C1(browser) {
  await freshBackend();
  const { context, page } = await openStudio(browser);
  try {
    await waitText(light(page), /^MCP apagado$/, "C1(+): al entrar");
    assert((await light(page).locator("button").count()) === 0, "C1(-): la luz tiene botones");
    assert((await cmd({ cmd: "ai_call" })).status === 200, "C1: ai_call");
    await waitText(light(page), /^IA conectada$/, "C1(+): tras ai_call", 7000);
    const eid = await addEntity("Barril c1", 6000, 6000, "human_ops");
    await sleep(600);
    assert(!/editando/.test(await light(page).innerText()), "C1(-): una tanda de la persona pone «IA editando»");
    const r = await cmd({ cmd: "ai_ops", label: "IA mueve c1", ops: [{ name: "entity.move", target: eid, args: { x: 6010, z: 6010 } }] });
    assert(r.ok, "C1: ai_ops");
    await waitText(light(page), /^IA editando$/, "C1(+): tras ai_ops", 3000);
    await waitText(light(page), /^IA conectada$/, "C1(+): pasados 4 s", 6000);
    assert((await cmd({ cmd: "stop_backend" })).ok, "C1: stop_backend");
    await waitText(light(page), /^IA · sin datos$/, "C1(-): sin backend", 12000);
    assert((await cmd({ cmd: "start_backend" })).ok, "C1: start_backend");
  } finally {
    await closeAudited(context);
  }
}

// --- C2 pausa ------------------------------------------------------------------
async function C2(browser) {
  await freshBackend();
  const eid = await addEntity("Barril c2", 6100, 6100);
  const { context, page } = await openStudio(browser);
  try {
    await activatePanel(page, "ia");
    // Negativo primero: sin optimismo
    const fake = async (route) => route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true,"paused":true}' });
    await page.route("**/api/ai/pause", fake);
    // La lectura autoritativa queda retenida: si la web copiara la respuesta del POST, se vería ya (W2-08).
    const reads = await hold(page, "**/api/coedit");
    await iaPanel(page).getByRole("button", { name: "Pausar IA" }).click();
    await reads.waitHeld("C2(-): lectura tras el POST");
    await sleep(500);
    assert(!/en pausa/.test(await light(page).innerText()), "C2(-): la luz dice «en pausa» con la respuesta falsa (Yf)");
    assert(!/en pausa/.test(await iaPanel(page).innerText()), "C2(-): la pestaña dice «en pausa» con la respuesta falsa");
    await reads.release();
    await sleep(1000);
    assert(!/en pausa/.test(await light(page).innerText()), "C2(-): «en pausa» tras la lectura autoritativa");
    await page.unroute("**/api/ai/pause", fake);

    const btn = iaPanel(page).getByRole("button", { name: "Pausar IA" });
    await btn.focus();
    const posts = countPosts(page, "/api/ai/pause");
    await page.keyboard.press("Enter");
    await waitText(light(page), /^IA en pausa$/, "C2(+): luz en pausa");
    posts.stop();
    assert(posts.n === 1 && JSON.parse(posts.bodies[0]).paused === true, "C2(+): POST de pausa: " + JSON.stringify(posts.bodies));
    await iaPanel(page).getByRole("button", { name: "Reanudar IA" }).waitFor({ state: "visible", timeout: 3000 });
    const r = await cmd({ cmd: "ai_ops", label: "IA en pausa", ops: [{ name: "entity.move", target: eid, args: { x: 6200, z: 6200 } }] });
    assert(!r.ok && r.code === "ai_paused", "C2(+): ai_ops en pausa no dio ai_paused: " + JSON.stringify(r));
    const s = await cmd({ cmd: "snapshot" });
    assert(s.doc.entities.find((e) => e.id === eid).x === 6100, "C2(+): la escena cambió en pausa");
    await page.reload();
    await login(context, page);
    await waitText(light(page), /^IA en pausa$/, "C2(+): tras recargar");
    await activatePanel(page, "ia");
    await iaPanel(page).getByRole("button", { name: "Reanudar IA" }).click();
    await waitText(light(page), /^(MCP apagado|IA conectada|IA editando|IA inactiva)$/, "C2(+): reanudada");
    const r2 = await cmd({ cmd: "ai_ops", label: "IA reanudada", ops: [{ name: "entity.move", target: eid, args: { x: 6200, z: 6200 } }] });
    assert(r2.ok, "C2(+): ai_ops tras reanudar: " + JSON.stringify(r2));
    assert((await cmd({ cmd: "stop_backend" })).ok, "C2: stop");
    await waitText(light(page), /sin datos/, "C2(-): sin backend", 12000);
    assert(await iaPanel(page).getByRole("button", { name: /IA$/ }).isDisabled(), "C2(-): el botón sigue activo sin backend");
    assert((await cmd({ cmd: "start_backend" })).ok, "C2: start");
  } finally {
    await closeAudited(context);
  }
}

async function applyButtons(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("button")).filter((b) =>
      /^Aplicar/.test((b.getAttribute("aria-label") || b.textContent || "").trim())
    ).length
  );
}

// --- C3 propuesta de aplicar ---------------------------------------------------------
async function C3(browser) {
  await freshBackend();
  await addEntity("Barril c3", 6300, 6300);
  const { context, page } = await openStudio(browser);
  const card = page.locator('[data-testid="propuesta-ia"]');
  try {
    await activatePanel(page, "ia");
    // Una propuesta de la persona no saca tarjeta
    let s = await cmd({ cmd: "snapshot" });
    assert((await cmd({ cmd: "human_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C3: human_apply_request");
    await sleep(1000);
    assert((await card.count()) === 0, "C3(-): tarjeta con una propuesta de la persona (Yj)");

    // Positivo: propuesta de la IA y aprobar
    s = await cmd({ cmd: "snapshot" });
    // Se cuenta desde antes de proponer: cero envíos y cero filas hasta el clic (W2-07).
    const posts = countPosts(page, "/api/apply");
    const opsBefore = await cmd({ cmd: "count_ops" });
    assert((await cmd({ cmd: "ai_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C3: ai_apply_request");
    await card.waitFor({ state: "visible", timeout: 5000 });
    assert((await card.innerText()).includes("revisión " + s.rev), "C3(+): la tarjeta no dice la revisión");
    assert((await applyButtons(page)) === 1, "C3(-): más de un botón empieza por «Aplicar» (Yi)");
    await sleep(1000);
    assert(posts.n === 0, "C3(-): POST /api/apply sin aprobar: " + posts.n);
    assert((await cmd({ cmd: "count_ops" })).n === opsBefore.n, "C3(-): una fila nueva sin aprobar");
    await card.getByRole("button", { name: "Aprobar y aplicar rev " + s.rev }).click();
    const deadline = Date.now() + 5000;
    while (posts.n === 0 && Date.now() < deadline) await sleep(50);
    posts.stop();
    const body = JSON.parse(posts.bodies[0] || "{}");
    assert(posts.n === 1 && body.rev === s.rev && body.hash === s.hash, "C3(+): POST /api/apply: " + JSON.stringify(posts.bodies));
    await activatePanel(page, "actividad");
    await page.locator("tr[data-op-id]").first().waitFor({ state: "visible", timeout: 5000 });
    const rowRev = await page.locator("tr[data-op-id]").first().innerText();
    assert(rowRev.includes(String(s.rev)), "C3(+): la fila no lleva la revisión aprobada: " + rowRev);

    // Negativo: la escena cambia después de la propuesta -> desactivado y 0 POST (Yg, Yh)
    await activatePanel(page, "ia");
    s = await cmd({ cmd: "snapshot" });
    assert((await cmd({ cmd: "ai_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C3: ai_apply_request 2");
    await card.waitFor({ state: "visible", timeout: 5000 });
    await addEntity("Barril c3b", 6310, 6310, "human_ops");
    await waitText(card, /La escena cambió desde la propuesta/, "C3(-): aviso de propuesta atrasada");
    const posts2 = countPosts(page, "/api/apply");
    const staleBtn = card.getByRole("button", { name: /^Aprobar y aplicar/ });
    assert(await staleBtn.isDisabled(), "C3(-): el botón de una propuesta atrasada sigue activo (Yh)");
    await staleBtn.click({ force: true }).catch(() => {});
    await sleep(500);
    posts2.stop();
    assert(posts2.n === 0, "C3(-): una propuesta atrasada mandó POST /api/apply");

    // Negativo: 409 stale_apply del backend (page.route): su código a la vista y ninguna fila nueva
    s = await cmd({ cmd: "snapshot" });
    assert((await cmd({ cmd: "ai_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C3: ai_apply_request 3");
    await waitText(card, new RegExp("revisión " + s.rev), "C3: tarjeta nueva");
    const rowsBefore = await cmd({ cmd: "count_ops" });
    const r409 = async (route) =>
      route.fulfill({ status: 409, contentType: "application/json", body: '{"ok":false,"code":"stale_apply","pointer":"/rev","msg":"cambió"}' });
    await page.route("**/api/apply", r409);
    await card.getByRole("button", { name: /^Aprobar y aplicar/ }).click();
    await waitText(card, /stale_apply/, "C3(-): código stale_apply a la vista");
    await page.unroute("**/api/apply", r409);
    const rowsAfter = await cmd({ cmd: "count_ops" });
    assert(rowsAfter.n === rowsBefore.n, "C3(-): fila nueva tras un 409");

    // Descartar -> sin tarjeta y 0 peticiones
    const any = { n: 0 };
    const onReq = (req) => {
      if (req.method() === "POST") any.n += 1;
    };
    page.on("request", onReq);
    await card.getByRole("button", { name: "Descartar" }).click();
    await sleep(300);
    page.off("request", onReq);
    assert((await card.count()) === 0 && any.n === 0, "C3(-): Descartar dejó la tarjeta o mandó peticiones");
  } finally {
    await closeAudited(context);
  }
}

const HOSTILE = '<img src=x onerror="window.__x=1">';

async function domSafe(page) {
  return page.evaluate(() => ({ imgs: document.querySelectorAll("img").length, x: typeof window.__x }));
}

// --- C4 tandas de la IA y Deshacer tanda -------------------------------------------------
async function C4(browser) {
  await freshBackend();
  const eid = await addEntity("Barril rojo", 6400, 6400, "human_ops");
  const { context, page } = await openStudio(browser);
  try {
    await activatePanel(page, "ia");
    const a = await cmd({ cmd: "ai_ops", label: "IA tanda uno", ops: [{ name: "entity.move", target: eid, args: { x: 6410, z: 6410 } }] });
    const b = await cmd({ cmd: "ai_ops", label: "IA tanda dos", ops: [{ name: "entity.move", target: eid, args: { x: 6420, z: 6420 } }, { name: "entity.set", target: eid, args: { yaw: 30 } }] });
    assert(a.ok && b.ok, "C4: ai_ops");
    const rowA = iaPanel(page).locator('[data-batch="' + a.batch + '"]');
    const rowB = iaPanel(page).locator('[data-batch="' + b.batch + '"]');
    await rowB.waitFor({ state: "visible", timeout: 5000 });
    const order = await iaPanel(page).locator("[data-batch]").evaluateAll((els) => els.map((e) => e.dataset.batch));
    assert(order.indexOf(b.batch) < order.indexOf(a.batch), "C4(+): la más nueva no va arriba: " + order);
    assert((await rowB.innerText()).includes("IA tanda dos") && /2 cambios/.test(await rowB.innerText()), "C4(+): fila de la tanda dos");
    await rowB.getByRole("button", { name: /Deshacer la tanda/ }).click();
    await waitForSnap((s) => {
      const e = s.doc.entities.find((x) => x.id === eid);
      return e.x === 6410 && e.yaw === 0;
    }, "C4(+): tanda dos deshecha");
    await waitText(rowB, /deshecha/, "C4(+): fila deshecha");
    assert((await rowB.getByRole("button").count()) === 0, "C4(+): la fila deshecha conserva su botón");
    assert((await rowA.getByRole("button", { name: /Deshacer la tanda/ }).count()) === 1, "C4(+): la tanda uno ya no está viva");

    // Negativo: retoque de la persona después -> parcial con aviso y su valor conservado (Yk)
    const c = await cmd({ cmd: "ai_ops", label: "IA gira", ops: [{ name: "entity.set", target: eid, args: { yaw: 45 } }] });
    assert(c.ok, "C4: ai_ops gira");
    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
    await activatePanel(page, "propiedades");
    await page.locator("#f-yaw").focus();
    await waitEditable(page, "#f-yaw");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("90");
    await page.keyboard.press("Enter");
    await waitForSnap((s) => s.doc.entities.find((x) => x.id === eid).yaw === 90, "C4: rumbo 90 de la persona");
    await page.locator("#f-yaw").evaluate((el) => el.blur());
    await activatePanel(page, "ia");
    const rowC = iaPanel(page).locator('[data-batch="' + c.batch + '"]');
    await rowC.getByRole("button", { name: /Deshacer la tanda/ }).click();
    const aviso = page.locator('[data-aviso="deshacer-tanda-parcial"]');
    await aviso.waitFor({ state: "visible", timeout: 5000 });
    const txt = await aviso.innerText();
    assert(txt.includes("Barril rojo") && /rumbo/.test(txt), "C4(-): el aviso no nombra la entidad y el rumbo: " + txt);
    const s = await cmd({ cmd: "snapshot" });
    assert(s.doc.entities.find((x) => x.id === eid).yaw === 90, "C4(-): se perdió el rumbo de la persona");

    // Negativo: 409 already_reverted -> tanda-no-deshecha
    const r409 = async (route) =>
      route.fulfill({ status: 409, contentType: "application/json", body: '{"ok":false,"code":"already_reverted","pointer":"/batch_id","msg":"ya"}' });
    await page.route("**/api/scene/batches/**", r409);
    await rowA.getByRole("button", { name: /Deshacer la tanda/ }).click();
    await page.locator('[data-aviso="tanda-no-deshecha"]').waitFor({ state: "visible", timeout: 5000 });
    await page.unroute("**/api/scene/batches/**", r409);

    // Texto hostil en la etiqueta (Yl)
    const h = await cmd({ cmd: "ai_ops", label: HOSTILE, ops: [{ name: "entity.move", target: eid, args: { x: 6430, z: 6430 } }] });
    const rowH = iaPanel(page).locator('[data-batch="' + h.batch + '"]');
    await rowH.waitFor({ state: "visible", timeout: 5000 });
    assert((await rowH.innerText()).includes(HOSTILE), "C4(-): la etiqueta hostil no se ve literal");
    const safe = await domSafe(page);
    assert(safe.imgs === 0 && safe.x === "undefined", "C4(-): HTML de la etiqueta insertado: " + JSON.stringify(safe));
  } finally {
    await closeAudited(context);
  }
}

// --- C5 presencia ----------------------------------------------------------------------------
async function C5(browser) {
  await freshBackend();
  const e1 = await addEntity("Barril c5", 6500, 6500, "human_ops");
  const e3 = await addEntity("Barril c5 borrable", 6520, 6520, "human_ops");
  const { context, page } = await openStudio(browser);
  const row = (id) => page.locator('[data-panel="jerarquia"] [data-entity-id="' + id + '"]');
  try {
    await row(e1).waitFor({ state: "visible", timeout: 5000 });
    const h = await cmd({ cmd: "human_ops", label: "Persona mueve", ops: [{ name: "entity.move", target: e1, args: { x: 6501, z: 6501 } }] });
    assert(h.ok, "C5: human_ops");
    await sleep(800);
    assert((await page.locator("[data-ia-reciente]").count()) === 0, "C5(-): marca con una tanda de la persona (Yn)");
    const r = await cmd({
      cmd: "ai_ops",
      label: "IA mueve y crea",
      ops: [{ name: "entity.move", target: e1, args: { x: 6510, z: 6510 } }, addOp("Barril de la IA", 6530, 6530)],
    });
    assert(r.ok && r.created.length === 1, "C5: ai_ops");
    const e2 = r.created[0];
    await row(e1).locator("[data-ia-reciente]").waitFor({ state: "visible", timeout: 5000 });
    await row(e2).locator("[data-ia-reciente]").waitFor({ state: "visible", timeout: 5000 });
    assert(/^IA · hace/.test((await row(e1).locator("[data-ia-reciente]").innerText()).trim()), "C5(+): texto de la marca");
    const d = await cmd({ cmd: "ai_ops", label: "IA borra", ops: [{ name: "entity.delete", target: e3, args: {} }] });
    assert(d.ok, "C5: ai_ops borra");
    await sleep(800);
    assert((await row(e3).count()) === 0, "C5(-): la entidad borrada deja fila");
    await sleep(10500);
    assert((await page.locator("[data-ia-reciente]").count()) === 0, "C5(+): la marca no caduca a los 10 s (Ym)");
  } finally {
    await closeAudited(context);
  }
}

// --- C6 Historial ------------------------------------------------------------------------------
async function C6(browser) {
  await freshBackend();
  const eid = await addEntity("Barril c6", 6600, 6600, "human_ops");
  const ai = await cmd({ cmd: "ai_ops", label: "IA c6", ops: [{ name: "entity.move", target: eid, args: { x: 6610, z: 6610 } }] });
  const nul = await cmd({ cmd: "ai_ops", label: null, ops: [{ name: "entity.move", target: eid, args: { x: 6620, z: 6620 } }] });
  const hos = await cmd({ cmd: "human_ops", label: HOSTILE, ops: [{ name: "entity.move", target: eid, args: { x: 6630, z: 6630 } }] });
  assert(ai.ok && nul.ok && hos.ok, "C6: tandas");
  const { context, page } = await openStudio(browser);
  const hist = () => page.locator('[data-panel="historial"]');
  try {
    // Al entrar, las tandas salen de /api/scene/changes, sin ningún evento (Yo)
    await activatePanel(page, "historial");
    const rAi = hist().locator('[data-batch="' + ai.batch + '"]');
    await rAi.waitFor({ state: "visible", timeout: 5000 });
    assert((await rAi.getAttribute("data-autor")) === "ai" && /IA/.test(await rAi.innerText()), "C6(+): autor IA");
    assert((await rAi.innerText()).includes("r" + ai.rev), "C6(+): rN");
    const rHos = hist().locator('[data-batch="' + hos.batch + '"]');
    assert((await rHos.getAttribute("data-autor")) === "human" && /Tú/.test(await rHos.innerText()), "C6(+): autor persona");
    assert((await rHos.innerText()).includes(HOSTILE), "C6(-): texto hostil no literal");
    const safe = await domSafe(page);
    assert(safe.imgs === 0 && safe.x === "undefined", "C6(-): HTML insertado: " + JSON.stringify(safe));
    assert((await hist().locator('[data-batch="' + nul.batch + '"]').innerText()).includes("Sin nombre"), "C6(-): etiqueta null");
    const order = await hist().locator("[data-batch]").evaluateAll((els) => els.map((e) => e.dataset.batch));
    assert(order.indexOf(hos.batch) < order.indexOf(ai.batch), "C6(+): la más nueva no va arriba");

    await hist().getByRole("button", { name: "IA", exact: true }).click();
    const autoresIa = await hist().locator("[data-batch]").evaluateAll((els) => els.map((e) => e.dataset.autor));
    assert(autoresIa.length > 0 && autoresIa.every((x) => x === "ai"), "C6(+): filtro IA: " + autoresIa);
    await hist().getByRole("button", { name: "Tuyas", exact: true }).click();
    const autoresTu = await hist().locator("[data-batch]").evaluateAll((els) => els.map((e) => e.dataset.autor));
    assert(autoresTu.length > 0 && autoresTu.every((x) => x === "human"), "C6(+): filtro Tuyas: " + autoresTu);
    await hist().getByRole("button", { name: "Todas", exact: true }).click();

    // Un deshacer de la persona -> su tanda atenuada
    const undoBtn = page.locator('[data-testid="barra-superior"] button', { hasText: /^Deshacer\b/ }).first();
    await undoBtn.click();
    await waitText(rHos, /deshecha/, "C6(+): tanda deshecha atenuada");

    // Recargar -> las mismas filas
    await page.reload();
    await login(context, page);
    await activatePanel(page, "historial");
    await hist().locator('[data-batch="' + ai.batch + '"]').waitFor({ state: "visible", timeout: 5000 });
    await hist().locator('[data-batch="' + hos.batch + '"]').waitFor({ state: "visible", timeout: 5000 });

    // Sin SSE: la lectura de cada 3 s trae las tandas (Yp)
    const cut = async (route) => route.abort();
    await page.route("**/api/events", cut);
    await page.reload();
    await login(context, page).catch(() => {});
    await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: 10000 });
    await activatePanel(page, "historial");
    const late = await cmd({ cmd: "ai_ops", label: "IA sin SSE", ops: [{ name: "entity.move", target: eid, args: { x: 6640, z: 6640 } }] });
    assert(late.ok, "C6: ai_ops sin SSE");
    await hist().locator('[data-batch="' + late.batch + '"]').waitFor({ state: "visible", timeout: 5000 });
    await page.unroute("**/api/events", cut);
  } finally {
    await closeAudited(context);
  }
}

// --- C7 Deshacer y Rehacer -----------------------------------------------------------------------
async function C7(browser) {
  await freshBackend();
  const { context, page } = await openStudio(browser);
  const bar = page.locator('[data-testid="barra-superior"]');
  const undoBtn = bar.locator("button", { hasText: /^Deshacer\b/ }).first();
  const redoBtn = bar.locator("button", { hasText: /^Rehacer\b/ }).first();
  async function waitDisabled(btn, want, desc) {
    const deadline = Date.now() + 7000;
    while (Date.now() < deadline) {
      if ((await btn.isDisabled()) === want) return;
      await sleep(100);
    }
    throw new Error("timeout (" + desc + ")");
  }
  try {
    await waitDisabled(undoBtn, true, "C7(+): Deshacer desactivado al empezar");
    await waitDisabled(redoBtn, true, "C7(+): Rehacer desactivado al empezar");
    assert((await undoBtn.getAttribute("title")) === "Nada que deshacer", "C7(+): title de Deshacer");
    assert((await redoBtn.getAttribute("title")) === "Nada que rehacer", "C7(+): title de Rehacer");
    // Solo la IA: la persona sigue sin nada que deshacer
    await addEntity("Barril c7 IA", 6700, 6700);
    await sleep(1500);
    assert(await undoBtn.isDisabled(), "C7(-): Deshacer activo con solo una tanda de la IA (Yq)");
    // Una edición de la persona -> Deshacer activo; deshacer -> Rehacer activo
    const h = await cmd({ cmd: "human_ops", label: "Colocar c7", ops: [addOp("Barril c7", 6710, 6710)] });
    assert(h.ok, "C7: human_ops");
    await waitDisabled(undoBtn, false, "C7(+): Deshacer activo tras la persona");
    await undoBtn.click();
    await waitDisabled(redoBtn, false, "C7(+): Rehacer activo tras deshacer");
    await waitDisabled(undoBtn, true, "C7(+): Deshacer desactivado tras deshacer la única");
    await redoBtn.click();
    await waitDisabled(undoBtn, false, "C7(+): Deshacer activo tras rehacer");
    // La última tanda de la persona revertida: la vista coincide con el backend. Revertir la saca de
    // la pila, así que Deshacer sigue activo por la de antes, y deshacer la quita de verdad.
    const h2 = await cmd({ cmd: "human_ops", label: "Colocar c7b", ops: [addOp("Barril c7b", 6720, 6720)] });
    const rv = await cmd({ cmd: "human_revert", batch: h2.batch });
    assert(rv.ok, "C7: human_revert: " + JSON.stringify(rv));
    await sleep(1000);
    await waitDisabled(undoBtn, false, "C7(-): Deshacer desactivado con una tanda viva debajo");
    await undoBtn.click();
    await waitForSnap((s) => !s.doc.entities.some((e) => e.name === "Barril c7"), "C7(-): deshacer la de antes");
    await waitDisabled(undoBtn, true, "C7(-): Deshacer activo sin nada que deshacer");
  } finally {
    await closeAudited(context);
  }
}

// --- C8 limpieza -------------------------------------------------------------------------------------
async function C8(browser) {
  await freshBackend();
  const { context, page } = await openStudio(browser);
  try {
    assert((await page.locator('[data-hueco="historial"], [data-hueco="ia"]').count()) === 0, "C8(-): siguen los huecos");
    await activatePanel(page, "ia");
    await activatePanel(page, "historial");
    await rememberSecrets(context, page);
  } finally {
    await closeAudited(context);
  }
}

// --- C9 carreras y huecos del Historial (Sol R21: W2-01 a W2-06) -----------------------------------
async function C9(browser) {
  await freshBackend();
  const eid = await addEntity("Barril c9", 6900, 6900, "human_ops");
  const first = await cmd({ cmd: "ai_ops", label: "IA c9 antes", ops: [{ name: "entity.move", target: eid, args: { x: 6901, z: 6901 } }] });
  assert(first.ok, "C9: ai_ops antes");
  const hist = (page) => page.locator('[data-panel="historial"]');
  const bar = (page) => page.locator('[data-testid="barra-superior"]');

  // W2-05 y W2-01: /api/coedit retenido al entrar; llega una tanda antes de cargar el Historial.
  let reads = null;
  let ctx = await openStudio(browser, async (context) => {
    reads = await hold(context, "**/api/coedit");
  });
  try {
    const { page } = ctx;
    await reads.waitHeld("C9: primera lectura de coedición");
    const undoBtn = bar(page).locator("button", { hasText: /^Deshacer\b/ }).first();
    const redoBtn = bar(page).locator("button", { hasText: /^Rehacer\b/ }).first();
    assert(await undoBtn.isDisabled(), "C9(-): Deshacer activo sin conocer las pilas (W2-05)");
    assert(await redoBtn.isDisabled(), "C9(-): Rehacer activo sin conocer las pilas (W2-05)");
    const mid = await cmd({ cmd: "ai_ops", label: "IA c9 durante", ops: [{ name: "entity.move", target: eid, args: { x: 6902, z: 6902 } }] });
    assert(mid.ok, "C9: ai_ops durante");
    await activatePanel(page, "historial");
    await hist(page).locator('[data-batch="' + mid.batch + '"]').waitFor({ state: "visible", timeout: 5000 });
    await reads.release();
    await hist(page).locator('[data-batch="' + first.batch + '"]').waitFor({ state: "visible", timeout: 5000 }).catch(() => {
      throw new Error("C9(-): falta la tanda de antes tras un evento aislado (W2-01)");
    });
  } finally {
    await closeAudited(ctx.context);
  }

  // W2-04: una lectura vieja que llega tarde no pisa la nueva.
  ctx = await openStudio(browser);
  try {
    const { page } = ctx;
    await waitText(light(page), /^(MCP apagado|IA conectada|IA inactiva)$/, "C9: luz inicial");
    const old = await hold(page, "**/api/coedit", true);
    await old.waitHeld("C9: lectura periódica", 8000);
    const pr = await page.evaluate(async () => {
      const r = await fetch("/api/ai/pause", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": localStorage.getItem("csrf") || "" },
        body: JSON.stringify({ paused: true }),
      });
      return r.status;
    });
    assert(pr === 200, "C9: pausa " + pr);
    await waitText(light(page), /^IA en pausa$/, "C9(+): pausa leída");
    await old.release();
    await sleep(1000);
    assert(/^IA en pausa$/.test((await light(page).innerText()).trim()), "C9(-): una lectura vieja pisó la pausa (W2-04)");
  } finally {
    await closeAudited(ctx.context);
  }
  assert((await cmd({ cmd: "stop_backend" })).ok && (await cmd({ cmd: "start_backend" })).ok, "C9: reinicio sin pausa");

  // W2-06: el éxito de aprobar N no borra la propuesta N+1 que llegó mientras.
  ctx = await openStudio(browser);
  try {
    const { page } = ctx;
    const card = page.locator('[data-testid="propuesta-ia"]');
    await activatePanel(page, "ia");
    const s = await cmd({ cmd: "snapshot" });
    assert((await cmd({ cmd: "ai_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C9: propuesta N");
    await card.waitFor({ state: "visible", timeout: 5000 });
    const ap = await hold(page, "**/api/apply", true);
    await card.getByRole("button", { name: "Aprobar y aplicar rev " + s.rev }).click();
    await ap.waitHeld("C9: aprobar N");
    assert((await cmd({ cmd: "ai_apply_request", rev: s.rev, hash: s.hash })).status === 200, "C9: propuesta N+1");
    await sleep(800);
    await ap.release();
    await sleep(1000);
    assert((await card.count()) === 1, "C9(-): el éxito de N borró la propuesta N+1 (W2-06)");
  } finally {
    await closeAudited(ctx.context);
  }

  // W2-02: ante stale_base se recupera lo que el backend todavía guarda.
  ctx = await openStudio(browser, async (context) => {
    await context.route("**/api/events", (route) => route.abort());
  }, true);
  try {
    const { page } = ctx;
    await activatePanel(page, "historial");
    await hist(page).locator('[data-batch="' + first.batch + '"]').waitFor({ state: "visible", timeout: 8000 });
    let faked = 0;
    const stale = async (route) => {
      if (faked > 0) return route.continue();
      faked += 1;
      return route.fulfill({ status: 409, contentType: "application/json", body: '{"ok":false,"code":"stale_base","pointer":"/since_rev","msg":"fuera"}' });
    };
    await page.route("**/api/scene/changes*", stale);
    const late = await cmd({ cmd: "ai_ops", label: "IA c9 tras hueco", ops: [{ name: "entity.move", target: eid, args: { x: 6903, z: 6903 } }] });
    assert(late.ok, "C9: ai_ops tras hueco");
    const deadline = Date.now() + 5000;
    while (faked === 0 && Date.now() < deadline) await sleep(50);
    assert(faked === 1, "C9: no llegó la lectura con stale_base");
    await hist(page).locator('[data-batch="' + late.batch + '"]').waitFor({ state: "visible", timeout: 8000 }).catch(() => {
      throw new Error("C9(-): tras stale_base no se recuperó la tanda disponible (W2-02)");
    });
  } finally {
    await closeAudited(ctx.context);
  }

  // W2-03: más de 200 tandas guardadas: el Historial las trae todas.
  await freshBackend();
  const big = await cmd({ cmd: "ai_ops", label: "IA c9 primera", ops: [addOp("Barril c9 primero", 6950, 6950)] });
  assert(big.ok, "C9: primera tanda");
  for (let i = 0; i < 205; i += 1) {
    const r = await cmd({ cmd: "ai_ops", label: "IA c9 n" + i, ops: [{ name: "entity.move", target: big.created[0], args: { x: 6951 + i, z: 6950 } }] });
    assert(r.ok, "C9: tanda " + i + ": " + JSON.stringify(r));
  }
  ctx = await openStudio(browser);
  try {
    const { page } = ctx;
    await activatePanel(page, "historial");
    const snap = await cmd({ cmd: "snapshot" });
    await hist(page).locator('[data-batch="b-' + snap.rev + '"]').waitFor({ state: "visible", timeout: 8000 });
    const n = await hist(page).locator("[data-batch]").count();
    assert((await hist(page).locator('[data-batch="' + big.batch + '"]').count()) === 1, "C9(-): Historial recortado: " + n + " filas, falta la primera de 206 (W2-03)");
  } finally {
    await closeAudited(ctx.context);
  }
}

// --- C10 desconectar (plan de coedición §2.3) -----------------------------------
async function C10(browser) {
  await freshBackend();
  const { context, page } = await openStudio(browser);
  try {
    await activatePanel(page, "ia");
    const posts = countPosts(page, "/api/ai/disconnect");
    await iaPanel(page).getByRole("button", { name: "Desconectar" }).click();
    await iaPanel(page).getByRole("button", { name: "Cancelar" }).click();
    await sleep(500);
    assert(posts.n === 0, "C10(-): Cancelar mandó el POST: " + posts.n);
    assert((await cmd({ cmd: "ai_call" })).status === 200, "C10(-): la IA no vale tras cancelar");
    await iaPanel(page).getByRole("button", { name: "Desconectar" }).click();
    await iaPanel(page).getByRole("button", { name: "Sí, desconectar" }).click();
    await waitText(light(page), /^IA desconectada$/, "C10(+): luz desconectada");
    posts.stop();
    assert(posts.n === 1, "C10(+): POST de desconectar: " + posts.n);
    assert((await cmd({ cmd: "ai_call" })).status === 401, "C10(+): la clave de la IA sigue valiendo");
    assert((await iaPanel(page).getByRole("button", { name: /IA$|Desconectar/ }).count()) === 0,
      "C10(+): quedan Pausar o Desconectar con la IA desconectada");
    await page.reload();
    await login(context, page);
    await waitText(light(page), /^IA desconectada$/, "C10(+): tras recargar");
  } finally {
    await closeAudited(context);
  }
}

const RUNNERS = { C1, C2, C3, C4, C5, C6, C7, C8, C9, C10 };

async function main() {
  const rows = resolveSelectedRows();
  const browser = await chromium.launch({ headless: true });
  try {
    for (const id of rows) {
      await RUNNERS[id](browser);
      console.log(id + " OK");
    }
    assert(storageLeaks.length === 0, "C8(-): un secreto en el almacenamiento de " + storageLeaks.join(", "));
    assert(externalRequests.length === 0, "C8(-): peticiones externas: " + externalRequests.join(", "));
    assert(pageErrors.length === 0, "C8(-): errores de JS: " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "C8(-): violación de CSP en consola"
    );
    const secrets = [HUMAN_KEY, ...seenCookies, ...seenCsrf];
    assert(!consoleTexts.some((t) => secrets.some((s) => s && t.includes(s))), "C8(-): un secreto en la consola");
    console.log("COEDIT E2E OK (" + rows.join(",") + ")");
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
