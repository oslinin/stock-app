import React, { useState } from "react";
import { previewOrder, ticketOrder } from "../api/screener";
import { errorMessage } from "../api/client";

function OrderTicketPanel({ strategyId, expiryRaw, contracts }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await fn({ strategyId, expiry: expiryRaw, contracts }));
    } catch (err) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel order-panel">
      <h3>Order ticket</h3>
      <p className="order-safety">
        Nothing auto-executes. Preview runs an IBKR whatIf (margin/commission);
        staging places the combo with <code>transmit=false</code> for you to
        review and transmit inside IBKR yourself.
      </p>
      <div className="order-buttons">
        <button disabled={busy} onClick={() => run(previewOrder)}>
          Preview in IBKR
        </button>
        <button disabled={busy} onClick={() => run(ticketOrder)}>
          Stage order
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="order-result">
          <p>
            <strong>{result.status}</strong> — {result.message}
          </p>
          {result.whatIf?.available && (
            <p>
              Init margin: {result.whatIf.initMargin ?? "—"} · Maint margin:{" "}
              {result.whatIf.maintMargin ?? "—"} · Commission:{" "}
              {result.whatIf.commission ?? "—"}
              {result.whatIf.warningText && ` · ${result.whatIf.warningText}`}
            </p>
          )}
          {result.manualSpec && (
            <pre className="manual-spec">
              {JSON.stringify(result.manualSpec, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default OrderTicketPanel;
