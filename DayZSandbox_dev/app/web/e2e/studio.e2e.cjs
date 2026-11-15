"use strict";
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { chromium } = require("playwright");

const BASE = process.env.DSBX_URL;
const HUMAN_KEY = process.env.DSBX_HUMAN_KEY;
if (!BASE || !HUMAN_KEY) {
  console.error("FALLO: faltan DSBX_URL o DSBX_HUMAN_KEY");
  process.exit(2);
}

const ALL_ROWS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12"];
function resolveSelectedRows() {
  const raw = process.env.DSBX_ONLY;
  if (!raw || !raw.trim()) return ALL_ROWS.slice();
  const parts = raw
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  for (const p of parts) {
    if (!ALL_ROWS.includes(p)) {
      throw new Error("DSBX_ONLY contiene una fila desconocida: " + p);
    }
  }
  return parts;
}

const SCHEMA_PATH = path.resolve(__dirname, "../../../schemas/scene.schema.json");
const FIXTURE_SCENE_PATH = path.resolve(__dirname, "../../../fixtures/escena-basica-cine.json");
const CATALOG_PATH = path.resolve(__dirname, "../../../fixtures/catalog-m1.json");
const DEFAULT_AMBIENTE = JSON.parse(fs.readFileSync(FIXTURE_SCENE_PATH, "utf8")).ambiente;

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

// POST que cambian la escena o el juego. Los negativos de «no actúa» cuentan solo estos:
// el préstamo de un campo enfocado (/api/lease…) y el guardado del perfil (/api/profile)
// son efectos del foco y del layout, no de la acción que se prueba (arbitraje del orquestador).
const EFFECT_POST_PATHS = ["/api/scene/ops", "/api/scene/undo", "/api/scene/redo", "/api/apply", "/api/reset"];
function isEffectPost(req) {
  if (req.method() !== "POST") return false;
  const p = new URL(req.url()).pathname;
  return EFFECT_POST_PATHS.includes(p) || p.startsWith("/api/scene/batches/");
}

// Antes de escribir el perfil a mano hay que dejar quieta la página: un guardado pendiente
// (agrupado a 500 ms) o en vuelo de la página anterior pisaría lo escrito antes de recargar.
async function quietPageForProfileWrite(page) {
  await page.goto("about:blank");
  await sleep(800);
}

const consoleTexts = [];
const pageErrors = [];
const externalRequests = [];
const seenCsrf = new Set();
const seenCookies = new Set();

function track(page) {
  page.on("console", (m) => {
    consoleTexts.push(m.text());
  });
  page.on("pageerror", (err) => {
    pageErrors.push(err && err.message ? err.message : String(err));
  });
  page.on("request", (req) => {
    const u = req.url();
    if (u === "about:blank") return;
    if (!u.startsWith(BASE + "/") && u !== BASE) {
      externalRequests.push(u);
    }
  });
}

async function rememberSecrets(context, page) {
  const csrf = await page.evaluate(() => localStorage.getItem("csrf")).catch(() => null);
  if (csrf) seenCsrf.add(csrf);
  const cookies = await context.cookies().catch(() => []);
  for (const c of cookies) {
    if (c.name.startsWith("dsbx_session_") && c.value) {
      seenCookies.add(c.value);
    }
  }
}

async function resetBackendState() {
  const st = await cmd({ cmd: "start_backend" });
  assert(st && st.ok, "start_backend fallo en reset");
  const co = await cmd({ cmd: "count_ops" });
  const ls = await cmd({ cmd: "leases" });
  if ((co && co.n > 0) || (ls && ls.leases && ls.leases.length > 0)) {
    const sp = await cmd({ cmd: "stop_backend" });
    assert(sp && sp.ok, "stop_backend fallo en reset");
    const st2 = await cmd({ cmd: "start_backend" });
    assert(st2 && st2.ok, "start_backend (reinicio) fallo en reset");
  }
  const pw = await cmd({ cmd: "profile_write", text: null });
  assert(pw && pw.ok, "profile_write(null) fallo en reset");
  const snap = await cmd({ cmd: "snapshot" });
  assert(snap && snap.ok, "snapshot fallo en reset");
  const ops = [];
  for (const e of snap.doc.entities || []) {
    ops.push({ name: "entity.delete", target: e.id, args: {} });
  }
  for (const c of snap.doc.cameras || []) {
    ops.push({ name: "camera.delete", target: c.id, args: {} });
  }
  const curAmb = snap.doc.ambiente || {};
  const ambDiff = {};
  for (const k of Object.keys(DEFAULT_AMBIENTE)) {
    if (curAmb[k] !== DEFAULT_AMBIENTE[k]) ambDiff[k] = DEFAULT_AMBIENTE[k];
  }
  if (Object.keys(ambDiff).length > 0) {
    ops.push({ name: "ambient.set", args: ambDiff });
  }
  if (ops.length > 0) {
    const r = await cmd({ cmd: "ai_ops", label: "Limpiar escena", ops });
    assert(r && r.ok, "resetBackendState ai_ops fallo: " + JSON.stringify(r));
  }
}

async function loginIfNeeded(context, page, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const hasBar =
      (await page.locator('[data-testid="barra-superior"]').count()) > 0 &&
      (await page.locator('[data-testid="barra-superior"]').first().isVisible().catch(() => false));
    const isConnected =
      hasBar && (await page.getByText("Conectado", { exact: true }).isVisible().catch(() => false));
    if (isConnected) break;
    const hasLogin =
      (await page.locator("#human-key").count()) > 0 &&
      (await page.locator("#human-key").first().isVisible().catch(() => false));
    if (hasLogin) {
      await page.locator("#human-key").fill(HUMAN_KEY);
      await page.getByRole("button", { name: "Entrar" }).click();
      break;
    }
    await sleep(100);
  }
  await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: timeoutMs });
  await page.locator('[data-testid="accion-principal"] button').first().waitFor({ state: "visible", timeout: timeoutMs });
  await page.getByText("Conectado", { exact: true }).waitFor({ state: "visible", timeout: timeoutMs });
  await rememberSecrets(context, page);
}

async function openStudio(browser, opts = {}) {
  const context = await browser.newContext({
    viewport: opts.viewport || { width: 1280, height: 720 },
    colorScheme: opts.colorScheme || "dark",
  });
  const page = await context.newPage();
  track(page);
  if (opts.beforeGoto) {
    await opts.beforeGoto(page, context);
  }
  await page.goto(BASE + "/");
  await loginIfNeeded(context, page, opts.timeoutMs || 15000);
  return { context, page };
}

const PANEL_TITLE_RE = {
  jerarquia: /^Jerarqu[ií]a\b/i,
  mapa: /^Mapa\b/i,
  propiedades: /^Propiedades\b/i,
  anadir: /^A[ñn]adir\b/i,
  actividad: /^Actividad\b/i,
  validacion: /^Validaci[oó]n\b/i,
  historial: /^Historial\b/i,
  ia: /^IA\b/i,
  camaras: /^C[áa]maras\b/i,
  tomas: /^Tomas\b/i,
  preparacion: /^Preparaci[oó]n\b/i,
  "vista-previa": /^Vista previa/i,
};

function tabLocator(page, panelId) {
  const byAttr = page.locator('.dv-tab[data-tab-panel-id="' + panelId + '"]');
  return byAttr;
}

async function findTab(page, panelId) {
  const byAttr = tabLocator(page, panelId);
  if ((await byAttr.count()) > 0) return byAttr.first();
  const re = PANEL_TITLE_RE[panelId] || new RegExp("^" + panelId + "\\b", "i");
  return page.locator(".dv-tab", { hasText: re }).first();
}

async function activatePanel(page, panelId) {
  const panel = page.locator('[data-panel="' + panelId + '"]');
  if ((await panel.count()) > 0 && (await panel.first().isVisible().catch(() => false))) {
    return panel.first();
  }
  const tab = await findTab(page, panelId);
  await tab.click();
  await panel.first().waitFor({ state: "visible", timeout: 5000 });
  return panel.first();
}

async function readDockDisposition(page) {
  return page.evaluate(() => {
    const groups = Array.from(document.querySelectorAll(".dv-groupview")).filter(
      (g) => g.getClientRects().length > 0 && g.getBoundingClientRect().width > 0
    );
    const items = groups.map((g) => {
      const r = g.getBoundingClientRect();
      const tabs = Array.from(g.querySelectorAll(".dv-tab")).map(
        (t) => t.dataset.tabPanelId || (t.getAttribute("aria-label") || t.textContent || "").trim()
      );
      const actEl = g.querySelector('.dv-tab[aria-selected="true"], .dv-active-tab');
      const active = actEl
        ? actEl.dataset.tabPanelId || (actEl.getAttribute("aria-label") || actEl.textContent || "").trim()
        : null;
      return {
        topBucket: Math.round(r.top / 40),
        leftBucket: Math.round(r.left / 40),
        rect: {
          left: Math.round(r.left),
          top: Math.round(r.top),
          width: Math.round(r.width),
          height: Math.round(r.height),
        },
        tabs,
        active,
      };
    });
    items.sort((a, b) => (a.topBucket - b.topBucket) || (a.leftBucket - b.leftBucket));
    return items;
  });
}

async function switchMode(page, modeName) {
  const re = modeName === "rodaje" ? /^Rodaje\b/ : /^Escena\b/;
  const btn = page.locator('[data-testid="barra-superior"] [role="group"] button', { hasText: re }).first();
  await btn.click();
  await page.waitForFunction(
    (expectedReSrc) => {
      const rx = new RegExp(expectedReSrc);
      const bs = Array.from(
        document.querySelectorAll('[data-testid="barra-superior"] [role="group"] button')
      );
      const b = bs.find((el) => rx.test((el.textContent || "").trim()));
      return !!b && b.getAttribute("aria-pressed") === "true";
    },
    re.source,
    { timeout: 5000 }
  );
}

async function checkSlotExposed(page) {
  return page.evaluate(() => {
    const slot = document.querySelector('[data-testid="accion-principal"]');
    if (!slot) return { ok: false, reason: "falta [data-testid=accion-principal]" };
    if (slot.closest("[data-panel], .dv-dockview, .dv-groupview")) {
      return { ok: false, reason: "la ranura esta dentro de Dockview o de un panel" };
    }
    const bar = document.querySelector('[data-testid="barra-superior"]');
    if (!bar || !bar.contains(slot)) {
      return { ok: false, reason: "la ranura no esta dentro de barra-superior" };
    }
    const btn = slot.querySelector("button");
    if (!btn) return { ok: false, reason: "sin boton dentro de accion-principal" };
    const r = btn.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return { ok: false, reason: "boton sin dimensiones" };
    if (r.left < -0.5 || r.top < -0.5 || r.right > window.innerWidth + 0.5 || r.bottom > window.innerHeight + 0.5) {
      return { ok: false, reason: "boton fuera de la ventana: " + JSON.stringify(r) };
    }
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const hit = document.elementFromPoint(cx, cy);
    const exposed = !!hit && (hit === btn || btn.contains(hit));
    return {
      ok: exposed,
      reason: exposed ? "ok" : "tapado por " + (hit ? hit.tagName + "#" + hit.id + "." + hit.className : "null"),
    };
  });
}

async function assertSlotExposed(page, ctxLabel) {
  const res = await checkSlotExposed(page);
  assert(res.ok, ctxLabel + ": ranura principal no expuesta (" + res.reason + ")");
}

async function assertNoPageScroll(page, ctxLabel) {
  const sc = await page.evaluate(() => {
    const el = document.scrollingElement || document.documentElement;
    return { sh: el.scrollHeight, ch: el.clientHeight };
  });
  assert(
    sc.sh === sc.ch,
    ctxLabel + ": la pagina se desplaza (scrollHeight=" + sc.sh + ", clientHeight=" + sc.ch + ")"
  );
}

async function waitEditable(page, selector, timeoutMs = 5000) {
  await page.waitForFunction(
    (sel) => {
      const el = document.querySelector(sel);
      return !!el && !el.readOnly && !el.disabled;
    },
    selector,
    { timeout: timeoutMs }
  );
}

async function waitForSnap(predicate, desc, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await cmd({ cmd: "snapshot" });
    if (last && last.ok && predicate(last)) return last;
    await sleep(100);
  }
  throw new Error("timeout esperando snapshot (" + desc + "): rev=" + (last && last.rev));
}

async function openToolsMenu(page) {
  const btn = page.locator('[data-testid="barra-superior"] button', { hasText: /^Herramientas\b/ }).first();
  await btn.click();
  await sleep(120);
  return btn;
}

async function clickToolsItem(page, textRe) {
  await openToolsMenu(page);
  let item = page.locator('button, [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]', {
    hasText: textRe,
  });
  if ((await item.count()) === 0 || !(await item.first().isVisible().catch(() => false))) {
    const sub = page.locator('button, [role="menuitem"]', { hasText: /^Layouts\b/i });
    if ((await sub.count()) > 0 && (await sub.first().isVisible().catch(() => false))) {
      await sub.first().click();
      await sleep(100);
    }
    item = page.locator('button, [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]', {
      hasText: textRe,
    });
  }
  await item.first().waitFor({ state: "visible", timeout: 5000 });
  await item.first().click();
}

// ============================================================================
// S1: Chasis y huecos
// ============================================================================
async function runS1(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser, { viewport: { width: 1280, height: 720 } });
  try {
    // Negativo: 5 s quieto sin tocar nada -> 0 peticiones a /api/scene/ops, /api/apply ni /api/lease
    const forbiddenIdle = [];
    const onReq = (req) => {
      const u = new URL(req.url());
      if (
        u.pathname === "/api/scene/ops" ||
        u.pathname === "/api/apply" ||
        u.pathname === "/api/lease" ||
        u.pathname.startsWith("/api/lease/")
      ) {
        forbiddenIdle.push(req.method() + " " + u.pathname);
      }
    };
    page.on("request", onReq);
    await sleep(5000);
    page.off("request", onReq);
    assert(
      forbiddenIdle.length === 0,
      "S1(-): peticiones en 5 s en reposo: " + forbiddenIdle.join(", ")
    );

    // Positivo: como mucho una accion principal (exactamente un boton que empieza por Aplicar)
    const applyBtns = await page.evaluate(() => {
      const bs = Array.from(document.querySelectorAll("button"));
      return bs
        .map((b) => (b.getAttribute("aria-label") || b.textContent || "").trim())
        .filter((t) => t.startsWith("Aplicar"));
    });
    assert(
      applyBtns.length === 1 && /^Aplicar rev \d+/.test(applyBtns[0]),
      "S1(+): botones Aplicar inesperados: " + JSON.stringify(applyBtns)
    );
    await assertSlotExposed(page, "S1(+) inicial");

    // Positivo: barra superior en una fila de 44 px
    const barMetrics = await page.evaluate(() => {
      const bar = document.querySelector('[data-testid="barra-superior"]');
      if (!bar) return null;
      const tr = bar.getBoundingClientRect();
      const kids = Array.from(bar.children).filter((e) => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden";
      });
      const rs = kids.map((k) => k.getBoundingClientRect());
      const mids = rs.map((r) => r.top + r.height / 2);
      const midSpread = mids.length ? Math.max(...mids) - Math.min(...mids) : 0;
      const inside = rs.every((r) => r.top >= tr.top - 1 && r.bottom <= tr.bottom + 1);
      return {
        height: Math.round(tr.height),
        fits: bar.scrollWidth <= bar.clientWidth + 1,
        oneRow: midSpread <= 4 && inside,
        midSpread,
      };
    });
    assert(barMetrics && barMetrics.height === 44, "S1(+): alto barra superior != 44: " + JSON.stringify(barMetrics));
    assert(barMetrics.fits && barMetrics.oneRow, "S1(+): barra superior partida o desbordada: " + JSON.stringify(barMetrics));

    // Positivo: layout de fabrica de Escena (§4.3)
    const dispEscena = await readDockDisposition(page);
    const tabsEscena = dispEscena.map((g) => g.tabs);
    assert(
      JSON.stringify(tabsEscena) ===
        JSON.stringify([
          ["jerarquia"],
          ["mapa"],
          ["propiedades", "anadir"],
          ["actividad", "validacion", "historial", "ia"],
        ]),
      "S1(+): grupos de fabrica en Escena distintos de §4.3: " + JSON.stringify(tabsEscena)
    );
    assert(dispEscena[2].active === "propiedades", "S1(+): propiedades no activa en Escena");
    assert(dispEscena[3].active === "actividad", "S1(+): actividad no activa en Escena");

    // Comprobar todos los paneles y huecos de Escena + 0 controles activos en huecos (mata Xt)
    const HUECOS_TEXT = {
      mapa: [
        "El mapa llega con S-mapa.",
        "Mientras tanto, coloca con Intro desde Añadir y escribe X y Z en Propiedades.",
      ],
      historial: [
        "El historial llega en la parte 2.",
        "Deshacer y Rehacer ya funcionan desde la barra de arriba.",
      ],
      ia: ["La pestaña de la IA llega en la parte 2."],
      camaras: [
        "Llega con F4 y F5.",
        "Aquí irán las cámaras, las tomas, la preparación y la vista previa del mapa.",
      ],
      tomas: [
        "Llega con F4 y F5.",
        "Aquí irán las cámaras, las tomas, la preparación y la vista previa del mapa.",
      ],
      preparacion: [
        "Llega con F4 y F5.",
        "Aquí irán las cámaras, las tomas, la preparación y la vista previa del mapa.",
      ],
      "vista-previa": [
        "Llega con F4 y F5.",
        "Aquí irán las cámaras, las tomas, la preparación y la vista previa del mapa.",
      ],
    };

    async function verifyHueco(id) {
      await activatePanel(page, id);
      const h = page.locator('[data-hueco="' + id + '"]');
      await h.first().waitFor({ state: "visible", timeout: 5000 });
      const txt = (await h.first().innerText()).replace(/\s+/g, " ").trim();
      for (const piece of HUECOS_TEXT[id]) {
        assert(txt.includes(piece), "S1(+): hueco " + id + " sin texto '" + piece + "': '" + txt + "'");
      }
      const activeControls = await h.first().evaluate((root) => {
        const sel = [
          "button:not([disabled]):not([aria-disabled='true'])",
          "input:not([disabled]):not([aria-disabled='true'])",
          "select:not([disabled]):not([aria-disabled='true'])",
          "textarea:not([disabled]):not([aria-disabled='true'])",
          "a[href]",
          "[contenteditable]:not([contenteditable='false'])",
          "[role='button']:not([aria-disabled='true'])",
          "[tabindex]:not([tabindex='-1'])",
        ].join(", ");
        return Array.from(root.querySelectorAll(sel)).map((e) => e.tagName + ":" + (e.textContent || "").trim());
      });
      assert(
        activeControls.length === 0,
        "S1(-): hueco " + id + " tiene controles activos: " + JSON.stringify(activeControls)
      );
    }

    for (const pId of ["jerarquia", "mapa", "propiedades", "anadir", "actividad", "validacion", "historial", "ia"]) {
      await activatePanel(page, pId);
      if (HUECOS_TEXT[pId]) await verifyHueco(pId);
    }
    await activatePanel(page, "propiedades");
    await activatePanel(page, "actividad");

    // Positivo: layout de fabrica de Rodaje (§4.3) y sus huecos
    await switchMode(page, "rodaje");
    const dispRodaje = await readDockDisposition(page);
    const tabsRodaje = dispRodaje.map((g) => g.tabs);
    assert(
      JSON.stringify(tabsRodaje) ===
        JSON.stringify([
          ["camaras", "tomas"],
          ["mapa"],
          ["preparacion", "propiedades"],
          ["actividad", "vista-previa"],
        ]),
      "S1(+): grupos de fabrica en Rodaje distintos de §4.3: " + JSON.stringify(tabsRodaje)
    );
    assert(dispRodaje[3].active === "actividad", "S1(+): actividad no activa en Rodaje");

    for (const pId of ["camaras", "tomas", "mapa", "preparacion", "propiedades", "actividad", "vista-previa"]) {
      await activatePanel(page, pId);
      if (HUECOS_TEXT[pId]) await verifyHueco(pId);
    }
    await switchMode(page, "escena");

    // Positivo: las tres luces con nombre a 1280, 1366 y 1600 px
    for (const w of [1280, 1366, 1600]) {
      await page.setViewportSize({ width: w, height: 720 });
      await sleep(200);
      await page.getByText("Conectado", { exact: true }).waitFor({ state: "visible", timeout: 5000 });
      const statusCheck = await page.evaluate(() => {
        const bar = document.querySelector('[data-testid="barra-estado"]');
        if (!bar) return { ok: false, reason: "falta barra-estado" };
        const br = bar.getBoundingClientRect();
        if (br.left < -0.5 || br.right > window.innerWidth + 0.5 || br.bottom > window.innerHeight + 0.5) {
          return { ok: false, reason: "barra-estado fuera de ventana" };
        }
        const fullText = (bar.innerText || "").replace(/\s+/g, " ").trim();
        const hasBackend = /\bBackend\b/.test(fullText) && /\bConectado\b/.test(fullText) && /\bhace \d+\s*(s|min|h)\b/.test(fullText);
        const hasSrv = /\bServidor\b/.test(fullText) && /\bSin datos\b/.test(fullText);
        const hasCli = /\bTu juego\b/.test(fullText) && /\bSin datos\b/.test(fullText);
        const hasCat = /Cat[áa]logo:\s*fixture/.test(fullText);
        const hasVal = /Escena sin errores/.test(fullText);
        const bridgeTitles = Array.from(bar.querySelectorAll("[title]")).filter((el) =>
          /Llega con el bridge/i.test(el.getAttribute("title") || "")
        ).length;
        const kidsInside = Array.from(bar.querySelectorAll("*")).every((el) => {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) return true;
          return r.left >= -0.5 && r.right <= window.innerWidth + 0.5 && r.bottom <= window.innerHeight + 0.5;
        });
        return {
          ok: hasBackend && hasSrv && hasCli && hasCat && hasVal && bridgeTitles >= 2 && kidsInside,
          fullText,
          bridgeTitles,
          kidsInside,
        };
      });
      assert(
        statusCheck.ok,
        "S1(+): barra de estado incorrecta a " + w + " px: " + JSON.stringify(statusCheck)
      );
    }
    console.log("S1 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S2: Perfil (D3, CU-31)
// ============================================================================
async function dragTabToGroup(page, srcPanelId, dstPanelId) {
  const srcTab = await findTab(page, srcPanelId);
  const dstTab = await findTab(page, dstPanelId);
  const dstBox = await dstTab.boundingBox();
  assert(dstBox, "S2: sin boundingBox en pestaña destino " + dstPanelId);
  await srcTab.dragTo(dstTab, {
    targetPosition: { x: Math.max(4, dstBox.width - 6), y: Math.round(dstBox.height / 2) },
  });
  await sleep(150);
  let disp = await readDockDisposition(page);
  let together = disp.some((g) => g.tabs.includes(srcPanelId) && g.tabs.includes(dstPanelId));
  if (!together) {
    const dstVoid = page
      .locator(".dv-groupview")
      .filter({ has: dstTab })
      .locator(".dv-void-container")
      .first();
    if ((await dstVoid.count()) > 0 && (await dstVoid.isVisible().catch(() => false))) {
      await srcTab.dragTo(dstVoid);
      await sleep(150);
      disp = await readDockDisposition(page);
      together = disp.some((g) => g.tabs.includes(srcPanelId) && g.tabs.includes(dstPanelId));
    }
  }
  if (!together) {
    const dstContent = page
      .locator(".dv-groupview")
      .filter({ has: dstTab })
      .locator(".dv-content-container")
      .first();
    await srcTab.dragTo(dstContent);
    await sleep(150);
  }
}

async function runS2(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    const factoryDisp = (await readDockDisposition(page)).map((g) => g.tabs);

    // Positivo 1: Arrastrar con el raton la pestaña validacion al grupo de jerarquia -> POST /api/profile 200
    const postProfileP = page.waitForResponse(
      (r) => r.url().endsWith("/api/profile") && r.request().method() === "POST",
      { timeout: 10000 }
    );
    await dragTabToGroup(page, "validacion", "jerarquia");
    const postResp = await postProfileP;
    assert(postResp.status() === 200, "S2(+): POST /api/profile no dio 200: " + postResp.status());

    const movedDisp = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(movedDisp) !== JSON.stringify(factoryDisp) &&
        movedDisp.some((tabs) => tabs.includes("jerarquia") && tabs.includes("validacion")),
      "S2(+): el arrastre no movio validacion junto a jerarquia: " + JSON.stringify(movedDisp)
    );

    const savedAfterDrag = await cmd({ cmd: "profile_read" });
    assert(savedAfterDrag && savedAfterDrag.text, "S2(+): profile_read vacio tras arrastrar");
    const parsedSaved = JSON.parse(savedAfterDrag.text);
    assert(parsedSaved.v === 1 && parsedSaved.layouts && parsedSaved.layouts.escena, "S2(+): layouts.escena vacio");

    // Recargar -> misma disposicion (grupos y paneles en orden)
    await page.reload();
    await loginIfNeeded(context, page);
    const reloadedDisp = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(reloadedDisp) === JSON.stringify(movedDisp),
      "S2(+): disposicion tras recargar distinta: " + JSON.stringify(reloadedDisp) + " vs " + JSON.stringify(movedDisp)
    );

    // Tambien tras borrar sessionStorage y todo localStorage salvo csrf (mata Xg)
    const storageCheck = await page.evaluate(() => {
      const extraLocal = [];
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k !== "csrf") {
          extraLocal.push(k);
          localStorage.removeItem(k);
        }
      }
      const sessCount = sessionStorage.length;
      sessionStorage.clear();
      return { extraLocal, sessCount };
    });
    assert(
      storageCheck.extraLocal.length === 0 && storageCheck.sessCount === 0,
      "S2(+): datos ajenos a csrf en web storage: " + JSON.stringify(storageCheck)
    );
    await page.reload();
    await loginIfNeeded(context, page);
    const afterStorageClearDisp = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(afterStorageClearDisp) === JSON.stringify(movedDisp),
      "S2(+): se perdio el layout tras limpiar localStorage/sessionStorage (Xg): " +
        JSON.stringify(afterStorageClearDisp)
    );

    // Escena -> Rodaje -> Escena: cada modo con su layout y el mismo hash en snapshot (CU-31)
    const snap0 = await cmd({ cmd: "snapshot" });
    await switchMode(page, "rodaje");
    const rodajeDisp = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(rodajeDisp) ===
        JSON.stringify([
          ["camaras", "tomas"],
          ["mapa"],
          ["preparacion", "propiedades"],
          ["actividad", "vista-previa"],
        ]),
      "S2(+): Rodaje no arranco con su propio layout: " + JSON.stringify(rodajeDisp)
    );
    await switchMode(page, "escena");
    const backEscenaDisp = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(backEscenaDisp) === JSON.stringify(movedDisp),
      "S2(+): Escena perdio su layout al volver de Rodaje: " + JSON.stringify(backEscenaDisp)
    );
    const snap1 = await cmd({ cmd: "snapshot" });
    assert(
      snap1.hash === snap0.hash && snap1.rev === snap0.rev,
      "S2(+): cambiar de modo altero el hash o rev de la escena"
    );

    // Negativo 1: Basura en el fichero -> layout y atajos de fabrica con perfil-corrupto + ranura responde (mata Xh)
    await quietPageForProfileWrite(page);
    await cmd({ cmd: "profile_write", text: "{perfil-corrupto-no-json" });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    const corruptAviso = page.locator('[data-aviso="perfil-corrupto"]');
    await corruptAviso.first().waitFor({ state: "visible", timeout: 5000 });
    const corruptRole = await corruptAviso.first().getAttribute("role");
    assert(corruptRole === "alert" || corruptRole === "status", "S2(-): perfil-corrupto sin role alert/status");
    const dispAfterCorrupt = (await readDockDisposition(page)).map((g) => g.tabs);
    assert(
      JSON.stringify(dispAfterCorrupt) === JSON.stringify(factoryDisp),
      "S2(-): perfil-corrupto no cargo layout de fabrica: " + JSON.stringify(dispAfterCorrupt)
    );
    await assertSlotExposed(page, "S2(-) con perfil-corrupto");

    // Negativo 2a: Layout con panel desconocido -> layout-incompatible y atajos guardados intactos + ranura responde (mata Xi)
    const unknownPanelLayout = JSON.parse(JSON.stringify(parsedSaved.layouts.escena));
    if (unknownPanelLayout.panels && typeof unknownPanelLayout.panels === "object") {
      const firstKey = Object.keys(unknownPanelLayout.panels)[0];
      unknownPanelLayout.panels["panel-desconocido"] = Object.assign(
        {},
        unknownPanelLayout.panels[firstKey],
        {
          id: "panel-desconocido",
          contentComponent: "panel-desconocido",
          component: "panel-desconocido",
        }
      );
    }
    (function appendUnknownView(node) {
      if (!node || typeof node !== "object") return false;
      if (node.data && Array.isArray(node.data.views)) {
        node.data.views.push("panel-desconocido");
        return true;
      }
      if (Array.isArray(node.data)) {
        for (const ch of node.data) {
          if (appendUnknownView(ch)) return true;
        }
      }
      return false;
    })(unknownPanelLayout.grid && unknownPanelLayout.grid.root);
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text: JSON.stringify({
        v: 1,
        layouts: { escena: unknownPanelLayout, rodaje: null },
        keymap: { colocar: "G" },
      }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    const incompAviso1 = page.locator('[data-aviso="layout-incompatible"]');
    await incompAviso1.first().waitFor({ state: "visible", timeout: 5000 });
    assert(
      JSON.stringify((await readDockDisposition(page)).map((g) => g.tabs)) === JSON.stringify(factoryDisp),
      "S2(-): panel desconocido no volvio al layout de fabrica"
    );
    await assertSlotExposed(page, "S2(-) con panel desconocido");
    await clickToolsItem(page, /Atajos de teclado/);
    const colocarRow1 = page.locator('[role="dialog"] [data-action="colocar"]');
    await colocarRow1.waitFor({ state: "visible", timeout: 5000 });
    assert(/\bG\b/.test(await colocarRow1.innerText()), "S2(-): no se conservo el atajo G con layout-incompatible");
    await page.keyboard.press("Escape");

    // Negativo 2b: Layout que fromJSON no acepta -> layout-incompatible, atajos intactos y ranura responde (mata Xi)
    const badFromJsonLayout = JSON.parse(JSON.stringify(parsedSaved.layouts.escena));
    (function corruptLeafForFromJson(node) {
      if (!node || typeof node !== "object") return false;
      if (node.data && Array.isArray(node.data.views)) {
        node.data = { id: 12345, views: null };
        return true;
      }
      if (Array.isArray(node.data)) {
        for (const ch of node.data) {
          if (corruptLeafForFromJson(ch)) return true;
        }
      }
      return false;
    })(badFromJsonLayout.grid && badFromJsonLayout.grid.root);
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text: JSON.stringify({
        v: 1,
        layouts: {
          escena: badFromJsonLayout,
          rodaje: null,
        },
        keymap: { colocar: "G" },
      }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    await page.locator('[data-aviso="layout-incompatible"]').first().waitFor({ state: "visible", timeout: 5000 });
    assert(
      JSON.stringify((await readDockDisposition(page)).map((g) => g.tabs)) === JSON.stringify(factoryDisp),
      "S2(-): fromJSON invalido no volvio al layout de fabrica"
    );
    await assertSlotExposed(page, "S2(-) con fromJSON invalido");
    await clickToolsItem(page, /Atajos de teclado/);
    assert(
      /\bG\b/.test(await page.locator('[role="dialog"] [data-action="colocar"]').innerText()),
      "S2(-): fromJSON invalido perdio el atajo G"
    );
    await page.keyboard.press("Escape");

    // Negativo 3a: Orden de escrituras (mata Xy): retener primer POST /api/profile (cambio A),
    // hacer cambio B, esperar 1,5 s (> agrupamiento de 500 ms) con A retenida -> exactamente 1 POST iniciado;
    // soltar A -> sale un segundo POST con B, profile_read acaba con B y, al recargar, se ve B
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text: JSON.stringify({ v: 1, layouts: { escena: null, rodaje: null }, keymap: {} }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    assert(
      !(await page.locator('[data-aviso="atajos-corregidos"]').first().isVisible().catch(() => false)),
      "S2(-): salio atajos-corregidos con un perfil limpio"
    );

    let postCount = 0;
    const postBodies = [];
    let resolveCapturedA;
    let resolveReleaseA;
    let resolveCapturedB;
    const capturedA = new Promise((r) => {
      resolveCapturedA = r;
    });
    const gateA = new Promise((r) => {
      resolveReleaseA = r;
    });
    const capturedB = new Promise((r) => {
      resolveCapturedB = r;
    });
    const profileRouteHandler = async (route) => {
      const req = route.request();
      if (req.method() === "POST") {
        postCount += 1;
        try {
          postBodies.push(JSON.parse(req.postData() || "{}"));
        } catch {
          postBodies.push(null);
        }
        if (postCount === 1) {
          resolveCapturedA();
          await gateA;
          await route.continue();
          return;
        }
        if (postCount === 2) {
          await route.continue();
          resolveCapturedB();
          return;
        }
      }
      await route.continue();
    };
    await page.route("**/api/profile", profileRouteHandler);
    try {
      await clickToolsItem(page, /Atajos de teclado/);
      const dlg = page.locator('[role="dialog"]');
      await dlg.waitFor({ state: "visible", timeout: 5000 });

      // Cambio A: colocar -> G (queda retenido en vuelo)
      await dlg.locator('[data-action="colocar"] button', { hasText: /Cambiar/ }).click();
      await page.keyboard.press("g");
      await Promise.race([
        capturedA,
        sleep(5000).then(() => {
          throw new Error("S2(-): no salio el primer POST /api/profile (cambio A)");
        }),
      ]);
      assert(
        postCount === 1 && postBodies[0] && postBodies[0].keymap && postBodies[0].keymap.colocar === "G",
        "S2(-): el primer POST /api/profile no llevaba el cambio A (G): " + JSON.stringify(postBodies)
      );

      // Cambio B mientras A sigue en vuelo: colocar -> H; esperar 1,5 s con A retenida
      await dlg.locator('[data-action="colocar"] button', { hasText: /Cambiar/ }).click();
      await page.keyboard.press("h");
      await sleep(1500);
      assert(
        postCount === 1,
        "S2(-): con A retenida durante 1,5 s se inicio mas de un POST /api/profile (Xy): postCount=" + postCount
      );

      // Soltar A: entonces debe salir el segundo POST con B
      resolveReleaseA();
      await Promise.race([
        capturedB,
        sleep(6000).then(() => {
          throw new Error("S2(-): tras soltar A no salio el segundo POST /api/profile con B");
        }),
      ]);
      const deadlineB = Date.now() + 6000;
      while (Date.now() < deadlineB) {
        const pr = await cmd({ cmd: "profile_read" });
        if (pr && pr.text) {
          try {
            const j = JSON.parse(pr.text);
            if (j.keymap && j.keymap.colocar === "H") break;
          } catch {}
        }
        await sleep(100);
      }
      await sleep(250);
      assert(
        postCount === 2 && postBodies[1] && postBodies[1].keymap && postBodies[1].keymap.colocar === "H",
        "S2(-): segundo POST /api/profile inesperado (Xy): postCount=" +
          postCount +
          ", bodies=" +
          JSON.stringify(postBodies.map((b) => b && b.keymap))
      );
    } finally {
      await page.unroute("**/api/profile", profileRouteHandler);
    }

    const finalOrderRead = await cmd({ cmd: "profile_read" });
    assert(finalOrderRead && finalOrderRead.text, "S2(-): profile_read vacio tras orden de escrituras");
    const finalOrderJson = JSON.parse(finalOrderRead.text);
    assert(
      finalOrderJson.keymap && finalOrderJson.keymap.colocar === "H",
      "S2(-): cambio A piso a B en profile_read (Xy): " + JSON.stringify(finalOrderJson.keymap)
    );
    await page.keyboard.press("Escape");
    await page.reload();
    await loginIfNeeded(context, page);
    await clickToolsItem(page, /Atajos de teclado/);
    const afterOrderText = await page.locator('[role="dialog"] [data-action="colocar"]').innerText();
    assert(/\bH\b/.test(afterOrderText), "S2(-): al recargar no se ve el cambio B (H): " + afterOrderText);
    await page.keyboard.press("Escape");

    // Negativo 3b: Atajos reparados al cargar (mata XF)
    // Corrida 1: perfil valido con {"aplicar": "Ctrl+W"} (tecla del navegador) -> vuelve a Ctrl+Intro, sale atajos-corregidos y funciona
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text:
        JSON.stringify({
          v: 1,
          layouts: { escena: null, rodaje: null },
          keymap: { aplicar: "Ctrl+W" },
        }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    const fixedAviso1 = page.locator('[data-aviso="atajos-corregidos"]');
    await fixedAviso1.first().waitFor({ state: "visible", timeout: 5000 });
    const fixedRole1 = await fixedAviso1.first().getAttribute("role");
    assert(fixedRole1 === "alert" || fixedRole1 === "status", "S2(-): atajos-corregidos sin role alert/status");
    await clickToolsItem(page, /Atajos de teclado/);
    const aplicarRepairedTxt = await page.locator('[role="dialog"] [data-action="aplicar"]').innerText();
    assert(
      /Ctrl\s*\+\s*(Intro|Enter)/i.test(aplicarRepairedTxt) && !/Ctrl\s*\+\s*W/i.test(aplicarRepairedTxt),
      "S2(-): aplicar con Ctrl+W no volvio a Ctrl+Intro al cargar (XF): " + aplicarRepairedTxt
    );
    await page.keyboard.press("Escape");
    await page.locator('[role="dialog"]').waitFor({ state: "hidden", timeout: 5000 });
    await page.waitForFunction(
      () => {
        const b = document.querySelector('[data-testid="accion-principal"] button');
        return !!b && !b.disabled;
      },
      null,
      { timeout: 5000 }
    );
    const opsBeforeRep1 = await cmd({ cmd: "count_ops" });
    const repApplyRespP = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
      { timeout: 5000 }
    );
    await page.keyboard.press("Control+Enter");
    assert((await repApplyRespP).status() === 200, "S2(-): Ctrl+Intro reparado no disparo POST /api/apply 200 (XF)");
    assert(
      (await cmd({ cmd: "count_ops" })).n === opsBeforeRep1.n + 1,
      "S2(-): Ctrl+Intro reparado no creo una orden (XF)"
    );

    // Corrida 2: perfil valido con {"colocar": null} (obligatoria sin tecla) -> vuelve a Intro, sale atajos-corregidos y funciona
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text:
        JSON.stringify({
          v: 1,
          layouts: { escena: null, rodaje: null },
          keymap: { colocar: null },
        }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    const fixedAviso2 = page.locator('[data-aviso="atajos-corregidos"]');
    await fixedAviso2.first().waitFor({ state: "visible", timeout: 5000 });
    await clickToolsItem(page, /Atajos de teclado/);
    const colocarRepairedTxt = await page.locator('[role="dialog"] [data-action="colocar"]').innerText();
    assert(
      /\b(Intro|Enter)\b/i.test(colocarRepairedTxt) && !/Sin tecla/i.test(colocarRepairedTxt),
      "S2(-): colocar: null no volvio a Intro al cargar (XF): " + colocarRepairedTxt
    );
    await page.keyboard.press("Escape");
    await page.locator('[role="dialog"]').waitFor({ state: "hidden", timeout: 5000 });
    await activatePanel(page, "anadir");
    const repBarrel = page.locator('[data-panel="anadir"] [data-cls="Barrel_Red"]').first();
    await repBarrel.focus();
    await page.keyboard.press("Space");
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-panel="anadir"] [data-cls="Barrel_Red"]');
        return !!el && el.getAttribute("aria-pressed") === "true";
      },
      null,
      { timeout: 3000 }
    );
    const snapBeforeRep2 = await cmd({ cmd: "snapshot" });
    await page.keyboard.press("Enter");
    await waitForSnap(
      (s) => s.doc.entities.length === snapBeforeRep2.doc.entities.length + 1,
      "colocar con tecla de serie Intro tras reparar colocar: null (XF)"
    );
    await page.evaluate(() => {
      if (document.activeElement && document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    });
    await sleep(120);

    // Corrida 3 (revisión de Sol, F09): reparar un choque no puede dejar otro nuevo, y una tecla
    // propia que no está en ningún choque (Duplicar en Ctrl+K) sobrevive a la reparación
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text:
        JSON.stringify({
          v: 1,
          layouts: { escena: null, rodaje: null },
          keymap: { colocar: "Ctrl+Z", deshacer: "G", rehacer: "G", duplicar: "Ctrl+K" },
        }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    await page.locator('[data-aviso="atajos-corregidos"]').first().waitFor({ state: "visible", timeout: 5000 });
    await clickToolsItem(page, /Atajos de teclado/);
    const keyRowTxt = async (act) =>
      (await page.locator('[role="dialog"] [data-action="' + act + '"]').innerText()).replace(/\s+/g, " ");
    const kColocar = await keyRowTxt("colocar");
    const kDeshacer = await keyRowTxt("deshacer");
    assert(
      !(/Ctrl\s*\+\s*Z/i.test(kColocar) && /Ctrl\s*\+\s*Z/i.test(kDeshacer)),
      "S2(-): tras reparar el perfil, Colocar y Deshacer comparten Ctrl+Z (F09): " + kColocar + " | " + kDeshacer
    );
    const kDuplicar = await keyRowTxt("duplicar");
    assert(
      /Ctrl\s*\+\s*K/i.test(kDuplicar),
      "S2(-): la reparación de choques se llevó la tecla propia de Duplicar, que no chocaba (F09): " + kDuplicar
    );
    await page.keyboard.press("Escape");
    await page.locator('[role="dialog"]').waitFor({ state: "hidden", timeout: 5000 });

    // Negativo 4: Layout guardado con panel titulado <img src=x> -> titulo del registro y 0 img
    const hostileLayout = JSON.parse(JSON.stringify(parsedSaved.layouts.escena));
    function poisonTitles(node) {
      if (!node || typeof node !== "object") return;
      if ("title" in node) node.title = "<img src=x>";
      for (const k of Object.keys(node)) poisonTitles(node[k]);
    }
    poisonTitles(hostileLayout);
    if (hostileLayout.panels && typeof hostileLayout.panels === "object") {
      for (const k of Object.keys(hostileLayout.panels)) {
        hostileLayout.panels[k].title = "<img src=x>";
      }
    }
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text: JSON.stringify({ v: 1, layouts: { escena: hostileLayout, rodaje: null }, keymap: {} }) + "\n",
    });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    const hostileCheck = await page.evaluate(() => {
      const imgs = document.querySelectorAll("img").length;
      const tabTexts = Array.from(document.querySelectorAll(".dv-tab")).map((t) => (t.textContent || "").trim());
      return { imgs, tabTexts };
    });
    assert(hostileCheck.imgs === 0, "S2(-): aparecio un <img> desde el layout guardado");
    assert(
      !hostileCheck.tabTexts.some((t) => t.includes("<img")) &&
        hostileCheck.tabTexts.some((t) => /Jerarqu[ií]a/.test(t)),
      "S2(-): las pestañas usaron el titulo del perfil en vez del registro: " + JSON.stringify(hostileCheck.tabTexts)
    );

    console.log("S2 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S3: La ranura nunca se tapa (CU-25)
// ============================================================================
async function runS3(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    const widths = [390, 768, 1024, 1280, 1366, 1600];

    // 1. Layouts de fabrica en Escena y Rodaje a los 6 anchos + sin desplazamiento
    for (const mode of ["escena", "rodaje"]) {
      await switchMode(page, mode);
      for (const w of widths) {
        await page.setViewportSize({ width: w, height: 720 });
        await sleep(150);
        await assertSlotExposed(page, "S3(+) " + mode + " a " + w + " px");
        await assertNoPageScroll(page, "S3(-) " + mode + " a " + w + " px");
      }
    }
    await page.setViewportSize({ width: 1280, height: 720 });
    await switchMode(page, "escena");

    // 2. Con paneles movidos (Propiedades a la izquierda + arrastre)
    await clickToolsItem(page, /Propiedades a la izquierda/);
    await sleep(200);
    await assertSlotExposed(page, "S3(+) Propiedades a la izquierda");
    await assertNoPageScroll(page, "S3(-) Propiedades a la izquierda");

    await dragTabToGroup(page, "validacion", "jerarquia");
    await assertSlotExposed(page, "S3(+) tras arrastrar panel");
    await assertNoPageScroll(page, "S3(-) tras arrastrar panel");

    // 3. Con Herramientas abierto
    await openToolsMenu(page);
    await assertSlotExposed(page, "S3(+) con Herramientas abierto");
    await assertNoPageScroll(page, "S3(-) con Herramientas abierto");
    await page.keyboard.press("Escape");

    // 4. Con aviso perfil-corrupto de S2
    await quietPageForProfileWrite(page);
    await cmd({ cmd: "profile_write", text: "corrupto!!!" });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    await page.locator('[data-aviso="perfil-corrupto"]').first().waitFor({ state: "visible", timeout: 5000 });
    for (const w of widths) {
      await page.setViewportSize({ width: w, height: 720 });
      await sleep(120);
      await assertSlotExposed(page, "S3(+) perfil-corrupto a " + w + " px");
      await assertNoPageScroll(page, "S3(-) perfil-corrupto a " + w + " px");
    }

    // 5. Con aviso layout-incompatible de S2
    await quietPageForProfileWrite(page);
    await cmd({
      cmd: "profile_write",
      text: JSON.stringify({
        v: 1,
        layouts: { escena: { grid: { root: null }, panels: { inventado: { id: "inventado" } } }, rodaje: null },
        keymap: {},
      }) + "\n",
    });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(BASE + "/");
    await loginIfNeeded(context, page);
    await page.locator('[data-aviso="layout-incompatible"]').first().waitFor({ state: "visible", timeout: 5000 });
    for (const w of widths) {
      await page.setViewportSize({ width: w, height: 720 });
      await sleep(120);
      await assertSlotExposed(page, "S3(+) layout-incompatible a " + w + " px");
      await assertNoPageScroll(page, "S3(-) layout-incompatible a " + w + " px");
    }

    console.log("S3 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S4: Jerarquía (D2)
// ============================================================================
async function runS4(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    const jer = page.locator('[data-panel="jerarquia"]');
    await jer.waitFor({ state: "visible", timeout: 5000 });

    // Negativo: nunca «Nada en el juego»; en esta parte siempre «Sin lectura del juego»
    const jerTxt0 = await jer.innerText();
    assert(/Sin lectura del juego/.test(jerTxt0), "S4(+): falta 'Sin lectura del juego' en Jerarquia");
    const bodyTxt0 = await page.locator("body").innerText();
    assert(!/Nada en el juego/i.test(bodyTxt0), "S4(-): aparece 'Nada en el juego' sin lectura");

    // Positivo: escena vacia -> «Esta escena está vacía.» y «Añade tu primer objeto» abre Añadir con foco en #libq
    assert(/Esta escena est[áa] vac[íi]a\./.test(jerTxt0), "S4(+): falta 'Esta escena está vacía.'");
    const ctaBtn = jer.getByRole("button", { name: /A[ñn]ade tu primer objeto/ });
    await ctaBtn.waitFor({ state: "visible", timeout: 5000 });
    await ctaBtn.click();
    await page.locator('[data-panel="anadir"]').waitFor({ state: "visible", timeout: 5000 });
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "libq", null, {
      timeout: 5000,
    });

    // Negativo (mata Xj): page.route contesta 200 a POST /api/scene/ops sin pasarlo al backend -> 0 filas nuevas en 2 s
    let interceptedOps = 0;
    const fakeOpsHandler = async (route) => {
      if (route.request().method() === "POST") {
        interceptedOps += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json; charset=utf-8",
          body: JSON.stringify({
            ok: true,
            rev: 99,
            hash: "0".repeat(64),
            batch: "b-99",
            created: ["obj-99"],
            partial: [],
          }),
        });
        return;
      }
      await route.continue();
    };
    await page.route("**/api/scene/ops", fakeOpsHandler);
    // Un fantasma que dura milisegundos (la entidad pintada con la respuesta y borrada por la
    // lectura autoritativa) también es estado optimista: se vigila todo el rato, no solo al final.
    await page.evaluate(() => {
      window.__dsbxGhost = 0;
      const obs = new MutationObserver(() => {
        if (document.querySelector('[data-panel="jerarquia"] [data-entity-id]')) window.__dsbxGhost += 1;
      });
      obs.observe(document.body, { subtree: true, childList: true, attributes: true });
      window.__dsbxGhostObs = obs;
    });
    try {
      const barrelItem = page.locator('[data-panel="anadir"] [data-cls="Barrel_Red"]').first();
      await barrelItem.click();
      await page.keyboard.press("Enter");
      const d = Date.now() + 3000;
      while (Date.now() < d && interceptedOps === 0) await sleep(50);
      assert(interceptedOps === 1, "S4(-): colocar no disparo POST /api/scene/ops");
      await sleep(2000);
      const ghostCount = await page.locator('[data-panel="jerarquia"] [data-entity-id]').count();
      const ghostSeen = await page.evaluate(() => {
        if (window.__dsbxGhostObs) window.__dsbxGhostObs.disconnect();
        return window.__dsbxGhost || 0;
      });
      assert(
        ghostCount === 0 && ghostSeen === 0,
        "S4(-): el arbol pinto la entidad con la respuesta del POST (Xj): ahora=" + ghostCount + ", vista=" + ghostSeen
      );
      await page.keyboard.press("Escape");
    } finally {
      await page.unroute("**/api/scene/ops", fakeOpsHandler);
    }

    // Positivo: dos ai_ops aparecen en el arbol sin recargar en < 3 s
    const t0 = Date.now();
    const r1 = await cmd({
      cmd: "ai_ops",
      label: "IA coloca 1",
      ops: [{ name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril alfa", x: 6100, z: 7600, yaw: 0 } }],
    });
    const r2 = await cmd({
      cmd: "ai_ops",
      label: "IA coloca 2",
      ops: [{ name: "entity.add", args: { kind: "objeto", cls: "WoodenCrate", name: "Caja beta", x: 6120, z: 7610, yaw: 0 } }],
    });
    assert(r1.ok && r2.ok, "S4(+): ai_ops fallaron");
    const id1 = r1.created[0];
    const id2 = r2.created[0];

    const tree = page.locator('[data-panel="jerarquia"] [role="tree"][aria-label="Jerarquía"]');
    await tree.locator('[role="treeitem"][data-entity-id="' + id1 + '"]').waitFor({ state: "visible", timeout: 3000 });
    await tree.locator('[role="treeitem"][data-entity-id="' + id2 + '"]').waitFor({ state: "visible", timeout: 3000 });
    assert(Date.now() - t0 < 3000, "S4(+): tardaron >= 3 s en aparecer sin recargar");

    // Añadir un tercero para probar rango Mayus+clic con elemento intermedio
    const r3 = await cmd({
      cmd: "ai_ops",
      label: "IA coloca 3",
      ops: [{ name: "entity.add", args: { kind: "objeto", cls: "Barrel_Blue", name: "Barril gamma", x: 6140, z: 7620, yaw: 0 } }],
    });
    const id3 = r3.created[0];
    await tree.locator('[role="treeitem"][data-entity-id="' + id3 + '"]').waitFor({ state: "visible", timeout: 3000 });

    const item1 = tree.locator('[role="treeitem"][data-entity-id="' + id1 + '"]');
    const item2 = tree.locator('[role="treeitem"][data-entity-id="' + id2 + '"]');
    const item3 = tree.locator('[role="treeitem"][data-entity-id="' + id3 + '"]');

    // Seleccion con clic y flechas Arriba/Abajo
    await item1.click();
    assert((await item1.getAttribute("aria-selected")) === "true", "S4(+): clic no selecciono id1");
    await page.keyboard.press("ArrowDown");
    await page.waitForFunction(
      (eid) => {
        const el = document.querySelector('[data-entity-id="' + eid + '"]');
        return !!el && el.getAttribute("aria-selected") === "true";
      },
      id2,
      { timeout: 3000 }
    );
    await page.keyboard.press("ArrowUp");
    await page.waitForFunction(
      (eid) => {
        const el = document.querySelector('[data-entity-id="' + eid + '"]');
        return !!el && el.getAttribute("aria-selected") === "true";
      },
      id1,
      { timeout: 3000 }
    );

    // Ctrl+clic añade o quita
    await item3.click({ modifiers: ["Control"] });
    assert(
      (await item1.getAttribute("aria-selected")) === "true" &&
        (await item2.getAttribute("aria-selected")) !== "true" &&
        (await item3.getAttribute("aria-selected")) === "true",
      "S4(+): Ctrl+clic no selecciono id1 + id3"
    );

    // Mayus+clic selecciona seguidos
    await item1.click();
    await item3.click({ modifiers: ["Shift"] });
    assert(
      (await item1.getAttribute("aria-selected")) === "true" &&
        (await item2.getAttribute("aria-selected")) === "true" &&
        (await item3.getAttribute("aria-selected")) === "true",
      "S4(+): Mayus+clic no selecciono el rango id1..id3"
    );

    // El buscador filtra sin perder la seleccion
    await item1.click();
    const searchInput = jer.locator('input[placeholder*="Buscar"], input[type="search"], input').first();
    await searchInput.fill("Caja beta");
    await sleep(150);
    assert(await item2.isVisible(), "S4(+): el buscador oculto la coincidencia Caja beta");
    assert(!(await item1.isVisible().catch(() => false)), "S4(+): el buscador no filtro Barril alfa");
    await searchInput.fill("");
    await sleep(150);
    assert(
      (await item1.isVisible()) && (await item1.getAttribute("aria-selected")) === "true",
      "S4(+): el buscador perdio la seleccion de id1"
    );

    // Supr borra lo seleccionado en una tanda (el snapshot lo confirma)
    await item1.click();
    await item2.click({ modifiers: ["Control"] });
    await page.keyboard.press("Delete");
    const snapAfterDel = await waitForSnap(
      (s) => s.doc.entities.length === 1 && s.doc.entities[0].id === id3,
      "borrado Supr de id1 e id2"
    );
    assert(snapAfterDel.doc.entities.length === 1, "S4(+): Supr no borro las entidades seleccionadas");
    const bodyTxtEnd = await page.locator("body").innerText();
    assert(!/Nada en el juego/i.test(bodyTxtEnd), "S4(-): aparece 'Nada en el juego' al final");

    console.log("S4 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S5: Inspector del esquema
// ============================================================================
async function runS5(browser) {
  await resetBackendState();
  const rAdd = await cmd({
    cmd: "ai_ops",
    label: "Objeto S5",
    ops: [{ name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril rojo", x: 6000, z: 7000, yaw: 45 } }],
  });
  assert(rAdd.ok, "S5: fallo ai_ops inicial");
  const eid = rAdd.created[0];
  const rawSchema = JSON.parse(fs.readFileSync(SCHEMA_PATH, "utf8"));
  const allSchemaProps = Object.keys(rawSchema.$defs.nonActorEntity.properties);
  const expectedMainProps = allSchemaProps.filter((k) => k !== "id");

  const { context, page } = await openStudio(browser);
  try {
    const item = page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]');
    await item.waitFor({ state: "visible", timeout: 5000 });
    await item.click();
    await activatePanel(page, "propiedades");

    // El formulario principal enseña las propiedades del esquema en su orden, sin `id`;
    // `id` va dentro de «Detalles técnicos» (<details> al final) con #f-id y data-field="id"
    const schemaDomLayout = await page.evaluate(() => {
      const panel = document.querySelector('[data-panel="propiedades"]');
      if (!panel) return null;
      const dedup = (els) =>
        els
          .filter((el) => {
            const f = el.getAttribute("data-field");
            const anc = el.parentElement && el.parentElement.closest("[data-field]");
            return !anc || anc.getAttribute("data-field") !== f;
          })
          .map((el) => el.getAttribute("data-field"));
      const allFields = Array.from(panel.querySelectorAll("[data-field]"));
      const outsideDetails = dedup(allFields.filter((el) => !el.closest("details")));
      const detailsEls = Array.from(panel.querySelectorAll("details"));
      const techDetails =
        detailsEls.find((d) => /Detalles t[ée]cnicos/i.test((d.querySelector("summary") || d).textContent || "")) ||
        detailsEls[0] ||
        null;
      const insideDetails = techDetails ? dedup(Array.from(techDetails.querySelectorAll("[data-field]"))) : [];
      const fIdInDetails = !!(techDetails && techDetails.querySelector("#f-id"));
      const summaryText =
        techDetails && techDetails.querySelector("summary")
          ? (techDetails.querySelector("summary").textContent || "").trim()
          : "";
      return {
        outsideDetails,
        hasDetails: !!techDetails,
        summaryText,
        insideDetails,
        fIdInDetails,
      };
    });
    assert(
      schemaDomLayout && JSON.stringify(schemaDomLayout.outsideDetails) === JSON.stringify(expectedMainProps),
      "S5(+): orden de [data-field] fuera de <details> != nonActorEntity sin id: " +
        JSON.stringify(schemaDomLayout && schemaDomLayout.outsideDetails) +
        " vs " +
        JSON.stringify(expectedMainProps)
    );
    assert(
      schemaDomLayout.hasDetails &&
        /Detalles t[ée]cnicos/i.test(schemaDomLayout.summaryText) &&
        schemaDomLayout.insideDetails.includes("id") &&
        schemaDomLayout.fIdInDetails,
      "S5(+): falta [data-field='id'] o #f-id dentro de <details> «Detalles técnicos»: " +
        JSON.stringify(schemaDomLayout)
    );

    // Comprobar id="f-<prop>", label asociada y data-min/data-max iguales a los del esquema
    const attrs = await page.evaluate((props) => {
      const out = {};
      const panel = document.querySelector('[data-panel="propiedades"]');
      for (const p of props) {
        const el = document.getElementById("f-" + p);
        const wrap =
          (el && el.closest('[data-field="' + p + '"]')) ||
          (panel && panel.querySelector('[data-field="' + p + '"]'));
        const hasLabel =
          !!el &&
          (!!document.querySelector('label[for="f-' + p + '"]') ||
            !!el.closest("label") ||
            !!el.getAttribute("aria-labelledby") ||
            !!el.getAttribute("aria-label") ||
            !!(wrap && wrap.querySelector("label")));
        out[p] = el
          ? {
              exists: true,
              dataField: el.getAttribute("data-field") || (wrap && wrap.getAttribute("data-field")) || null,
              min: el.getAttribute("data-min") ?? (wrap && wrap.getAttribute("data-min")) ?? null,
              max: el.getAttribute("data-max") ?? (wrap && wrap.getAttribute("data-max")) ?? null,
              inputmode: el.getAttribute("inputmode"),
              type: el.getAttribute("type"),
              hasLabel,
            }
          : { exists: false };
      }
      return out;
    }, allSchemaProps);
    for (const p of allSchemaProps) {
      assert(attrs[p].exists && attrs[p].dataField === p, "S5(+): falta #f-" + p + " con data-field=" + p);
      assert(attrs[p].hasLabel, "S5(+): #f-" + p + " sin label");
    }
    assert(attrs.x.min === "0" && attrs.x.max === "15360", "S5(+): data-min/max de x incorrectos: " + JSON.stringify(attrs.x));
    assert(attrs.z.min === "0" && attrs.z.max === "15360", "S5(+): data-min/max de z incorrectos: " + JSON.stringify(attrs.z));
    assert(attrs.yaw.min === "0" && attrs.yaw.max === "360", "S5(+): data-min/max de yaw incorrectos: " + JSON.stringify(attrs.yaw));

    // Negativo: sin flechas del navegador en los campos numericos (pruebas-mejoras.js:1860)
    assert(
      attrs.x.type !== "number" && attrs.x.inputmode === "decimal" && attrs.z.inputmode === "decimal",
      "S5(-): campos numericos sin inputmode=decimal o con type=number: " + JSON.stringify({ x: attrs.x, z: attrs.z })
    );
    await page.evaluate(() => {
      if (document.activeElement && document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    });
    const fxBox = await page.locator("#f-x").boundingBox();
    assert(fxBox && fxBox.width > 24, "S5(-): #f-x sin caja visible");
    const spinClip = {
      x: fxBox.x + fxBox.width - 20,
      y: fxBox.y + 2,
      width: 18,
      height: Math.max(4, fxBox.height - 4),
    };
    await page.mouse.move(2, 2);
    await sleep(150);
    const shotAway = await page.screenshot({ clip: spinClip });
    await page.mouse.move(fxBox.x + fxBox.width - 8, fxBox.y + fxBox.height / 2);
    await sleep(250);
    const shotHover = await page.screenshot({ clip: spinClip });
    assert(shotAway.equals(shotHover), "S5(-): salen flechas del navegador al pasar el raton sobre #f-x");
    await page.mouse.move(2, 2);

    // Positivo (mata Xl): el foco en X manda el prestamo ANTES de dejar escribir y leases lo ve
    let resolveLeaseCaptured;
    let resolveLeaseGate;
    let leaseReqBody = null;
    const leaseCaptured = new Promise((r) => {
      resolveLeaseCaptured = r;
    });
    const leaseGate = new Promise((r) => {
      resolveLeaseGate = r;
    });
    // El manejador avisa cuando ha soltado la petición retenida: el unroute del finally espera a
    // ese aviso; si no, Playwright resuelve la petición por su cuenta y el continue llega tarde.
    let resolveHeldDone;
    const heldDone = new Promise((r) => {
      resolveHeldDone = r;
    });
    const holdLeaseHandler = async (route) => {
      const req = route.request();
      const held = req.method() === "POST" && new URL(req.url()).pathname === "/api/lease";
      if (held) {
        leaseReqBody = JSON.parse(req.postData() || "{}");
        resolveLeaseCaptured();
        await leaseGate;
      }
      try {
        await route.continue();
      } catch (e) {
        if (!/already handled/i.test(String(e && e.message))) throw e;
      } finally {
        if (held) resolveHeldDone();
      }
    };
    await page.route("**/api/lease", holdLeaseHandler);
    try {
      await page.locator("#f-x").focus();
      await Promise.race([
        leaseCaptured,
        sleep(5000).then(() => {
          throw new Error("S5(+): enfocar #f-x no pidio POST /api/lease (Xl)");
        }),
      ]);
      assert(
        leaseReqBody && leaseReqBody.target === eid && leaseReqBody.field === "x",
        "S5(+): cuerpo de POST /api/lease inesperado: " + JSON.stringify(leaseReqBody)
      );
      const readOnlyWhilePending = await page.locator("#f-x").evaluate((el) => el.readOnly);
      assert(readOnlyWhilePending === true, "S5(+): #f-x dejo escribir antes del 200 de /api/lease (Xl)");
    } finally {
      resolveLeaseGate();
      await Promise.race([heldDone, sleep(5000)]);
      await page.unroute("**/api/lease", holdLeaseHandler);
    }

    await waitEditable(page, "#f-x");
    const liveLeases = await cmd({ cmd: "leases" });
    assert(
      liveLeases.ok && liveLeases.leases.some((l) => l.target === eid && l.field === "x"),
      "S5(+): leases no ve el prestamo vivo de #f-x: " + JSON.stringify(liveLeases)
    );

    // Con el foco en X, un ai_ops que mueve esa entidad -> 409 busy_human
    const busyAttempt = await cmd({
      cmd: "ai_ops",
      label: "IA intenta mover",
      ops: [{ name: "entity.move", target: eid, args: { x: 6500, z: 7000 } }],
    });
    assert(
      busyAttempt.ok === false && busyAttempt.code === "busy_human",
      "S5(+): ai_ops con prestamo activo no dio busy_human: " + JSON.stringify(busyAttempt)
    );

    // X con el teclado -> el snapshot cambia y last_commit da «Mover …» de la persona
    await page.keyboard.press("Control+a");
    await page.keyboard.type("6250");
    await page.keyboard.press("Enter");
    await waitForSnap((s) => s.doc.entities[0] && s.doc.entities[0].x === 6250, "edicion de X a 6250");
    const lastC = await cmd({ cmd: "last_commit" });
    assert(
      lastC.ok &&
        lastC.author &&
        lastC.author.role === "human" &&
        typeof lastC.label === "string" &&
        /^Mover\b/.test(lastC.label),
      "S5(+): last_commit no es 'Mover ...' de human: " + JSON.stringify(lastC)
    );

    // Al salir del campo, el prestamo se suelta y el mismo ai_ops pasa
    await page.locator("#f-x").evaluate((el) => el.blur());
    const deadlineRel = Date.now() + 5000;
    while (Date.now() < deadlineRel) {
      const ls = await cmd({ cmd: "leases" });
      if (ls.ok && ls.leases.length === 0) break;
      await sleep(100);
    }
    const freeLeases = await cmd({ cmd: "leases" });
    assert(freeLeases.leases.length === 0, "S5(+): el prestamo no se solto al perder el foco: " + JSON.stringify(freeLeases));

    const freeAttempt = await cmd({
      cmd: "ai_ops",
      label: "IA mueve tras soltar",
      ops: [{ name: "entity.move", target: eid, args: { x: 6500, z: 7000 } }],
    });
    assert(freeAttempt.ok === true, "S5(+): ai_ops fallo tras soltar el prestamo: " + JSON.stringify(freeAttempt));
    await page.waitForFunction(
      () => {
        const el = document.getElementById("f-x");
        return !!el && /^6500\b/.test(String(el.value).replace(/\./g, ""));
      },
      null,
      { timeout: 5000 }
    );

    // Ambiente edita con ambient.set
    const ambRow = page
      .locator('[data-panel="jerarquia"] [role="treeitem"], [data-panel="jerarquia"] button', {
        hasText: /^Ambiente\b/i,
      })
      .first();
    await ambRow.click();
    await page.locator("#f-viento").waitFor({ state: "visible", timeout: 5000 });
    await page.locator("#f-viento").focus();
    await waitEditable(page, "#f-viento");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("8");
    await page.keyboard.press("Enter");
    await page.locator("#f-viento").evaluate((el) => el.blur());
    await waitForSnap((s) => s.doc.ambiente && s.doc.ambiente.viento === 8, "ambient.set viento=8");

    // Negativo (mata Xm y Xu): X = 99999 -> conserva borrador, aria-invalid, out_of_map + ruta en campo y Validacion, Aplicar desactivado; Esc resuelve
    await item.click();
    await page.locator("#f-x").focus();
    await waitEditable(page, "#f-x");
    const rejectRespP = page.waitForResponse(
      (r) => r.url().endsWith("/api/scene/ops") && r.request().method() === "POST",
      { timeout: 5000 }
    );
    await page.keyboard.press("Control+a");
    await page.keyboard.type("99999");
    await page.keyboard.press("Enter");
    const rejectResp = await rejectRespP;
    assert(rejectResp.status() === 422, "S5(-): X=99999 no respondio 422: " + rejectResp.status());
    await sleep(150);

    const draftVal = await page.locator("#f-x").inputValue();
    assert(draftVal === "99999", "S5(-): tras 422 el campo volvio al valor del documento (Xm): " + draftVal);
    assert((await page.locator("#f-x").getAttribute("aria-invalid")) === "true", "S5(-): #f-x sin aria-invalid=true");
    const propsErrTxt = await page.locator('[data-panel="propiedades"]').innerText();
    assert(
      propsErrTxt.includes("out_of_map") && propsErrTxt.includes("/entities/0/x"),
      "S5(-): Propiedades no enseña out_of_map y /entities/0/x: " + propsErrTxt
    );
    const applyDisabledWithErr = await page.locator('[data-testid="accion-principal"] button').first().isDisabled();
    assert(applyDisabledWithErr === true, "S5(-): Aplicar sigue activo con un borrador rechazado (Xu)");

    const snapUnchanged = await cmd({ cmd: "snapshot" });
    assert(snapUnchanged.doc.entities[0].x === 6500, "S5(-): snapshot cambio tras rechazo 422");

    await activatePanel(page, "validacion");
    const valRow = page.locator('[data-panel="validacion"] [data-error-pointer="/entities/0/x"]');
    await valRow.first().waitFor({ state: "visible", timeout: 5000 });
    const valRowTxt = await valRow.first().innerText();
    assert(
      valRowTxt.includes("out_of_map") && valRowTxt.includes("/entities/0/x"),
      "S5(-): Validacion sin out_of_map o ruta: " + valRowTxt
    );

    // Esc resuelve el borrador rechazado
    await page.locator("#f-x").focus();
    await page.keyboard.press("Escape");
    await sleep(200);
    assert((await page.locator("#f-x").inputValue()) !== "99999", "S5(-): Esc no descarto el borrador 99999");
    assert((await page.locator("#f-x").getAttribute("aria-invalid")) !== "true", "S5(-): Esc no limpio aria-invalid");
    assert((await valRow.count()) === 0, "S5(-): Esc no quito la fila de Validacion");
    assert(
      !(await page.locator('[data-testid="accion-principal"] button').first().isDisabled()),
      "S5(-): Esc no reactivo Aplicar"
    );
    await page.locator("#f-x").evaluate((el) => el.blur());

    // Negativo (mata Xk): Generado de verdad desde /api/schema (añadir nota y quitar yaw)
    const customSchema = JSON.parse(JSON.stringify(rawSchema));
    customSchema.$defs.nonActorEntity.properties.nota = { type: "string" };
    delete customSchema.$defs.nonActorEntity.properties.yaw;
    customSchema.$defs.nonActorEntity.required = customSchema.$defs.nonActorEntity.required.filter(
      (k) => k !== "yaw"
    );
    const schemaRoute = async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify(customSchema),
      });
    };
    await page.route("**/api/schema", schemaRoute);
    try {
      await page.reload();
      await loginIfNeeded(context, page);
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
      await activatePanel(page, "propiedades");
      const notaLoc = page.locator('[data-panel="propiedades"] [data-field="nota"]');
      await notaLoc.first().waitFor({ state: "visible", timeout: 5000 });
      const schemaDrivenCheck = await page.evaluate(() => {
        const nota = document.getElementById("f-nota") || document.querySelector('[data-field="nota"]');
        const yaw = document.getElementById("f-yaw") || document.querySelector('[data-field="yaw"]');
        const propsText = (document.querySelector('[data-panel="propiedades"]').innerText || "");
        const notaReadOnly = nota
          ? nota.tagName === "INPUT" || nota.tagName === "TEXTAREA" || nota.tagName === "SELECT"
            ? !!(nota.readOnly || nota.disabled || nota.getAttribute("aria-readonly") === "true")
            : true
          : false;
        return {
          hasNota: !!nota,
          notaReadOnly,
          hasYaw: !!yaw,
          hasRumboLabel: /\bRumbo\b/.test(propsText),
        };
      });
      assert(schemaDrivenCheck.hasNota, "S5(-): no salio el campo 'nota' añadido al esquema (Xk)");
      assert(schemaDrivenCheck.notaReadOnly, "S5(-): el campo desconocido 'nota' no salio en solo lectura");
      assert(!schemaDrivenCheck.hasYaw && !schemaDrivenCheck.hasRumboLabel, "S5(-): no desaparecio Rumbo/yaw al quitarlo del esquema (Xk)");
    } finally {
      await page.unroute("**/api/schema", schemaRoute);
    }

    // Negativo: clase quitada del catalogo -> «· no está en el catálogo» y 0 peticiones al enfocar/salir
    const rawCat = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
    const catalogRoute = async (route) => {
      const resp = await route.fetch();
      const j = await resp.json();
      j.classes.objeto = (j.classes.objeto || rawCat.classes.objeto).filter((c) => c !== "Barrel_Red");
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify(j),
      });
    };
    await page.route("**/api/catalog", catalogRoute);
    let opsSentUnknownCls = 0;
    const countOpsReq = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") {
        opsSentUnknownCls += 1;
      }
    };
    page.on("request", countOpsReq);
    try {
      await page.reload();
      await loginIfNeeded(context, page);
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
      await activatePanel(page, "propiedades");
      const clsInfo = await page.evaluate(() => {
        const s = document.getElementById("f-cls");
        if (!s) return null;
        const opt = s.selectedOptions && s.selectedOptions[0];
        return { value: s.value, text: opt ? opt.textContent : s.textContent || "" };
      });
      assert(
        clsInfo &&
          clsInfo.value === "Barrel_Red" &&
          clsInfo.text.includes("Barrel_Red") &&
          /no est[áa] en el cat[áa]logo/i.test(clsInfo.text),
        "S5(-): clase fuera de catalogo mal pintada: " + JSON.stringify(clsInfo)
      );
      await page.locator("#f-cls").focus();
      await sleep(100);
      await page.keyboard.press("Tab");
      await sleep(200);
      await ambRow.click();
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
      await sleep(200);
      assert(opsSentUnknownCls === 0, "S5(-): se mando POST /api/scene/ops con clase fuera de catalogo");
      const snapCls = await cmd({ cmd: "snapshot" });
      assert(snapCls.doc.entities[0].cls === "Barrel_Red", "S5(-): cambio la clase fuera de catalogo");
    } finally {
      page.off("request", countOpsReq);
      await page.unroute("**/api/catalog", catalogRoute);
    }

    // ---- Regresiones de la revisión de Sol del código (F01, F04, F05, F06) ----
    const continueSafe = async (route) => {
      try {
        await route.continue();
      } catch (e) {
        if (!/already handled/i.test(String(e && e.message))) throw e;
      }
    };
    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
    await activatePanel(page, "propiedades");

    // F04: sin préstamo concedido, el selector de Clase ni cambia ni manda nada
    {
      let releaseLease;
      const leaseGate = new Promise((r) => {
        releaseLease = r;
      });
      let leaseSeen = false;
      const holdClsLease = async (route) => {
        const req = route.request();
        if (req.method() === "POST" && new URL(req.url()).pathname === "/api/lease") {
          leaseSeen = true;
          await leaseGate;
        }
        await continueSafe(route);
      };
      let effectPosts = 0;
      const onEffect = (req) => {
        if (isEffectPost(req)) effectPosts += 1;
      };
      await page.route("**/api/lease", holdClsLease);
      page.on("request", onEffect);
      try {
        await page.locator("#f-cls").focus();
        const d = Date.now() + 3000;
        while (!leaseSeen && Date.now() < d) await sleep(50);
        assert(leaseSeen, "S5(-): enfocar Clase no pidio prestamo (F04)");
        const values = await page.locator("#f-cls option").evaluateAll((os) => os.map((o) => o.value));
        const current = await page.locator("#f-cls").inputValue();
        const other = values.find((v) => v !== current);
        if (other) await page.locator("#f-cls").selectOption(other).catch(() => {});
        await sleep(400);
        assert(effectPosts === 0, "S5(-): Clase cambio sin prestamo concedido (F04): " + effectPosts);
      } finally {
        page.off("request", onEffect);
        releaseLease();
        await sleep(200);
        await page.unroute("**/api/lease", holdClsLease);
      }
      await page.locator("#f-cls").evaluate((el) => el.blur());
      await sleep(200);
    }

    // F05: una renovación rechazada retira el préstamo y X vuelve a solo lectura
    {
      const failRenew = async (route) => {
        const req = route.request();
        if (req.method() === "POST" && /\/api\/lease\/[^/]+\/renew$/.test(new URL(req.url()).pathname)) {
          await route.fulfill({
            status: 409,
            contentType: "application/json; charset=utf-8",
            body: JSON.stringify({ ok: false, code: "lease_expired", pointer: "", msg: "caducado" }),
          });
          return;
        }
        await continueSafe(route);
      };
      await page.route("**/api/lease/**", failRenew);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page
          .waitForFunction(() => {
            const el = document.getElementById("f-x");
            return !!el && el.readOnly;
          }, null, { timeout: 5000 })
          .catch(() => {
            throw new Error("S5(-): tras una renovacion 409 el campo X siguio editable (F05)");
          });
      } finally {
        await page.unroute("**/api/lease/**", failRenew);
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // F06: un 422 que llega después de Esc no resucita el borrador descartado
    {
      let releaseOps;
      const opsGate = new Promise((r) => {
        releaseOps = r;
      });
      let opsHeld = false;
      const holdOps = async (route) => {
        if (route.request().method() === "POST") {
          opsHeld = true;
          await opsGate;
        }
        await continueSafe(route);
      };
      await page.route("**/api/scene/ops", holdOps);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("99999");
        await page.keyboard.press("Enter");
        const d = Date.now() + 3000;
        while (!opsHeld && Date.now() < d) await sleep(50);
        assert(opsHeld, "S5(-): F06: no salio el POST de X");
        await page.keyboard.press("Escape");
        await sleep(150);
        releaseOps();
        await sleep(900);
        const st6 = await page.evaluate(() => {
          const el = document.getElementById("f-x");
          const btn = document.querySelector('[data-testid="accion-principal"] button');
          return { inv: el && el.getAttribute("aria-invalid"), val: el && el.value, applyOff: !!(btn && btn.disabled) };
        });
        assert(
          st6.inv !== "true" && st6.val !== "99999" && !st6.applyOff,
          "S5(-): un 422 tardio resucito el borrador descartado con Esc (F06): " + JSON.stringify(st6)
        );
      } finally {
        await page.unroute("**/api/scene/ops", holdOps);
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // F06 (2): un éxito que llega tarde no borra el borrador escrito después del envío
    {
      let releaseOps2;
      const opsGate2 = new Promise((r) => {
        releaseOps2 = r;
      });
      let opsHeld2 = false;
      const holdOps2 = async (route) => {
        if (route.request().method() === "POST") {
          opsHeld2 = true;
          await opsGate2;
        }
        await continueSafe(route);
      };
      await page.route("**/api/scene/ops", holdOps2);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7300");
        await page.keyboard.press("Enter");
        const d = Date.now() + 3000;
        while (!opsHeld2 && Date.now() < d) await sleep(50);
        assert(opsHeld2, "S5(-): F06 (2): no salio el POST de X=7300");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7301");
        releaseOps2();
        await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7300;
        }, "F06 (2): X=7300 aplicado", 8000);
        await sleep(500);
        const vLate = await page.locator("#f-x").inputValue();
        assert(vLate === "7301", "S5(-): un exito tardio borro el borrador escrito despues del envio (F06): " + vLate);
      } finally {
        releaseOps2();
        await page.unroute("**/api/scene/ops", holdOps2);
        await page.keyboard.press("Escape");
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // N2: salir del campo con la respuesta de Intro aún en camino no vuelve a mandar ese valor
    // después: si la IA movió la entidad entretanto, su cambio se queda. Para que el documento de la
    // web siga viejo al salir (como con la máquina cargada), sin SSE y con las lecturas retenidas.
    {
      let releaseResp3;
      const respGate3 = new Promise((r) => {
        releaseResp3 = r;
      });
      let releaseScene3;
      const sceneGate3 = new Promise((r) => {
        releaseScene3 = r;
      });
      let firstOpsSeen = false;
      const holdResp3 = async (route) => {
        if (route.request().method() === "POST" && !firstOpsSeen) {
          firstOpsSeen = true;
          const resp = await route.fetch(); // llega al backend; solo se retiene la respuesta
          await respGate3;
          await route.fulfill({ response: resp });
          return;
        }
        await continueSafe(route);
      };
      const sseCut3 = async (route) => {
        await route.fulfill({ status: 503, contentType: "text/plain; charset=utf-8", body: "sse-cut" });
      };
      let holdSceneOn = false;
      const holdScene3 = async (route) => {
        if (holdSceneOn && route.request().method() === "GET") await sceneGate3;
        await continueSafe(route);
      };
      await page.route("**/api/events", sseCut3);
      await page.route("**/api/scene", holdScene3);
      await page.route("**/api/scene/ops", holdResp3);
      try {
        await page.goto(BASE + "/");
        await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: 10000 });
        await page.getByText("Reconectando…", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
        await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
        await activatePanel(page, "propiedades");
        holdSceneOn = true;
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7400");
        await page.keyboard.press("Enter");
        const snapA = await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7400;
        }, "N2: X=7400 en el backend", 8000);
        const zNow = snapA.doc.entities.find((x) => x.id === eid).z;
        await page.locator("#f-x").evaluate((el) => el.blur());
        const dRel3 = Date.now() + 5000;
        while (Date.now() < dRel3) {
          if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
          await sleep(80);
        }
        const rAi3 = await cmd({
          cmd: "ai_ops",
          label: "IA mueve mientras vuelve la respuesta",
          ops: [{ name: "entity.move", target: eid, args: { x: 7450, z: zNow } }],
        });
        assert(rAi3.ok, "S5(-): N2: ai_ops entity.move fallo: " + JSON.stringify(rAi3));
        releaseResp3();
        await sleep(300);
        holdSceneOn = false;
        releaseScene3();
        await sleep(1500);
        const snapN2 = await cmd({ cmd: "snapshot" });
        const xN2 = snapN2.doc.entities.find((x) => x.id === eid).x;
        assert(
          xN2 === 7450,
          "S5(-): salir del campo volvio a mandar X=7400 y piso el cambio de la IA (N2): x=" + xN2
        );
      } finally {
        releaseResp3();
        holdSceneOn = false;
        releaseScene3();
        await sleep(200);
        await page.unroute("**/api/scene/ops", holdResp3);
        await page.unroute("**/api/scene", holdScene3);
        await page.unroute("**/api/events", sseCut3);
      }
      // Vuelta al estudio con SSE para lo que sigue
      await page.goto(BASE + "/");
      await loginIfNeeded(context, page);
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
      await activatePanel(page, "propiedades");
    }

    // F01: X y luego Z con las lecturas de /api/scene retenidas; no se pierde X
    {
      let releaseScene;
      const sceneGate = new Promise((r) => {
        releaseScene = r;
      });
      const holdScene = async (route) => {
        if (route.request().method() === "GET") await sceneGate;
        await continueSafe(route);
      };
      await page.route("**/api/scene", holdScene);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7111");
        await page.keyboard.press("Tab");
        await waitEditable(page, "#f-z");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7222");
        await page.keyboard.press("Enter");
        await sleep(700);
      } finally {
        releaseScene();
        await sleep(300);
        await page.unroute("**/api/scene", holdScene);
      }
      const snapF1 = await waitForSnap((s) => {
        const e = s.doc.entities.find((x) => x.id === eid);
        return !!e && e.z === 7222;
      }, "F01: Z aplicado", 8000);
      const entF1 = snapF1.doc.entities.find((x) => x.id === eid);
      assert(entF1.x === 7111 && entF1.z === 7222, "S5(-): X y luego Z perdieron X (F01): " + JSON.stringify({ x: entF1.x, z: entF1.z }));
    }

    // ---- Regresiones de la ronda 2 de Sol del código (R2-01, R2-02, R2-04 y el NEGATIVO de Ctrl+Intro) ----
    const xOf = async () => (await cmd({ cmd: "snapshot" })).doc.entities.find((x) => x.id === eid);
    const releaseLeases = async () => {
      const dl = Date.now() + 5000;
      while (Date.now() < dl) {
        if ((await cmd({ cmd: "leases" })).leases.length === 0) return;
        await sleep(80);
      }
    };

    // R2-02: X=7100 con Intro mientras otra tanda está en camino, y después 7200 sin Intro: la
    // confirmación de 7100 sale igual; Esc descarta solo el 7200
    {
      let releaseA;
      const gateA = new Promise((r) => {
        releaseA = r;
      });
      let heldA = false;
      const holdFirstOps = async (route) => {
        if (route.request().method() === "POST" && !heldA) {
          heldA = true;
          await gateA; // la petición no llega al backend hasta soltarla
        }
        await continueSafe(route);
      };
      await page.route("**/api/scene/ops", holdFirstOps);
      try {
        await page.locator("#f-yaw").focus();
        await waitEditable(page, "#f-yaw");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("33");
        await page.keyboard.press("Enter");
        const dA = Date.now() + 3000;
        while (!heldA && Date.now() < dA) await sleep(50);
        assert(heldA, "S5(-): R2-02: no salio el POST del rumbo");
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7100");
        await page.keyboard.press("Enter");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7200");
        releaseA();
        await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7100;
        }, "R2-02: X=7100 confirmado con Intro", 8000).catch(async (err) => {
          const e = await xOf();
          throw new Error("S5(-): la confirmacion de X=7100 se perdio al escribir 7200 despues (R2-02): x=" + (e && e.x) + " · " + err.message);
        });
        await sleep(300);
        assert((await page.locator("#f-x").inputValue()) === "7200", "S5(-): R2-02: el borrador 7200 no siguio en el campo");
        await page.keyboard.press("Escape");
        await sleep(300);
        const vAfterEsc = await page.locator("#f-x").inputValue();
        const eAfterEsc = await xOf();
        assert(
          eAfterEsc.x === 7100 && vAfterEsc === "7100",
          "S5(-): tras Esc, X no se quedo en 7100 (R2-02): " + JSON.stringify({ x: eAfterEsc.x, campo: vAfterEsc })
        );
      } finally {
        releaseA();
        await sleep(200);
        await page.unroute("**/api/scene/ops", holdFirstOps);
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // NEGATIVO de la ronda 2: Ctrl+Intro con la confirmacion del campo aun en camino sigue hasta Aplicar
    {
      let releaseRespN;
      const gateRespN = new Promise((r) => {
        releaseRespN = r;
      });
      let seenN = false;
      const holdRespN = async (route) => {
        if (route.request().method() === "POST" && !seenN) {
          seenN = true;
          const resp = await route.fetch();
          await gateRespN;
          await route.fulfill({ response: resp });
          return;
        }
        await continueSafe(route);
      };
      let applyPostsN = 0;
      const onApplyN = (req) => {
        if (req.method() === "POST" && new URL(req.url()).pathname === "/api/apply") applyPostsN += 1;
      };
      await page.route("**/api/scene/ops", holdRespN);
      page.on("request", onApplyN);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7600");
        await page.keyboard.press("Enter");
        await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7600;
        }, "NEG-R2: X=7600 en el backend", 8000);
        const applyRespP = page.waitForResponse(
          (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
          { timeout: 8000 }
        );
        await page.keyboard.press("Control+Enter");
        await sleep(200);
        releaseRespN();
        const applyResp = await applyRespP.catch(() => null);
        assert(
          applyResp && applyResp.status() === 200 && applyPostsN === 1,
          "S5(-): Ctrl+Intro con la confirmacion del campo en camino no siguio hasta Aplicar (NEGATIVO R2): " +
            JSON.stringify({ status: applyResp && applyResp.status(), posts: applyPostsN })
        );
      } finally {
        releaseRespN();
        page.off("request", onApplyN);
        await sleep(200);
        await page.unroute("**/api/scene/ops", holdRespN);
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // R2-04: una tanda que no vuelve nunca no deja la fila parada: pasado el plazo sale el aviso y la
    // edicion siguiente se manda
    {
      let releaseHang;
      const gateHang = new Promise((r) => {
        releaseHang = r;
      });
      let hung = false;
      let hungRoute = null;
      const hangFirstOps = async (route) => {
        if (route.request().method() === "POST" && !hung) {
          hung = true;
          hungRoute = route;
          await gateHang; // no se suelta nunca durante la prueba
          return;
        }
        await continueSafe(route);
      };
      await page.route("**/api/scene/ops", hangFirstOps);
      try {
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7500");
        await page.keyboard.press("Enter");
        await page
          .locator('[data-aviso="sin-respuesta"]')
          .first()
          .waitFor({ state: "visible", timeout: 16000 })
          .catch(() => {
            throw new Error("S5(-): una tanda sin respuesta no dio el aviso sin-respuesta en 16 s (R2-04)");
          });
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7501");
        await page.keyboard.press("Enter");
        await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7501;
        }, "R2-04: X=7501 tras el plazo", 8000).catch(async (err) => {
          const e = await xOf();
          throw new Error("S5(-): tras una tanda sin respuesta la fila siguio parada (R2-04): x=" + (e && e.x) + " · " + err.message);
        });
      } finally {
        releaseHang();
        if (hungRoute) {
          try {
            await hungRoute.abort();
          } catch (e) {
            // la página ya canceló esa petición
          }
        }
        await page.unroute("**/api/scene/ops", hangFirstOps);
        await page.locator("#f-x").evaluate((el) => el.blur());
        await sleep(200);
      }
    }

    // R2-01: sin SSE y con las lecturas de la escena fallando, X y luego Z no pierden X: Z no sale
    // (aviso escena-sin-releer y su borrador se queda) y sale bien cuando la lectura vuelve
    {
      let fail503 = false;
      const sceneFail = async (route) => {
        if (fail503 && route.request().method() === "GET") {
          await route.fulfill({ status: 503, contentType: "application/json; charset=utf-8", body: '{"ok":false,"code":"internal","msg":"x"}' });
          return;
        }
        await continueSafe(route);
      };
      const sseCut4 = async (route) => {
        await route.fulfill({ status: 503, contentType: "text/plain; charset=utf-8", body: "sse-cut" });
      };
      await page.route("**/api/events", sseCut4);
      await page.route("**/api/scene", sceneFail);
      try {
        await releaseLeases();
        await page.goto(BASE + "/");
        await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: 10000 });
        await page.getByText("Reconectando…", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
        await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
        await activatePanel(page, "propiedades");
        const before = await xOf();
        fail503 = true;
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7311");
        await page.keyboard.press("Tab");
        await waitEditable(page, "#f-z");
        await page.keyboard.press("Control+a");
        await page.keyboard.type("7322");
        await page.keyboard.press("Enter");
        await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.x === 7311;
        }, "R2-01: X=7311", 8000);
        await page
          .locator('[data-aviso="escena-sin-releer"]')
          .first()
          .waitFor({ state: "visible", timeout: 8000 })
          .catch(() => {
            throw new Error("S5(-): R2-01: sin lectura de la escena no salio el aviso escena-sin-releer");
          });
        const mid = await xOf();
        assert(
          mid.x === 7311 && mid.z === before.z,
          "S5(-): sin lectura de la escena, Z salio con la X vieja y la perdio (R2-01): " +
            JSON.stringify({ x: mid.x, z: mid.z, zAntes: before.z })
        );
        assert((await page.locator("#f-z").inputValue()) === "7322", "S5(-): R2-01: el borrador de Z no se quedo en su campo");
        fail503 = false;
        await page.keyboard.press("Enter");
        const fin = await waitForSnap((s) => {
          const e = s.doc.entities.find((x) => x.id === eid);
          return !!e && e.z === 7322;
        }, "R2-01: Z=7322 cuando vuelve la lectura", 8000);
        const eFin = fin.doc.entities.find((x) => x.id === eid);
        assert(eFin.x === 7311 && eFin.z === 7322, "S5(-): R2-01: al volver la lectura, X y Z no quedaron bien: " + JSON.stringify({ x: eFin.x, z: eFin.z }));

        // R2-05: todavía sin SSE. X=7400 con la respuesta retenida; volver a escribir 7311 (el valor
        // que la web aún cree que hay) y Ctrl+Intro: X tiene que acabar en 7311 y Aplicar dar 200
        let releaseR5;
        const gateR5 = new Promise((r) => {
          releaseR5 = r;
        });
        let seenR5 = false;
        const holdRespR5 = async (route) => {
          if (route.request().method() === "POST" && !seenR5) {
            seenR5 = true;
            const resp = await route.fetch();
            await gateR5;
            await route.fulfill({ response: resp });
            return;
          }
          await continueSafe(route);
        };
        await page.route("**/api/scene/ops", holdRespR5);
        try {
          await page.locator("#f-x").focus();
          await waitEditable(page, "#f-x");
          await page.keyboard.press("Control+a");
          await page.keyboard.type("7400");
          await page.keyboard.press("Enter");
          await waitForSnap((s) => {
            const e = s.doc.entities.find((x) => x.id === eid);
            return !!e && e.x === 7400;
          }, "R2-05: X=7400 en el backend", 8000);
          await page.keyboard.press("Control+a");
          await page.keyboard.type("7311");
          const applyRespR5 = page.waitForResponse(
            (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
            { timeout: 10000 }
          );
          await page.keyboard.press("Control+Enter");
          await sleep(300);
          releaseR5();
          const respR5 = await applyRespR5.catch(() => null);
          await sleep(500);
          const eR5 = await xOf();
          assert(
            eR5.x === 7311 && respR5 && respR5.status() === 200,
            "S5(-): Ctrl+Intro con un «sin cambios» decidido sobre el documento viejo perdio X=7311 (R2-05): " +
              JSON.stringify({ x: eR5.x, apply: respR5 && respR5.status() })
          );
        } finally {
          releaseR5();
          await sleep(200);
          await page.unroute("**/api/scene/ops", holdRespR5);
        }
      } finally {
        fail503 = false;
        await page.unroute("**/api/scene", sceneFail);
        await page.unroute("**/api/events", sseCut4);
      }
    }

    console.log("S5 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S6: Añadir y presupuesto (A6)
// ============================================================================
async function runS6(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    await activatePanel(page, "anadir");
    const anadir = page.locator('[data-panel="anadir"]');
    const tablist = anadir.locator('[role="tablist"][aria-label="Tipo"]');
    await tablist.waitFor({ state: "visible", timeout: 5000 });

    // Positivo: pestañas que caben en el panel (pruebas-mejoras.js:1586)
    for (const w of [1280, 1366, 1600]) {
      await page.setViewportSize({ width: w, height: 720 });
      await sleep(120);
      const fit = await tablist.evaluate((c) => {
        const r = c.getBoundingClientRect();
        const tabs = Array.from(c.querySelectorAll('[role="tab"], button'));
        const out = tabs.filter((b) => {
          const q = b.getBoundingClientRect();
          return q.left < r.left - 1 || q.right > r.right + 1;
        });
        return { n: tabs.length, out: out.length, scroll: c.scrollWidth > c.clientWidth + 1 };
      });
      assert(
        fit.n === 4 && fit.out === 0 && !fit.scroll,
        "S6(+): pestañas de Añadir no caben a " + w + " px: " + JSON.stringify(fit)
      );
    }
    await page.setViewportSize({ width: 1280, height: 720 });

    // Negativo: Actores existe, desactivada, con «Llega con F3» en su title
    const actoresTab = tablist.locator('[role="tab"], button', { hasText: /^Actores\b/ }).first();
    const actCheck = await actoresTab.evaluate((el) => ({
      disabled: !!(el.disabled || el.getAttribute("aria-disabled") === "true"),
      title: el.getAttribute("title") || "",
    }));
    assert(
      actCheck.disabled && /Llega con F3/.test(actCheck.title),
      "S6(-): pestaña Actores no desactivada o sin title 'Llega con F3': " + JSON.stringify(actCheck)
    );

    // Positivo: el buscador #libq se conserva al cambiar de pestaña
    await page.locator("#libq").fill("Barrel");
    await tablist.locator('[role="tab"], button', { hasText: /^Infectados\b/ }).first().click();
    await sleep(100);
    assert((await page.locator("#libq").inputValue()) === "Barrel", "S6(+): #libq no se conservo en Infectados");
    await tablist.locator('[role="tab"], button', { hasText: /^Objetos\b/ }).first().click();
    await sleep(100);
    assert((await page.locator("#libq").inputValue()) === "Barrel", "S6(+): #libq no se conservo al volver a Objetos");
    await page.locator("#libq").fill("");

    // Positivo: vista previa con raton y teclado, «Sin captura…» y «Sin tamaño en el catálogo», 0 img / url()
    const itemBarrel = anadir.locator('[data-cls="Barrel_Red"]').first();
    await itemBarrel.hover();
    await sleep(120);
    const prevHover = await page.locator("#libPrev").innerText();
    assert(
      prevHover.includes("Barrel_Red") &&
        /Sin captura del juego todav[íi]a/.test(prevHover) &&
        /Sin tama[ñn]o en el cat[áa]logo/.test(prevHover),
      "S6(+): #libPrev con raton incompleto: " + prevHover
    );

    await page.mouse.move(2, 2);
    const itemCrate = anadir.locator('[data-cls="WoodenCrate"]').first();
    await itemCrate.focus();
    await sleep(120);
    const prevKey = await page.locator("#libPrev").innerText();
    assert(
      prevKey.includes("WoodenCrate") &&
        /Sin captura del juego todav[íi]a/.test(prevKey) &&
        /Sin tama[ñn]o en el cat[áa]logo/.test(prevKey),
      "S6(+): #libPrev con teclado no actualizo a WoodenCrate: " + prevKey
    );

    const noMedia = await anadir.evaluate((col) => {
      const imgs = col.querySelectorAll("img, picture, video, iframe, object, embed, image").length;
      const urls = [col, ...col.querySelectorAll("*")].filter((el) =>
        [null, "::before", "::after"].some((ps) => /url\(/.test(getComputedStyle(el, ps).backgroundImage || ""))
      ).length;
      return { imgs, urls };
    });
    assert(noMedia.imgs === 0 && noMedia.urls === 0, "S6(+): Añadir pinta imagenes o fondos url(): " + JSON.stringify(noMedia));

    // Positivo: medidores «n / tope» iguales a conteos del snapshot y topes de /api/catalog + «Tope total aún sin certificar»
    await cmd({
      cmd: "ai_ops",
      label: "Poblar presupuesto",
      ops: [
        { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "B1", x: 7000, z: 7000, yaw: 0 } },
        { name: "entity.add", args: { kind: "infectado", cls: "ZmbM_FarmerFat_Brown", name: "Z1", x: 7010, z: 7000, yaw: 0 } },
      ],
    });
    await page.waitForFunction(
      () => {
        const bObj = document.querySelector('[data-budget="objeto"]');
        const bZmb = document.querySelector('[data-budget="infectado"]');
        return !!bObj && /1\s*\/\s*20/.test(bObj.textContent || "") && !!bZmb && /1\s*\/\s*10/.test(bZmb.textContent || "");
      },
      null,
      { timeout: 5000 }
    );
    assert(/0\s*\/\s*3/.test(await page.locator('[data-budget="animal"]').innerText()), "S6(+): budget animal != 0 / 3");
    assert(/0\s*\/\s*2/.test(await page.locator('[data-budget="actor"]').innerText()), "S6(+): budget actor != 0 / 2");
    const anadirBudgetTxt = await anadir.innerText();
    assert(
      /2 entidades\s*·\s*Tope total a[úu]n sin certificar/.test(anadirBudgetTxt),
      "S6(+): falta '2 entidades · Tope total aún sin certificar': " + anadirBudgetTxt
    );

    // Negativo (mata Xn): Con 3 animales -> filas aria-disabled, Intro y clic -> 0 POST /api/scene/ops, nunca «ilimitado», foco recorre lista sin caer a body
    const addAnimals = await cmd({
      cmd: "ai_ops",
      label: "Tope animales",
      ops: [
        { name: "entity.add", args: { kind: "animal", cls: "Animal_CervusElaphus", name: "A1", x: 7100, z: 7100, yaw: 0 } },
        { name: "entity.add", args: { kind: "animal", cls: "Animal_CapreolusCapreolus", name: "A2", x: 7110, z: 7100, yaw: 0 } },
        { name: "entity.add", args: { kind: "animal", cls: "Animal_SusScrofa", name: "A3", x: 7120, z: 7100, yaw: 0 } },
      ],
    });
    assert(addAnimals.ok, "S6(-): ai_ops 3 animales fallo");

    await tablist.locator('[role="tab"], button', { hasText: /^Animales\b/ }).first().click();
    await page.waitForFunction(
      () => {
        const bAni = document.querySelector('[data-budget="animal"]');
        return !!bAni && /3\s*\/\s*3/.test(bAni.textContent || "");
      },
      null,
      { timeout: 5000 }
    );

    const animalRowsState = await anadir.evaluate((col) => {
      const rows = Array.from(col.querySelectorAll("[data-cls]"));
      return {
        n: rows.length,
        allAriaDisabled: rows.length > 0 && rows.every((r) => r.getAttribute("aria-disabled") === "true"),
        txt: col.innerText || "",
      };
    });
    assert(
      animalRowsState.n >= 3 && animalRowsState.allAriaDisabled,
      "S6(-): al tope de animales no todas las filas llevan aria-disabled=true: " + JSON.stringify(animalRowsState)
    );
    assert(
      !/ilimitad|sin tope|∞/i.test(animalRowsState.txt),
      "S6(-): el presupuesto presenta el total como ilimitado"
    );

    let capPosts = 0;
    const onCapReq = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") {
        capPosts += 1;
      }
    };
    page.on("request", onCapReq);
    try {
      const firstAni = anadir.locator("[data-cls]").first();
      await firstAni.click({ force: true });
      await sleep(150);
      await firstAni.focus();
      await page.keyboard.press("Space");
      await page.keyboard.press("Enter");
      await sleep(300);
      assert(capPosts === 0, "S6(-): al tope se envio POST /api/scene/ops (Xn): " + capPosts);
      const snapCap = await cmd({ cmd: "snapshot" });
      assert(
        snapCap.doc.entities.filter((e) => e.kind === "animal").length === 3,
        "S6(-): se supero el tope de 3 animales"
      );

      // El foco recorre la lista al tope y nunca cae a body
      await page.locator("#libq").focus();
      await page.keyboard.press("ArrowDown");
      let onRow = await page.evaluate(() => !!(document.activeElement && document.activeElement.hasAttribute("data-cls")));
      const stepKey = onRow ? "ArrowDown" : "Tab";
      if (!onRow) await page.keyboard.press("Tab");

      const visited = [];
      for (let i = 0; i < 3; i++) {
        const st = await page.evaluate(() => {
          const a = document.activeElement;
          const prev = document.getElementById("libPrev");
          return {
            isBody: !a || a === document.body,
            cls: a && a.getAttribute ? a.getAttribute("data-cls") : null,
            prevText: prev ? prev.innerText : "",
          };
        });
        assert(!st.isBody, "S6(-): el foco cayo a document.body recorriendo Añadir al tope");
        assert(st.cls && st.prevText.includes(st.cls), "S6(-): el foco al tope no enseña vista previa: " + JSON.stringify(st));
        visited.push(st.cls);
        if (i < 2) {
          await page.keyboard.press(stepKey);
          await sleep(80);
        }
      }
      assert(new Set(visited).size >= 2, "S6(-): el teclado no recorrio distintas filas al tope: " + JSON.stringify(visited));
    } finally {
      page.off("request", onCapReq);
    }

    console.log("S6 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S7: Colocar solo con teclado (D1 sin mapa, D4)
// ============================================================================
async function tabToLibqKeyboardOnly(page) {
  for (let i = 0; i < 35; i++) {
    const state = await page.evaluate(() => {
      const a = document.activeElement;
      if (!a) return { id: "", text: "" };
      return { id: a.id || "", text: (a.textContent || "").trim() };
    });
    if (state.id === "libq") return;
    if (/A[ñn]ade tu primer objeto/.test(state.text)) {
      await page.keyboard.press("Enter");
      await sleep(120);
      for (let j = 0; j < 10; j++) {
        const idNow = await page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
        if (idNow === "libq") return;
        await page.keyboard.press("Tab");
      }
    }
    await page.keyboard.press("Tab");
  }
  // Si Añadir estaba oculta y no habia CTA, abrir pestaña Añadir con teclado desde la pestaña activa Propiedades
  for (let i = 0; i < 35; i++) {
    const tabPanelId = await page.evaluate(
      () => (document.activeElement && document.activeElement.dataset && document.activeElement.dataset.tabPanelId) || ""
    );
    if (tabPanelId === "propiedades") {
      await page.keyboard.press("ArrowRight");
      await page.keyboard.press("Enter");
      await sleep(120);
      break;
    }
    await page.keyboard.press("Tab");
  }
  for (let i = 0; i < 15; i++) {
    const idNow = await page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
    if (idNow === "libq") return;
    await page.keyboard.press("Tab");
  }
  throw new Error("S7(+): no se pudo llegar a #libq solo con teclado");
}

async function runS7(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    // Positivo: SIN RATON: Tab hasta #libq, escribir, ArrowDown, Espacio, Intro
    await tabToLibqKeyboardOnly(page);

    // Negativo previo: Intro sin fila elegida -> 0 peticiones
    let idleEnterReqs = 0;
    const onIdleEnter = (req) => {
      if (isEffectPost(req)) idleEnterReqs += 1;
    };
    page.on("request", onIdleEnter);
    await page.keyboard.press("Enter");
    await sleep(300);
    page.off("request", onIdleEnter);
    assert(idleEnterReqs === 0, "S7(-): Intro sin fila elegida mando peticiones: " + idleEnterReqs);

    // Continuar flujo solo con teclado
    await page.keyboard.type("Barrel_Red");
    await sleep(100);
    await page.keyboard.press("ArrowDown");
    await sleep(80);
    await page.keyboard.press("Space");
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-panel="anadir"] [data-cls="Barrel_Red"]');
        return !!el && el.getAttribute("aria-pressed") === "true";
      },
      null,
      { timeout: 3000 }
    );
    await page.keyboard.press("Enter");

    const snapPlaced = await waitForSnap((s) => s.doc.entities.length === 1, "colocar Barrel_Red con teclado");
    const placed = snapPlaced.doc.entities[0];
    assert(
      placed.cls === "Barrel_Red" && placed.x === 7680 && placed.z === 7680 && placed.yaw === 0,
      "S7(+): entidad colocada distinta de (7680, 7680, yaw 0): " + JSON.stringify(placed)
    );

    // Queda seleccionada, Propiedades en primer plano y el foco en X
    await page.waitForFunction(
      (eid) => {
        const row = document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]');
        const fx = document.getElementById("f-x");
        return !!row && row.getAttribute("aria-selected") === "true" && document.activeElement === fx;
      },
      placed.id,
      { timeout: 5000 }
    );
    await waitEditable(page, "#f-x");

    // X, Tab, Z, Intro -> el snapshot cambia (todo sin raton)
    await page.keyboard.press("Control+a");
    await page.keyboard.type("7712");
    await page.keyboard.press("Tab");
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "f-z", null, {
      timeout: 3000,
    });
    await waitEditable(page, "#f-z");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("7734");
    await page.keyboard.press("Enter");

    await waitForSnap(
      (s) => s.doc.entities[0] && s.doc.entities[0].x === 7712 && s.doc.entities[0].z === 7734,
      "mover X=7712, Z=7734 con teclado"
    );

    // Ctrl+Intro -> op-N Pendiente con origen backend en Actividad
    const opsBeforeApply = await cmd({ cmd: "count_ops" });
    await page.keyboard.press("Control+Enter");
    await page.waitForFunction(
      () => {
        const rows = Array.from(document.querySelectorAll('[data-panel="actividad"] tbody tr[data-op-id]'));
        if (!rows.length) return false;
        const cells = Array.from(rows[0].querySelectorAll("td")).map((td) => (td.textContent || "").trim());
        return cells[2] === "Pendiente" && cells[4] === "backend";
      },
      null,
      { timeout: 5000 }
    );
    const opsAfterApply = await cmd({ cmd: "count_ops" });
    assert(opsAfterApply.n === opsBeforeApply.n + 1, "S7(+): Ctrl+Intro no creo exactamente una orden");

    // Negativo (mata Xw): teclas mantenidas (keyboard.down dos veces sin soltar, segunda con repeat: true)
    await activatePanel(page, "anadir");
    await page.locator("#libq").fill("");
    const crateRow = page.locator('[data-panel="anadir"] [data-cls="WoodenCrate"]').first();
    await crateRow.focus();
    await page.keyboard.press("Space");
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-panel="anadir"] [data-cls="WoodenCrate"]');
        return !!el && el.getAttribute("aria-pressed") === "true";
      },
      null,
      { timeout: 3000 }
    );

    let placeRepeatPosts = 0;
    const onPlaceRepeat = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") {
        placeRepeatPosts += 1;
      }
    };
    page.on("request", onPlaceRepeat);
    try {
      const firstPlaceRespP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/scene/ops" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await page.keyboard.down("Enter");
      const firstPlaceResp = await firstPlaceRespP;
      assert(firstPlaceResp.status() === 200, "S7(-): primera colocacion no dio 200: " + firstPlaceResp.status());
      await waitForSnap((s) => s.doc.entities.length >= 2, "primera colocacion con Enter mantenido");
      await sleep(200);
      await page.keyboard.down("Enter"); // repeat: true despues de acabar la primera peticion
      await sleep(300);
      await page.keyboard.up("Enter");
    } finally {
      page.off("request", onPlaceRepeat);
    }
    const snapAfterRepeatPlace = await cmd({ cmd: "snapshot" });
    assert(
      placeRepeatPosts === 1 && snapAfterRepeatPlace.doc.entities.length === 2,
      "S7(-): Intro mantenido coloco mas de una vez: posts=" +
        placeRepeatPosts +
        ", ents=" +
        snapAfterRepeatPlace.doc.entities.length
    );

    // Salir del campo para que Ctrl+Intro mantenido pruebe aplicar limpio sin guardas en vuelo
    if ((await page.evaluate(() => document.activeElement && document.activeElement.tagName)) === "INPUT") {
      await page.evaluate(() => document.activeElement.blur());
      await sleep(150);
    }
    await page.waitForFunction(
      () => {
        const b = document.querySelector('[data-testid="accion-principal"] button');
        return !!b && !b.disabled;
      },
      null,
      { timeout: 5000 }
    );

    let applyRepeatPosts = 0;
    const onApplyRepeat = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/apply") {
        applyRepeatPosts += 1;
      }
    };
    const opsBeforeRepeat = await cmd({ cmd: "count_ops" });
    page.on("request", onApplyRepeat);
    try {
      const firstApplyRespP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await page.keyboard.down("Control");
      await page.keyboard.down("Enter");
      const firstApplyResp = await firstApplyRespP;
      assert(firstApplyResp.status() === 200, "S7(-): primer POST /api/apply no dio 200: " + firstApplyResp.status());
      await page.waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 5000 }
      );
      await sleep(50);
      await page.keyboard.down("Enter"); // repeat: true despues del 200 y con Aplicar de nuevo activo (mata Xw)
      await sleep(300);
      await page.keyboard.up("Enter");
      await page.keyboard.up("Control");
    } finally {
      page.off("request", onApplyRepeat);
    }
    const opsAfterRepeat = await cmd({ cmd: "count_ops" });
    assert(
      applyRepeatPosts === 1 && opsAfterRepeat.n === opsBeforeRepeat.n + 1,
      "S7(-): Ctrl+Intro mantenido repitio POST /api/apply (Xw): posts=" + applyRepeatPosts
    );

    // Negativo: Intro con el foco en el buscador #libq no coloca dos veces
    await activatePanel(page, "anadir");
    const blueRow = page.locator('[data-panel="anadir"] [data-cls="Barrel_Blue"]').first();
    await blueRow.focus();
    await page.keyboard.press("Space");
    await page.locator("#libq").focus();
    let libqEnterPosts = 0;
    const onLibqEnter = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") libqEnterPosts += 1;
    };
    page.on("request", onLibqEnter);
    await page.keyboard.press("Enter");
    await sleep(350);
    page.off("request", onLibqEnter);
    assert(libqEnterPosts <= 1, "S7(-): Intro en #libq coloco dos veces: " + libqEnterPosts);
    await page.keyboard.press("Escape");

    // Negativo: recargar enseña la misma escena
    const snapBeforeReload = await cmd({ cmd: "snapshot" });
    await page.reload();
    await loginIfNeeded(context, page);
    for (const ent of snapBeforeReload.doc.entities) {
      await page
        .locator('[data-panel="jerarquia"] [data-entity-id="' + ent.id + '"]')
        .waitFor({ state: "visible", timeout: 5000 });
    }
    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + placed.id + '"]').click();
    await activatePanel(page, "propiedades");
    assert(
      /^7712\b/.test((await page.locator("#f-x").inputValue()).replace(/\./g, "")) &&
        /^7734\b/.test((await page.locator("#f-z").inputValue()).replace(/\./g, "")),
      "S7(-): tras recargar no coinciden las coordenadas guardadas"
    );

    // F03 (revisión de Sol): con el foco en un campo, Ctrl+Intro mantenido tampoco repite Aplicar
    await page.locator("#f-x").focus();
    await waitEditable(page, "#f-x");
    let fieldApplyPosts = 0;
    const onFieldApply = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/apply") fieldApplyPosts += 1;
    };
    page.on("request", onFieldApply);
    try {
      const firstFieldApplyP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
        { timeout: 8000 }
      );
      await page.keyboard.down("Control");
      await page.keyboard.down("Enter");
      const r1 = await firstFieldApplyP;
      assert(r1.status() === 200, "S7(-): F03: el primer Aplicar desde el campo no dio 200: " + r1.status());
      await page.waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 5000 }
      );
      await sleep(50);
      await page.keyboard.down("Enter"); // repeat: true con el foco todavía en #f-x
      await sleep(300);
      await page.keyboard.up("Enter");
      await page.keyboard.up("Control");
    } finally {
      page.off("request", onFieldApply);
    }
    assert(fieldApplyPosts === 1, "S7(-): Ctrl+Intro mantenido en un campo repitio Aplicar (F03): " + fieldApplyPosts);

    console.log("S7 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S8: Atajos (D4, CU-32)
// ============================================================================
async function openShortcutsDialogKeyboardOnly(page) {
  const trail = [];
  const where = () =>
    page.evaluate(() => {
      const a = document.activeElement;
      if (!a) return "-";
      return (a.tagName + (a.id ? "#" + a.id : "") + ":" + (a.textContent || "").trim().slice(0, 24)).replace(/\s+/g, " ");
    });
  await page.keyboard.press("Escape");
  for (let i = 0; i < 40; i++) {
    const isTools = await page.evaluate(() => {
      const a = document.activeElement;
      return !!a && a.tagName === "BUTTON" && /^Herramientas\b/.test((a.textContent || "").trim());
    });
    if (isTools) break;
    trail.push("T:" + (await where()));
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Enter");
  await sleep(150);

  let reached = false;
  for (let i = 0; i < 16; i++) {
    const txt = await page.evaluate(() => (document.activeElement && document.activeElement.textContent) || "");
    if (/Atajos de teclado/.test(txt)) {
      reached = true;
      break;
    }
    trail.push("D:" + (await where()));
    await page.keyboard.press("ArrowDown");
  }
  if (!reached) {
    for (let i = 0; i < 20; i++) {
      const txt = await page.evaluate(() => (document.activeElement && document.activeElement.textContent) || "");
      if (/Atajos de teclado/.test(txt)) {
        reached = true;
        break;
      }
      trail.push("T2:" + (await where()));
      await page.keyboard.press("Tab");
    }
  }
  assert(reached, "S8(+): no se alcanzo 'Atajos de teclado…' con teclado; foco: " + trail.slice(-30).join(" | "));
  await page.keyboard.press("Enter");
  const dlg = page.locator('[role="dialog"][aria-modal="true"]');
  await dlg.waitFor({ state: "visible", timeout: 5000 });
  return dlg;
}

async function assignShortcutByKeyboard(page, actionId, keyToPress) {
  let found = false;
  for (let i = 0; i < 45; i++) {
    const hit = await page.evaluate((act) => {
      const a = document.activeElement;
      if (!a || a.tagName !== "BUTTON") return null;
      const row = a.closest('[data-action="' + act + '"]');
      if (!row) return null;
      return {
        label: a.getAttribute("aria-label") || (a.textContent || "").trim(),
      };
    }, actionId);
    if (hit) {
      assert(
        !/^Aplicar\b/i.test(hit.label) && /Cambiar/i.test(hit.label),
        "S8(+): nombre accesible de Cambiar invalido en " + actionId + ": " + hit.label
      );
      found = true;
      break;
    }
    await page.keyboard.press("Tab");
  }
  assert(found, "S8(+): no se alcanzo con Tab el boton Cambiar de " + actionId);

  // Se espera el POST que lleva esta tecla, no uno cualquiera (un guardado del layout podía colarse),
  // y la tecla se pulsa cuando el diálogo ya está capturando, no tras una espera fija.
  const expectCombo = keyToPress.length === 1 ? keyToPress.toUpperCase() : keyToPress;
  const profRespP = page.waitForResponse(
    (r) => {
      if (!r.url().endsWith("/api/profile") || r.request().method() !== "POST") return false;
      try {
        const b = JSON.parse(r.request().postData() || "{}");
        return !!b.keymap && b.keymap[actionId] === expectCombo;
      } catch (e) {
        return false;
      }
    },
    { timeout: 8000 }
  );
  await page.keyboard.press("Enter");
  await page.locator("#kconf").waitFor({ state: "visible", timeout: 3000 });
  await page.keyboard.press(keyToPress);
  const profResp = await profRespP;
  assert(profResp.status() === 200, "S8(+): POST /api/profile al asignar " + actionId + " no dio 200");
}

async function runS8(browser) {
  await resetBackendState();
  const { context, page } = await openStudio(browser);
  try {
    // Positivo 1: Reasignar colocar -> G, aplicar -> Shift+F8, deshacer -> F2 y rehacer -> F3 solo con teclado (mata Xo)
    const dlg = await openShortcutsDialogKeyboardOnly(page);
    await assignShortcutByKeyboard(page, "colocar", "g");
    await assignShortcutByKeyboard(page, "aplicar", "Shift+F8");
    await assignShortcutByKeyboard(page, "deshacer", "F2");
    await assignShortcutByKeyboard(page, "rehacer", "F3");
    await page.keyboard.press("Escape");
    await dlg.waitFor({ state: "hidden", timeout: 5000 });

    const prof1 = await cmd({ cmd: "profile_read" });
    assert(prof1 && prof1.text, "S8(+): profile_read vacio tras reasignar 4 atajos");
    const prof1Json = JSON.parse(prof1.text);
    assert(
      prof1Json.keymap.colocar === "G" &&
        prof1Json.keymap.aplicar === "Shift+F8" &&
        prof1Json.keymap.deshacer === "F2" &&
        prof1Json.keymap.rehacer === "F3",
      "S8(+): keymap guardado incorrecto: " + JSON.stringify(prof1Json.keymap)
    );
    assert(
      !prof1.text.includes(HUMAN_KEY) && ![...seenCsrf].some((c) => c && prof1.text.includes(c)),
      "S8(+): secreto presente en profile_read"
    );

    // Recargar -> probar que G coloca, Shift+F8 aplica, F2 deshace y F3 rehace; y que Intro / Ctrl+Intro ya no hacen nada
    await page.reload();
    await loginIfNeeded(context, page);

    await activatePanel(page, "anadir");
    const barrel = page.locator('[data-panel="anadir"] [data-cls="Barrel_Red"]').first();
    await barrel.focus();
    await page.keyboard.press("Space");
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-panel="anadir"] [data-cls="Barrel_Red"]');
        return !!el && el.getAttribute("aria-pressed") === "true";
      },
      null,
      { timeout: 3000 }
    );

    // Negativo: Intro y Ctrl+Intro ya no hacen nada tras reasignar (0 peticiones)
    let oldKeysPosts = 0;
    const onOldKeys = (req) => {
      if (isEffectPost(req)) oldKeysPosts += 1;
    };
    page.on("request", onOldKeys);
    await page.keyboard.press("Enter");
    await sleep(250);
    await page.keyboard.press("Control+Enter");
    await sleep(250);
    page.off("request", onOldKeys);
    assert(oldKeysPosts === 0, "S8(-): Intro o Ctrl+Intro siguieron actuando tras reasignar: " + oldKeysPosts);

    // Negativo (mata Xq): «G» en #libq escribe la letra y no coloca
    await page.locator("#libq").focus();
    let libqGPosts = 0;
    const onLibqG = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/scene/ops") libqGPosts += 1;
    };
    page.on("request", onLibqG);
    await page.keyboard.press("g");
    await sleep(250);
    page.off("request", onLibqG);
    assert(
      (await page.locator("#libq").inputValue()).toLowerCase() === "g" && libqGPosts === 0,
      "S8(-): pulsar G en #libq coloco o no escribio la letra (Xq)"
    );
    await page.locator("#libq").fill("");
    await barrel.focus();
    if ((await barrel.getAttribute("aria-pressed")) !== "true") {
      await page.keyboard.press("Space");
    }

    // G coloca
    await page.keyboard.press("g");
    const snapG = await waitForSnap((s) => s.doc.entities.length === 1, "colocar con G");
    const placedId = snapG.doc.entities[0].id;
    const placedName = snapG.doc.entities[0].name;
    // §6.3: la web pone el foco en X cuando el documento trae lo nuevo; hay que esperar a ese foco
    // antes de quitarlo, o F2 llega con el foco en un campo y, con razón, no actúa (§6.2).
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "f-x", null, {
      timeout: 5000,
    });
    await page.locator("#f-x").evaluate((el) => el && el.blur());
    await page.waitForFunction(() => !document.activeElement || document.activeElement.id !== "f-x", null, {
      timeout: 3000,
    });
    await sleep(150);

    // F2 deshace y F3 rehace
    await page.keyboard.press("F2");
    await waitForSnap((s) => s.doc.entities.length === 0, "deshacer con F2");
    await page.keyboard.press("F3");
    await waitForSnap((s) => s.doc.entities.length === 1, "rehacer con F3");

    // Shift+F8 aplica + negativo mantenido (repeat -> un solo POST /api/apply, mata Xw)
    await page.waitForFunction(
      () => {
        const b = document.querySelector('[data-testid="accion-principal"] button');
        return !!b && !b.disabled;
      },
      null,
      { timeout: 5000 }
    );
    let shiftF8Posts = 0;
    const onShiftF8 = (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/api/apply") shiftF8Posts += 1;
    };
    const opsBeforeSF8 = await cmd({ cmd: "count_ops" });
    page.on("request", onShiftF8);
    try {
      const sf8RespP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await page.keyboard.down("Shift");
      await page.keyboard.down("F8");
      const sf8Resp = await sf8RespP;
      assert(sf8Resp.status() === 200, "S8(-): primer POST /api/apply con Shift+F8 no dio 200: " + sf8Resp.status());
      await page.waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 5000 }
      );
      await sleep(50);
      await page.keyboard.down("F8"); // repeat: true despues del 200 y con Aplicar de nuevo activo (mata Xw)
      await sleep(300);
      await page.keyboard.up("F8");
      await page.keyboard.up("Shift");
    } finally {
      page.off("request", onShiftF8);
    }
    const opsAfterSF8 = await cmd({ cmd: "count_ops" });
    assert(
      shiftF8Posts === 1 && opsAfterSF8.n === opsBeforeSF8.n + 1,
      "S8(-): Mayus+F8 mantenido repitio POST /api/apply (Xw): " + shiftF8Posts
    );

    // Positivo 2 (Reemplazar, mata Xp y XC) + Negativos de choques y navegador (mata Xv y Xr)
    await clickToolsItem(page, /Atajos de teclado/);
    await dlg.waitFor({ state: "visible", timeout: 5000 });

    // Choque reemplazable: duplicar -> F2 choca con Deshacer (opcional)
    await dlg.locator('[data-action="duplicar"] button', { hasText: /Cambiar/ }).click();
    await sleep(60);
    await page.keyboard.press("F2");
    const kconf = page.locator("#kconf");
    await kconf.waitFor({ state: "visible", timeout: 5000 });
    const kconfTxt1 = await kconf.innerText();
    assert(
      /Reemplazar/.test(kconfTxt1) && /Cancelar/.test(kconfTxt1),
      "S8(+): choque opcional duplicar->F2 sin Reemplazar/Cancelar (Xp): " + kconfTxt1
    );
    // Cancelar deja las dos como estaban
    await kconf.getByRole("button", { name: "Cancelar" }).click();
    assert(/\bF2\b/.test(await dlg.locator('[data-action="deshacer"]').innerText()), "S8(+): Cancelar altero deshacer");

    // Repetir con Reemplazar -> deja Deshacer «Sin tecla» (null en profile_read)
    const replacePostP = page.waitForResponse(
      (r) => r.url().endsWith("/api/profile") && r.request().method() === "POST",
      { timeout: 5000 }
    );
    await dlg.locator('[data-action="duplicar"] button', { hasText: /Cambiar/ }).click();
    await sleep(60);
    await page.keyboard.press("F2");
    await kconf.getByRole("button", { name: "Reemplazar" }).click();
    assert((await replacePostP).status() === 200, "S8(+): POST /api/profile tras Reemplazar no dio 200");
    assert(
      /Sin tecla/i.test(await dlg.locator('[data-action="deshacer"]').innerText()),
      "S8(+): Deshacer no quedo 'Sin tecla' en el dialogo"
    );

    const profAfterReplace = JSON.parse((await cmd({ cmd: "profile_read" })).text);
    assert(
      Object.prototype.hasOwnProperty.call(profAfterReplace.keymap, "deshacer") &&
        profAfterReplace.keymap.deshacer === null &&
        profAfterReplace.keymap.duplicar === "F2",
      "S8(+): Reemplazar no guardo deshacer: null en el perfil (XC): " + JSON.stringify(profAfterReplace.keymap)
    );

    // Negativo (mata Xv): borrar -> G choca con Colocar (obligatoria): «no puede quedarse sin tecla» y solo Cancelar
    await dlg.locator('[data-action="borrar"] button', { hasText: /Cambiar/ }).click();
    await sleep(60);
    await page.keyboard.press("g");
    await kconf.waitFor({ state: "visible", timeout: 5000 });
    const kconfMand = await kconf.innerText();
    assert(
      /no puede quedarse sin tecla/i.test(kconfMand),
      "S8(-): choque con obligatoria no dice 'no puede quedarse sin tecla' (Xv): " + kconfMand
    );
    assert(
      (await kconf.getByRole("button", { name: "Reemplazar" }).count()) === 0 &&
        (await kconf.getByRole("button", { name: "Cancelar" }).count()) === 1,
      "S8(-): choque con obligatoria ofrece Reemplazar (Xv)"
    );
    await kconf.getByRole("button", { name: "Cancelar" }).click();

    // Negativo (mata Xr): Ctrl+W y F5 -> «La atiende el navegador» y no se asigna
    for (const browserKey of ["Control+w", "F5"]) {
      await dlg.locator('[data-action="borrar"] button', { hasText: /Cambiar/ }).click();
      await sleep(60);
      await page.keyboard.press(browserKey);
      await sleep(100);
      const kcBrowser = await kconf.innerText();
      assert(
        /La atiende el navegador/i.test(kcBrowser),
        "S8(-): tecla reservada " + browserKey + " no dijo 'La atiende el navegador' (Xr): " + kcBrowser
      );
      const cancelBtn = kconf.getByRole("button", { name: "Cancelar" });
      if ((await cancelBtn.count()) > 0 && (await cancelBtn.isVisible().catch(() => false))) {
        await cancelBtn.click();
      }
    }
    await page.keyboard.press("Escape");

    // Recargar -> Deshacer sigue «Sin tecla» y F2 duplica
    await page.reload();
    await loginIfNeeded(context, page);
    await clickToolsItem(page, /Atajos de teclado/);
    assert(
      /Sin tecla/i.test(await page.locator('[role="dialog"] [data-action="deshacer"]').innerText()),
      "S8(+): al recargar Deshacer perdio 'Sin tecla' (XC)"
    );
    await page.keyboard.press("Escape");

    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + placedId + '"]').click();
    await page.keyboard.press("F2");
    const snapDup = await waitForSnap((s) => s.doc.entities.length === 2, "duplicar con F2");
    const copyEnt = snapDup.doc.entities.find((e) => e.id !== placedId);
    assert(
      copyEnt && /\(copia\)/.test(copyEnt.name) && copyEnt.x === snapG.doc.entities[0].x + 2,
      "S8(+): F2 no duplico con '(copia)' y X+2: " + JSON.stringify(copyEnt)
    );

    // Negativo: Mayus+F9, Esc y Espacio -> «Llega con F5» y 0 peticiones
    await page.locator('[data-testid="barra-estado"]').click({ position: { x: 8, y: 8 } });
    await page.keyboard.press("Escape"); // limpia seleccion si hubiera
    await sleep(100);
    let takeKeyPosts = 0;
    const onTakeKey = (req) => {
      if (isEffectPost(req)) takeKeyPosts += 1;
    };
    page.on("request", onTakeKey);
    try {
      for (const tk of ["Shift+F9", "Escape", "Space"]) {
        await page.keyboard.press(tk);
        await page.waitForFunction(
          () => /Llega con F5/.test(document.body.innerText || ""),
          null,
          { timeout: 3000 }
        );
      }
      await sleep(200);
      assert(takeKeyPosts === 0, "S8(-): Mayus+F9/Esc/Espacio enviaron peticiones: " + takeKeyPosts);
    } finally {
      page.off("request", onTakeKey);
    }

    // Positivo 3: Deshacer a medias (mata XA)
    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + placedId + '"]').click();
    await activatePanel(page, "propiedades");
    await page.locator("#f-yaw").focus();
    await waitEditable(page, "#f-yaw");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("10");
    await page.keyboard.press("Enter");
    await waitForSnap(
      (s) => s.doc.entities.find((e) => e.id === placedId).yaw === 10,
      "rumbo=10 por la persona"
    );
    await page.locator("#f-yaw").evaluate((el) => el.blur());
    const dRel = Date.now() + 5000;
    while (Date.now() < dRel) {
      if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
      await sleep(80);
    }

    const rAiYaw = await cmd({
      cmd: "ai_ops",
      label: "IA cambia rumbo a 20",
      ops: [{ name: "entity.set", target: placedId, args: { yaw: 20 } }],
    });
    assert(rAiYaw.ok, "S8(+): ai_ops yaw=20 fallo: " + JSON.stringify(rAiYaw));
    await waitForSnap(
      (s) => s.doc.entities.find((e) => e.id === placedId).yaw === 20,
      "rumbo=20 por la IA"
    );

    const undoBtn = page.locator('[data-testid="barra-superior"] button', { hasText: /^Deshacer\b/ }).first();
    await undoBtn.click();
    const partialAviso = page.locator('[data-aviso="deshacer-parcial"]');
    await partialAviso.first().waitFor({ state: "visible", timeout: 5000 });
    const partialTxt = await partialAviso.first().innerText();
    assert(
      (partialTxt.includes(placedName) || partialTxt.includes("Barrel_Red")) && /rumbo/i.test(partialTxt),
      "S8(+): deshacer-parcial no nombra la entidad y el rumbo (XA): " + partialTxt
    );
    const snapAfterPartial = await cmd({ cmd: "snapshot" });
    assert(
      snapAfterPartial.doc.entities.find((e) => e.id === placedId).yaw === 20,
      "S8(+): deshacer-parcial cambio el rumbo de 20"
    );

    // F02 (revisión de Sol): la Jerarquía no tiene atajos fijos; Borrar reasignado a F4 manda
    await openShortcutsDialogKeyboardOnly(page);
    await assignShortcutByKeyboard(page, "borrar", "F4");
    await page.keyboard.press("Escape");
    await page.locator('[role="dialog"][aria-modal="true"]').waitFor({ state: "hidden", timeout: 5000 });
    const treeRow = page.locator('[data-panel="jerarquia"] [data-entity-id="' + placedId + '"]');
    await treeRow.click();
    await page.keyboard.press("Delete");
    await sleep(500);
    const snapAfterSupr = await cmd({ cmd: "snapshot" });
    assert(
      snapAfterSupr.doc.entities.some((e) => e.id === placedId),
      "S8(-): Supr en la Jerarquia borro con Borrar reasignado a F4 (F02)"
    );
    await treeRow.click();
    await page.keyboard.press("F4");
    await waitForSnap((s) => !s.doc.entities.some((e) => e.id === placedId), "borrar con F4 desde la Jerarquia");

    console.log("S8 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S9: Actividad y sin backend (D2, CU-37)
// ============================================================================
async function runS9(browser) {
  await resetBackendState();
  const rEnt = await cmd({
    cmd: "ai_ops",
    label: "Entidad S9",
    ops: [{ name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril S9", x: 6000, z: 7000, yaw: 0 } }],
  });
  const eid = rEnt.created[0];

  const { context, page } = await openStudio(browser);
  try {
    await activatePanel(page, "actividad");
    assert((await page.locator("tbody").count()) === 1, "S9(+): debe haber una unica tbody en la pagina");

    // Positivo: Seis op_state -> seis filas con su etiqueta, clase chip <estado>, y 6ª columna Motivo
    const six = [
      { id: "op-s9-1", state: "pendiente", origin: "backend", label: "Pendiente", reason: null },
      { id: "op-s9-2", state: "ejecutando", origin: "servidor", label: "Ejecutando", reason: null },
      { id: "op-s9-3", state: "aplicado", origin: "servidor", label: "Aplicado", reason: null },
      { id: "op-s9-4", state: "observado", origin: "servidor", label: "Observado", reason: null },
      { id: "op-s9-5", state: "fallido", origin: "backend", label: "Fallido", reason: null },
      {
        id: "op-s9-6",
        state: "parcial",
        origin: "servidor",
        label: "Parcial",
        reason: "Fallo al crear obj-02 en el lote 1",
      },
    ];
    for (const s of six) {
      const payload = { cmd: "op_state", op_id: s.id, state: s.state, origin: s.origin };
      if (s.reason !== null) payload.reason = s.reason;
      const rr = await cmd(payload);
      assert(rr && rr.ok, "S9(+): op_state fallo en " + s.id);
    }

    for (const s of six) {
      const row = page.locator('tr[data-op-id="' + s.id + '"]');
      await row.waitFor({ state: "visible", timeout: 5000 });
      const chipCount = await row.locator(".chip." + s.state).count();
      assert(chipCount === 1, "S9(+): falta .chip." + s.state + " en " + s.id);
      const cells = await row.locator("td").allInnerTexts();
      assert(cells.length >= 7, "S9(+): la fila no tiene 7 columnas: " + cells.length);
      assert(cells[2].trim() === s.label, "S9(+): etiqueta de " + s.id + " != " + s.label + ": " + cells[2]);
      assert(cells[4].trim() === s.origin, "S9(+): origen de " + s.id + " != " + s.origin);
      const expectedMotivo = s.reason !== null ? s.reason : "—";
      assert(
        cells[5].trim() === expectedMotivo,
        "S9(+): columna Motivo de " + s.id + ": esperado '" + expectedMotivo + "', recibido '" + cells[5].trim() + "'"
      );
      assert(
        cells[6].trim() === "Aplicar",
        "S9(+): columna Operacion sin verb en " + s.id + " != 'Aplicar': '" + cells[6].trim() + "'"
      );
    }

    const thTexts = await page.locator('[data-panel="actividad"] thead th').allInnerTexts();
    if (thTexts.length > 0) {
      assert(
        thTexts.length >= 7 && /Motivo/i.test(thTexts[5]) && /Operaci[oó]n/i.test(thTexts[6]),
        "S9(+): cabeceras de Actividad sin Motivo/Operacion: " + JSON.stringify(thTexts)
      );
    }

    // Cuenta de en curso (2: pendiente + ejecutando) en la pestaña Actividad
    const actTab = await findTab(page, "actividad");
    const actTabTxt = await actTab.innerText();
    assert(/\b2\b/.test(actTabTxt), "S9(+): la pestaña Actividad no enseña la cuenta en curso (2): " + JSON.stringify(actTabTxt));

    // Filtros «En curso», «Fallos» y «Todas»
    const actPanel = page.locator('[data-panel="actividad"]');
    const clickFilter = async (nameRe) => {
      const f = actPanel.locator('button, [role="tab"], [role="radio"]', { hasText: nameRe }).first();
      await f.click();
      await sleep(120);
    };
    const visibleOpIds = () =>
      page.evaluate(() =>
        Array.from(document.querySelectorAll('[data-panel="actividad"] tbody tr[data-op-id]'))
          .filter((r) => r.getClientRects().length > 0)
          .map((r) => r.getAttribute("data-op-id"))
      );

    await clickFilter(/^En curso\b/);
    const enCursoIds = await visibleOpIds();
    assert(
      enCursoIds.length === 2 && enCursoIds.includes("op-s9-1") && enCursoIds.includes("op-s9-2"),
      "S9(+): filtro 'En curso' incorrecto: " + JSON.stringify(enCursoIds)
    );

    await clickFilter(/^Fallos\b/);
    const fallosIds = await visibleOpIds();
    assert(
      fallosIds.length === 2 && fallosIds.includes("op-s9-5") && fallosIds.includes("op-s9-6"),
      "S9(+): filtro 'Fallos' incorrecto: " + JSON.stringify(fallosIds)
    );

    await clickFilter(/^Todas\b/);
    const todasIds = await visibleOpIds();
    assert(todasIds.length === 6, "S9(+): filtro 'Todas' no devolvio las 6 filas: " + JSON.stringify(todasIds));

    // Positivo (mata XH): 7ª columna «Operación»: verb="scene.reset" -> «Quitar del juego», otro verb -> literal
    const rResetVerb = await cmd({
      cmd: "op_state",
      op_id: "op-s9-reset",
      state: "observado",
      origin: "servidor",
      verb: "scene.reset",
    });
    assert(rResetVerb && rResetVerb.ok, "S9(+): op_state verb=scene.reset fallo");
    const resetRow = page.locator('tr[data-op-id="op-s9-reset"]');
    await resetRow.waitFor({ state: "visible", timeout: 5000 });
    const resetCells = await resetRow.locator("td").allInnerTexts();
    assert(
      resetCells.length >= 7 && resetCells[6].trim() === "Quitar del juego",
      "S9(+): columna Operacion con verb='scene.reset' no dice 'Quitar del juego' (XH): " + JSON.stringify(resetCells)
    );

    const rCustomVerb = await cmd({
      cmd: "op_state",
      op_id: "op-s9-verb",
      state: "observado",
      origin: "servidor",
      verb: "take.run",
    });
    assert(rCustomVerb && rCustomVerb.ok, "S9(+): op_state verb=take.run fallo");
    const customVerbRow = page.locator('tr[data-op-id="op-s9-verb"]');
    await customVerbRow.waitFor({ state: "visible", timeout: 5000 });
    const customVerbCells = await customVerbRow.locator("td").allInnerTexts();
    assert(
      customVerbCells.length >= 7 && customVerbCells[6].trim() === "take.run",
      "S9(+): columna Operacion con otro verb no enseña el verb literal: " + JSON.stringify(customVerbCells)
    );

    // Negativo 1: stop_backend -> luces en gris con «hace N», sin-backend, «lo último que se supo»,
    // Propiedades y Añadir desactivados, Aplicar y Quitar del juego desactivados y Ctrl+S dice que no se guarda
    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]').click();
    await activatePanel(page, "propiedades");
    await page.locator("#f-x").waitFor({ state: "visible", timeout: 5000 });

    const rStop = await cmd({ cmd: "stop_backend" });
    assert(rStop && rStop.ok, "S9(-): stop_backend fallo");

    await page.locator('[data-aviso="sin-backend"]').first().waitFor({ state: "visible", timeout: 10000 });
    const statusOffTxt = await page.locator('[data-testid="barra-estado"]').innerText();
    assert(
      /\bhace \d+/.test(statusOffTxt) && /Sin validar/.test(statusOffTxt) && !/Escena sin errores/i.test(statusOffTxt),
      "S9(-): barra de estado sin backend incorrecta: " + statusOffTxt
    );
    const actOffTxt = await page.locator('[data-panel="actividad"]').innerText();
    assert(/lo [úu]ltimo que se supo/i.test(actOffTxt), "S9(-): Actividad sin 'lo último que se supo': " + actOffTxt);
    assert(
      await page.locator("#f-x").isDisabled(),
      "S9(-): Propiedades (#f-x) no se desactivo sin backend"
    );
    assert(
      await page.locator('[data-testid="accion-principal"] button').first().isDisabled(),
      "S9(-): Aplicar no se desactivo sin backend"
    );
    assert(
      await page.getByRole("button", { name: "Quitar del juego", exact: true }).isDisabled(),
      "S9(-): Quitar del juego no se desactivo sin backend"
    );

    await activatePanel(page, "anadir");
    const anadirOff = await page.locator('[data-panel="anadir"]').evaluate((col) => {
      const rows = Array.from(col.querySelectorAll("[data-cls]"));
      return (
        rows.length > 0 &&
        rows.every((r) => r.disabled || r.getAttribute("aria-disabled") === "true" || !!r.closest("fieldset[disabled]"))
      );
    });
    assert(anadirOff, "S9(-): Añadir no quedo desactivado sin backend");

    // Ctrl+S sin backend dice que no se puede guardar
    await page.locator('[data-testid="barra-estado"]').click({ position: { x: 6, y: 6 } });
    await page.keyboard.press("Control+s");
    await page.waitForFunction(
      () => /No se puede guardar:\s*no hay backend|sin conexi[óo]n.*no se puede/i.test(document.body.innerText || ""),
      null,
      { timeout: 4000 }
    );

    // start_backend y volver a entrar -> el aviso sin-backend se va
    const rStart = await cmd({ cmd: "start_backend" });
    assert(rStart && rStart.ok, "S9(-): start_backend fallo");
    const loginShownAuto = await page
      .locator("#human-key")
      .waitFor({ state: "visible", timeout: 5000 })
      .then(() => true)
      .catch(() => false);
    if (!loginShownAuto) {
      await page.reload();
      await page.locator("#human-key").waitFor({ state: "visible", timeout: 10000 });
    }
    await loginIfNeeded(context, page, 15000);
    const sinBackendVisible = await page
      .locator('[data-aviso="sin-backend"]')
      .first()
      .isVisible()
      .catch(() => false);
    assert(!sinBackendVisible, "S9(-): el aviso sin-backend no desaparecio al volver el backend");

    // Positivo + Negativo 2 (mata XB y XE): Con el backend vivo y solo el SSE cortado (page.route sobre /api/events):
    // - «Reconectando…» y «Aplicar» sigue activo (XB)
    // - Editar X en Propiedades -> el campo y el snapshot dicen lo mismo (XE)
    // - Un ai_ops aparece en la Jerarquía en < 5 s (XE)
    // - «Aplicar» -> 200 con la rev del snapshot, nunca stale_apply (XE, XB)
    const sseCutHandler = async (route) => {
      await route.fulfill({ status: 503, contentType: "text/plain; charset=utf-8", body: "sse-cut" });
    };
    await page.route("**/api/events", sseCutHandler);
    try {
      await page.reload();
      await page.locator('[data-testid="barra-superior"]').waitFor({ state: "visible", timeout: 10000 });
      await page.getByText("Reconectando…", { exact: true }).waitFor({ state: "visible", timeout: 10000 });
      const applyBtn = page.locator('[data-testid="accion-principal"] button').first();
      await page.waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 6000 }
      );
      assert(!(await applyBtn.isDisabled()), "S9(-): 'Reconectando…' desactivo Aplicar (XB)");

      const itemNoSse = page.locator('[data-panel="jerarquia"] [data-entity-id="' + eid + '"]');
      await itemNoSse.waitFor({ state: "visible", timeout: 6000 });
      await itemNoSse.click();
      await activatePanel(page, "propiedades");
      await page.locator("#f-x").focus();
      await waitEditable(page, "#f-x");
      const opsNoSseRespP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/scene/ops" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await page.keyboard.press("Control+a");
      await page.keyboard.type("6345");
      await page.keyboard.press("Enter");
      assert((await opsNoSseRespP).status() === 200, "S9(+): POST /api/scene/ops sin SSE no dio 200");
      await page.locator("#f-x").evaluate((el) => el.blur());
      const dNoSseLease = Date.now() + 4000;
      while (Date.now() < dNoSseLease) {
        if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
        await sleep(80);
      }
      await page.waitForFunction(
        () => {
          const fx = document.getElementById("f-x");
          return !!fx && String(fx.value).replace(/\./g, "") === "6345";
        },
        null,
        { timeout: 2000 }
      );
      const snapAfterEditNoSse = await cmd({ cmd: "snapshot" });
      const entAfterEditNoSse = snapAfterEditNoSse.doc.entities.find((e) => e.id === eid);
      const fxValNoSse = (await page.locator("#f-x").inputValue()).replace(/\./g, "");
      assert(
        entAfterEditNoSse && entAfterEditNoSse.x === 6345 && fxValNoSse === String(entAfterEditNoSse.x),
        "S9(+): sin SSE, el campo X y el snapshot no coinciden (XE): fx=" +
          fxValNoSse +
          ", snap=" +
          JSON.stringify(entAfterEditNoSse)
      );

      // Un ai_ops aparece en la Jerarquía en < 5 s sin SSE
      const tAiNoSse = Date.now();
      const rAiNoSse = await cmd({
        cmd: "ai_ops",
        label: "IA sin SSE",
        ops: [{ name: "entity.add", args: { kind: "objeto", cls: "WoodenCrate", name: "Caja sin SSE", x: 6400, z: 7100, yaw: 0 } }],
      });
      assert(rAiNoSse && rAiNoSse.ok, "S9(+): ai_ops sin SSE fallo");
      const idAiNoSse = rAiNoSse.created[0];
      await page
        .locator('[data-panel="jerarquia"] [data-entity-id="' + idAiNoSse + '"]')
        .waitFor({ state: "visible", timeout: 5000 });
      const elapsedAiNoSse = Date.now() - tAiNoSse;
      assert(
        elapsedAiNoSse < 5000,
        "S9(+): ai_ops sin SSE tardo >= 5 s en aparecer en Jerarquia (XE): " + elapsedAiNoSse + " ms"
      );

      // «Aplicar» -> 200 con la rev del snapshot, nunca stale_apply
      const snapBeforeApplyNoSse = await cmd({ cmd: "snapshot" });
      await page.waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 5000 }
      );
      assert(!(await applyBtn.isDisabled()), "S9(-): 'Reconectando…' desactivo Aplicar tras edicion (XB)");
      const applyP = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/apply" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await applyBtn.click();
      const applyResp = await applyP;
      const applyReqBody = JSON.parse(applyResp.request().postData() || "{}");
      const applyRespBody = await applyResp.json().catch(() => ({}));
      assert(
        applyResp.status() === 200 &&
          applyRespBody.code !== "stale_apply" &&
          applyReqBody.rev === snapBeforeApplyNoSse.rev &&
          applyReqBody.hash === snapBeforeApplyNoSse.hash,
        "S9(+): Aplicar sin SSE no dio 200 con la rev del snapshot (XE/XB): status=" +
          applyResp.status() +
          ", req=" +
          JSON.stringify(applyReqBody) +
          ", resp=" +
          JSON.stringify(applyRespBody) +
          ", snapRev=" +
          snapBeforeApplyNoSse.rev
      );
    } finally {
      await page.unroute("**/api/events", sseCutHandler);
    }

    console.log("S9 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S10: Validación (CU-02)
// ============================================================================
async function runS10(browser) {
  await resetBackendState();
  const rAdd = await cmd({
    cmd: "ai_ops",
    label: "Dos entidades S10",
    ops: [
      { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril primero", x: 6000, z: 7000, yaw: 0 } },
      { name: "entity.add", args: { kind: "objeto", cls: "WoodenCrate", name: "Caja segunda", x: 6100, z: 7100, yaw: 0 } },
    ],
  });
  const e1 = rAdd.created[0];
  const e2 = rAdd.created[1];

  const { context, page } = await openStudio(browser);
  try {
    // Provocar error out_of_map en e1 (indice 0)
    const row1 = page.locator('[data-panel="jerarquia"] [data-entity-id="' + e1 + '"]');
    const row2 = page.locator('[data-panel="jerarquia"] [data-entity-id="' + e2 + '"]');
    await row1.click();
    await activatePanel(page, "propiedades");
    await page.locator("#f-x").focus();
    await waitEditable(page, "#f-x");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("99999");
    await page.keyboard.press("Tab");

    await activatePanel(page, "validacion");
    const errRow = page.locator('[data-panel="validacion"] [data-error-pointer="/entities/0/x"]');
    await errRow.first().waitFor({ state: "visible", timeout: 5000 });
    assert(/1 problema/.test(await page.locator('[data-testid="barra-estado"]').innerText()), "S10(+): falta '1 problema' en la barra de estado");

    // Cambiar seleccion a e2 y poner Añadir delante para que «Ver» tenga que actuar de verdad
    await row2.click();
    await activatePanel(page, "anadir");

    // Positivo: «Ver» selecciona e1 y pone el foco en su #f-x
    await errRow.first().getByRole("button", { name: /^Ver\b/ }).click();
    await page.waitForFunction(
      (id1) => {
        const r = document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + id1 + '"]');
        const fx = document.getElementById("f-x");
        return !!r && r.getAttribute("aria-selected") === "true" && document.activeElement === fx;
      },
      e1,
      { timeout: 5000 }
    ).catch(async (err) => {
      const diag = await page.evaluate((id1) => {
        const r = document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + id1 + '"]');
        const a = document.activeElement;
        return {
          fila: r ? r.getAttribute("aria-selected") : "sin fila",
          activo: a ? a.id || a.tagName : null,
          fx: !!document.getElementById("f-x"),
          propiedades: !!document.querySelector('[data-panel="propiedades"]'),
        };
      }, e1);
      throw new Error("S10(+): «Ver» no seleccionó la entidad o no enfocó su X: " + JSON.stringify(diag) + " · " + err.message);
    });
    assert((await page.locator("#f-x").inputValue()) === "99999", "S10(+): #f-x no conserva 99999 al ir con Ver");

    // Al corregir, la fila desaparece y el contador de problemas baja
    await waitEditable(page, "#f-x");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("6050");
    await page.keyboard.press("Enter");
    await waitForSnap((s) => s.doc.entities[0].x === 6050, "correccion de X=6050 en S10");
    await page.waitForFunction(
      () =>
        document.querySelectorAll('[data-panel="validacion"] [data-error-pointer]').length === 0 &&
        /Escena sin errores/.test(document.querySelector('[data-testid="barra-estado"]').innerText || ""),
      null,
      { timeout: 5000 }
    );

    // Negativo (mata Xz): X invalido en la primera (e1) y despues e1 borrada por ai_ops (e2 pasa al indice 0) ->
    // la fila dice «Ya no existe» y «Ver» no selecciona e2 ni enfoca nada
    await page.locator("#f-x").focus();
    await waitEditable(page, "#f-x");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("99999");
    await page.keyboard.press("Enter");
    await errRow.first().waitFor({ state: "visible", timeout: 5000 });
    // Precondición de F07: con el campo rechazado, «Aplicar» está desactivado
    assert(
      await page.locator('[data-testid="accion-principal"] button').first().isDisabled(),
      "S10(-): «Aplicar» activo con un campo rechazado (precondición de F07)"
    );

    // Soltar el prestamo humano antes de que ai_ops borre e1
    await page
      .locator('[data-panel="jerarquia"] [role="treeitem"], [data-panel="jerarquia"] button', {
        hasText: /^Ambiente\b/i,
      })
      .first()
      .click();
    const dLease = Date.now() + 5000;
    while (Date.now() < dLease) {
      if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
      await sleep(80);
    }

    const rDel = await cmd({
      cmd: "ai_ops",
      label: "IA borra primera entidad",
      ops: [{ name: "entity.delete", target: e1, args: {} }],
    });
    assert(rDel.ok, "S10(-): ai_ops entity.delete fallo: " + JSON.stringify(rDel));

    await page.waitForFunction(
      (id1) => !document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + id1 + '"]'),
      e1,
      { timeout: 5000 }
    );
    await activatePanel(page, "validacion");
    await page.waitForFunction(
      () => {
        const r = document.querySelector('[data-panel="validacion"] [data-error-pointer="/entities/0/x"]');
        return !!r && /Ya no existe/i.test(r.innerText || "");
      },
      null,
      { timeout: 5000 }
    );

    const verGone = errRow.first().getByRole("button", { name: /^Ver\b/ });
    if ((await verGone.count()) > 0 && !(await verGone.first().isDisabled())) {
      await verGone.first().click();
      await sleep(200);
    }
    const e2Selected = await row2.getAttribute("aria-selected");
    const activeId = await page.evaluate(() => (document.activeElement && document.activeElement.id) || "");
    assert(
      e2Selected !== "true" && activeId !== "f-x",
      "S10(-): 'Ver' de entidad borrada selecciono la segunda entidad por indice o enfoco #f-x (Xz)"
    );

    // F07 (revisión de Sol): el borrador rechazado de una entidad que ya no existe no deja «Aplicar»
    // desactivado para siempre
    await page
      .waitForFunction(
        () => {
          const b = document.querySelector('[data-testid="accion-principal"] button');
          return !!b && !b.disabled;
        },
        null,
        { timeout: 5000 }
      )
      .catch(async (err) => {
        const t = await page.locator('[data-testid="accion-principal"] button').first().getAttribute("title");
        throw new Error(
          "S10(-): «Aplicar» sigue desactivado tras borrar la entidad del campo rechazado (F07): " + t + " · " + err.message
        );
      });

    // F08 (revisión de Sol): un error sin id de entidad no lleva «Ver», aunque el índice de su ruta lo
    // ocupe ahora otra entidad
    const rawCatS10 = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
    const catInventada = async (route) => {
      const resp = await route.fetch();
      const j = await resp.json();
      j.classes.objeto = (j.classes.objeto || rawCatS10.classes.objeto).concat(["ClaseInventada"]);
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify(j),
      });
    };
    await page.route("**/api/catalog", catInventada);
    try {
      await page.goto(BASE + "/");
      await loginIfNeeded(context, page);
      const nBefore = (await cmd({ cmd: "snapshot" })).doc.entities.length;
      const ptrCls = "/entities/" + nBefore + "/cls";
      await activatePanel(page, "anadir");
      await page.locator('[data-panel="anadir"] [data-cls="ClaseInventada"]').click();
      await page.waitForFunction(
        () => {
          const el = document.querySelector('[data-panel="anadir"] [data-cls="ClaseInventada"]');
          return !!el && el.getAttribute("aria-pressed") === "true";
        },
        null,
        { timeout: 3000 }
      );
      await page.keyboard.press("Enter");
      await activatePanel(page, "validacion");
      const clsRow = page.locator('[data-panel="validacion"] [data-error-pointer="' + ptrCls + '"]');
      await clsRow.first().waitFor({ state: "visible", timeout: 5000 });
      assert(
        (await cmd({ cmd: "snapshot" })).doc.entities.length === nBefore,
        "S10(-): la clase inventada entró en la escena"
      );

      const dLease2 = Date.now() + 5000;
      while (Date.now() < dLease2) {
        if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
        await sleep(80);
      }
      const rBarril = await cmd({
        cmd: "ai_ops",
        label: "IA añade un barril",
        ops: [
          { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril IA", x: 6200, z: 7200, yaw: 0 } },
        ],
      });
      assert(rBarril.ok, "S10(-): ai_ops entity.add fallo: " + JSON.stringify(rBarril));
      const idBarril = rBarril.created[0];
      await page.waitForFunction(
        (id) => !!document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + id + '"]'),
        idBarril,
        { timeout: 5000 }
      );
      const snapB = await cmd({ cmd: "snapshot" });
      assert(
        snapB.doc.entities[nBefore] && snapB.doc.entities[nBefore].id === idBarril,
        "S10(-): el barril de la IA no ocupa el índice " + nBefore
      );
      await activatePanel(page, "validacion");
      await clsRow.first().waitFor({ state: "visible", timeout: 5000 });
      const verSinId = await clsRow.first().getByRole("button", { name: /^Ver\b/ }).count();
      assert(
        verSinId === 0,
        "S10(-): el error sin id lleva «Ver», que por índice llevaría al barril de la IA (F08)"
      );
    } finally {
      await page.unroute("**/api/catalog", catInventada);
    }

    // R2-03 (ronda 2 de Sol): un 422 que llega después de que otra edición borrara la entidad no
    // resucita su borrador ni vuelve a bloquear «Aplicar». El préstamo se pierde sin salir del campo
    // (renovaciones rechazadas, como en F05): salir lo reconfirmaría y esa tanda taparía el defecto.
    {
      const snapR3 = await cmd({ cmd: "snapshot" });
      const victim = snapR3.doc.entities[snapR3.doc.entities.length - 1];
      let releaseR3;
      const gateR3 = new Promise((r) => {
        releaseR3 = r;
      });
      let seenR3 = false;
      const holdRespR3 = async (route) => {
        if (route.request().method() === "POST" && !seenR3) {
          seenR3 = true;
          const resp = await route.fetch(); // el backend ya lo rechaza; solo se retiene la respuesta
          await gateR3;
          await route.fulfill({ response: resp });
          return;
        }
        await continueSafe(route);
      };
      const failRenewR3 = async (route) => {
        const req = route.request();
        if (req.method() === "POST" && /\/api\/lease\/[^/]+\/renew$/.test(new URL(req.url()).pathname)) {
          await route.fulfill({
            status: 409,
            contentType: "application/json; charset=utf-8",
            body: JSON.stringify({ ok: false, code: "lease_expired", pointer: "", msg: "caducado" }),
          });
          return;
        }
        await continueSafe(route);
      };
      await page.route("**/api/scene/ops", holdRespR3);
      try {
        await page.locator('[data-panel="jerarquia"] [data-entity-id="' + victim.id + '"]').click();
        await activatePanel(page, "propiedades");
        await page.locator("#f-x").focus();
        await waitEditable(page, "#f-x");
        await page.route("**/api/lease/**", failRenewR3);
        await page.keyboard.press("Control+a");
        await page.keyboard.type("99999");
        await page.keyboard.press("Enter");
        const dR3 = Date.now() + 3000;
        while (!seenR3 && Date.now() < dR3) await sleep(50);
        assert(seenR3, "S10(-): R2-03: no salio el POST de X=99999");
        // Sin renovaciones, el backend caduca el préstamo (3 s) con el foco todavía en X
        const dl3 = Date.now() + 8000;
        while (Date.now() < dl3) {
          if ((await cmd({ cmd: "leases" })).leases.length === 0) break;
          await sleep(100);
        }
        assert((await cmd({ cmd: "leases" })).leases.length === 0, "S10(-): R2-03: el prestamo no caduco sin renovaciones");
        const rDel3 = await cmd({
          cmd: "ai_ops",
          label: "IA borra la entidad del campo rechazado",
          ops: [{ name: "entity.delete", target: victim.id, args: {} }],
        });
        assert(rDel3.ok, "S10(-): R2-03: ai_ops entity.delete fallo: " + JSON.stringify(rDel3));
        await page.waitForFunction(
          (id) => !document.querySelector('[data-panel="jerarquia"] [data-entity-id="' + id + '"]'),
          victim.id,
          { timeout: 5000 }
        );
        await sleep(300);
        releaseR3();
        await sleep(800);
        const applyOff = await page.locator('[data-testid="accion-principal"] button').first().isDisabled();
        assert(
          !applyOff,
          "S10(-): un 422 tardio de una entidad ya borrada volvio a bloquear Aplicar (R2-03)"
        );
      } finally {
        releaseR3();
        await sleep(200);
        await page.unroute("**/api/scene/ops", holdRespR3);
        await page.unroute("**/api/lease/**", failRenewR3);
      }
    }

    console.log("S10 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S11: Aspecto y limpieza
// ============================================================================
// Auditoría de contraste WCAG 2.1 AA portada de ui/prototipo/pruebas.js:226-248
const CONTRAST_AUDIT_FN = () => {
  const colors = (s) =>
    [...s.matchAll(/rgba?\(([^)]+)\)|color\(srgb ([^)]+)\)/g)].map((m) => {
      const p = (m[1] !== undefined ? m[1] : m[2]).split(/[ ,/]+/).filter(Boolean).map(Number);
      const k = m[1] !== undefined ? 1 : 255;
      return { r: p[0] * k, g: p[1] * k, b: p[2] * k, a: p.length > 3 ? p[3] : 1 };
    });
  const parse = (s) => colors(s)[0] || null;
  const over = (t, u) => ({
    r: t.r * t.a + u.r * (1 - t.a),
    g: t.g * t.a + u.g * (1 - t.a),
    b: t.b * t.a + u.b * (1 - t.a),
    a: 1,
  });
  const lum = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const bgOf = (el) => {
    const st = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      const g =
        /gradient/.test(cs.backgroundImage) &&
        colors(cs.backgroundImage).sort((u, v) => v.a - u.a)[0];
      if (g && g.a > 0) st.push(g);
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) {
        st.push(c);
        if (c.a >= 1) break;
      }
    }
    let u = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = st.length - 1; i >= 0; i--) u = over(st[i], u);
    return u;
  };
  const hex = (c) =>
    "#" +
    [c.r, c.g, c.b]
      .map((v) => Math.round(v).toString(16).padStart(2, "0"))
      .join("");
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const text = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join("")
      .trim();
    if (!text || el.closest('[disabled],[aria-disabled="true"]')) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (
      !r.width ||
      !r.height ||
      cs.visibility === "hidden" ||
      r.bottom < 0 ||
      r.right < 0 ||
      r.top > innerHeight ||
      r.left > innerWidth
    ) {
      continue;
    }
    let o = 1;
    for (let e = el; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity);
    if (o < 0.05) continue;
    const bg = bgOf(el);
    const fg0 = parse(cs.color);
    if (!fg0) continue;
    const fg = over({ ...fg0, a: fg0.a * o }, bg);
    const x = lum(fg);
    const y = lum(bg);
    const ratio = (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
    const size = parseFloat(cs.fontSize);
    const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) {
      out.push("«" + text.slice(0, 28) + "» " + hex(fg) + " sobre " + hex(bg) + " " + ratio.toFixed(2) + ":1");
    }
  }
  return out;
};

const SMALL_TEXT_FN = () => {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const text = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join("")
      .trim();
    if (!text) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (
      !r.width ||
      !r.height ||
      cs.visibility === "hidden" ||
      r.bottom <= 0 ||
      r.right <= 0 ||
      r.top >= innerHeight ||
      r.left >= innerWidth
    ) {
      continue;
    }
    const px = parseFloat(cs.fontSize);
    if (px < 12) out.push("«" + text.slice(0, 24) + "» " + px + "px");
  }
  return out;
};

async function waitAnimationsSettled(page) {
  await page
    .waitForFunction(
      () =>
        document
          .getAnimations()
          .every((a) => a.playState !== "running" || a.effect.getComputedTiming().iterations === Infinity),
      null,
      { timeout: 3000 }
    )
    .catch(() => {});
}

async function runS11(browser) {
  await resetBackendState();
  const rSeed = await cmd({
    cmd: "ai_ops",
    label: "Semilla S11",
    ops: [
      { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril S11", x: 6000, z: 7000, yaw: 0 } },
      { name: "entity.add", args: { kind: "infectado", cls: "ZmbM_FarmerFat_Brown", name: "Zombi S11", x: 6020, z: 7000, yaw: 0 } },
      { name: "entity.add", args: { kind: "animal", cls: "Animal_CervusElaphus", name: "Ciervo S11", x: 6040, z: 7000, yaw: 0 } },
    ],
  });
  const [objId, zmbId, aniId] = rSeed.created;

  const statesS11 = [
    ["op-s11-1", "pendiente", "backend", null, null],
    ["op-s11-2", "ejecutando", "servidor", null, null],
    ["op-s11-3", "aplicado", "servidor", null, null],
    ["op-s11-4", "observado", "servidor", null, "scene.reset"],
    ["op-s11-5", "fallido", "backend", null, null],
    ["op-s11-6", "parcial", "servidor", "Motivo parcial de contraste", null],
  ];
  for (const [id, st, orig, reason, verb] of statesS11) {
    const p = { cmd: "op_state", op_id: id, state: st, origin: orig };
    if (reason) p.reason = reason;
    if (verb) p.verb = verb;
    await cmd(p);
  }

  // Positivo 1 y 2: Contraste AA en oscuro y claro + ningun texto en uso por debajo de 12 px
  for (const scheme of ["dark", "light"]) {
    const { context, page } = await openStudio(browser, {
      viewport: { width: 1280, height: 720 },
      colorScheme: scheme,
    });
    try {
      const low = [];
      const tiny = [];
      const checkView = async (label) => {
        await waitAnimationsSettled(page);
        for (const f of await page.evaluate(CONTRAST_AUDIT_FN)) low.push(label + ": " + f);
        for (const t of await page.evaluate(SMALL_TEXT_FN)) tiny.push(label + ": " + t);
      };

      await checkView("escena-inicial");
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + objId + '"]').click();
      await activatePanel(page, "propiedades");
      await checkView("propiedades-entidad");

      await activatePanel(page, "anadir");
      await page.locator('[data-panel="anadir"] [data-cls="Barrel_Red"]').first().hover();
      await sleep(100);
      await checkView("anadir-vista-previa");

      await activatePanel(page, "validacion");
      await checkView("validacion");
      await activatePanel(page, "historial");
      await checkView("historial-hueco");
      await activatePanel(page, "ia");
      await checkView("ia-hueco");
      await activatePanel(page, "actividad");
      await checkView("actividad-chips");

      await openToolsMenu(page);
      await checkView("menu-herramientas");
      await page.keyboard.press("Escape");

      await clickToolsItem(page, /Atajos de teclado/);
      await page.locator('[role="dialog"]').waitFor({ state: "visible", timeout: 5000 });
      await checkView("dialogo-atajos");
      await page.keyboard.press("Escape");

      await switchMode(page, "rodaje");
      await checkView("rodaje");

      assert(
        low.length === 0,
        "S11(+): fallos de contraste AA en tema " + scheme + ": " + low.slice(0, 6).join(" | ")
      );
      assert(
        tiny.length === 0,
        "S11(+): textos < 12 px en tema " + scheme + ": " + tiny.slice(0, 6).join(" | ")
      );
    } finally {
      await context.close();
    }
  }

  // Positivos 3, 4, 5 y Negativos sobre un contexto limpio
  const { context, page } = await openStudio(browser);
  try {
    // Positivo 3: barras de desplazamiento finas (scrollbarWidth === 'thin')
    await activatePanel(page, "anadir");
    await activatePanel(page, "propiedades");
    const scrollCheck = await page.evaluate(() => {
      const scrollables = Array.from(document.querySelectorAll("[data-panel], [data-panel] *")).filter((el) => {
        const cs = getComputedStyle(el);
        return cs.overflowY === "auto" || cs.overflowY === "scroll";
      });
      return {
        n: scrollables.length,
        allThin: scrollables.length > 0 && scrollables.every((el) => getComputedStyle(el).scrollbarWidth === "thin"),
        samples: scrollables.slice(0, 5).map((el) => getComputedStyle(el).scrollbarWidth),
      };
    });
    assert(
      scrollCheck.n > 0 && scrollCheck.allThin,
      "S11(+): barras de desplazamiento no son finas (scrollbar-width: thin): " + JSON.stringify(scrollCheck)
    );

    // Positivo 4: un «Aplicar» desactivado se ve desactivado (pierde el fondo primario ambar, VIS-05)
    const applyBtn = page.locator('[data-testid="accion-principal"] button').first();
    const enabledStyle = await applyBtn.evaluate((b) => ({
      bg: getComputedStyle(b).backgroundColor,
      color: getComputedStyle(b).color,
      opacity: parseFloat(getComputedStyle(b).opacity),
    }));

    await page.locator('[data-panel="jerarquia"] [data-entity-id="' + objId + '"]').click();
    await page.locator("#f-x").focus();
    await waitEditable(page, "#f-x");
    await page.keyboard.press("Control+a");
    await page.keyboard.type("99999");
    await page.keyboard.press("Enter");
    await page.waitForFunction(
      () => {
        const b = document.querySelector('[data-testid="accion-principal"] button');
        return !!b && b.disabled;
      },
      null,
      { timeout: 5000 }
    );
    await waitAnimationsSettled(page);
    const disabledStyle = await applyBtn.evaluate((b) => ({
      bg: getComputedStyle(b).backgroundColor,
      color: getComputedStyle(b).color,
      opacity: parseFloat(getComputedStyle(b).opacity),
    }));
    assert(
      disabledStyle.bg !== enabledStyle.bg || disabledStyle.opacity < enabledStyle.opacity - 0.2,
      "S11(+): Aplicar desactivado se ve igual que activado: " +
        JSON.stringify({ enabledStyle, disabledStyle })
    );
    await page.locator("#f-x").focus();
    await page.keyboard.press("Escape");
    await page.locator("#f-x").evaluate((el) => el.blur());

    // Positivo 5: el mismo icono por tipo en Jerarquia, Añadir y Propiedades (CU-39)
    const svgSigFn = (rootSel) => {
      const root = document.querySelector(rootSel);
      if (!root) return null;
      const svgs = Array.from(root.querySelectorAll("svg")).filter(
        (s) => !s.closest("button[data-action], summary")
      );
      const sigOf = (svg) =>
        Array.from(svg.querySelectorAll("path, circle, rect, polygon, polyline, line"))
          .map(
            (n) =>
              n.tagName.toLowerCase() +
              ":" +
              (n.getAttribute("d") ||
                n.getAttribute("points") ||
                [
                  n.getAttribute("x"),
                  n.getAttribute("y"),
                  n.getAttribute("width"),
                  n.getAttribute("height"),
                  n.getAttribute("cx"),
                  n.getAttribute("cy"),
                  n.getAttribute("r"),
                  n.getAttribute("x1"),
                  n.getAttribute("y1"),
                  n.getAttribute("x2"),
                  n.getAttribute("y2"),
                ].join(","))
          )
          .join("|");
      return svgs.map(sigOf).filter(Boolean);
    };

    const kindsToCheck = [
      { id: objId, cls: "Barrel_Red", tabRe: /^Objetos\b/ },
      { id: zmbId, cls: "ZmbM_FarmerFat_Brown", tabRe: /^Infectados\b/ },
      { id: aniId, cls: "Animal_CervusElaphus", tabRe: /^Animales\b/ },
    ];
    for (const k of kindsToCheck) {
      const treeSigs = await page.evaluate(svgSigFn, '[data-panel="jerarquia"] [data-entity-id="' + k.id + '"]');
      assert(treeSigs && treeSigs.length >= 1, "S11(+): sin icono SVG en Jerarquia para " + k.cls);
      const treeIcon = treeSigs[0];

      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + k.id + '"]').click();
      await activatePanel(page, "propiedades");
      const propSigs = await page.evaluate(svgSigFn, '[data-panel="propiedades"]');
      assert(
        propSigs && propSigs.includes(treeIcon),
        "S11(+): Propiedades no usa el mismo trazado de icono que Jerarquia para " +
          k.cls +
          ": " +
          JSON.stringify({ treeIcon, propSigs })
      );

      await activatePanel(page, "anadir");
      await page
        .locator('[data-panel="anadir"] [role="tablist"][aria-label="Tipo"]')
        .locator('[role="tab"], button', { hasText: k.tabRe })
        .first()
        .click();
      await sleep(100);
      const addSigs = await page.evaluate(svgSigFn, '[data-panel="anadir"] [data-cls="' + k.cls + '"]');
      assert(
        addSigs && addSigs.includes(treeIcon),
        "S11(+): Añadir no usa el mismo trazado de icono que Jerarquia para " +
          k.cls +
          ": " +
          JSON.stringify({ treeIcon, addSigs })
      );
    }

    // Negativo: ni textarea ni [contenteditable] ni el documento crudo en JSON (D1, §7)
    const noJsonCheck = await page.evaluate(() => ({
      textareas: document.querySelectorAll("textarea").length,
      editables: document.querySelectorAll('[contenteditable]:not([contenteditable="false"])').length,
      rawJson: /"schema"\s*:\s*"dsbx\.scene\/1"|"entities"\s*:\s*\[/.test(document.body.innerText || ""),
    }));
    assert(
      noJsonCheck.textareas === 0 && noJsonCheck.editables === 0 && !noJsonCheck.rawJson,
      "S11(-): hay textarea, contenteditable o JSON crudo en pantalla: " + JSON.stringify(noJsonCheck)
    );

    // Negativo (mata Xx): Texto hostil en entidades, catalogo y reason de una orden
    const HOSTILE_A = '<a id="inyeccion" href="/api/scene">Abrir</a>';
    const HOSTILE_IMG = '<img src=x onerror="window.__x=1">';

    const rHostile = await cmd({
      cmd: "ai_ops",
      label: "Nombres hostiles",
      ops: [
        { name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: HOSTILE_A, x: 6200, z: 7200, yaw: 0 } },
        { name: "entity.add", args: { kind: "objeto", cls: "WoodenCrate", name: HOSTILE_IMG, x: 6220, z: 7200, yaw: 0 } },
      ],
    });
    assert(rHostile.ok, "S11(-): ai_ops nombres hostiles fallo");
    const [hIdA, hIdImg] = rHostile.created;

    await cmd({
      cmd: "op_state",
      op_id: "op-hostil",
      state: "parcial",
      origin: "servidor",
      reason: HOSTILE_A,
      verb: HOSTILE_IMG,
    });

    const hostileCatRoute = async (route) => {
      const resp = await route.fetch();
      const j = await resp.json();
      j.classes.objeto = [HOSTILE_IMG, ...(j.classes.objeto || [])];
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify(j),
      });
    };
    await page.route("**/api/catalog", hostileCatRoute);
    const unexpectedPaths = [];
    const watchHostileReqs = (req) => {
      const p = new URL(req.url()).pathname;
      if (p === "/x") unexpectedPaths.push(p);
    };
    page.on("request", watchHostileReqs);
    try {
      await page.reload();
      await loginIfNeeded(context, page);

      // Jerarquia enseña los textos literales
      const jerHostileTxt = await page.locator('[data-panel="jerarquia"]').innerText();
      assert(
        jerHostileTxt.includes(HOSTILE_A) && jerHostileTxt.includes(HOSTILE_IMG),
        "S11(-): Jerarquia no enseña literales hostiles (Xx): " + jerHostileTxt
      );

      // Propiedades y Validacion con la entidad hostil
      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + hIdA + '"]').click();
      await activatePanel(page, "propiedades");
      assert(
        (await page.locator("#f-name").inputValue()) === HOSTILE_A,
        "S11(-): #f-name no contiene el literal hostil A"
      );
      await page.locator("#f-x").focus();
      await waitEditable(page, "#f-x");
      await page.keyboard.press("Control+a");
      await page.keyboard.type("99999");
      await page.keyboard.press("Enter");
      await activatePanel(page, "validacion");
      await page.locator('[data-panel="validacion"] [data-error-pointer]').first().waitFor({ state: "visible", timeout: 5000 });
      await page.locator("#f-x").focus();
      await page.keyboard.press("Escape");
      await page.locator("#f-x").evaluate((el) => el.blur());

      await page.locator('[data-panel="jerarquia"] [data-entity-id="' + hIdImg + '"]').click();
      assert(
        (await page.locator("#f-name").inputValue()) === HOSTILE_IMG,
        "S11(-): #f-name no contiene el literal hostil IMG"
      );

      // Añadir enseña la clase hostil como texto literal
      await activatePanel(page, "anadir");
      await page
        .locator('[data-panel="anadir"] [role="tablist"][aria-label="Tipo"]')
        .locator('[role="tab"], button', { hasText: /^Objetos\b/ })
        .first()
        .click();
      await sleep(100);
      const addHostileTxt = await page.locator('[data-panel="anadir"]').innerText();
      assert(addHostileTxt.includes(HOSTILE_IMG), "S11(-): Añadir no enseña literal hostil del catalogo (Xx)");

      // Actividad enseña el reason y el verb hostiles como texto literal
      await activatePanel(page, "actividad");
      const actHostileCell = (
        await page.locator('tr[data-op-id="op-hostil"] td').nth(5).innerText()
      ).trim();
      assert(actHostileCell === HOSTILE_A, "S11(-): Actividad no enseña literal hostil en Motivo: " + actHostileCell);
      const actHostileVerbCell = (
        await page.locator('tr[data-op-id="op-hostil"] td').nth(6).innerText()
      ).trim();
      assert(
        actHostileVerbCell === HOSTILE_IMG,
        "S11(-): Actividad no enseña literal hostil en Operacion: " + actHostileVerbCell
      );

      // Comprobacion DOM y ejecucion tras mostrar todo sin disparar peticiones nuevas en reposo
      const reqsAfterRender = [];
      const onIdleHostile = (req) => reqsAfterRender.push(req.url());
      page.on("request", onIdleHostile);
      await sleep(400);
      page.off("request", onIdleHostile);

      const domSafety = await page.evaluate(() => ({
        inyeccion: document.querySelectorAll("#inyeccion").length,
        imgs: document.querySelectorAll('img[src="x"], img').length,
        winX: typeof window.__x,
      }));
      assert(
        domSafety.inyeccion === 0 && domSafety.imgs === 0 && domSafety.winX === "undefined",
        "S11(-): inyeccion HTML ejecutada o insertada en el DOM (Xx): " + JSON.stringify(domSafety)
      );
      assert(
        unexpectedPaths.length === 0 && reqsAfterRender.length === 0,
        "S11(-): texto hostil disparo peticiones nuevas: " + JSON.stringify({ unexpectedPaths, reqsAfterRender })
      );
    } finally {
      page.off("request", watchHostileReqs);
      await page.unroute("**/api/catalog", hostileCatRoute);
    }

    // Negativo: limpieza de almacenamientos, consola, peticiones externas y perfil
    const storageAudit = await page.evaluate(() => {
      const localEntries = {};
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        localEntries[k] = localStorage.getItem(k);
      }
      const sessEntries = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        sessEntries[k] = sessionStorage.getItem(k);
      }
      return { localEntries, sessEntries, docCookie: document.cookie };
    });
    const localKeys = Object.keys(storageAudit.localEntries);
    assert(
      localKeys.every((k) => k === "csrf") && Object.keys(storageAudit.sessEntries).length === 0,
      "S11(-): datos fuera de localStorage.csrf en el navegador: " + JSON.stringify({ localKeys, sess: storageAudit.sessEntries })
    );

    const forbiddenEverywhere = [HUMAN_KEY, ...seenCookies];
    const allNonCsrfText = [
      ...Object.entries(storageAudit.localEntries)
        .filter(([k]) => k !== "csrf")
        .map(([, v]) => v),
      ...Object.values(storageAudit.sessEntries),
      storageAudit.docCookie,
    ].join("\n");
    assert(
      !forbiddenEverywhere.some((s) => s && (allNonCsrfText.includes(s) || (storageAudit.localEntries.csrf || "").includes(s))),
      "S11(-): la clave o la cookie aparecen en almacenamiento del navegador"
    );

    const allSecrets = [HUMAN_KEY, ...seenCookies, ...seenCsrf];
    assert(
      !consoleTexts.some((t) => allSecrets.some((s) => s && t.includes(s))),
      "S11(-): secreto filtrado en la consola del navegador"
    );
    const profFinal = await cmd({ cmd: "profile_read" });
    if (profFinal && profFinal.text) {
      assert(
        !allSecrets.some((s) => s && profFinal.text.includes(s)),
        "S11(-): secreto filtrado en profile.json"
      );
    }

    assert(externalRequests.length === 0, "S11(-): peticiones fuera de 127.0.0.1:<puerto>: " + externalRequests.join(", "));
    assert(pageErrors.length === 0, "S11(-): errores de JS en la pagina: " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "S11(-): errores de CSP en la consola"
    );

    console.log("S11 OK");
  } finally {
    await context.close();
  }
}

// ============================================================================
// S12: Quitar del juego (A3, §4.1.1)
// ============================================================================
async function tabToButtonS12(page, exactName) {
  const isCurrent = () =>
    page.evaluate((target) => {
      const a = document.activeElement;
      if (!a || a.tagName !== "BUTTON") return false;
      const label = (a.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
      const txt = (a.textContent || "").replace(/\s+/g, " ").trim();
      return label === target || txt === target;
    }, exactName);

  if (await isCurrent()) return;
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Tab");
    if (await isCurrent()) return;
  }
  for (let i = 0; i < 14; i++) {
    await page.keyboard.press("Shift+Tab");
    if (await isCurrent()) return;
  }
  for (let i = 0; i < 45; i++) {
    await page.keyboard.press("Tab");
    if (await isCurrent()) return;
  }
  throw new Error("S12: no se alcanzo con teclado el boton «" + exactName + "»");
}

async function runS12(browser) {
  await resetBackendState();
  const rSeed = await cmd({
    cmd: "ai_ops",
    label: "Entidad S12",
    ops: [{ name: "entity.add", args: { kind: "objeto", cls: "Barrel_Red", name: "Barril S12", x: 6100, z: 7200, yaw: 0 } }],
  });
  assert(rSeed && rSeed.ok, "S12: fallo ai_ops inicial");
  const snap0 = await cmd({ cmd: "snapshot" });

  const { context, page } = await openStudio(browser);
  try {
    const resetBtn = page
      .locator('[data-testid="barra-superior"]')
      .getByRole("button", { name: "Quitar del juego", exact: true });
    await resetBtn.waitFor({ state: "visible", timeout: 5000 });

    const btnMeta = await resetBtn.evaluate((b) => ({
      inPrimarySlot: !!b.closest('[data-testid="accion-principal"]'),
      label: (b.getAttribute("aria-label") || b.textContent || "").replace(/\s+/g, " ").trim(),
      disabled: b.disabled,
    }));
    assert(
      !btnMeta.inPrimarySlot &&
        btnMeta.label === "Quitar del juego" &&
        !btnMeta.label.startsWith("Aplicar") &&
        !btnMeta.disabled,
      "S12(+): boton 'Quitar del juego' mal ubicado, desactivado o con mal nombre: " + JSON.stringify(btnMeta)
    );

    // Negativo: «Resetear» no aparece en ningun texto (pruebas-mejoras.js:797)
    assert(
      !/Resetear/i.test(await page.locator("body").innerText()),
      "S12(-): aparece 'Resetear' en Escena"
    );

    // Negativo 1: Con el teclado abrir popover y pulsar «Cancelar» -> 0 peticiones
    await tabToButtonS12(page, "Quitar del juego");
    let cancelPostReqs = 0;
    let cancelResetReqs = 0;
    const onCancelReq = (req) => {
      const p = new URL(req.url()).pathname;
      if (p === "/api/reset") cancelResetReqs += 1;
      if (isEffectPost(req)) cancelPostReqs += 1;
    };
    page.on("request", onCancelReq);
    try {
      await page.keyboard.press("Enter");
      const quitarConfirmBtn = page.getByRole("button", { name: "Quitar", exact: true });
      const cancelarConfirmBtn = page.getByRole("button", { name: "Cancelar", exact: true });
      await quitarConfirmBtn.waitFor({ state: "visible", timeout: 5000 });
      await cancelarConfirmBtn.waitFor({ state: "visible", timeout: 5000 });

      const popTxt = (await page.locator("body").innerText()).replace(/\s+/g, " ");
      assert(
        /Quita del juego lo de esta escena\.\s*Lo que no sea de la escena no se toca,\s*y el documento no cambia\./.test(
          popTxt
        ),
        "S12(+): texto de confirmacion del popover distinto de §4.1.1: " + popTxt
      );
      assert(!/Resetear/i.test(popTxt), "S12(-): aparece 'Resetear' con el popover abierto");

      await tabToButtonS12(page, "Cancelar");
      await page.keyboard.press("Enter");
      await quitarConfirmBtn.waitFor({ state: "hidden", timeout: 5000 });
      await sleep(300);
      assert(
        cancelResetReqs === 0 && cancelPostReqs === 0,
        "S12(-): «Cancelar» envio peticiones: reset=" + cancelResetReqs + ", post=" + cancelPostReqs
      );
    } finally {
      page.off("request", onCancelReq);
    }

    // Positivo + Negativo (mata XG): Con el teclado: «Quitar del juego», el popover y «Quitar» ->
    // POST /api/reset con doc_id, Origin y CSRF (200 {ok: true, op_id: "op-77"} sin pasarlo al backend);
    // sin evento -> ninguna fila nueva en 2 s; op_state de op-77 con verb: "scene.reset" -> fila con «Quitar del juego»
    const expectedCsrf = await page.evaluate(() => localStorage.getItem("csrf"));
    assert(expectedCsrf, "S12(+): falta localStorage.csrf");

    let capturedReset = null;
    let resolveResetArrived;
    let resolveReleaseReset;
    const resetArrivedP = new Promise((r) => {
      resolveResetArrived = r;
    });
    const releaseResetGate = new Promise((r) => {
      resolveReleaseReset = r;
    });
    const resetMock200 = async (route) => {
      const req = route.request();
      const allHeaders = await req.allHeaders();
      let parsedBody = null;
      try {
        parsedBody = JSON.parse(req.postData() || "{}");
      } catch {
        parsedBody = null;
      }
      capturedReset = {
        method: req.method(),
        pathname: new URL(req.url()).pathname,
        headers: allHeaders,
        body: parsedBody,
      };
      resolveResetArrived();
      await releaseResetGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify({ ok: true, op_id: "op-77" }),
      });
    };

    await page.route("**/api/reset", resetMock200);
    try {
      await tabToButtonS12(page, "Quitar del juego");
      await page.keyboard.press("Enter");
      await page.getByRole("button", { name: "Quitar", exact: true }).waitFor({ state: "visible", timeout: 5000 });
      await tabToButtonS12(page, "Quitar");
      await page.keyboard.press("Enter");

      await Promise.race([
        resetArrivedP,
        sleep(5000).then(() => {
          throw new Error("S12(+): pulsar «Quitar» con el teclado no envio POST /api/reset");
        }),
      ]);

      // Mientras la peticion esta en vuelo, «Quitar del juego» esta desactivado (§4.1.1)
      await page.waitForFunction(
        () => {
          const bs = Array.from(document.querySelectorAll('[data-testid="barra-superior"] button'));
          const b = bs.find((el) => (el.getAttribute("aria-label") || el.textContent || "").trim() === "Quitar del juego");
          return !!b && b.disabled;
        },
        null,
        { timeout: 3000 }
      );
      resolveReleaseReset();

      assert(
        capturedReset &&
          capturedReset.method === "POST" &&
          capturedReset.pathname === "/api/reset" &&
          capturedReset.body &&
          capturedReset.body.doc_id === snap0.doc_id &&
          Object.keys(capturedReset.body).length === 1,
        "S12(+): cuerpo o metodo de POST /api/reset incorrecto: " + JSON.stringify(capturedReset && capturedReset.body)
      );
      const ctxCookies = await context.cookies();
      const hasSessionCookie = ctxCookies.some((c) => c.name.startsWith("dsbx_session_") && !!c.value);
      const reqHeaders = capturedReset.headers || {};
      assert(
        reqHeaders["origin"] === BASE &&
          reqHeaders["x-csrf-token"] === expectedCsrf &&
          hasSessionCookie,
        "S12(+): POST /api/reset sin Origin, X-CSRF-Token o cookie de sesion: " +
          JSON.stringify({
            origin: reqHeaders["origin"],
            hasCsrf: reqHeaders["x-csrf-token"] === expectedCsrf,
            hasSessionCookie,
          })
      );

      // Negativo (mata XG): tras ese 200 y sin evento op.state, ninguna fila nueva en 2 s
      await activatePanel(page, "actividad");
      await sleep(2100);
      const rowsWithoutEvent = await page.locator('[data-panel="actividad"] tbody tr[data-op-id]').count();
      assert(
        rowsWithoutEvent === 0,
        "S12(-): se creo una fila en Actividad con la respuesta 200 sin op.state (XG): " + rowsWithoutEvent
      );
      const snapUnchanged = await cmd({ cmd: "snapshot" });
      assert(
        snapUnchanged.hash === snap0.hash && snapUnchanged.rev === snap0.rev,
        "S12(+): Quitar del juego cambio el documento"
      );

      // Positivo: un op_state de op-77 con verb: "scene.reset" -> su fila con «Quitar del juego» en Operación
      const rOp77 = await cmd({
        cmd: "op_state",
        op_id: "op-77",
        state: "pendiente",
        origin: "backend",
        verb: "scene.reset",
      });
      assert(rOp77 && rOp77.ok, "S12(+): op_state op-77 fallo");

      const row77 = page.locator('[data-panel="actividad"] tbody tr[data-op-id="op-77"]');
      await row77.waitFor({ state: "visible", timeout: 5000 });
      const cells77 = await row77.locator("td").allInnerTexts();
      assert(
        cells77.length >= 7 &&
          cells77[0].trim() === "op-77" &&
          cells77[2].trim() === "Pendiente" &&
          cells77[4].trim() === "backend" &&
          cells77[6].trim() === "Quitar del juego",
        "S12(+): fila op-77 incorrecta o sin 'Quitar del juego' en Operacion: " + JSON.stringify(cells77)
      );
    } finally {
      await page.unroute("**/api/reset", resetMock200);
    }

    // Negativo 2: un 409 queue_full de page.route -> su code y su pointer (y msg) a la vista, sin fila nueva
    const resetMock409 = async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify({
          ok: false,
          code: "queue_full",
          pointer: "/ops",
          msg: "Cola del bridge llena",
        }),
      });
    };
    await page.route("**/api/reset", resetMock409);
    try {
      const r409P = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/reset" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await resetBtn.click();
      await page.getByRole("button", { name: "Quitar", exact: true }).click();
      assert((await r409P).status() === 409, "S12(-): mock 409 no dio 409");
      await page.waitForFunction(
        () => {
          const t = document.body.innerText || "";
          return t.includes("queue_full") && t.includes("/ops") && t.includes("Cola del bridge llena");
        },
        null,
        { timeout: 5000 }
      );
      assert(
        (await page.locator('[data-panel="actividad"] tbody tr[data-op-id]').count()) === 1,
        "S12(-): el 409 queue_full añadio una fila en Actividad"
      );
    } finally {
      await page.unroute("**/api/reset", resetMock409);
    }

    // Negativo 3a: F2 trae la ruta real POST /api/reset en server.py (sin page.route);
    // exige cookie+Origin+CSRF (un fallo de CSRF daria 403 csrf_failed y una ruta desconocida, 404)
    // y sin servidor con escena responde 409 scene_unsupported -> apply-error visible, sin quitar-no-disponible ni fila nueva
    const real409RespP = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/reset" && r.request().method() === "POST",
      { timeout: 5000 }
    );
    await resetBtn.click();
    await page.getByRole("button", { name: "Quitar", exact: true }).click();
    const real409Resp = await real409RespP;
    const real409Json = await real409Resp.json().catch(() => ({}));
    assert(
      real409Resp.status() === 409 && real409Json.code === "scene_unsupported",
      "S12(-): la ruta real /api/reset no respondio 409 scene_unsupported (comprueba cookie/Origin/CSRF): status=" +
        real409Resp.status() +
        ", body=" +
        JSON.stringify(real409Json)
    );

    const applyErrAviso = page.locator('[data-aviso="apply-error"]');
    await applyErrAviso.first().waitFor({ state: "visible", timeout: 5000 });
    const applyErrRole = await applyErrAviso.first().getAttribute("role");
    assert(applyErrRole === "alert", "S12(-): apply-error sin role alert: " + applyErrRole);
    const applyErrTxt = await applyErrAviso.first().innerText();
    assert(
      applyErrTxt.includes("scene_unsupported"),
      "S12(-): apply-error no contiene 'scene_unsupported': " + applyErrTxt
    );
    assert(
      (await page.locator('[data-aviso="quitar-no-disponible"]').count()) === 0,
      "S12(-): aparecio quitar-no-disponible con 409 scene_unsupported"
    );
    await sleep(400);
    assert(
      (await page.locator('[data-panel="actividad"] tbody tr[data-op-id]').count()) === 1,
      "S12(-): el 409 scene_unsupported de /api/reset añadio una fila en Actividad"
    );
    await applyErrAviso.first().getByRole("button", { name: "Cerrar", exact: true }).click();
    await applyErrAviso.first().waitFor({ state: "hidden", timeout: 5000 });

    // Negativo 3b: como F2 trae la ruta /api/reset, el 404 not_found ya solo se ve con el mock
    // -> quitar-no-disponible, sin fila nueva
    const resetMock404 = async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify({
          ok: false,
          code: "not_found",
          pointer: "",
          msg: "Ruta desconocida",
        }),
      });
    };
    await page.route("**/api/reset", resetMock404);
    try {
      const r404P = page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api/reset" && r.request().method() === "POST",
        { timeout: 5000 }
      );
      await resetBtn.click();
      await page.getByRole("button", { name: "Quitar", exact: true }).click();
      const r404Resp = await r404P;
      const r404Json = await r404Resp.json().catch(() => ({}));
      assert(
        r404Resp.status() === 404 && r404Json.code === "not_found",
        "S12(-): mock 404 de /api/reset no respondio 404 not_found: status=" +
          r404Resp.status() +
          ", body=" +
          JSON.stringify(r404Json)
      );

      const noDispAviso = page.locator('[data-aviso="quitar-no-disponible"]');
      await noDispAviso.first().waitFor({ state: "visible", timeout: 5000 });
      const noDispRole = await noDispAviso.first().getAttribute("role");
      assert(noDispRole === "alert" || noDispRole === "status", "S12(-): quitar-no-disponible sin role alert/status");
      const noDispTxt = await noDispAviso.first().innerText();
      assert(
        /Quitar del juego llega con F2/.test(noDispTxt),
        "S12(-): quitar-no-disponible no dice 'Quitar del juego llega con F2': " + noDispTxt
      );
      await sleep(400);
      assert(
        (await page.locator('[data-panel="actividad"] tbody tr[data-op-id]').count()) === 1,
        "S12(-): el 404 de /api/reset añadio una fila en Actividad"
      );
    } finally {
      await page.unroute("**/api/reset", resetMock404);
    }

    // Negativo 4: «Resetear» no aparece tampoco en Rodaje, y sin backend «Quitar del juego» queda desactivado
    await switchMode(page, "rodaje");
    assert(!/Resetear/i.test(await page.locator("body").innerText()), "S12(-): aparece 'Resetear' en Rodaje");
    await switchMode(page, "escena");

    await cmd({ cmd: "stop_backend" });
    await page.locator('[data-aviso="sin-backend"]').first().waitFor({ state: "visible", timeout: 10000 });
    assert(await resetBtn.isDisabled(), "S12(-): 'Quitar del juego' no se desactivo sin backend");
    await cmd({ cmd: "start_backend" });

    console.log("S12 OK");
  } finally {
    await cmd({ cmd: "start_backend" }).catch(() => {});
    await context.close();
  }
}

const ROW_RUNNERS = {
  S1: runS1,
  S2: runS2,
  S3: runS3,
  S4: runS4,
  S5: runS5,
  S6: runS6,
  S7: runS7,
  S8: runS8,
  S9: runS9,
  S10: runS10,
  S11: runS11,
  S12: runS12,
};

async function main() {
  const selectedRows = resolveSelectedRows();
  const browser = await chromium.launch({ headless: true });
  try {
    for (const rowId of selectedRows) {
      await ROW_RUNNERS[rowId](browser);
    }
    // Comprobacion transversal al final de cualquier corrida (tambien con DSBX_ONLY)
    assert(externalRequests.length === 0, "Peticiones externas detectadas: " + externalRequests.join(", "));
    assert(pageErrors.length === 0, "Errores de JS (pageerror): " + pageErrors.join(" | "));
    assert(
      !consoleTexts.some((t) => t.includes("Content Security Policy") || t.includes("Refused to")),
      "Violacion de CSP en consola"
    );
    const allSecrets = [HUMAN_KEY, ...seenCookies, ...seenCsrf];
    assert(
      !consoleTexts.some((t) => allSecrets.some((s) => s && t.includes(s))),
      "Un secreto aparece en la consola del navegador"
    );
    console.log("STUDIO E2E OK (" + selectedRows.join(",") + ")");
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
