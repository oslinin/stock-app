import React from "react";

const LABELS = {
  ENTER: "ENTER",
  ARMED: "ARMED",
  WAIT: "WAIT",
  NO_DATA: "NO DATA",
};

function VerdictBadge({ verdict }) {
  const v = LABELS[verdict] ? verdict : "NO_DATA";
  return <span className={`badge badge-${v.toLowerCase()}`}>{LABELS[v]}</span>;
}

export default VerdictBadge;
