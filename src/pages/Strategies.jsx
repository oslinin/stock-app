import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { listSpecs } from "../api/specs";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

const FILTERS = {
  status: ["", "draft", "needs_review", "approved", "archived"],
  origin: ["", "manual", "youtube", "corpus"],
  category: ["", "options", "stock", "crypto"],
};

export function SectionBadges({ sections }) {
  if (!sections) return null;
  return (
    <span className="section-badges">
      {Object.entries(sections).map(([name, status]) => (
        <span key={name} className={`badge badge-${status}`} title={`${name}: ${status}`}>
          {name}
        </span>
      ))}
    </span>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status.replace("_", " ")}</span>;
}

function Strategies() {
  const [connected, setConnected] = useState(hasBackend());
  const [specs, setSpecs] = useState([]);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ status: "", origin: "", category: "" });
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const params = Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v)
      );
      setSpecs(await listSpecs(params));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [filters]);

  useEffect(() => {
    if (!connected) return undefined;
    const kickoff = setTimeout(refresh, 0);
    return () => clearTimeout(kickoff);
  }, [connected, refresh]);

  if (!connected) {
    return (
      <div className="screener">
        <h1>Strategies</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  return (
    <div className="screener">
      <div className="screener-header">
        <h1>Strategies</h1>
        <div className="screener-header-right">
          <button onClick={() => navigate("/strategies/new")}>New strategy</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <div className="filter-row">
          {Object.entries(FILTERS).map(([name, values]) => (
            <label key={name}>
              {name}
              <select
                value={filters[name]}
                onChange={(e) => setFilters({ ...filters, [name]: e.target.value })}
              >
                {values.map((v) => (
                  <option key={v} value={v}>
                    {v || "all"}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <table className="legs-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Origin</th>
              <th>Status</th>
              <th>Sections</th>
            </tr>
          </thead>
          <tbody>
            {specs.map((s) => (
              <tr key={s.id}>
                <td>
                  <Link to={`/strategies/${s.id}`}>{s.name}</Link>
                </td>
                <td>{s.category}</td>
                <td>{s.origin}</td>
                <td>
                  <StatusBadge status={s.status} />
                </td>
                <td>
                  <SectionBadges sections={s.sections} />
                </td>
              </tr>
            ))}
            {specs.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No strategies match. Create one, or clear the filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Strategies;
