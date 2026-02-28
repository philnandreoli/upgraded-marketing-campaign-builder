import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listCampaigns, deleteCampaign } from "../api";

export default function Dashboard({ events }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setCampaigns(await listCampaigns());
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Auto-refresh when a pipeline event arrives
  useEffect(() => {
    if (events.length > 0) load();
  }, [events.length]);

  const handleDelete = async (id) => {
    if (!confirm("Delete this campaign?")) return;
    await deleteCampaign(id);
    load();
  };

  if (loading && campaigns.length === 0) {
    return (
      <div className="loading">
        <span className="spinner" /> Loading campaigns…
      </div>
    );
  }

  if (campaigns.length === 0) {
    return (
      <div className="empty-state">
        <p>No campaigns yet.</p>
        <Link to="/new" className="btn btn-primary">
          + Create your first campaign
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="section-header">
        <h2>Campaigns</h2>
        <Link to="/new" className="btn btn-primary">
          + New Campaign
        </Link>
      </div>

      {campaigns.map((c) => (
        <div key={c.id} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <Link to={`/campaign/${c.id}`} style={{ fontWeight: 600 }}>
              {c.product_or_service}
            </Link>
            <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginTop: "0.2rem" }}>
              {c.goal}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span className={`badge badge-${c.status}`}>{c.status.replace(/_/g, " ")}</span>
            <button className="btn btn-outline" style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }} onClick={() => handleDelete(c.id)}>
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
