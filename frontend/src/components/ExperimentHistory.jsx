import { useState, useEffect, useCallback } from "react";
import { listExperimentLearnings, createExperimentLearning } from "../api";
import { useToast } from "../ToastContext";

/** Parse a comma-separated tag string into a deduplicated, trimmed array. */
function parseTags(tagsString) {
  return tagsString ? tagsString.split(",").map((t) => t.trim()).filter(Boolean) : [];
}

/**
 * ExperimentHistory — workspace-level experiment learnings section.
 *
 * Displays a searchable/filterable list of experiment learnings
 * with the ability to add new learnings.
 */

export default function ExperimentHistory({ workspaceId, isViewer = false }) {
  const { addToast } = useToast();
  const [learnings, setLearnings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [formData, setFormData] = useState({ title: "", summary: "", tags: "", campaign_id: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const data = await listExperimentLearnings(workspaceId);
      setLearnings(Array.isArray(data) ? data : data?.items ?? []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title.trim()) return;
    setSubmitting(true);
    try {
      await createExperimentLearning(workspaceId, {
        title: formData.title,
        summary: formData.summary,
        tags: parseTags(formData.tags),
        campaign_id: formData.campaign_id || null,
      });
      setFormData({ title: "", summary: "", tags: "", campaign_id: "" });
      setFormOpen(false);
      addToast({ type: "success", stage: "Learning Saved", message: "Experiment learning added." });
      await load();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to save learning." });
    } finally {
      setSubmitting(false);
    }
  };

  // Collect all unique tags
  const allTags = [...new Set(learnings.flatMap((l) => l.tags || []))].sort();

  // Filter learnings
  const filtered = learnings.filter((l) => {
    const matchesSearch = !searchQuery ||
      (l.title || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (l.summary || "").toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTag = !tagFilter || (l.tags || []).includes(tagFilter);
    return matchesSearch && matchesTag;
  });

  if (loading) {
    return (
      <div className="card">
        <h2>🧪 Experiment Learnings</h2>
        <div className="loading"><span className="spinner" /> Loading learnings…</div>
      </div>
    );
  }

  if (error && learnings.length === 0) {
    return (
      <div className="card stage-error-card">
        <h2>🧪 Experiment Learnings</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="section-header-row" style={{ marginBottom: "1rem" }}>
        <h2>🧪 Experiment Learnings</h2>
        {!isViewer && !formOpen && (
          <button
            className="btn btn-primary"
            style={{ fontSize: "0.82rem" }}
            onClick={() => setFormOpen(true)}
          >
            + Add Learning
          </button>
        )}
      </div>

      {/* Search & filter */}
      <div className="exp-history-filters" style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search learnings…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="exp-config-input"
          style={{ flex: 1, minWidth: "180px" }}
          aria-label="Search learnings"
        />
        {allTags.length > 0 && (
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="exp-config-select"
            style={{ minWidth: "140px" }}
            aria-label="Filter by tag"
          >
            <option value="">All tags</option>
            {allTags.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
      </div>

      {/* Add form */}
      {formOpen && (
        <form onSubmit={handleSubmit} className="exp-learning-form" style={{ marginBottom: "1rem" }}>
          <label className="exp-metric-field">
            <span>Title</span>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData((p) => ({ ...p, title: e.target.value }))}
              required
              placeholder="What did you learn?"
            />
          </label>
          <label className="exp-metric-field">
            <span>Summary</span>
            <textarea
              value={formData.summary}
              onChange={(e) => setFormData((p) => ({ ...p, summary: e.target.value }))}
              placeholder="Detailed description of the learning…"
              rows={3}
              style={{ resize: "vertical" }}
            />
          </label>
          <label className="exp-metric-field">
            <span>Tags (comma-separated)</span>
            <input
              type="text"
              value={formData.tags}
              onChange={(e) => setFormData((p) => ({ ...p, tags: e.target.value }))}
              placeholder="conversion, email, cta"
            />
          </label>
          <div className="exp-metric-form-actions" style={{ marginTop: "0.5rem" }}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Saving…" : "Save Learning"}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => setFormOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Learnings list */}
      {filtered.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)", padding: "1rem 0", textAlign: "center" }}>
          {learnings.length === 0 ? "No learnings recorded yet." : "No learnings match your search."}
        </p>
      ) : (
        <div className="exp-learnings-list">
          {filtered.map((l, i) => (
            <div key={l.id || i} className="exp-learning-card">
              <div className="exp-learning-card-header">
                <strong>{l.title}</strong>
                {l.created_at && (
                  <span style={{ fontSize: "0.72rem", color: "var(--color-text-dim)" }}>
                    {new Date(l.created_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              {l.summary && (
                <p style={{ fontSize: "0.82rem", color: "var(--color-text-muted)", marginTop: "0.25rem" }}>
                  {l.summary}
                </p>
              )}
              {l.tags && l.tags.length > 0 && (
                <div className="exp-learning-tags" style={{ marginTop: "0.4rem" }}>
                  {l.tags.map((t) => (
                    <span
                      key={t}
                      className="badge"
                      style={{
                        background: "rgba(99,102,241,0.15)",
                        color: "var(--color-primary-hover)",
                        fontSize: "0.68rem",
                        cursor: "pointer",
                      }}
                      onClick={() => setTagFilter(t)}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
