import { useCallback, useEffect, useState } from "react";
import {
  listBudgetEntries,
  createBudgetEntry,
  deleteBudgetEntry,
  getCampaignBudgetSummary,
} from "../api";
import BudgetCharts from "./BudgetCharts.jsx";
import BudgetAlertBanner from "./BudgetAlertBanner.jsx";

const ENTRY_TYPE_OPTIONS = [
  { value: "planned", label: "Planned" },
  { value: "actual", label: "Actual" },
];

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

export default function BudgetSection({ workspaceId, campaignId, isViewer = false }) {
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
          {!isViewer && (
            <button
              className="btn btn-primary"
              onClick={() => setFormOpen((prev) => !prev)}
              aria-expanded={formOpen}
            >
              {formOpen ? "Cancel" : "+ Add Entry"}
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
              <label className="budget-form-field">
                <span>Category</span>
                <input
                  type="text"
                  name="category"
                  value={form.category}
                  onChange={handleChange}
                  placeholder="e.g. Advertising"
                />
              </label>
              <label className="budget-form-field">
                <span>Date</span>
                <input
                  type="date"
                  name="entry_date"
                  value={form.entry_date}
                  onChange={handleChange}
                  required
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
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Saving…" : "Save Entry"}
            </button>
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
                      <th>Category</th>
                      <th>Description</th>
                      <th className="budget-table-amount">Amount</th>
                      {!isViewer && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {plannedEntries.map((entry) => (
                      <tr key={entry.id}>
                        <td>{formatDate(entry.entry_date)}</td>
                        <td>{entry.category || "—"}</td>
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
                      <th>Category</th>
                      <th>Description</th>
                      <th className="budget-table-amount">Amount</th>
                      {!isViewer && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {actualEntries.map((entry) => (
                      <tr key={entry.id}>
                        <td>{formatDate(entry.entry_date)}</td>
                        <td>{entry.category || "—"}</td>
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
