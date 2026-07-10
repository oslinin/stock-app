import React, { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  compilePreview,
  createBacktest,
  getBacktest,
  getSetupSheet,
  importOoTradeLog,
  listRobustness,
  runRobustness,
} from "../api/backtests";
import { listSpecs } from "../api/specs";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

const fmt = (v, digits = 2) =>
  v === null || v === undefined ? "–" : Number(v).toFixed(digits);
const pct = (v, digits = 1) =>
  v === null || v === undefined ? "–" : `${(Number(v) * 100).toFixed(digits)}%`;

function Backtests() {
  const [connected, setConnected] = useState(hasBackend());
  const [specs, setSpecs] = useState([]);
  const [specId, setSpecId] = useState("");
  const [preview, setPreview] = useState(null);
  const [run, setRun] = useState(null);
  const [robustness, setRobustness] = useState([]);
  const [error, setError] = useState(null);
  const [ooFile, setOoFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const refreshSpecs = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      setSpecs(await listSpecs());
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refreshSpecs, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refreshSpecs]);

  useEffect(() => {
    if (!specId) {
      setPreview(null);
      return;
    }
    compilePreview(Number(specId))
      .then(setPreview)
      .catch((err) => setError(errorMessage(err)));
  }, [specId]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Backtests</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const refreshRun = async (id) => {
    try {
      const r = await getBacktest(id);
      setRun(r);
      if (r.status === "done") {
        setRobustness(await listRobustness(id));
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const enqueue = async () => {
    if (!specId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createBacktest({ specId: Number(specId), engine: "optopsy" });
      await refreshRun(created.id);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail?.unsupported) {
        setError(`Not runnable through the local engine: ${detail.unsupported.join("; ")}`);
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  };

  const showSetupSheet = async () => {
    if (!run) return;
    try {
      const sheet = await getSetupSheet(run.id);
      window.alert(
        `Option Omega setup sheet:\n\n${JSON.stringify(sheet.setupSheet, null, 2)}\n\n` +
          `Ignored by the local engine:\n${sheet.unsupported.join("\n")}`
      );
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const uploadOo = async (e) => {
    e.preventDefault();
    if (!ooFile || !specId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await importOoTradeLog(Number(specId), ooFile);
      setOoFile(null);
      await refreshRun(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const runBootstrap = async () => {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      await runRobustness(run.id, { kind: "bootstrap", params: { n: 2000 } });
      setRobustness(await listRobustness(run.id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screener">
      <h1>Backtests</h1>
      {error && <p className="error">{error}</p>}

      <div className="panel">
        <h3>Run a spec</h3>
        <div className="filter-row">
          <label>
            spec
            <select value={specId} onChange={(e) => setSpecId(e.target.value)}>
              <option value="">choose a spec</option>
              {specs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.status})
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={enqueue} disabled={!preview?.supported || busy}>
            Run in local engine
          </button>
        </div>
        {preview && !preview.supported && (
          <p className="muted">
            Not mapped to a local (optopsy) strategy: {preview.unsupported.join("; ")}. Use the
            Option Omega manual bridge below instead.
          </p>
        )}
        {preview?.supported && (
          <p className="muted">
            Maps to optopsy <code>{preview.optopsyStrategy}</code>.
            {preview.unsupported.length > 0 && ` Ignored: ${preview.unsupported.join("; ")}`}
          </p>
        )}
      </div>

      <div className="panel">
        <h3>Option Omega manual bridge</h3>
        <p className="muted">
          Generate a setup sheet from the fields above, run it by hand in Option Omega, then
          upload the exported trade-log CSV here.
        </p>
        <div className="filter-row">
          <button type="button" className="ghost" onClick={showSetupSheet} disabled={!run}>
            View setup sheet for last run
          </button>
        </div>
        <form className="filter-row" onSubmit={uploadOo}>
          <input type="file" accept=".csv" onChange={(e) => setOoFile(e.target.files?.[0] || null)} />
          <button type="submit" disabled={!ooFile || !specId || busy}>
            Import OO trade log
          </button>
        </form>
      </div>

      {run && (
        <div className="panel">
          <div className="panel-title-row">
            <h3>
              Run #{run.id} — {run.engine}
            </h3>
            <span className="muted">{run.status}</span>
          </div>
          {run.status === "failed" && <p className="error">{run.error}</p>}
          {run.metrics && (
            <div className="risk-tiles">
              <div className="risk-tile">
                <div className="risk-tile-label">CAGR</div>
                <div className="risk-tile-value">{pct(run.metrics.cagr)}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Win rate</div>
                <div className="risk-tile-value">{pct(run.metrics.winRate)}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Expectancy</div>
                <div className="risk-tile-value">{fmt(run.metrics.expectancy)}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Max DD</div>
                <div className="risk-tile-value">{pct(run.metrics.maxDd)}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Sharpe</div>
                <div className="risk-tile-value">{fmt(run.metrics.sharpe)}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Trades</div>
                <div className="risk-tile-value">{run.metrics.tradeCount}</div>
              </div>
            </div>
          )}
          {run.status === "done" && (
            <button type="button" className="ghost" onClick={runBootstrap} disabled={busy}>
              Run bootstrap robustness
            </button>
          )}
          {robustness.map((r) => (
            <div key={r.id} className="event-row">
              <strong>{r.kind}</strong>
              <pre className="manual-spec">{JSON.stringify(r.results, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Backtests;
