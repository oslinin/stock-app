import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { approveSpec, getSpec, getSpecDoc } from "../api/specs";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";
import PayoffChart from "../components/PayoffChart.jsx";
import { SectionBadges, StatusBadge } from "./Strategies.jsx";

const EXIT_LABELS = {
  profit_target_pct_credit: "Profit target (% of credit)",
  stop_loss_x_credit: "Stop loss (× credit)",
  time_exit_dte: "Time exit (DTE)",
};

function Quote({ provenance, sourceRef }) {
  if (!provenance || !provenance.quote) return <span className="muted">—</span>;
  const { quote, timestamp_s: ts, page } = provenance;
  let locator = null;
  if (ts != null && sourceRef && sourceRef.includes("youtube")) {
    const sep = sourceRef.includes("?") ? "&" : "?";
    locator = (
      <a href={`${sourceRef}${sep}t=${ts}`} target="_blank" rel="noreferrer">
        {ts}s
      </a>
    );
  } else if (ts != null) {
    locator = <span>at {ts}s</span>;
  } else if (page != null) {
    locator = <span>p. {page}</span>;
  }
  return (
    <span>
      “{quote}” {locator}
    </span>
  );
}

function StrategyDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [connected, setConnected] = useState(hasBackend());
  const [record, setRecord] = useState(null);
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  const [refPrice, setRefPrice] = useState(100);

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const [spec, docData] = await Promise.all([
        getSpec(id),
        getSpecDoc(id, { reference_price: refPrice }),
      ]);
      setRecord(spec);
      setDoc(docData);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [id, refPrice]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Strategy</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const approve = async () => {
    setError(null);
    try {
      setRecord(await approveSpec(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  if (!record) {
    return (
      <div className="screener">
        <h1>Strategy</h1>
        {error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}
      </div>
    );
  }

  const spec = record.spec || {};
  const sourceRef = spec.meta?.source_ref || "";
  const payoff = doc?.payoff;

  return (
    <div className="screener">
      <div className="screener-header">
        <h1>{record.name}</h1>
        <div className="screener-header-right">
          <button onClick={() => navigate(`/strategies/${id}/edit`)}>Edit</button>
          {record.status !== "approved" && (
            <button onClick={approve}>Approve</button>
          )}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <p>
        <StatusBadge status={record.status} /> <SectionBadges sections={record.sections} />{" "}
        <span className="muted">
          {record.category} · {record.origin} · v{record.version}
          {sourceRef && (
            <>
              {" · "}
              <a href={sourceRef} target="_blank" rel="noreferrer">
                source
              </a>
            </>
          )}
        </span>
      </p>
      {doc?.needs_review && (
        <p className="warn">
          Needs review: unstated rules below are flagged, not invented.
        </p>
      )}
      {spec.meta?.description && <p>{spec.meta.description}</p>}

      <div className="panel">
        <h3>Structure — {spec.universe?.underlyings?.join(", ") || "?"}</h3>
        <table className="legs-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Direction</th>
              <th>Right</th>
              <th>Strike rule</th>
              <th>DTE</th>
            </tr>
          </thead>
          <tbody>
            {(spec.structure || []).map((leg, i) => {
              const { kind, ...params } = leg.strike_rule || {};
              return (
                <tr key={i}>
                  <td>{i}</td>
                  <td className={leg.direction === "short" ? "action-sell" : "action-buy"}>
                    {leg.direction}
                  </td>
                  <td>{leg.right === "C" ? "call" : "put"}</td>
                  <td>
                    {kind}{" "}
                    <span className="muted">
                      {Object.entries(params)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ")}
                    </span>
                  </td>
                  <td>{leg.dte_target ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {payoff && payoff.points?.length > 0 && (
        <div className="panel">
          <div className="panel-title-row">
            <h3>Payoff (illustrative)</h3>
            <label className="contracts-input">
              ref price{" "}
              <input
                type="number"
                value={refPrice}
                onChange={(e) => setRefPrice(Number(e.target.value) || 100)}
              />
            </label>
          </div>
          <div className="payoff-chart">
            <PayoffChart
              payoff={payoff.points}
              breakevens={payoff.breakevens}
              spot={payoff.assumptions?.reference_price}
              xLabel="Underlying at expiration"
            />
          </div>
          <p className="muted">{payoff.assumptions?.note}</p>
        </div>
      )}

      <div className="panel">
        <h3>Entry rules</h3>
        {(spec.entry || []).length === 0 ? (
          <p className="warn">⚠ No entry conditions stated in source.</p>
        ) : (
          <table className="legs-table">
            <thead>
              <tr>
                <th>Condition</th>
                <th>Params</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {spec.entry.map((cond, i) => (
                <tr key={i}>
                  <td>{cond.kind}</td>
                  <td>{JSON.stringify(cond.params)}</td>
                  <td>
                    <Quote provenance={cond.provenance} sourceRef={sourceRef} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h3>Exit rules</h3>
        <table className="legs-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Value</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(EXIT_LABELS).map(([field, label]) => {
              const value = spec.exit?.[field];
              const unspecified = value === "unspecified" || value == null;
              return (
                <tr key={field}>
                  <td>{label}</td>
                  <td className={unspecified ? "warn" : ""}>
                    {unspecified ? "⚠ not stated in source" : value}
                  </td>
                  <td>
                    <Quote
                      provenance={spec.exit?.provenance?.[field]}
                      sourceRef={sourceRef}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Adjustments</h3>
        {(spec.adjustments || []).length === 0 ? (
          <p className="muted">No adjustment rules stated in source.</p>
        ) : (
          <table className="legs-table">
            <thead>
              <tr>
                <th>Trigger</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {spec.adjustments.map((adj, i) => (
                <tr key={i}>
                  <td>
                    {adj.trigger?.kind} {JSON.stringify(adj.trigger?.params)}
                  </td>
                  <td>{adj.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h3>Sizing & gates</h3>
        <p>
          {spec.sizing?.bp_pct != null && `${spec.sizing.bp_pct}% of buying power · `}
          {spec.sizing?.fixed_contracts != null &&
            `${spec.sizing.fixed_contracts} contracts · `}
          {spec.sizing?.bp_pct == null && spec.sizing?.fixed_contracts == null && (
            <span className="warn">⚠ sizing not stated in source · </span>
          )}
          max {spec.sizing?.max_concurrent ?? 1} concurrent
        </p>
        {(spec.gates || []).map((gate, i) => (
          <p key={i} className="muted">
            gate: {gate.kind} {JSON.stringify(gate.params)}
          </p>
        ))}
        {(spec.unsupported_conditions || []).length > 0 && (
          <>
            <h3>Rules the schema cannot express</h3>
            {spec.unsupported_conditions.map((rule, i) => (
              <p key={i} className="warn">
                {rule}
              </p>
            ))}
          </>
        )}
      </div>

      {record.claimedPerformance && (
        <div className="panel">
          <h3>Claimed performance (source claims — unverified)</h3>
          {Object.entries(record.claimedPerformance)
            .filter(([k]) => k !== "quote")
            .map(([k, v]) => (
              <p key={k}>
                <strong>{k}</strong>: {String(v)} <span className="muted">(claim)</span>
              </p>
            ))}
          {record.claimedPerformance.quote && (
            <p className="muted">“{record.claimedPerformance.quote}”</p>
          )}
        </div>
      )}
    </div>
  );
}

export default StrategyDetail;
