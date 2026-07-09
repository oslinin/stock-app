import React, { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  getRisk,
  getSummary,
  listPositions,
  uploadFidelityCsv,
} from "../api/portfolio";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";
import ProvenanceBadge from "../components/ProvenanceBadge.jsx";

const GROUP_OPTIONS = [
  { value: "", label: "All" },
  { value: "account", label: "By account" },
  { value: "underlying", label: "By underlying" },
];

const fmt = (v, digits = 2) =>
  v === null || v === undefined ? "–" : Number(v).toFixed(digits);
const money = (v) =>
  v === null || v === undefined ? "–" : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function provenanceFor(position) {
  return {
    source: position.source,
    asof: position.asof || new Date().toISOString(),
    latency: position.source === "ibkr_live" ? "live" : "eod",
  };
}

function PositionsTable({ positions }) {
  if (positions.length === 0) return <p className="muted">No positions.</p>;
  return (
    <table className="legs-table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Type</th>
          <th>Qty</th>
          <th>Last</th>
          <th>Avg cost</th>
          <th>β-weighted Δ</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p, i) => (
          <tr key={`${p.symbol}-${p.strike ?? ""}-${p.right ?? ""}-${p.expiry ?? ""}-${i}`}>
            <td>
              {p.symbol}
              {p.secType === "OPT" && ` ${p.expiry} ${p.strike}${p.right}`}
            </td>
            <td>{p.secType}</td>
            <td>{p.quantity}</td>
            <td>{fmt(p.lastPrice)}</td>
            <td>{fmt(p.avgCost)}</td>
            <td>{fmt(p.betaWeightedDelta)}</td>
            <td>
              <ProvenanceBadge provenance={provenanceFor(p)} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Portfolio() {
  const [connected, setConnected] = useState(hasBackend());
  const [groupBy, setGroupBy] = useState("");
  const [positions, setPositions] = useState([]);
  const [groups, setGroups] = useState(null);
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [risk, setRisk] = useState(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [accountLabel, setAccountLabel] = useState("default");
  const [uploading, setUploading] = useState(false);

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const [posResult, summaryResult] = await Promise.all([
        listPositions(groupBy || undefined),
        getSummary(),
      ]);
      setPositions(posResult.positions || []);
      setGroups(posResult.groups || null);
      setSummary(summaryResult.summary);
      setAccounts(summaryResult.accounts || []);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [groupBy]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Portfolio</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const upload = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    setError(null);
    try {
      await uploadFidelityCsv(uploadFile, accountLabel || "default");
      setUploadFile(null);
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const runRisk = async () => {
    setRiskLoading(true);
    setError(null);
    try {
      setRisk(await getRisk());
    } catch (err) {
      setError(errorMessage(err));
      setRisk(null);
    } finally {
      setRiskLoading(false);
    }
  };

  return (
    <div className="screener">
      <h1>Portfolio</h1>
      {error && <p className="error">{error}</p>}

      <div className="panel">
        <h3>Accounts</h3>
        {accounts.length === 0 && (
          <p className="muted">
            No accounts yet — upload a Fidelity CSV below, or connect IB Gateway
            for live positions.
          </p>
        )}
        {accounts.length > 0 && (
          <table className="legs-table">
            <thead>
              <tr>
                <th>Broker</th>
                <th>Label</th>
                <th>Net liq</th>
                <th>Buying power</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={`${a.broker}-${a.label}`}>
                  <td>{a.broker}</td>
                  <td>{a.label}</td>
                  <td>{typeof a.netLiquidation === "number" ? money(a.netLiquidation) : a.netLiquidation ?? "–"}</td>
                  <td>{typeof a.buyingPower === "number" ? money(a.buyingPower) : a.buyingPower ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form className="filter-row" onSubmit={upload}>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
          />
          <input
            value={accountLabel}
            onChange={(e) => setAccountLabel(e.target.value)}
            placeholder="account label"
            size={12}
          />
          <button type="submit" disabled={!uploadFile || uploading}>
            {uploading ? "uploading…" : "Upload Fidelity CSV"}
          </button>
        </form>
      </div>

      {summary && (
        <div className="panel">
          <h3>Aggregate greeks</h3>
          <div className="risk-tiles">
            <div className="risk-tile">
              <div className="risk-tile-label">Positions</div>
              <div className="risk-tile-value">{summary.count}</div>
            </div>
            <div className="risk-tile">
              <div className="risk-tile-label">Σ Delta</div>
              <div className="risk-tile-value">{fmt(summary.totalDelta)}</div>
            </div>
            <div className="risk-tile">
              <div className="risk-tile-label">Σ β-weighted Δ</div>
              <div className="risk-tile-value">{fmt(summary.totalBetaWeightedDelta)}</div>
            </div>
            <div className="risk-tile">
              <div className="risk-tile-label">Σ Theta</div>
              <div className="risk-tile-value">{fmt(summary.totalTheta)}</div>
            </div>
            <div className="risk-tile">
              <div className="risk-tile-label">Σ Vega</div>
              <div className="risk-tile-value">{fmt(summary.totalVega)}</div>
            </div>
          </div>
          <p className="muted">
            Greeks read as unavailable until IBKR model-greek enrichment lands
            (see backend README) — quantity and price are live.
          </p>
        </div>
      )}

      <div className="panel">
        <h3>Risk (forward-looking 1-day CVaR)</h3>
        <button type="button" onClick={runRisk} disabled={riskLoading}>
          {riskLoading ? "simulating…" : "Run risk simulation"}
        </button>
        {risk && (
          <>
            <div className="risk-tiles">
              <div className="risk-tile">
                <div className="risk-tile-label">CVaR 95%</div>
                <div className="risk-tile-value">{typeof risk.cvar95 === "number" ? money(risk.cvar95) : "–"}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">CVaR 99%</div>
                <div className="risk-tile-value">{typeof risk.cvar99 === "number" ? money(risk.cvar99) : "–"}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Priced</div>
                <div className="risk-tile-value">{risk.priced}</div>
              </div>
              <div className="risk-tile">
                <div className="risk-tile-label">Scenarios</div>
                <div className="risk-tile-value">{risk.scenarios}</div>
              </div>
            </div>
            {risk.excluded?.length > 0 && (
              <>
                <p className="muted">
                  {risk.excluded.length} position(s) excluded (non-priceable):
                </p>
                <ul className="excluded-list">
                  {risk.excluded.map((p, i) => (
                    <li key={i}>
                      {p.symbol}
                      {p.secType === "OPT" && ` ${p.expiry} ${p.strike}${p.right}`} — {p.reason}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>

      <div className="panel">
        <div className="panel-title-row">
          <h3>Positions</h3>
          <div className="filter-row">
            {GROUP_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={groupBy === opt.value ? "" : "ghost"}
                onClick={() => setGroupBy(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        {groups ? (
          Object.entries(groups).map(([key, rows]) => (
            <div key={key} className="position-group">
              <h4>{key}</h4>
              <PositionsTable positions={rows} />
            </div>
          ))
        ) : (
          <PositionsTable positions={positions} />
        )}
      </div>
    </div>
  );
}

export default Portfolio;
