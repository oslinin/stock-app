import React, { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import {
  createAlertRule,
  deleteAlertRule,
  listAlertEvents,
  listAlertRules,
  patchAlertRule,
} from "../api/screener";
import { hasBackend } from "../config";
import BackendOffline from "../components/BackendOffline.jsx";

function Alerts() {
  const [connected, setConnected] = useState(hasBackend());
  const [rules, setRules] = useState([]);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [email, setEmail] = useState("");
  const [onArmed, setOnArmed] = useState(true);
  const [onEnter, setOnEnter] = useState(true);

  const refresh = useCallback(async () => {
    if (!hasBackend()) return;
    setError(null);
    try {
      const [ruleList, eventList] = await Promise.all([
        listAlertRules(),
        listAlertEvents(),
      ]);
      setRules(ruleList);
      setEvents(eventList);
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
        <h1>Alerts</h1>
        <BackendOffline onSaved={() => setConnected(hasBackend())} />
      </div>
    );
  }

  const create = async () => {
    const on = [onArmed && "ARMED", onEnter && "ENTER"].filter(Boolean);
    if (on.length === 0) return;
    try {
      await createAlertRule({
        strategyId: "vix_hedge",
        channels: ["email"],
        on,
        email,
        active: true,
      });
      setEmail("");
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const toggle = async (rule) => {
    try {
      await patchAlertRule(rule.id, { active: !rule.active });
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const remove = async (rule) => {
    try {
      await deleteAlertRule(rule.id);
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="screener">
      <h1>Alerts</h1>
      {error && <p className="error">{error}</p>}

      <div className="panel">
        <h3>New rule</h3>
        <div className="alert-form">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email (blank = backend default)"
          />
          <label>
            <input
              type="checkbox"
              checked={onArmed}
              onChange={(e) => setOnArmed(e.target.checked)}
            />
            ARMED
          </label>
          <label>
            <input
              type="checkbox"
              checked={onEnter}
              onChange={(e) => setOnEnter(e.target.checked)}
            />
            ENTER
          </label>
          <button onClick={create}>Add rule</button>
        </div>
      </div>

      <div className="panel">
        <h3>Rules</h3>
        {rules.length === 0 && <p className="muted">No alert rules yet.</p>}
        {rules.length > 0 && (
          <table className="legs-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>On</th>
                <th>Email</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.strategyId}</td>
                  <td>{rule.on.join(", ")}</td>
                  <td>{rule.email || "(default)"}</td>
                  <td>
                    <button className="ghost" onClick={() => toggle(rule)}>
                      {rule.active ? "on" : "off"}
                    </button>
                  </td>
                  <td>
                    <button className="ghost" onClick={() => remove(rule)}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h3>Recent events</h3>
        {events.length === 0 && <p className="muted">Nothing fired yet.</p>}
        {events.map((ev) => (
          <div key={ev.id} className="event-row">
            <strong>{ev.verdict}</strong> · {ev.tradingDate}
            {ev.expiry && ` · exp ${ev.expiry}`}
            <pre className="manual-spec">{ev.summary}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Alerts;
