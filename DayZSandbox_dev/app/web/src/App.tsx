import { useCallback, useEffect, useRef, useState } from "react";
import type { FunctionComponent } from "react";
import {
  DockviewReact,
  type DockviewReadyEvent,
  type IDockviewPanelHeaderProps,
  type IDockviewPanelProps,
} from "dockview-react";
import { AddPanel } from "./panels/AddPanel";
import { ActivityPanel } from "./panels/ActivityPanel";
import { HierarchyPanel } from "./panels/HierarchyPanel";
import { PlaceholderPanel } from "./panels/Placeholders";
import { PropertiesPanel, confirmActiveFieldBeforeApply } from "./panels/PropertiesPanel";
import { ValidationPanel } from "./panels/ValidationPanel";
import {
  ACTIONS,
  BROWSER_RESERVED_COMBOS,
  comboOf,
  findConflict,
  keyLabel,
  type ShortcutActionDef,
} from "./shortcuts";
import {
  PANEL_TITLES,
  getAllowedPanelsForMode,
  toggleStudioPanel,
} from "./layout";
import {
  applyCurrentModePropsLeftPreset,
  applyLayoutToDockview,
  copySelectedCoordinates,
  deleteSelectedEntities,
  duplicateSelectedEntity,
  fetchAuthoritativeScene,
  getDockviewApi,
  getState,
  handleDockviewLayoutChange,
  handleOpStateEvent,
  handleSnapshotEvent,
  loadInitialStudioData,
  markBackendAlive,
  markBackendDown,
  openPropertiesAndFocus,
  placeSelectedCatalogItem,
  releaseActiveLeaseOnUnmount,
  resetAllShortcutsToDefault,
  resetCurrentModeLayoutToFactory,
  resetStudioState,
  setDockviewApi,
  setFlash,
  setState,
  switchStudioMode,
  triggerApplyScene,
  triggerResetScene,
  triggerUndoRedo,
  updateShortcutBinding,
  useStudioStore,
} from "./store";
import type { StudioPanelId } from "./types";

type PanelComponent = FunctionComponent<IDockviewPanelProps>;

function placeholderFor(id: StudioPanelId): PanelComponent {
  return function Placeholder() {
    return <PlaceholderPanel id={id} />;
  };
}

const PANEL_COMPONENTS: Record<string, PanelComponent> = {
  jerarquia: HierarchyPanel,
  mapa: placeholderFor("mapa"),
  propiedades: PropertiesPanel,
  anadir: AddPanel,
  actividad: ActivityPanel,
  validacion: ValidationPanel,
  historial: placeholderFor("historial"),
  ia: placeholderFor("ia"),
  camaras: placeholderFor("camaras"),
  tomas: placeholderFor("tomas"),
  preparacion: placeholderFor("preparacion"),
  "vista-previa": placeholderFor("vista-previa"),
};

function StudioTab({ api }: IDockviewPanelHeaderProps) {
  // Se suscribe al título como la pestaña de serie de dockview-react (useTitle): sin esto, un
  // setTitle (la cuenta de Actividad, §5.4) no se repinta.
  const [title, setTitle] = useState(api.title ?? "");
  useEffect(() => {
    const disposable = api.onDidTitleChange((event) => {
      setTitle(event.title ?? "");
    });
    if (title !== (api.title ?? "")) setTitle(api.title ?? "");
    return () => {
      disposable.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);
  return <span className="studio-tab">{title}</span>;
}

const TAB_COMPONENTS: Record<string, FunctionComponent<IDockviewPanelHeaderProps>> = {
  studioTab: StudioTab,
};

interface ConflictState {
  actionId: string;
  combo: string;
  other: ShortcutActionDef;
}

function formatSaveAge(lastCommitPerfMs: number | null, now: number): string {
  if (lastCommitPerfMs === null) return "sin guardar";
  const sec = Math.max(0, Math.floor((now - lastCommitPerfMs) / 1000));
  if (sec <= 59) return `hace ${sec} s`;
  const min = Math.floor(sec / 60);
  if (min <= 59) return `hace ${min} min`;
  return `hace ${Math.floor(min / 60)} h`;
}

function formatEventAge(lastEventPerfMs: number, now: number): string {
  const sec = Math.max(0, Math.floor((now - lastEventPerfMs) / 1000));
  if (sec <= 59) return `hace ${sec} s`;
  const min = Math.floor(sec / 60);
  if (min <= 59) return `hace ${min} min`;
  return `hace ${Math.floor(min / 60)} h`;
}

function isTextField(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node || !node.tagName) return false;
  const tag = node.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    node.isContentEditable === true
  );
}

export default function App() {
  const st = useStudioStore();
  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [capturing, setCapturing] = useState<string | null>(null);
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [captureMsg, setCaptureMsg] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const shortcutsReturnFocus = useRef<HTMLElement | null>(null);

  const expireSession = useCallback(() => {
    releaseActiveLeaseOnUnmount();
    setState({
      view: "login",
      connected: false,
      loginMessage: "Sesión caducada: vuelve a entrar",
    });
  }, []);

  // Entrada (§3.2, P1): csrf en localStorage y GET /api/session.
  useEffect(() => {
    let cancelled = false;
    const csrf = localStorage.getItem("csrf");
    if (!csrf) {
      setState({ view: "login" });
      return;
    }
    fetch("/api/session", { credentials: "same-origin" })
      .then((res) => {
        if (cancelled) return;
        if (res.status === 200) {
          setState({ view: "studio" });
          void loadInitialStudioData();
        } else {
          setState({ view: "login" });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ view: "login" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // SSE y reconexión (P1-P9b).
  useEffect(() => {
    if (st.view !== "studio") return;
    let cancelled = false;
    let es: EventSource | null = null;
    let retryTimer: number | null = null;
    let checking = false;

    function close() {
      if (es) {
        es.close();
        es = null;
      }
    }

    function scheduleRetry() {
      if (cancelled) return;
      retryTimer = window.setTimeout(checkSession, 3000);
    }

    function checkSession() {
      if (cancelled || checking) return;
      checking = true;
      fetch("/api/session", { credentials: "same-origin" })
        .then((res) => {
          checking = false;
          if (cancelled) return;
          if (res.status === 401) {
            close();
            expireSession();
          } else {
            start();
          }
        })
        .catch(() => {
          checking = false;
          if (cancelled) return;
          markBackendDown();
          scheduleRetry();
        });
    }

    function start() {
      if (cancelled) return;
      close();
      const src = new EventSource("/api/events");
      es = src;
      src.addEventListener("snapshot", (ev) => {
        try {
          handleSnapshotEvent(
            JSON.parse((ev as MessageEvent).data) as Parameters<
              typeof handleSnapshotEvent
            >[0]
          );
        } catch {
          // evento malformado: se ignora
        }
      });
      src.addEventListener("op.state", (ev) => {
        try {
          handleOpStateEvent(
            JSON.parse((ev as MessageEvent).data) as Parameters<
              typeof handleOpStateEvent
            >[0]
          );
        } catch {
          // evento malformado: se ignora
        }
      });
      src.addEventListener("scene.commit", () => {
        void fetchAuthoritativeScene(true);
      });
      src.onopen = () => {
        if (cancelled) return;
        markBackendAlive();
        setState({ connected: true });
      };
      src.onerror = () => {
        if (cancelled) return;
        setState({ connected: false });
        if (src.readyState === EventSource.CLOSED) {
          checkSession();
        }
      };
    }

    start();
    return () => {
      cancelled = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      close();
    };
  }, [st.view, expireSession]);

  // Sin SSE abierto: sesión y escena cada 3 s (§3.2).
  useEffect(() => {
    if (st.view !== "studio" || st.connected) return;
    let cancelled = false;
    const poll = () => {
      fetch("/api/session", { credentials: "same-origin" })
        .then((res) => {
          if (cancelled) return;
          if (res.status === 401) {
            expireSession();
            return;
          }
          markBackendAlive();
          void fetchAuthoritativeScene(false);
        })
        .catch(() => {
          if (!cancelled) markBackendDown();
        });
    };
    poll();
    const id = window.setInterval(poll, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [st.view, st.connected, expireSession]);

  // Recalculo de edades (§5.2.3 de F1b-web / P2b).
  useEffect(() => {
    if (st.view !== "studio") return;
    const id = window.setInterval(() => {
      setState((prev) => ({ tick: prev.tick + 1 }));
    }, 1000);
    return () => window.clearInterval(id);
  }, [st.view]);

  // El aviso breve se retira solo.
  useEffect(() => {
    if (!st.flash) return;
    const id = window.setTimeout(() => {
      if (getState().flash === st.flash) setFlash(null);
    }, 4000);
    return () => window.clearTimeout(id);
  }, [st.flash]);

  // Foco del diálogo de atajos y devolución al cerrar.
  useEffect(() => {
    if (st.shortcutsOpen) {
      window.setTimeout(() => dialogRef.current?.focus(), 0);
    } else if (shortcutsReturnFocus.current) {
      shortcutsReturnFocus.current.focus?.();
      shortcutsReturnFocus.current = null;
    }
  }, [st.shortcutsOpen]);

  // Cierre de menú/popover al pulsar fuera.
  useEffect(() => {
    if (!st.toolsMenuOpen && !popoverOpen) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      if (t && (t.closest("[data-keep-open]") || t.closest("[data-menu-trigger]"))) return;
      if (st.toolsMenuOpen) setState({ toolsMenuOpen: false });
      setPopoverOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [st.toolsMenuOpen, popoverOpen]);

  // Atajos (§6.2) y captura de teclas del diálogo (§6.4).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const cur = getState();
      if (cur.view !== "studio") return;
      const target = e.target as HTMLElement | null;

      if (cur.shortcutsOpen) {
        if (conflict) {
          if (e.key === "Escape") {
            e.preventDefault();
            setConflict(null);
          }
          return;
        }
        if (capturing) {
          if (e.key === "Escape") {
            e.preventDefault();
            setCapturing(null);
            setCaptureMsg(null);
            return;
          }
          const combo = comboOf(e);
          if (!combo) return;
          e.preventDefault();
          if (BROWSER_RESERVED_COMBOS.has(combo)) {
            setCaptureMsg("La atiende el navegador. Elige otra.");
            return;
          }
          const other = findConflict(cur.keymap, capturing, combo);
          if (other) {
            if (other.mandatory) {
              setCaptureMsg(
                `${keyLabel(combo)} ya es «${other.name}», que no puede quedarse sin tecla. Elige otra.`
              );
            } else {
              setConflict({ actionId: capturing, combo, other });
              setCapturing(null);
              setCaptureMsg(null);
            }
            return;
          }
          updateShortcutBinding(capturing, combo);
          setCapturing(null);
          setCaptureMsg(null);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setState({ shortcutsOpen: false });
        }
        return;
      }

      const inField = isTextField(target);
      const combo = comboOf(e);

      if (inField) {
        const aplicar = cur.keymap["aplicar"];
        if (combo && aplicar && combo === aplicar) {
          e.preventDefault();
          // Una tecla mantenida no repite Aplicar tampoco desde un campo (§6.2; Sol, F03).
          if (e.repeat) return;
          void (async () => {
            const ok = await confirmActiveFieldBeforeApply();
            if (ok) await triggerApplyScene();
          })();
        }
        return;
      }

      if (!combo) return;

      if (combo === "Escape") {
        if (cur.toolsMenuOpen) {
          e.preventDefault();
          setState({ toolsMenuOpen: false });
          return;
        }
        if (popoverOpen) {
          e.preventDefault();
          setPopoverOpen(false);
          return;
        }
        if (cur.placingItem) {
          e.preventDefault();
          setState({ placingItem: null });
          return;
        }
        if (cur.keymap["parar"] === "Escape") {
          e.preventDefault();
          setFlash("Llega con F5");
        }
        return;
      }

      if (target && target.tagName === "BUTTON" && e.key === " ") return;

      const bound = ACTIONS.filter((a) => cur.keymap[a.id] === combo);
      const active = bound.find((a) => a.ctx !== "toma");
      if (!active) {
        if (bound.length > 0) {
          // Una tecla que solo es de toma no le quita a un botón, enlace o resumen su activación
          // nativa: con Colocar fuera de Intro, Intro tiene que seguir pulsando botones.
          if (
            (combo === "Enter" || combo === "Space") &&
            target &&
            target.matches("button, a[href], summary")
          ) {
            return;
          }
          e.preventDefault();
          setFlash("Llega con F5");
        }
        return;
      }

      if (e.repeat && ["colocar", "aplicar", "preparar", "rodar"].includes(active.id)) {
        return;
      }

      switch (active.id) {
        case "colocar":
          if (cur.placingItem && !cur.sinBackend) {
            e.preventDefault();
            void placeSelectedCatalogItem();
          }
          return;
        case "aplicar":
          e.preventDefault();
          void (async () => {
            const ok = await confirmActiveFieldBeforeApply();
            if (ok) await triggerApplyScene();
          })();
          return;
        case "deshacer":
          e.preventDefault();
          void triggerUndoRedo(false);
          return;
        case "rehacer":
          e.preventDefault();
          void triggerUndoRedo(true);
          return;
        case "guardar":
          e.preventDefault();
          setFlash(
            cur.sinBackend
              ? "No se puede guardar: no hay backend"
              : "Cada cambio se guarda al momento"
          );
          return;
        case "borrar":
          e.preventDefault();
          void deleteSelectedEntities();
          return;
        case "duplicar":
          e.preventDefault();
          void duplicateSelectedEntity();
          return;
        case "seleccionar-todo":
          e.preventDefault();
          setState({ selectedIds: (cur.doc?.entities ?? []).map((x) => x.id) });
          return;
        case "ir-propiedades":
          e.preventDefault();
          openPropertiesAndFocus();
          return;
        case "copiar-coordenadas":
          e.preventDefault();
          copySelectedCoordinates();
          return;
        case "modo-escena":
          e.preventDefault();
          switchStudioMode("escena");
          return;
        case "modo-rodaje":
          e.preventDefault();
          switchStudioMode("rodaje");
          return;
        default:
          return;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [capturing, conflict, popoverOpen]);

  // §5.4: la pestaña de Actividad lleva la cuenta de las órdenes en curso. Solo se toca el
  // título cuando cambia, para no disparar guardados del layout de más.
  const activeOpsCount = st.rows.filter(
    (r) => r.state === "pendiente" || r.state === "ejecutando"
  ).length;
  useEffect(() => {
    const panel = getDockviewApi()?.getPanel("actividad");
    if (!panel) return;
    const title = activeOpsCount > 0 ? `Actividad · ${activeOpsCount}` : "Actividad";
    if (panel.title !== title) panel.api.setTitle(title);
  });

  const onLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (loginBusy) return;
    setLoginBusy(true);
    fetch("/api/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: password }),
    })
      .then(async (res) => {
        setLoginBusy(false);
        if (res.status === 200) {
          const data = (await res.json()) as { csrf?: string };
          if (data.csrf) localStorage.setItem("csrf", data.csrf);
          setPassword("");
          resetStudioState();
          void loadInitialStudioData();
        } else {
          setState({ loginMessage: "Clave no válida" });
        }
      })
      .catch(() => {
        setLoginBusy(false);
        setState({ loginMessage: "Clave no válida" });
      });
  };

  const onReady = useCallback((event: DockviewReadyEvent) => {
    setDockviewApi(event.api);
    event.api.onDidLayoutChange(() => {
      handleDockviewLayoutChange();
    });
    const cur = getState();
    applyLayoutToDockview(event.api, cur.mode, cur.layouts[cur.mode]);
  }, []);

  const onDialogKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const root = dialogRef.current;
    if (!root) return;
    const focusables = Array.from(
      root.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      )
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const activeEl = document.activeElement as HTMLElement | null;
    if (e.shiftKey && (activeEl === first || activeEl === root)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && activeEl === last) {
      e.preventDefault();
      first.focus();
    }
  };

  if (st.view === "checking") {
    return (
      <main className="page">
        <h1>Estudio · DayZ Sandbox</h1>
        <p>Cargando…</p>
      </main>
    );
  }

  if (st.view === "login") {
    return (
      <main className="page">
        <h1>Estudio · DayZ Sandbox</h1>
        <form onSubmit={onLogin} className="login-form">
          <label htmlFor="human-key">
            Clave de persona (<code>human_key</code> de <code>backend.json</code>)
          </label>
          <input
            id="human-key"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button type="submit" disabled={loginBusy}>
            Entrar
          </button>
          {st.loginMessage ? <p role="alert">{st.loginMessage}</p> : null}
        </form>
      </main>
    );
  }

  const now = performance.now();
  const docName = st.doc?.name ?? (st.docInfo ? "Escena" : "Sin escena");
  const lastObservedRevs = st.rows
    .filter((r) => r.state === "observado" && typeof r.rev === "number")
    .map((r) => r.rev as number);
  const lastObservedRev =
    lastObservedRevs.length > 0 ? Math.max(...lastObservedRevs) : null;
  const pendingChanges =
    st.docInfo && lastObservedRev !== null ? st.docInfo.rev - lastObservedRev : 0;
  const pendingLabel =
    pendingChanges > 0
      ? `${pendingChanges} ${pendingChanges === 1 ? "cambio sin aplicar" : "cambios sin aplicar"}`
      : "Sin aplicar";

  const rejectedCount = Object.keys(st.rejectedDrafts).length;
  const applyDisabled =
    !st.docInfo || st.applying || st.sinBackend || rejectedCount > 0;
  const applyTitle = st.sinBackend
    ? "Sin conexión con el backend: no se puede aplicar"
    : rejectedCount > 0
    ? "Corrige o descarta (Esc) los campos con error antes de aplicar"
    : !st.docInfo
    ? "Sin escena cargada"
    : undefined;

  const failingRows = st.rows.filter(
    (r) => r.state === "fallido" || r.state === "parcial"
  ).length;
  const problemCount = st.validationErrors.length + failingRows;
  const validationText = st.sinBackend
    ? "Sin validar"
    : problemCount === 0
    ? "Escena sin errores"
    : `${problemCount} ${problemCount === 1 ? "problema" : "problemas"}`;

  const mode = st.mode;
  const allowedPanels = getAllowedPanelsForMode(mode);
  const api = getDockviewApi();

  const closeShortcuts = () => {
    setCapturing(null);
    setConflict(null);
    setCaptureMsg(null);
    setState({ shortcutsOpen: false });
  };

  return (
    <div className="studio-shell">
      <header className="topbar" data-testid="barra-superior">
        <div className="topbar-left">
          <div className="doc-summary" title={st.docInfo ? `rev ${st.docInfo.rev}` : undefined}>
            <span className="doc-name">{docName}</span>
            <span className="doc-meta">{pendingLabel}</span>
            <span className="doc-meta">
              {formatSaveAge(st.lastCommitPerfMs, now)}
            </span>
          </div>
          <button
            type="button"
            className="btn sm"
            title="Deshacer"
            disabled={st.sinBackend || !st.docInfo}
            onClick={() => void triggerUndoRedo(false)}
          >
            Deshacer <kbd>{keyLabel(st.keymap["deshacer"])}</kbd>
          </button>
          <button
            type="button"
            className="btn sm"
            title="Rehacer"
            disabled={st.sinBackend || !st.docInfo}
            onClick={() => void triggerUndoRedo(true)}
          >
            Rehacer <kbd>{keyLabel(st.keymap["rehacer"])}</kbd>
          </button>
        </div>

        <div className="topbar-center">
          <div className="mode-switch" role="group" aria-label="Modo">
            <button
              type="button"
              aria-pressed={mode === "escena"}
              onClick={() => switchStudioMode("escena")}
            >
              Escena <kbd>{keyLabel(st.keymap["modo-escena"])}</kbd>
            </button>
            <button
              type="button"
              aria-pressed={mode === "rodaje"}
              onClick={() => switchStudioMode("rodaje")}
            >
              Rodaje <kbd>{keyLabel(st.keymap["modo-rodaje"])}</kbd>
            </button>
          </div>
        </div>

        <div className="topbar-right">
          <div data-keep-open data-menu-trigger>
            <button
              type="button"
              className="btn sm"
              disabled={st.sinBackend || st.applying || st.removing}
              aria-haspopup="dialog"
              aria-expanded={popoverOpen}
              onClick={() => setPopoverOpen((v) => !v)}
            >
              Quitar del juego
            </button>
            {popoverOpen ? (
              <div className="menu popover" role="dialog" aria-label="Quitar del juego">
                <p className="popover-text">
                  Quita del juego lo de esta escena. Lo que no sea de la escena no se
                  toca, y el documento no cambia.
                </p>
                <div className="popover-actions">
                  <button
                    type="button"
                    className="btn sm danger"
                    onClick={() => {
                      setPopoverOpen(false);
                      void triggerResetScene();
                    }}
                  >
                    Quitar
                  </button>
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() => setPopoverOpen(false)}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div data-testid="accion-principal">
            <button
              type="button"
              className="btn primary"
              title={applyTitle}
              disabled={applyDisabled}
              onClick={() => void triggerApplyScene()}
            >
              Aplicar rev {st.docInfo ? st.docInfo.rev : "—"}
            </button>
          </div>

          <div data-menu-trigger>
            <button
              type="button"
              className="btn sm"
              aria-haspopup="menu"
              aria-expanded={st.toolsMenuOpen}
              onClick={() => setState({ toolsMenuOpen: !st.toolsMenuOpen })}
            >
              Herramientas
            </button>
            {st.toolsMenuOpen ? (
              <div className="menu" role="menu" data-keep-open>
                <div className="menu-sec">Paneles</div>
                {allowedPanels.map((id) => (
                  <button
                    key={id}
                    type="button"
                    role="menuitem"
                    className="mi"
                    onClick={() => {
                      if (api) toggleStudioPanel(api, mode, id);
                      setState({ toolsMenuOpen: false });
                    }}
                  >
                    <span>{PANEL_TITLES[id]}</span>
                    <span>{api?.getPanel(id) ? "Abierto" : "Cerrado"}</span>
                  </button>
                ))}
                <div className="menu-sep" />
                <div className="menu-sec">Layouts</div>
                <button
                  type="button"
                  role="menuitem"
                  className="mi"
                  onClick={() => {
                    resetCurrentModeLayoutToFactory();
                    setState({ toolsMenuOpen: false });
                  }}
                >
                  De fábrica
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="mi"
                  onClick={() => {
                    applyCurrentModePropsLeftPreset();
                    setState({ toolsMenuOpen: false });
                  }}
                >
                  Propiedades a la izquierda
                </button>
                <div className="menu-sep" />
                <button
                  type="button"
                  role="menuitem"
                  className="mi"
                  onClick={() => {
                    shortcutsReturnFocus.current =
                      document.activeElement as HTMLElement | null;
                    setState({ shortcutsOpen: true, toolsMenuOpen: false });
                  }}
                >
                  Atajos de teclado…
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="notices">
        {st.notice ? (
          <div className="notice-strip" role="alert" data-aviso={st.notice.kind}>
            <span>{st.notice.message}</span>
            <button
              type="button"
              className="btn sm"
              onClick={() => setState({ notice: null })}
            >
              Cerrar
            </button>
          </div>
        ) : null}
        {st.flash ? (
          <div className="notice-strip" role="status" data-aviso="info">
            <span>{st.flash}</span>
          </div>
        ) : null}
        {st.applyError ? (
          <div className="notice-strip err" role="alert" data-aviso="apply-error">
            <span>
              {st.applyError.code}
              {st.applyError.pointer ? ` · ${st.applyError.pointer}` : ""}
              {st.applyError.msg ? `: ${st.applyError.msg}` : ""}
            </span>
            <button
              type="button"
              className="btn sm"
              onClick={() => setState({ applyError: null })}
            >
              Cerrar
            </button>
          </div>
        ) : null}
      </div>

      <div className="workspace">
        <DockviewReact
          className="dockview-theme-dsbx"
          components={PANEL_COMPONENTS}
          tabComponents={TAB_COMPONENTS}
          disableFloatingGroups
          onReady={onReady}
        />
      </div>

      <footer className="statusbar" data-testid="barra-estado">
        <span className="peer back-label">Backend</span>
        <span className={st.connected ? "peer ok" : "peer warn"}>
          <span className="dot" />
          <span>{st.connected ? "Conectado" : "Reconectando…"}</span>
        </span>
        <span className="peer stale">{formatEventAge(st.lastEventPerfMs, now)}</span>
        <span className="peer stale" title="Llega con el bridge">
          <span className="dot" />
          Servidor · Sin datos
        </span>
        <span className="peer stale" title="Llega con el bridge">
          <span className="dot" />
          Tu juego · Sin datos
        </span>
        <span>Catálogo: {st.catalog?.source ?? "fixture"}</span>
        <span>{validationText}</span>
      </footer>

      {st.shortcutsOpen ? (
        <div className="modal-bg" data-keep-open>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Atajos de teclado"
            tabIndex={-1}
            ref={dialogRef}
            onKeyDown={onDialogKeyDown}
          >
            <div className="modal-h">
              <span>Atajos de teclado</span>
              <button type="button" className="btn sm" onClick={closeShortcuts}>
                Cerrar
              </button>
            </div>
            <div className="modal-b">
              <div className="klist" role="list">
                {ACTIONS.map((action) => (
                  <div
                    key={action.id}
                    role="listitem"
                    className="krow"
                    data-action={action.id}
                  >
                    <span>{action.name}</span>
                    <span className="krow-ctx">
                      {action.ctx === "global"
                        ? "global"
                        : action.ctx === "escena"
                        ? "escena"
                        : "toma"}
                    </span>
                    <kbd>{keyLabel(st.keymap[action.id])}</kbd>
                    <button
                      type="button"
                      className="btn sm"
                      aria-label={`Cambiar la tecla de ${action.name}`}
                      onClick={() => {
                        setConflict(null);
                        setCaptureMsg(null);
                        setCapturing(action.id);
                      }}
                    >
                      Cambiar
                    </button>
                  </div>
                ))}
              </div>
              <div id="kconf" className="kconf" hidden={!captureMsg && !conflict && !capturing}>
                {conflict ? (
                  <>
                    <span>
                      {keyLabel(conflict.combo)} ya es «{conflict.other.name}»
                    </span>
                    <span className="kconf-actions">
                      <button
                        type="button"
                        className="btn sm"
                        onClick={() => {
                          updateShortcutBinding(
                            conflict.actionId,
                            conflict.combo,
                            conflict.other.id
                          );
                          setConflict(null);
                        }}
                      >
                        Reemplazar
                      </button>
                      <button
                        type="button"
                        className="btn sm"
                        onClick={() => setConflict(null)}
                      >
                        Cancelar
                      </button>
                    </span>
                  </>
                ) : (
                  <span>
                    {captureMsg ?? "Pulsa una tecla…"}
                    {captureMsg && capturing
                      ? ""
                      : ""}
                  </span>
                )}
                {capturing && !conflict ? (
                  <span className="kconf-actions">
                    <button
                      type="button"
                      className="btn sm"
                      onClick={() => {
                        setCapturing(null);
                        setCaptureMsg(null);
                      }}
                    >
                      Cancelar
                    </button>
                  </span>
                ) : null}
              </div>
            </div>
            <div className="modal-f">
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  resetAllShortcutsToDefault();
                  setCapturing(null);
                  setConflict(null);
                  setCaptureMsg(null);
                }}
              >
                Restaurar
              </button>
              <span className="meta">Esc cierra el diálogo</span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
