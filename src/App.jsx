import React, { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import StockLookup from "./pages/StockLookup.jsx";
import Screener from "./pages/Screener.jsx";
import Alerts from "./pages/Alerts.jsx";
import Strategies from "./pages/Strategies.jsx";
import StrategyDetail from "./pages/StrategyDetail.jsx";
import SpecEditor from "./pages/SpecEditor.jsx";
import OptionChain from "./pages/OptionChain.jsx";
import Watchlist from "./pages/Watchlist.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import Bots from "./pages/Bots.jsx";
import Backtests from "./pages/Backtests.jsx";
import "./App.css";

function App() {
  const [navOpen, setNavOpen] = useState(false);

  // close the drawer on Escape
  useEffect(() => {
    if (!navOpen) return undefined;
    const onKeyDown = (e) => e.key === "Escape" && setNavOpen(false);
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [navOpen]);

  return (
    <div className="layout">
      <div className="topbar">
        <button
          type="button"
          className={`nav-toggle${navOpen ? " nav-toggle-open" : ""}`}
          aria-label={navOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
        <span className="topbar-title">stock-app</span>
      </div>
      {navOpen && (
        <div
          className="nav-scrim"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}
      <nav
        className={`sidebar${navOpen ? " sidebar-open" : ""}`}
        onClick={() => setNavOpen(false)}
      >
        <div className="sidebar-title">stock-app</div>
        <NavLink to="/" end>
          Stock Lookup
        </NavLink>
        <NavLink to="/screener">VIX Screener</NavLink>
        <NavLink to="/strategies">Strategies</NavLink>
        <NavLink to="/backtests">Backtests</NavLink>
        <NavLink to="/chain">Option Chain</NavLink>
        <NavLink to="/watchlist">Watchlist</NavLink>
        <NavLink to="/portfolio">Portfolio</NavLink>
        <NavLink to="/bots">Bots</NavLink>
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
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/chain" element={<OptionChain />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/alerts" element={<Alerts />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
