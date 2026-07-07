import React, { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import { cssVar } from "../chartjs.js";

// Vertical reference markers: solid line at the current price, dashed lines
// at each breakeven, with small direct labels along the top.
const markersPlugin = {
  id: "payoffMarkers",
  afterDatasetsDraw(chart, _args, opts) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales.x) return;
    const drawLine = (x, color, dash, label, labelY) => {
      if (x < chartArea.left || x > chartArea.right) return;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash(dash);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.font = `11px ${cssVar("--sans", "sans-serif")}`;
      ctx.textAlign = "center";
      ctx.fillText(label, x, labelY);
      ctx.restore();
    };
    // two label rows so "now" and breakeven labels never collide
    (opts.breakevens || []).forEach((be) =>
      drawLine(
        scales.x.getPixelForValue(be),
        opts.mutedColor,
        [4, 4],
        `BE ${be}`,
        chartArea.top - 4
      )
    );
    if (opts.spot != null) {
      drawLine(
        scales.x.getPixelForValue(opts.spot),
        opts.accentColor,
        [],
        `now ${opts.spot}`,
        chartArea.top - 17
      );
    }
  },
};

function useThemeVersion() {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const bump = () => setVersion((v) => v + 1);
    mq.addEventListener("change", bump);
    return () => mq.removeEventListener("change", bump);
  }, []);
  return version;
}

function PayoffChart({
  payoff,
  breakevens = [],
  spot = null,
  title,
  xLabel = "VIX at expiration",
}) {
  const themeVersion = useThemeVersion();
  if (!payoff || payoff.length === 0) return null;

  const green = cssVar("--green", "#15803d");
  const red = cssVar("--red", "#b91c1c");
  const greenBg = cssVar("--green-bg", "rgba(21,128,61,0.12)");
  const redBg = cssVar("--red-bg", "rgba(185,28,28,0.12)");
  const text = cssVar("--text", "#6b6375");
  const border = cssVar("--border", "#e5e4e7");
  const accent = cssVar("--accent", "#aa3bff");

  const segSign = (ctx) => (ctx.p0.parsed.y + ctx.p1.parsed.y) / 2 >= 0;
  const data = {
    datasets: [
      {
        label: "P&L at expiration",
        data: payoff,
        borderWidth: 2,
        pointRadius: 0,
        pointHitRadius: 12,
        pointHoverRadius: 4,
        fill: "origin",
        segment: {
          borderColor: (ctx) => (segSign(ctx) ? green : red),
          backgroundColor: (ctx) => (segSign(ctx) ? greenBg : redBg),
        },
        borderColor: green,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "nearest", axis: "x", intersect: false },
    layout: { padding: { top: 32 } },
    plugins: {
      legend: { display: false },
      title: {
        display: Boolean(title),
        text: title,
        color: text,
        font: { size: 13, weight: "normal" },
      },
      tooltip: {
        callbacks: {
          title: (items) => `${xLabel}: ${items[0].parsed.x}`,
          label: (item) =>
            `P&L: ${item.parsed.y >= 0 ? "+" : "−"}$${Math.abs(item.parsed.y).toLocaleString()}`,
        },
      },
      payoffMarkers: {
        breakevens,
        spot,
        mutedColor: text,
        accentColor: accent,
      },
    },
    scales: {
      x: {
        type: "linear",
        title: { display: true, text: xLabel, color: text },
        grid: { color: "transparent" },
        ticks: { color: text },
      },
      y: {
        title: { display: true, text: "P&L ($)", color: text },
        grid: {
          color: (ctx) => (ctx.tick.value === 0 ? text : border),
          lineWidth: (ctx) => (ctx.tick.value === 0 ? 1.5 : 1),
        },
        ticks: {
          color: text,
          callback: (v) => `$${Number(v).toLocaleString()}`,
        },
      },
    },
  };

  return (
    <div className="payoff-chart" key={themeVersion}>
      <Line data={data} options={options} plugins={[markersPlugin]} />
    </div>
  );
}

export default PayoffChart;
