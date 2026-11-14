import { useEffect, useRef, useState } from "react";

type View = "checking" | "login" | "queue";

interface OpData {
  op_id: string;
  state: string;
  rev?: number;
  hash?: string;
  at_ms?: number;
  origin?: string;
  age_ms?: number;
}

interface Anchor {
  atMs: number;
  ageMs: number | null;
  perfMs: number;
  unknown: boolean;
}

interface Row {
  op_id: string;
  state: string;
  rev?: number;
  hash?: string;
  at_ms?: number;
  origin?: string;
  anchor: Anchor;
}

interface DocInfo {
  doc_id: string;
  rev: number;
  hash: string;
}

const STATE_LABELS: Record<string, string> = {
  pendiente: "Pendiente",
  ejecutando: "Ejecutando",
  aplicado: "Aplicado",
  observado: "Observado",
  fallido: "Fallido",
  parcial: "Parcial",
};

// Solo las seis claves propias: un estado como «toString» no puede colarse por el prototipo.
function isKnownState(state: string): boolean {
  return Object.prototype.hasOwnProperty.call(STATE_LABELS, state);
}

function stateLabel(state: string): string {
  return isKnownState(state) ? STATE_LABELS[state] : `Desconocido (${state})`;
}

function makeAnchor(op: OpData, source: "snapshot" | "op.state", existing?: Row): Anchor {
  const perf = performance.now();
  const atMs = typeof op.at_ms === "number" ? op.at_ms : 0;
  if (existing && existing.anchor.atMs === atMs) {
    if (source === "snapshot" && typeof op.age_ms === "number") {
      const displayed = existing.anchor.unknown || existing.anchor.ageMs === null
        ? null
        : existing.anchor.ageMs + (perf - existing.anchor.perfMs);
      if (displayed === null || op.age_ms > displayed) {
        return { atMs, ageMs: op.age_ms, perfMs: perf, unknown: false };
      }
    }
    return existing.anchor;
  }
  if (source === "snapshot" && typeof op.age_ms === "number") {
    return { atMs, ageMs: op.age_ms, perfMs: perf, unknown: false };
  }
  const nowWall = Date.now();
  if (atMs - nowWall > 2000) {
    return { atMs, ageMs: null, perfMs: perf, unknown: true };
  }
  return { atMs, ageMs: Math.max(0, nowWall - atMs), perfMs: perf, unknown: false };
}

function rowFromOp(op: OpData, source: "snapshot" | "op.state", existing?: Row): Row {
  return {
    op_id: op.op_id,
    state: op.state,
    rev: op.rev,
    hash: op.hash,
    at_ms: op.at_ms,
    origin: op.origin,
    anchor: makeAnchor(op, source, existing),
  };
}

function displayedAgeMs(row: Row): number | null {
  if (row.anchor.unknown || row.anchor.ageMs === null) return null;
  return row.anchor.ageMs + (performance.now() - row.anchor.perfMs);
}

function formatAge(row: Row): string {
  const age = displayedAgeMs(row);
  if (age === null) return "Edad desconocida";
  const totalSec = Math.floor(age / 1000);
  if (totalSec <= 59) return `${totalSec} s`;
  const totalMin = Math.floor(age / 60000);
  if (totalMin <= 59) return `${totalMin} min`;
  return `${Math.floor(age / 3600000)} h`;
}

function opNumber(opId: string): number {
  const m = /^op-(\d+)$/.exec(opId);
  return m ? parseInt(m[1], 10) : -1;
}

export default function App() {
  const [view, setView] = useState<View>("checking");
  const [loginMessage, setLoginMessage] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [docInfo, setDocInfo] = useState<DocInfo | null>(null);
  const [connected, setConnected] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const checkingRef = useRef(false);

  // Carga inicial (§5.2.1)
  useEffect(() => {
    let cancelled = false;
    const csrf = localStorage.getItem("csrf");
    if (!csrf) {
      setView("login");
      return;
    }
    fetch("/api/session", { credentials: "same-origin" })
      .then((res) => {
        if (cancelled) return;
        if (res.status === 200) {
          setView("queue");
        } else {
          setView("login");
        }
      })
      .catch(() => {
        if (!cancelled) setView("login");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Recalculo de edades cada segundo (§5.2.3)
  useEffect(() => {
    if (view !== "queue") return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [view]);

  // SSE (§5.2.3 y §5.2.4)
  useEffect(() => {
    if (view !== "queue") return;
    let cancelled = false;

    const closeCurrent = () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };

    const handleClosed = () => {
      if (cancelled || checkingRef.current) return;
      checkingRef.current = true;
      fetch("/api/session", { credentials: "same-origin" })
        .then((res) => {
          checkingRef.current = false;
          if (cancelled) return;
          if (res.status === 401) {
            closeCurrent();
            setConnected(false);
            setLoginMessage("Sesión caducada: vuelve a entrar");
            setView("login");
          } else {
            start();
          }
        })
        .catch(() => {
          // Sin respuesta (backend caído): se vuelve a mirar, para no quedarse en «Reconectando…» sin reconectar.
          checkingRef.current = false;
          if (!cancelled) {
            setConnected(false);
            window.setTimeout(handleClosed, 3000);
          }
        });
    };

    const start = () => {
      if (cancelled) return;
      closeCurrent();
      const es = new EventSource("/api/events");
      esRef.current = es;
      es.addEventListener("snapshot", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as {
          doc_id: string;
          rev: number;
          hash: string;
          ops: OpData[];
        };
        setDocInfo({ doc_id: data.doc_id, rev: data.rev, hash: data.hash });
        setRows((prev) => {
          const byId = new Map(prev.map((r) => [r.op_id, r]));
          return (data.ops || []).map((op) => rowFromOp(op, "snapshot", byId.get(op.op_id)));
        });
      });
      es.addEventListener("op.state", (ev) => {
        const op = JSON.parse((ev as MessageEvent).data) as OpData;
        setRows((prev) => {
          const existing = prev.find((r) => r.op_id === op.op_id);
          const row = rowFromOp(op, "op.state", existing);
          if (existing) return prev.map((r) => (r.op_id === op.op_id ? row : r));
          return [...prev, row];
        });
      });
      es.addEventListener("scene.commit", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as { rev: number; hash: string };
        setDocInfo((prev) => (prev ? { ...prev, rev: data.rev, hash: data.hash } : prev));
      });
      es.onopen = () => {
        if (!cancelled) setConnected(true);
      };
      es.onerror = () => {
        if (cancelled) return;
        if (es.readyState === EventSource.CLOSED) {
          setConnected(false);
          handleClosed();
        } else {
          setConnected(false);
        }
      };
    };

    start();
    return () => {
      cancelled = true;
      closeCurrent();
    };
  }, [view]);

  const onLogin = (e: React.FormEvent) => {
    e.preventDefault();
    fetch("/api/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: password }),
    })
      .then(async (res) => {
        if (res.status === 200) {
          const data = (await res.json()) as { csrf: string };
          localStorage.setItem("csrf", data.csrf);
          setPassword("");
          setLoginMessage(null);
          setRows([]);
          setDocInfo(null);
          setApplyError(null);
          setView("queue");
        } else if (res.status === 401) {
          setLoginMessage("Clave no válida");
        } else {
          setLoginMessage("Clave no válida");
        }
      })
      .catch(() => {
        setLoginMessage("Clave no válida");
      });
  };

  const onApply = () => {
    if (!docInfo || applying) return;
    setApplying(true);
    setApplyError(null);
    fetch("/api/apply", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": localStorage.getItem("csrf") ?? "",
      },
      body: JSON.stringify({ doc_id: docInfo.doc_id, rev: docInfo.rev, hash: docInfo.hash }),
    })
      .then(async (res) => {
        const data = (await res.json().catch(() => null)) as
          | { ok?: boolean; code?: string; msg?: string }
          | null;
        if (res.status === 401 || (res.status === 403 && data?.code === "csrf_failed")) {
          setLoginMessage("Sesión caducada: vuelve a entrar");
          setView("login");
          return;
        }
        if (!res.ok) {
          const code = data?.code ?? String(res.status);
          const msg = data?.msg ?? "";
          setApplyError(msg ? `${code}: ${msg}` : code);
        }
      })
      .catch(() => {
        setApplyError("Error de red");
      })
      .finally(() => setApplying(false));
  };

  if (view === "checking") {
    return (
      <main className="page">
        <h1>Cola de órdenes</h1>
        <p>Cargando…</p>
      </main>
    );
  }

  if (view === "login") {
    return (
      <main className="page">
        <h1>Cola de órdenes</h1>
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
          <button type="submit">Entrar</button>
          {loginMessage ? <p role="alert">{loginMessage}</p> : null}
        </form>
      </main>
    );
  }

  const sorted = [...rows].sort((a, b) => opNumber(b.op_id) - opNumber(a.op_id));

  return (
    <main className="page">
      <h1>Cola de órdenes</h1>
      <p>{connected ? "Conectado" : "Reconectando…"}</p>
      <button type="button" onClick={onApply} disabled={!docInfo || applying}>
        {docInfo ? `Aplicar rev ${docInfo.rev}` : "Aplicar"}
      </button>
      {applyError ? <p role="alert">{applyError}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Orden</th>
            <th>Revisión</th>
            <th>Estado</th>
            <th>Edad</th>
            <th>Origen</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.op_id} data-op-id={row.op_id}>
              <td>{row.op_id}</td>
              <td>{row.hash ? `${row.rev} ${row.hash.slice(0, 8)}` : `${row.rev ?? ""}`}</td>
              <td>
                <span className={isKnownState(row.state) ? `chip ${row.state}` : "chip"}>
                  {stateLabel(row.state)}
                </span>
              </td>
              <td>{formatAge(row)}</td>
              <td>{row.origin ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
