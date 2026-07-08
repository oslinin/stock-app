import React from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import StockLookup from "./pages/StockLookup.jsx";
import Screener from "./pages/Screener.jsx";
import Alerts from "./pages/Alerts.jsx";
import Strategies from "./pages/Strategies.jsx";
import StrategyDetail from "./pages/StrategyDetail.jsx";
import SpecEditor from "./pages/SpecEditor.jsx";
import OptionChain from "./pages/OptionChain.jsx";
import "./App.css";

function App() {
  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="sidebar-title">stock-app</div>
        <NavLink to="/" end>
          Stock Lookup
        </NavLink>
        <NavLink to="/screener">VIX Screener</NavLink>
        <NavLink to="/strategies">Strategies</NavLink>
        <NavLink to="/chain">Option Chain</NavLink>
        <NavLink to="/alerts">Alerts</NavLink>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<StockLookup />} />
          <Route path="/screener" element={<Screener />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/strategies/new" element={<SpecEditor />} />
          <Route path="/strategies/:id" element={<StrategyDetail />} />
          <Route path="/strategies/:id/edit" element={<SpecEditor />} />
          <Route path="/chain" element={<OptionChain />} />
          <Route path="/alerts" element={<Alerts />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
