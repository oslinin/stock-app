import React, { useState } from "react";
import axios from "axios";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import "./App.css";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

function App() {
  const [symbol, setSymbol] = useState("");
  const [stockData, setStockData] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [error, setError] = useState(null);
  const API_KEY = import.meta.env.VITE_API_KEY;

  const fetchStock = async () => {
    if (!symbol) return;
    setError(null);
    try {
      const [quoteRes, timeSeriesRes] = await Promise.all([
        axios.get("https://www.alphavantage.co/query", {
          params: {
            function: "GLOBAL_QUOTE",
            symbol,
            apikey: API_KEY,
          },
        }),
        axios.get("https://www.alphavantage.co/query", {
          params: {
            function: "TIME_SERIES_DAILY",
            symbol,
            outputsize: "compact",
            apikey: API_KEY,
          },
        }),
      ]);

      const quote = quoteRes.data["Global Quote"];
      if (!quote || !quote["01. symbol"]) {
        setError("Symbol not found or API limit reached.");
        setStockData(null);
        setChartData(null);
        return;
      }
      setStockData(quote);

      const timeSeries = timeSeriesRes.data["Time Series (Daily)"];
      if (timeSeries) {
        const dates = Object.keys(timeSeries).slice(0, 30).reverse();
        const prices = dates.map((d) => parseFloat(timeSeries[d]["4. close"]));
        setChartData({
          labels: dates,
          datasets: [
            {
              label: `${symbol} Closing Price`,
              data: prices,
              borderColor: "#4a90e2",
              backgroundColor: "rgba(74, 144, 226, 0.1)",
              tension: 0.3,
              fill: true,
            },
          ],
        });
      }
    } catch (err) {
      setError("Failed to fetch stock data.");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") fetchStock();
  };

  return (
    <div className="App">
      <h1>📈 My Stock App</h1>
      <div className="search-bar">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          placeholder="Enter stock symbol (e.g., AAPL)"
        />
        <button onClick={fetchStock}>Search</button>
      </div>

      {error && <p className="error">{error}</p>}

      {stockData && (
        <div className="stock-card">
          <h2>{stockData["01. symbol"]}</h2>
          <p>Price: <strong>${parseFloat(stockData["05. price"]).toFixed(2)}</strong></p>
          <p>Change: {stockData["09. change"]} ({stockData["10. change percent"]})</p>
          <p>Volume: {parseInt(stockData["06. volume"]).toLocaleString()}</p>
        </div>
      )}

      {chartData && (
        <div className="chart-container">
          <Line
            data={chartData}
            options={{
              responsive: true,
              plugins: {
                legend: { position: "top" },
                title: { display: true, text: "Last 30 Days" },
              },
            }}
          />
        </div>
      )}
    </div>
  );
}

export default App;
