import { useCallback, useEffect, useRef, useState } from "react";
import {
  listBudgetEntries,
  createBudgetEntry,
  deleteBudgetEntry,
  getCampaignBudgetSummary,
} from "../api";
import BudgetCharts from "./BudgetCharts.jsx";
import BudgetAlertBanner from "./BudgetAlertBanner.jsx";
import DatePicker from "./DatePicker";

const ENTRY_TYPE_OPTIONS = [
  { value: "planned", label: "Planned" },
  { value: "actual", label: "Actual" },
];

const CHANNEL_META = {
  email: { label: "Email", icon: "✉️" },
  social_media: { label: "Social Media", icon: "📱" },
  paid_ads: { label: "Paid Ads", icon: "💰" },
  content_marketing: { label: "Content Marketing", icon: "✍️" },
  seo: { label: "SEO", icon: "🔍" },
  influencer: { label: "Influencer", icon: "🌟" },
  events: { label: "Events", icon: "🎪" },
  pr: { label: "PR", icon: "📰" },
};

const SOCIAL_PLATFORM_META = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  linkedin: "LinkedIn",
};

function channelLabel(value) {
  return CHANNEL_META[value]?.label || value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function channelIcon(value) {
  return CHANNEL_META[value]?.icon || "📢";
}

function socialPlatformLabel(value) {
  return SOCIAL_PLATFORM_META[value] || value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatChannelDisplay(cat) {
  if (!cat) return "—";
  if (cat.startsWith("social_media:")) {
    const platform = cat.split(":")[1];
    return `${channelIcon("social_media")} ${socialPlatformLabel(platform)}`;
  }
  return `${channelIcon(cat)} ${channelLabel(cat)}`;
}

function ChannelPicker({ channels, socialPlatforms, value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const hasSocial = channels.includes("social_media");
  const isSocialSubPlatform = hasSocial && socialPlatforms.some((p) => value === `social_media:${p}`);

  function displayLabel() {
    if (!value) return null;
    if (value.startsWith("social_media:")) {
      const platform = value.split(":")[1];
      return `${channelIcon("social_media")} Social Media — ${socialPlatformLabel(platform)}`;
    }
    return `${channelIcon(value)} ${channelLabel(value)}`;
  }

  function select(val) {
    onChange(val);
    setOpen(false);
  }

  return (
    <div className="budget-channel-picker" ref={ref}>
      <button
        type="button"
        className="datepicker-trigger"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={value ? "datepicker-value" : "datepicker-placeholder"}>
          {value ? displayLabel() : "Select channel"}
        </span>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="datepicker-icon">
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {open && (
        <div className="budget-channel-dropdown">
          {channels.map((ch) => {
            if (ch === "social_media" && hasSocial && socialPlatforms.length > 0) {
              return (
                <div key={ch} className="budget-channel-group">
                  <div className="budget-channel-group-label">
                    <span className="budget-channel-item-icon">{channelIcon(ch)}</span>
                    {channelLabel(ch)}
                  </div>
                  <div className="budget-channel-sub-list">
                    {socialPlatforms.map((p) => {
                      const val = `social_media:${p}`;
                      return (
                        <button
                          key={val}
                          type="button"
                          className={`budget-channel-item${value === val ? " budget-channel-item--selected" : ""}`}
                          onClick={() => select(val)}
                        >
                          {socialPlatformLabel(p)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            }
            return (
              <button
                key={ch}
                type="button"
                className={`budget-channel-item${value === ch ? " budget-channel-item--selected" : ""}`}
                onClick={() => select(ch)}
              >
                <span className="budget-channel-item-icon">{channelIcon(ch)}</span>
                {channelLabel(ch)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatCurrency(amount, currency = "USD") {
  return Number(amount).toLocaleString(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  });
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr + (dateStr.includes("T") ? "" : "T00:00:00"));
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

const emptyForm = {
  entry_type: "actual",
  amount: "",
  currency: "USD",
  category: "",
  description: "",
  entry_date: new Date().toISOString().split("T")[0],
};

export default function BudgetSection({ workspaceId, campaignId, isViewer = false, channels = [], socialPlatforms = [] }) {
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const load = useCallback(async () => {
    if (!workspaceId || !campaignId) return;
    try {
      const [entriesData, summaryData] = await Promise.all([
        listBudgetEntries(workspaceId, campaignId),
        getCampaignBudgetSummary(workspaceId, campaignId),
      ]);
      setEntries(entriesData);
      setSummary(summaryData);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.amount || !form.entry_date) return;
    setSubmitting(true);
    try {
      await createBudgetEntry(workspaceId, campaignId, {
        entry_type: form.entry_type,
        amount: parseFloat(form.amount),
        currency: form.currency.toUpperCase(),
        category: form.category || null,
        description: form.description || null,
        entry_date: form.entry_date,
      });
      setForm({ ...emptyForm });
      setFormOpen(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (entryId) => {
    setDeletingId(entryId);
    try {
      await deleteBudgetEntry(workspaceId, campaignId, entryId);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="card">
        <h2>💰 Budget</h2>
        <div className="loading"><span className="spinner" /> Loading budget data…</div>
      </div>
    );
  }

  if (error && entries.length === 0 && !summary) {
    return (
      <div className="card stage-error-card">
        <h2>💰 Budget</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Failed to load budget data</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  const plannedEntries = entries.filter((e) => e.entry_type === "planned");
  const actualEntries = entries.filter((e) => e.entry_type === "actual");

  return (
    <div className="budget-section">
      {summary?.is_alert_triggered && (
        <BudgetAlertBanner summary={summary} />
      )}

      {summary && (
        <BudgetCharts summary={summary} />
      )}

      <div className="card">
        <div className="section-header-row">
          <h2>💰 Budget Entries</h2>
          {!isViewer && !formOpen && (
            <button
              className="budget-add-entry-btn"
              onClick={() => setFormOpen(true)}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              Add Entry
            </button>
          )}
        </div>

        {error && (
          <p className="budget-error" style={{ color: "var(--color-danger)", marginBottom: "0.75rem" }}>{error}</p>
        )}

        {formOpen && (
          <form className="budget-entry-form" onSubmit={handleSubmit}>
            <div className="budget-form-row">
              <label className="budget-form-field">
                <span>Type</span>
                <select name="entry_type" value={form.entry_type} onChange={handleChange}>
                  {ENTRY_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
              <label className="budget-form-field">
                <span>Amount</span>
                <input
                  type="number"
                  name="amount"
                  value={form.amount}
                  onChange={handleChange}
                  min="0"
                  step="0.01"
                  placeholder="0.00"
                  required
                />
              </label>
              <label className="budget-form-field">
                <span>Currency</span>
                <input
                  type="text"
                  name="currency"
                  value={form.currency}
                  onChange={handleChange}
                  maxLength={3}
                  placeholder="USD"
                />
              </label>
            </div>
            <div className="budget-form-row">
              <div className="budget-form-field">
                <span>Channel</span>
                <ChannelPicker
                  channels={channels}
                  socialPlatforms={socialPlatforms}
                  value={form.category}
                  onChange={(val) => setForm((prev) => ({ ...prev, category: val }))}
                />
              </div>
              <label className="budget-form-field">
                <span>Date</span>
                <DatePicker
                  value={form.entry_date}
                  onChange={(e) => handleChange({ target: { name: "entry_date", value: e.target.value } })}
                />
              </label>
            </div>
            <label className="budget-form-field budget-form-field--full">
              <span>Description</span>
              <input
                type="text"
                name="description"
                value={form.description}
                onChange={handleChange}
                placeholder="Optional description"
              />
            </label>
            <div className="budget-form-actions">
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Saving…" : "Save Entry"}
              </button>
              <button type="button" className="btn btn-outline" onClick={() => { setFormOpen(false); setForm({ ...emptyForm }); }}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {entries.length === 0 ? (
          <p className="budget-empty">No budget entries yet.{!isViewer && " Click \"+ Add Entry\" to get started."}</p>
        ) : (
          <div className="budget-entries-tables">
            {plannedEntries.length > 0 && (
              <div className="budget-entry-group">
                <h3>Planned</h3>
                <table className="budget-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Channel</th>
                      <th>Description</th>
                      <th className="budget-table-amount">Amount</th>
                      {!isViewer && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {plannedEntries.map((entry) => (
                      <tr key={entry.id}>
                        <td>{formatDate(entry.entry_date)}</td>
                        <td>{formatChannelDisplay(entry.category)}</td>
                        <td>{entry.description || "—"}</td>
                        <td className="budget-table-amount">{formatCurrency(entry.amount, entry.currency)}</td>
                        {!isViewer && (
                          <td>
                            <button
                              className="btn btn-outline budget-delete-btn"
                              disabled={deletingId === entry.id}
                              onClick={() => handleDelete(entry.id)}
                              aria-label={`Delete entry ${entry.description || entry.category || entry.id}`}
                            >
                              {deletingId === entry.id ? "…" : "✕"}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {actualEntries.length > 0 && (
              <div className="budget-entry-group">
                <h3>Actual Spend</h3>
                <table className="budget-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Channel</th>
                      <th>Description</th>
                      <th className="budget-table-amount">Amount</th>
                      {!isViewer && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {actualEntries.map((entry) => (
                      <tr key={entry.id}>
                        <td>{formatDate(entry.entry_date)}</td>
                        <td>{formatChannelDisplay(entry.category)}</td>
                        <td>{entry.description || "—"}</td>
                        <td className="budget-table-amount">{formatCurrency(entry.amount, entry.currency)}</td>
                        {!isViewer && (
                          <td>
                            <button
                              className="btn btn-outline budget-delete-btn"
                              disabled={deletingId === entry.id}
                              onClick={() => handleDelete(entry.id)}
                              aria-label={`Delete entry ${entry.description || entry.category || entry.id}`}
                            >
                              {deletingId === entry.id ? "…" : "✕"}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
