import React, { useState } from "react";
import axios from "axios";
import "./App.css";

function App() {
  const [symbol, setSymbol] = useState("");
  const [stockData, setStockData] = useState(null);
  const API_KEY = "YOUR_ALPHA_VANTAGE_API_KEY";

  const fetchStock = async () => {
    if (!symbol) return;
    const res = await axios.get("https://www.alphavantage.co/query", {
      params: {
        function: "GLOBAL_QUOTE",
        symbol,
        apikey: API_KEY,
      },
    });
    setStockData(res.data["Global Quote"]);
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
    </div>
  );
}

export default App;
