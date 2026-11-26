"use strict";
const { chromium } = require("playwright");
const readline = require("readline");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
const EVIL_URL = process.env.DSBX_EVIL_URL;
if (!BASE || !HUMAN_KEY || !EVIL_URL) {
  console.error("FALLO: faltan DSBX_URL, DSBX_HUMAN_KEY o DSBX_EVIL_URL");
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const rl = readline.createInterface({ input: process.stdin });
const waiters = [];
const ready = [];
rl.on("line", (line) => {
  let obj;
  try { obj = JSON.parse(line); } catch { return; }
  if (waiters.length) waiters.shift()(obj);
  else ready.push(obj);
});
function cmd(obj) {
  return new Promise((resolve) => {
    if (ready.length) {
      // No debería haber respuestas sin pedirlas; aun así, se descarta.
      ready.shift();
    }
    waiters.push(resolve);
    process.stdout.write(JSON.stringify(obj) + "\n");
  });
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const consoleTexts = [];
function track(page) {
  page.on("console", (m) => consoleTexts.push(m.text()));
}
// csrf emitidos en la corrida, para buscarlos en la consola al final (C-04); nunca se imprimen.
const seenCsrf = new Set();
async function rememberCsrf(page) {
  const v = await page.evaluate(() => localStorage.getItem("csrf"));
  if (v) seenCsrf.add(v);
}

function rowLoc(page, opId) {
  return page.locator('tr[data-op-id="' + opId + '"]');
}
async function cell(page, opId, idx) {
  return (await rowLoc(page, opId).locator("td").nth(idx).innerText()).trim();
}
function parseAgeMs(text) {
  const t = text.trim();
  if (t === "Edad desconocida") return null;
  let m = /^(\d+) s$/.exec(t);
  if (m) return parseInt(m[1], 10) * 1000;
  m = /^(\d+) min$/.exec(t);
  if (m) return parseInt(m[1], 10) * 60000;
  m = /^(\d+) h$/.exec(t);
  if (m) return parseInt(m[1], 10) * 3600000;
  return NaN;
}
async function ageOf(page, opId) {
  return parseAgeMs(await cell(page, opId, 3));
}
async function waitForAgeAtLeast(page, opId, minMs, timeoutMs) {
  const deadline = Date.now() + (timeoutMs || 10000);
  let last = null;
  while (Date.now() < deadline) {
    if ((await rowLoc(page, opId).count()) > 0) {
      last = await ageOf(page, opId);
      if (last !== null && !Number.isNaN(last) && last >= minMs) return last;
    }
    await sleep(200);
  }
  throw new Error("edad de " + opId + " no llego a " + minMs + " ms (ultima: " + last + ")");
}
async function waitRow(page, opId, timeoutMs) {
  await rowLoc(page, opId).first().waitFor({ state: "visible", timeout: timeoutMs || 10000 });
}
async function waitCellText(page, opId, idx, expected, timeoutMs) {
  const deadline = Date.now() + (timeoutMs || 10000);
  let last = "";
  while (Date.now() < deadline) {
    if ((await rowLoc(page, opId).count()) > 0) {
      last = await cell(page, opId, idx);
      if (last === expected) return last;
    }
    await sleep(200);
  }
  throw new Error("celda " + idx + " de " + opId + ": esperado '" + expected + "', ultimo '" + last + "'");
}
async function login(page, key) {
  await page.locator("#human-key").fill(key);
  await page.getByRole("button", { name: "Entrar" }).click();
}
async function waitQueue(page, timeoutMs) {
  await page.getByRole("button", { name: /^Aplicar/ }).waitFor({ state: "visible", timeout: timeoutMs || 10000 });
  await page.getByText("Conectado", { exact: true }).waitFor({ state: "visible", timeout: timeoutMs || 10000 });
}
async function waitLoginForm(page, timeoutMs) {
  await page.locator("#human-key").waitFor({ state: "visible", timeout: timeoutMs || 15000 });
}
async function waitApplyEnabled(page) {
  await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find((x) => x.textContent && x.textContent.startsWith("Aplicar"));
    return !!b && !b.disabled;
  }, null, { timeout: 10000 });
}

async function forceSnapshot(page) {
  let count = 0;
  const handler = async (route) => {
    count += 1;
    if (count === 1) {
      await route.fulfill({ status: 503, contentType: "text/plain; charset=utf-8", body: "x" });
    } else {
      await route.continue();
    }
  };
  await page.route("**/api/events", handler);
  try {
    await cmd({ cmd: "drop_sse" });
    const deadline = Date.now() + 10000;
    while (count < 2 && Date.now() < deadline) await sleep(100);
    await sleep(700);
  } finally {
    await page.unroute("**/api/events", handler);
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    track(page);

    // P1 entrada
    await page.goto(BASE + "/");
    await waitLoginForm(page);
    await login(page, "clave-mala-de-prueba");
    await page.getByText("Clave no válida", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
    let cookies = await context.cookies();
    assert(!cookies.some((c) => c.name.startsWith("dsbx_session_")), "P1: cookie tras clave mala");
    await login(page, HUMAN_KEY);
    await waitQueue(page);
    await rememberCsrf(page);
    cookies = await context.cookies();
    const sess = cookies.find((c) => c.name.startsWith("dsbx_session_"));
    assert(sess, "P1: falta cookie de sesion");
    assert(sess.httpOnly === true, "P1: cookie sin HttpOnly");
    assert(sess.sameSite === "Strict", "P1: cookie sin SameSite Strict");
    const storage = await page.evaluate(() => {
      const vals = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        vals.push(localStorage.getItem(k));
      }
      const svals = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        svals.push(sessionStorage.getItem(k));
      }
      return { csrf: localStorage.getItem("csrf"), all: vals.join("\n"), sess: svals.join("\n"), doc: document.cookie };
    });
    assert(storage.csrf && storage.csrf.length >= 10, "P1: localStorage sin csrf");
    assert(!storage.all.includes(HUMAN_KEY) && !storage.sess.includes(HUMAN_KEY) && !storage.doc.includes(HUMAN_KEY),
      "P1: la clave esta en un almacenamiento");
    assert(!storage.all.includes(sess.value) && !storage.sess.includes(sess.value) && !storage.doc.includes(sess.value),
      "P1: el valor de la cookie esta en un almacenamiento");
    console.log("P1 OK");

    // P2 pendiente que envejece
    await page.getByRole("button", { name: /^Aplicar rev / }).click();
    await waitRow(page, "op-1");
    assert((await cell(page, "op-1", 2)) === "Pendiente", "P2: op-1 no Pendiente");
    assert((await cell(page, "op-1", 4)) === "backend", "P2: origen no backend");
    await sleep(3000);
    const ageP2 = await waitForAgeAtLeast(page, "op-1", 3000, 5000);
    assert(ageP2 !== null && ageP2 >= 3000, "P2: edad < 3 s");
    assert((await cell(page, "op-1", 2)) === "Pendiente", "P2: dejo de estar Pendiente");
    console.log("P2 OK");

    // P2b reloj que retrocede (contexto propio)
    const ctx2 = await browser.newContext();
    const page2 = await ctx2.newPage();
    track(page2);
    await page2.clock.install();
    await page2.goto(BASE + "/");
    await waitLoginForm(page2);
    await login(page2, HUMAN_KEY);
    await waitQueue(page2);
    await rememberCsrf(page2);
    const beforeIds = await page2.evaluate(() =>
      Array.from(document.querySelectorAll("tr[data-op-id]")).map((x) => x.getAttribute("data-op-id")));
    await page2.getByRole("button", { name: /^Aplicar rev / }).click();
    let opK = null;
    {
      const deadline = Date.now() + 10000;
      while (Date.now() < deadline && !opK) {
        const ids = await page2.evaluate(() =>
          Array.from(document.querySelectorAll("tr[data-op-id]")).map((x) => x.getAttribute("data-op-id")));
        opK = ids.find((id) => !beforeIds.includes(id)) || null;
        if (!opK) await sleep(200);
      }
    }
    assert(opK, "P2b: sin orden K");
    await page2.clock.pauseAt((await page2.evaluate(() => Date.now())) + 500);
    await sleep(4000);
    await forceSnapshot(page2);
    const age0 = await waitForAgeAtLeast(page2, opK, 3000, 10000);
    assert(age0 >= 3000, "P2b(0): edad no corregida al alza");
    await page2.clock.runFor(3000);
    const age1 = await waitForAgeAtLeast(page2, opK, age0 + 2000, 10000);
    assert(age1 >= age0 + 2000, "P2b(1): no sumo 3 s");
    const fakeNow = await page2.evaluate(() => Date.now());
    await page2.clock.setSystemTime(fakeNow - 3600000);
    await page2.clock.runFor(2000);
    const age2 = await waitForAgeAtLeast(page2, opK, age1 + 1000, 10000);
    assert(age2 >= age1 + 1000, "P2b(2): no sumo 2 s tras retroceder");
    await forceSnapshot(page2);
    await sleep(300);
    const age3txt = await cell(page2, opK, 3);
    const age3 = parseAgeMs(age3txt);
    assert(age3 !== null && age3 >= age2, "P2b(3): la edad bajo con un snapshot");
    const opResp = await cmd({ cmd: "op_state", op_id: opK, state: "pendiente", origin: "backend" });
    assert(opResp && opResp.ok, "P2b(4): op_state fallo");
    await waitCellText(page2, opK, 3, "Edad desconocida", 10000);
    await sleep(2000);
    await page2.clock.setSystemTime(opResp.at_ms + 500);
    await page2.reload();
    await waitQueue(page2);
    await waitRow(page2, opK);
    const age5 = await waitForAgeAtLeast(page2, opK, 1000, 10000);
    assert(age5 >= 1000, "P2b(5): edad tras recargar < 1 s");
    assert((await cell(page2, opK, 3)) !== "0 s", "P2b(5): edad 0 s tras recargar");
    await ctx2.close();
    console.log("P2b OK");

    // P3 los seis estados
    const seq = [
      ["ejecutando", "backend", "Ejecutando"],
      ["aplicado", "servidor", "Aplicado"],
      ["observado", "servidor", "Observado"],
      ["parcial", "servidor", "Parcial"],
      ["fallido", "backend", "Fallido"],
    ];
    for (const [st, origin, label] of seq) {
      const r = await cmd({ cmd: "op_state", op_id: "op-1", state: st, origin });
      assert(r && r.ok, "P3: op_state " + st);
      await waitCellText(page, "op-1", 2, label, 10000);
      assert((await cell(page, "op-1", 4)) === origin, "P3: origen de " + st);
      const a = await ageOf(page, "op-1");
      assert(a !== null && a < 2000, "P3: edad no vuelve a < 2 s en " + st);
    }
    const rh = await cmd({ cmd: "op_state", op_id: "op-1", state: "hecho", origin: "backend" });
    assert(rh && rh.ok, "P3: op_state hecho");
    await waitCellText(page, "op-1", 2, "Desconocido (hecho)", 10000);
    // Un estado que coincide con una propiedad heredada de Object tampoco es uno de los seis.
    const rp = await cmd({ cmd: "op_state", op_id: "op-1", state: "toString", origin: "backend" });
    assert(rp && rp.ok, "P3: op_state toString");
    await waitCellText(page, "op-1", 2, "Desconocido (toString)", 10000);
    console.log("P3 OK");

    // P4 sin estado optimista
    const sceneInfo = await page.evaluate(async () => {
      const r = await fetch("/api/scene", { credentials: "same-origin" });
      const j = await r.json();
      return { doc_id: j.doc_id, rev: j.rev, hash: j.hash };
    });
    const countBeforeP4 = await cmd({ cmd: "count_ops" });
    const fakeData = JSON.stringify({
      doc_id: sceneInfo.doc_id, rev: sceneInfo.rev, hash: sceneInfo.hash, doc: {},
      ops: [{ op_id: "op-9999", state: "pendiente", rev: sceneInfo.rev, hash: sceneInfo.hash,
        at_ms: Date.now(), origin: "backend", age_ms: 0 }],
    });
    const fakeBody = "id: 999999999\nevent: snapshot\ndata: " + fakeData + "\nretry: 60000\n\n";
    let fakeServed = false;
    const fakeHandler = async (route) => {
      if (!fakeServed) {
        fakeServed = true;
        await route.fulfill({ status: 200, contentType: "text/event-stream; charset=utf-8", body: fakeBody });
      } else {
        await route.continue();
      }
    };
    await page.route("**/api/events", fakeHandler);
    await page.reload();
    await page.getByRole("button", { name: /^Aplicar/ }).waitFor({ state: "visible", timeout: 10000 });
    await waitRow(page, "op-9999", 10000);
    const applyRespP = page.waitForResponse(
      (r) => r.url().includes("/api/apply") && r.request().method() === "POST", { timeout: 10000 });
    await page.getByRole("button", { name: /^Aplicar rev / }).click();
    const applyResp = await applyRespP;
    assert(applyResp.status() === 200, "P4: POST no 200");
    const applyJson = await applyResp.json();
    const realOpId = applyJson.op_id;
    assert(realOpId, "P4: POST sin op_id");
    const countAfterP4 = await cmd({ cmd: "count_ops" });
    assert(countAfterP4.n === countBeforeP4.n + 1, "P4: count_ops no sube 1");
    await sleep(3000);
    assert((await rowLoc(page, realOpId).count()) === 0, "P4: fila optimista de la orden real");
    await page.unroute("**/api/events", fakeHandler);
    await page.reload();
    await waitQueue(page);
    await waitRow(page, realOpId, 10000);
    assert((await cell(page, realOpId, 2)) === "Pendiente", "P4: la orden real no Pendiente tras recargar");
    assert((await rowLoc(page, "op-9999").count()) === 0, "P4: op-9999 sigue tras recargar");
    console.log("P4 OK");

    // P5 CSRF en el navegador
    const countBeforeP5 = await cmd({ cmd: "count_ops" });
    const rowsBeforeP5 = await page.locator("tbody tr").count();
    const p5 = await page.evaluate(async () => {
      const s = await (await fetch("/api/scene", { credentials: "same-origin" })).json();
      const body = JSON.stringify({ doc_id: s.doc_id, rev: s.rev, hash: s.hash });
      const out = [];
      const r1 = await fetch("/api/apply", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body });
      out.push({ status: r1.status, json: await r1.json().catch(() => null) });
      const r2 = await fetch("/api/apply", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": "token-malo" }, body });
      out.push({ status: r2.status, json: await r2.json().catch(() => null) });
      return out;
    });
    assert(p5.length === 2 && p5.every((x) => x.status === 403 && x.json && x.json.code === "csrf_failed"),
      "P5: no fueron 403 csrf_failed");
    const countAfterP5 = await cmd({ cmd: "count_ops" });
    assert(countAfterP5.n === countBeforeP5.n, "P5: count_ops cambio");
    await sleep(500);
    assert((await page.locator("tbody tr").count()) === rowsBeforeP5, "P5: aparecio una fila");
    console.log("P5 OK");

    // P6 web ajena
    const needle = '"POST /api/apply HTTP/1.1" 403';
    const logBefore = await cmd({ cmd: "log_count", needle });
    const countBeforeP6 = await cmd({ cmd: "count_ops" });
    const evilPage = await context.newPage();
    track(evilPage);
    await evilPage.goto(EVIL_URL);
    let logNow = logBefore;
    {
      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        logNow = await cmd({ cmd: "log_count", needle });
        if (logNow.n >= logBefore.n + 2) break;
        await sleep(300);
      }
    }
    assert(logNow.n >= logBefore.n + 2, "P6: no llegaron los 2 POST 403 al log");
    const countAfterP6 = await cmd({ cmd: "count_ops" });
    assert(countAfterP6.n === countBeforeP6.n, "P6: count_ops cambio");
    const replay = await cmd({ cmd: "replay_stolen" });
    assert(replay && replay.captured === true, "P6: cookie no capturada");
    assert(replay.session_status === 200, "P6: GET session robada no 200");
    assert(JSON.stringify(replay.session_keys) === JSON.stringify(["ok"]), "P6: session_keys no [ok]");
    assert(replay.apply_status === 403 && replay.apply_code === "csrf_failed", "P6: apply robado no 403 csrf_failed");
    assert(replay.ops_delta === 0, "P6: ops_delta no 0");
    await evilPage.close();
    console.log("P6 OK");

    // P7 sesion vieja
    await page.getByText("Conectado", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
    const rRestart = await cmd({ cmd: "restart" });
    assert(rRestart && rRestart.ok, "P7: restart fallo");
    await page.getByText("Sesión caducada: vuelve a entrar", { exact: true })
      .waitFor({ state: "visible", timeout: 15000 });
    await waitLoginForm(page);
    await login(page, HUMAN_KEY);
    await waitQueue(page);
    await rememberCsrf(page);
    await waitApplyEnabled(page);
    await sleep(500);
    assert((await rowLoc(page, "op-1").count()) === 0, "P7: op-1 sigue tras reiniciar y entrar");
    console.log("P7 OK");

    // P8 nada de secretos
    const sessionText = await page.evaluate(async () => {
      const r = await fetch("/api/session", { credentials: "same-origin" });
      return { status: r.status, text: await r.text() };
    });
    assert(sessionText.status === 200 && sessionText.text.trim() === '{"ok": true}',
      "P8: cuerpo de sesion no exacto");
    const homeResp = await fetch(BASE + "/");
    assert(homeResp.status === 200, "P8: / no 200");
    const homeText = await homeResp.text();
    assert(!homeText.includes(HUMAN_KEY), "P8: clave en el HTML");
    const assetPaths = Array.from(homeText.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)).map((m) => m[1]);
    assert(assetPaths.length >= 1, "P8: HTML sin assets");
    for (const p of assetPaths) {
      const ar = await fetch(BASE + p);
      assert(ar.status === 200, "P8: asset no 200 " + p);
      const at = await ar.text();
      assert(!at.includes(HUMAN_KEY), "P8: clave en un asset");
    }
    assert(!consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "P8: mensaje de consola de CSP");
    console.log("P8 OK");

    async function heldSessionRoute(pg) {
      let captureResolve;
      let releaseResolve;
      const captured = new Promise((r) => { captureResolve = r; });
      const gate = new Promise((r) => { releaseResolve = r; });
      const handler = async (route) => {
        const req = route.request();
        if (req.method() === "GET" && req.url().includes("/api/session")) {
          captureResolve();
          await gate;
          await route.fulfill({ status: 401, contentType: "application/json; charset=utf-8",
            body: JSON.stringify({ ok: false, code: "unauthorized", pointer: "", msg: "Credencial no válida" }) });
        } else {
          await route.continue();
        }
      };
      await pg.route("**/api/session", handler);
      return { handler, captured, release: () => releaseResolve() };
    }
    async function assertBStillWorks(pgB) {
      await pgB.getByRole("button", { name: /^Aplicar/ }).waitFor({ state: "visible", timeout: 10000 });
      const respP = pgB.waitForResponse(
        (r) => r.url().includes("/api/apply") && r.request().method() === "POST", { timeout: 10000 });
      await pgB.getByRole("button", { name: /^Aplicar rev / }).click();
      const resp = await respP;
      assert(resp.status() === 200, "P9: Aplicar de B no 200");
      const j = await resp.json();
      assert(j && j.op_id, "P9: Aplicar de B sin op_id");
      await waitRow(pgB, j.op_id, 10000);
    }

    // P9a dos pestañas, recuperacion
    {
      const pageA = await context.newPage();
      const pageB = await context.newPage();
      track(pageA); track(pageB);
      await pageA.goto(BASE + "/");
      await pageB.goto(BASE + "/");
      await waitQueue(pageA); await waitQueue(pageB);
      const hold = await heldSessionRoute(pageA);
      const rr = await cmd({ cmd: "restart" });
      assert(rr && rr.ok, "P9a: restart fallo");
      await Promise.race([hold.captured, sleep(15000).then(() => { throw new Error("P9a: no se capturo GET de A"); })]);
      await waitLoginForm(pageB, 15000);
      await login(pageB, HUMAN_KEY);
      await waitQueue(pageB); await rememberCsrf(pageB); await waitApplyEnabled(pageB);
      hold.release();
      await waitLoginForm(pageA, 15000);
      await assertBStillWorks(pageB);
      await pageA.unroute("**/api/session", hold.handler);
      await pageA.close(); await pageB.close();
    }
    console.log("P9a OK");

    // P9b dos pestañas, carga inicial
    {
      const pageA = await context.newPage();
      const pageB = await context.newPage();
      track(pageA); track(pageB);
      await pageA.goto(BASE + "/");
      await pageB.goto(BASE + "/");
      await waitQueue(pageA); await waitQueue(pageB);
      const hold = await heldSessionRoute(pageA);
      await pageA.reload();
      await Promise.race([hold.captured, sleep(15000).then(() => { throw new Error("P9b: no se capturo GET inicial de A"); })]);
      const rr = await cmd({ cmd: "restart" });
      assert(rr && rr.ok, "P9b: restart fallo");
      await waitLoginForm(pageB, 15000);
      await login(pageB, HUMAN_KEY);
      await waitQueue(pageB); await rememberCsrf(pageB); await waitApplyEnabled(pageB);
      hold.release();
      await waitLoginForm(pageA, 15000);
      await assertBStillWorks(pageB);
      await pageA.unroute("**/api/session", hold.handler);
      await pageA.close(); await pageB.close();
    }
    console.log("P9b OK");

    // P10 web con mod falso: Aplicar lleva la fila nueva a Observado (servidor)
    {
      const page10 = await context.newPage();
      track(page10);
      await page10.goto(BASE + "/");
      await page10.waitForFunction(() => !!document.querySelector("#human-key") ||
        Array.from(document.querySelectorAll("button")).some(
          (b) => b.textContent && b.textContent.startsWith("Aplicar")),
        null, { timeout: 15000 });
      if ((await page10.locator("#human-key").count()) > 0 &&
          await page10.locator("#human-key").isVisible()) {
        await login(page10, HUMAN_KEY);
      }
      await waitQueue(page10);
      await rememberCsrf(page10);
      await waitApplyEnabled(page10);
      const started = await cmd({ cmd: "start_fake_mod" });
      assert(started && started.ok, "P10: el mod falso no reconcilio");
      const respP10 = page10.waitForResponse(
        (r) => r.url().includes("/api/apply") && r.request().method() === "POST", { timeout: 10000 });
      await page10.getByRole("button", { name: /^Aplicar rev / }).click();
      const resp10 = await respP10;
      assert(resp10.status() === 200, "P10: Aplicar no 200");
      const j10 = await resp10.json();
      assert(j10 && j10.op_id, "P10: Aplicar sin op_id");
      await waitRow(page10, j10.op_id, 10000);
      await waitCellText(page10, j10.op_id, 2, "Observado", 15000);
      assert((await cell(page10, j10.op_id, 4)) === "servidor", "P10: origen no servidor");
      console.log("P10 OK");

      // P11 web sin mod: la fila pasa de Pendiente a Fallido con TTL corto
      const stopped = await cmd({ cmd: "stop_fake_mod" });
      assert(stopped && stopped.ok, "P11: stop_fake_mod fallo");
      const ttlSet = await cmd({ cmd: "set_bridge_ttl", ms: 1200 });
      assert(ttlSet && ttlSet.ok, "P11: set_bridge_ttl fallo");
      const respP11 = page10.waitForResponse(
        (r) => r.url().includes("/api/apply") && r.request().method() === "POST", { timeout: 10000 });
      await page10.getByRole("button", { name: /^Aplicar rev / }).click();
      const resp11 = await respP11;
      assert(resp11.status() === 200, "P11: Aplicar no 200");
      const j11 = await resp11.json();
      assert(j11 && j11.op_id && j11.op_id !== j10.op_id, "P11: Aplicar sin op_id nuevo");
      await waitRow(page10, j11.op_id, 10000);
      await waitCellText(page10, j11.op_id, 2, "Fallido", 15000);
      assert((await cell(page10, j11.op_id, 2)) !== "Aplicado", "P11: llego a Aplicado sin mod");
      assert((await cell(page10, j11.op_id, 4)) === "backend", "P11: origen no backend");
      console.log("P11 OK");
      await page10.close();
    }

    // P8 sobre la consola de TODA la corrida, P9 incluido: ni la clave ni ningun csrf emitido (C-04).
    assert(seenCsrf.size >= 5, "P8: no se registraron los csrf de las entradas");
    const secretos = [HUMAN_KEY, ...seenCsrf];
    assert(!consoleTexts.some((t) => secretos.some((s) => s && t.includes(s))),
      "P8: un secreto aparece en la consola del navegador");
    console.log("P8 consola sin secretos OK");

    await context.close();
    console.log("E2E OK");
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
