import React from "react";

const usd = (v) =>
  v == null
    ? "—"
    : `${v < 0 ? "−" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString(undefined, {
        maximumFractionDigits: 0,
      })}`;

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function SpreadSummary({ spread }) {
  if (!spread) return null;
  const net = spread.net || {};
  return (
    <div className="stats-row">
      <Stat
        label={net.isDebit ? "Net debit" : "Net credit"}
        value={usd(Math.abs(net.totalUsd ?? 0) * (net.isDebit ? -1 : 1))}
        tone={net.isDebit ? "red" : "green"}
      />
      <Stat label="Max loss" value={usd(spread.maxLossUsd)} tone="red" />
      <Stat label="Max gain" value={usd(spread.maxGainUsd)} tone="green" />
      <Stat
        label="Breakevens"
        value={(spread.breakevens || []).map((b) => b.toFixed(2)).join(" / ") || "—"}
      />
      <Stat label="Expiry" value={`${spread.expiry} (${spread.dte}d)`} />
      <Stat
        label="Centered on"
        value={`${spread.center} (${spread.centerSource})`}
      />
    </div>
  );
}

export default SpreadSummary;
