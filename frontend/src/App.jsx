import { Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import NewCampaign from "./pages/NewCampaign.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import useWebSocket from "./hooks/useWebSocket.js";
import ThemeToggle from "./components/ThemeToggle.jsx";

export default function App() {
  const { events, connected } = useWebSocket(null);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span role="img" aria-label="rocket">🚀</span> Campaign Builder
        </h1>
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/new">+ New Campaign</NavLink>
          <ThemeToggle />
          <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
            <span
              className={`ws-indicator ${connected ? "connected" : "disconnected"}`}
            />
            {connected ? "Live" : "Offline"}
          </span>
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard events={events} />} />
          <Route path="/new" element={<NewCampaign />} />
          <Route path="/campaign/:id" element={<CampaignDetail />} />
        </Routes>
      </main>
    </div>
  );
}
