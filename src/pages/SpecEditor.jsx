import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { createSpec, getSpec, updateSpec } from "../api/specs";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

const DEFAULT_STRUCTURE = [
  {
    right: "P",
    direction: "short",
    ratio: 1,
    strike_rule: { kind: "delta_target", delta: 0.3 },
    dte_target: 45,
  },
  {
    right: "P",
    direction: "long",
    ratio: 1,
    strike_rule: { kind: "fixed_width_from_leg", from_leg: 0, width: 5.0 },
    dte_target: 45,
  },
];

// exits are entered as a number or left blank = "unspecified" (the
// backend sentinel: rules the source never stated are never invented)
function exitValue(raw) {
  return raw === "" ? "unspecified" : Number(raw);
}

function exitField(spec, field) {
  const v = spec?.exit?.[field];
  return v == null || v === "unspecified" ? "" : String(v);
}

function SpecEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [connected, setConnected] = useState(hasBackend());
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("options");
  const [sourceRef, setSourceRef] = useState("");
  const [underlyings, setUnderlyings] = useState("SPY");
  const [profitTarget, setProfitTarget] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [timeExit, setTimeExit] = useState("");
  const [bpPct, setBpPct] = useState("");
  const [maxConcurrent, setMaxConcurrent] = useState("1");
  const [structureJson, setStructureJson] = useState(
    JSON.stringify(DEFAULT_STRUCTURE, null, 2)
  );
  const [entryJson, setEntryJson] = useState("[]");
  const [advancedJson, setAdvancedJson] = useState(
    JSON.stringify({ adjustments: [], gates: [], unsupported_conditions: [] }, null, 2)
  );

  const load = useCallback(async () => {
    if (!id || !hasBackend()) return;
    try {
      const record = await getSpec(id);
      const spec = record.spec || {};
      setName(spec.meta?.name || record.name);
      setDescription(spec.meta?.description || "");
      setCategory(spec.meta?.category || record.category);
      setSourceRef(spec.meta?.source_ref || "");
      setUnderlyings((spec.universe?.underlyings || []).join(","));
      setProfitTarget(exitField(spec, "profit_target_pct_credit"));
      setStopLoss(exitField(spec, "stop_loss_x_credit"));
      setTimeExit(exitField(spec, "time_exit_dte"));
      setBpPct(spec.sizing?.bp_pct != null ? String(spec.sizing.bp_pct) : "");
      setMaxConcurrent(String(spec.sizing?.max_concurrent ?? 1));
      setStructureJson(JSON.stringify(spec.structure || [], null, 2));
      setEntryJson(JSON.stringify(spec.entry || [], null, 2));
      setAdvancedJson(
        JSON.stringify(
          {
            adjustments: spec.adjustments || [],
            gates: spec.gates || [],
            unsupported_conditions: spec.unsupported_conditions || [],
          },
          null,
          2
        )
      );
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [id]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(load, 0);
    return () => clearTimeout(kickoff);
  }, [connected, load]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Strategy editor</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const save = async () => {
    setError(null);
    let structure, entry, advanced;
    try {
      structure = JSON.parse(structureJson);
      entry = JSON.parse(entryJson);
      advanced = JSON.parse(advancedJson);
    } catch (err) {
      setError(`invalid JSON: ${err.message}`);
      return;
    }
    const spec = {
      meta: {
        name,
        description,
        category,
        origin: "manual",
        source_ref: sourceRef,
      },
      universe: {
        underlyings: underlyings
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
        sec_type: category === "crypto" ? "perp" : "option",
      },
      structure,
      entry,
      exit: {
        profit_target_pct_credit: exitValue(profitTarget),
        stop_loss_x_credit: exitValue(stopLoss),
        time_exit_dte: exitValue(timeExit),
      },
      adjustments: advanced.adjustments || [],
      gates: advanced.gates || [],
      unsupported_conditions: advanced.unsupported_conditions || [],
      sizing: {
        bp_pct: bpPct === "" ? null : Number(bpPct),
        max_concurrent: Number(maxConcurrent) || 1,
      },
    };
    try {
      const record = id
        ? await updateSpec(id, { spec })
        : await createSpec({ spec });
      navigate(`/strategies/${record.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="screener">
      <h1>{id ? "Edit strategy" : "New strategy"}</h1>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <div className="settings-grid">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="options">options</option>
              <option value="stock">stock</option>
              <option value="crypto">crypto</option>
            </select>
          </label>
          <label>
            Underlyings (comma-separated)
            <input value={underlyings} onChange={(e) => setUnderlyings(e.target.value)} />
          </label>
          <label>
            Source URL (video/PDF)
            <input value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} />
          </label>
          <label>
            Description
            <input value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </div>
      </div>
      <div className="panel">
        <h3>Exits — leave blank if the source doesn’t state a rule</h3>
        <div className="settings-grid">
          <label>
            Profit target (% of credit)
            <input
              type="number"
              value={profitTarget}
              onChange={(e) => setProfitTarget(e.target.value)}
              placeholder="unspecified"
            />
          </label>
          <label>
            Stop loss (× credit)
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              placeholder="unspecified"
            />
          </label>
          <label>
            Time exit (DTE)
            <input
              type="number"
              value={timeExit}
              onChange={(e) => setTimeExit(e.target.value)}
              placeholder="unspecified"
            />
          </label>
        </div>
      </div>
      <div className="panel">
        <h3>Sizing</h3>
        <div className="settings-grid">
          <label>
            % of buying power
            <input
              type="number"
              value={bpPct}
              onChange={(e) => setBpPct(e.target.value)}
              placeholder="unspecified"
            />
          </label>
          <label>
            Max concurrent positions
            <input
              type="number"
              value={maxConcurrent}
              onChange={(e) => setMaxConcurrent(e.target.value)}
            />
          </label>
        </div>
      </div>
      <div className="panel">
        <h3>Structure (JSON)</h3>
        <textarea
          className="json-editor"
          rows={12}
          value={structureJson}
          onChange={(e) => setStructureJson(e.target.value)}
          spellCheck={false}
        />
        <h3>Entry conditions (JSON)</h3>
        <textarea
          className="json-editor"
          rows={6}
          value={entryJson}
          onChange={(e) => setEntryJson(e.target.value)}
          spellCheck={false}
        />
        <h3>Adjustments / gates / unsupported (JSON)</h3>
        <textarea
          className="json-editor"
          rows={6}
          value={advancedJson}
          onChange={(e) => setAdvancedJson(e.target.value)}
          spellCheck={false}
        />
      </div>
      <div className="order-buttons">
        <button onClick={save}>{id ? "Save new version" : "Create strategy"}</button>
      </div>
    </div>
  );
}

export default SpecEditor;
