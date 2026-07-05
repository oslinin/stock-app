import React, { useState } from "react";
import { getApiBase, getToken, setApiBase, setToken } from "../config";

function BackendOffline({ message, onSaved }) {
  const [base, setBase] = useState(getApiBase());
  const [token, setTokenValue] = useState(getToken());

  const save = () => {
    setApiBase(base);
    setToken(token);
    onSaved();
  };

  return (
    <div className="panel offline-panel">
      <h2>Backend not connected</h2>
      <p>
        The screener needs the VIX backend (FastAPI + IB Gateway on your VPS —
        see <code>deploy/README.md</code>). Enter its URL and API token once;
        they are stored only in this browser.
      </p>
      {message && <p className="error">{message}</p>}
      <div className="settings-grid">
        <label>
          API base URL
          <input
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder="https://vix.yourdomain.com/api/v1"
          />
        </label>
        <label>
          API token
          <input
            type="password"
            value={token}
            onChange={(e) => setTokenValue(e.target.value)}
            placeholder="Bearer token from deploy/.env"
          />
        </label>
        <button onClick={save}>Save &amp; connect</button>
      </div>
    </div>
  );
}

export default BackendOffline;
