import React from "react";

// Every /marketdata response carries {provenance: {source, asof, latency}}.
// This badge is the UI half of the "provenance everywhere" rule: data is
// never shown without saying where it came from and how fresh it is.
function ProvenanceBadge({ provenance }) {
  if (!provenance) return null;
  const { source, asof, latency } = provenance;
  const stamp = asof ? new Date(asof).toLocaleTimeString() : "";
  return (
    <span
      className={`provenance provenance-${latency}`}
      title={`source: ${source}\nas of: ${asof}\nlatency: ${latency}`}
    >
      {source} · {latency}
      {stamp ? ` · ${stamp}` : ""}
    </span>
  );
}

export default ProvenanceBadge;
