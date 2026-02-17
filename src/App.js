import React, { useState } from "react";
import axios from "axios";
import "./App.css";
import { Line } from "react-chartjs-2";
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
  const API_KEY = "6Q4XW688FOUHZKGG";

  const fetchStock = async () => {
    if (!symbol) return;
    try {
      const [quoteRes, chartRes] = await Promise.all([
        axios.get("https://www.alphavantage.co/query", {
          params: {
            function: "GLOBAL_QUOTE",
            symbol,
            apikey: API_KEY
          }
        }),
        axios.get("https://www.alphavantage.co/query", {
          params: {
            function: "TIME_SERIES_DAILY",
            symbol,
            apikey: API_KEY
          }
        })
      ]);

      setStockData(quoteRes.data["Global Quote"]);

      const dailyData = chartRes.data["Time Series (Daily)"];
      if (dailyData) {
        const labels = Object.keys(dailyData).slice(0, 7).reverse();
        const prices = labels.map(date => dailyData[date]["4. close"]);
        setChartData({
          labels,
          datasets: [
            {
              label: "Price (Last 7 Days)",
              data: prices,
              borderColor: "#4bc0c0",
              backgroundColor: "rgba(75,192,192,0.2)",
            }
          ]
        });
      }
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };

  return (
    <div className="App">
      <h1>📈 My Stock App</h1>
      <input
        value={symbol}
        onChange={(e) => setSymbol(e.target.value.toUpperCase())}
        placeholder="Enter stock symbol (e.g., AAPL)"
      />
      <button onClick={fetchStock}>Search</button>

      {stockData && (
        <div className="stock-card">
          <h2>{stockData["01. symbol"]}</h2>
          <p>Price: ${stockData["05. price"]}</p>
          <p>Change %: {stockData["10. change percent"]}</p>
        </div>
      )}

      {chartData && (
        <div className="chart-container">
          <Line data={chartData} />
        </div>
      )}
    </div>
  );
}

export default App;
