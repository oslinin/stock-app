import React from "react";

const fmt = (v) => (v == null ? "—" : Number(v).toFixed(2));

function SpreadTable({ legs }) {
  if (!legs || legs.length === 0) return null;
  return (
    <table className="legs-table">
      <thead>
        <tr>
          <th>Action</th>
          <th>Leg</th>
          <th>Qty</th>
          <th>Bid</th>
          <th>Ask</th>
          <th>Mid</th>
        </tr>
      </thead>
      <tbody>
        {legs.map((leg) => (
          <tr key={leg.id}>
            <td>
              <span className={leg.action === "BUY" ? "action-buy" : "action-sell"}>
                {leg.action}
              </span>
            </td>
            <td>
              {leg.strike}
              {leg.right}
            </td>
            <td>{leg.qty}</td>
            <td>{fmt(leg.bid)}</td>
            <td>{fmt(leg.ask)}</td>
            <td>{fmt(leg.mid)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default SpreadTable;
