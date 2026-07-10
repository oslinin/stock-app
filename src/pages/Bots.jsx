import React, { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  createBot,
  getBotRuns,
  killAllBots,
  killBot,
  listBots,
  pauseBot,
  startBot,
} from "../api/bots";
import { listSpecs } from "../api/specs";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

function Bots() {
  const [connected, setConnected] = useState(hasBackend());
  const [bots, setBots] = useState([]);
  const [approvedSpecs, setApprovedSpecs] = useState([]);
  const [specId, setSpecId] = useState("");
  const [bpPct, setBpPct] = useState("0.05");
  const [fixedContracts, setFixedContracts] = useState("1");
  const [error, setError] = useState(null);
  const [blockers, setBlockers] = useState(null);
  const [runsByBot, setRunsByBot] = useState({});

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const [botList, specList] = await Promise.all([listBots(), listSpecs({ status: "approved" })]);
      setBots(botList);
      setApprovedSpecs(specList);
      setSpecId((prev) => prev || specList[0]?.id || "");
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Bots</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const create = async (e) => {
    e.preventDefault();
    if (!specId) return;
    setError(null);
    setBlockers(null);
    try {
      await createBot({
        specId: Number(specId),
        mode: "paper",
        bpPct: Number(bpPct) || 0.05,
        fixedContracts: fixedContracts ? Number(fixedContracts) : null,
      });
      refresh();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.blockers) {
        setBlockers(detail.blockers);
      } else {
        setError(errorMessage(err));
      }
    }
  };

  const act = async (fn, id) => {
    try {
      await fn(id);
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const toggleRuns = async (id) => {
    if (runsByBot[id]) {
      setRunsByBot((prev) => ({ ...prev, [id]: undefined }));
      return;
    }
    try {
      const runs = await getBotRuns(id);
      setRunsByBot((prev) => ({ ...prev, [id]: runs }));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="screener">
      <h1>Bots</h1>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Paper bots only auto-transmit with PAPER_AUTO_TRANSMIT=true on the
        backend; otherwise every order stages for manual review in TWS. A bot
        can only be created from an <strong>approved</strong> spec with fully
        specified exits, no adjustment rules, and only runtime-supported
        conditions/strike rules — see backend/README.md.
      </p>

      <div className="panel">
        <h3>New paper bot</h3>
        <form className="filter-row" onSubmit={create}>
          <label>
            spec
            <select value={specId} onChange={(e) => setSpecId(e.target.value)}>
              {approvedSpecs.length === 0 && <option value="">no approved specs</option>}
              {approvedSpecs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            BP%
            <input
              value={bpPct}
              onChange={(e) => setBpPct(e.target.value)}
              size={5}
              placeholder="0.05"
            />
          </label>
          <label>
            contracts
            <input
              value={fixedContracts}
              onChange={(e) => setFixedContracts(e.target.value)}
              size={4}
              placeholder="1"
            />
          </label>
          <button type="submit" disabled={!specId}>
            Create
          </button>
        </form>
        {blockers && (
          <div className="offline-panel">
            <p>Spec isn't runtime-executable yet:</p>
            <ul className="excluded-list">
              {blockers.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-title-row">
          <h3>Bots</h3>
          <button type="button" className="ghost" onClick={() => act(killAllBots)}>
            kill all
          </button>
        </div>
        {bots.length === 0 && <p className="muted">No bots yet.</p>}
        {bots.length > 0 && (
          <table className="legs-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Spec</th>
                <th>Mode</th>
                <th>Status</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bots.map((b) => (
                <React.Fragment key={b.id}>
                  <tr>
                    <td>{b.id}</td>
                    <td>{b.specId}</td>
                    <td>{b.mode}</td>
                    <td>{b.status}</td>
                    <td>{b.positionState}</td>
                    <td>
                      {b.status === "draft" && (
                        <button className="ghost" onClick={() => act(startBot, b.id)}>
                          start
                        </button>
                      )}
                      {b.status === "running" && (
                        <button className="ghost" onClick={() => act(pauseBot, b.id)}>
                          pause
                        </button>
                      )}
                      {b.status === "paused" && (
                        <button className="ghost" onClick={() => act(startBot, b.id)}>
                          resume
                        </button>
                      )}
                      {b.status !== "killed" && (
                        <button className="ghost" onClick={() => act(killBot, b.id)}>
                          kill
                        </button>
                      )}
                      <button className="ghost" onClick={() => toggleRuns(b.id)}>
                        runs
                      </button>
                    </td>
                  </tr>
                  {runsByBot[b.id] && (
                    <tr>
                      <td colSpan={6}>
                        {runsByBot[b.id].length === 0 && <p className="muted">No ticks yet.</p>}
                        {runsByBot[b.id].map((r, i) => (
                          <div key={i} className="event-row">
                            <strong>{r.positionState}</strong> · {r.action}
                            {r.detail && ` · ${r.detail}`}
                            <span className="muted"> · {new Date(r.tickAt).toLocaleTimeString()}</span>
                          </div>
                        ))}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Bots;
