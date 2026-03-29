import { useState } from "react";
import { recordMetrics } from "../api";
import { useToast } from "../ToastContext";

/**
 * MetricEntryPanel — form for entering/recording metrics per variant.
 *
 * Allows the user to enter impressions, clicks, conversions, and revenue
 * for each variant and submit them to the backend.
 */

const SOURCE_META = {
  manual: { label: "Manual", color: "var(--color-primary)" },
  csv: { label: "CSV", color: "#8B5CF6" },
  webhook: { label: "Webhook", color: "#F49D37" },
  api: { label: "API", color: "#EC4899" },
};

function SourceBadge({ source }) {
  const meta = SOURCE_META[source] || SOURCE_META.manual;
  return (
    <span
      className="badge"
      style={{
        background: `${meta.color}22`,
        color: meta.color,
        fontSize: "0.68rem",
        padding: "0.15rem 0.5rem",
      }}
    >
      {meta.label}
    </span>
  );
}

const emptyEntry = { impressions: "", clicks: "", conversions: "", revenue: "" };

export default function MetricEntryPanel({ workspaceId, campaignId, experimentId, variants = ["A", "B"], onRecorded, isViewer = false }) {
  const { addToast } = useToast();
  const [activeVariant, setActiveVariant] = useState(variants[0] || "A");
  const [formData, setFormData] = useState(() => {
    const init = {};
    for (const v of variants) init[v] = { ...emptyEntry };
    return init;
  });
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (variant, field, value) => {
    setFormData((prev) => ({
      ...prev,
      [variant]: { ...prev[variant], [field]: value },
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const data = formData[activeVariant];
    if (!data.impressions && !data.clicks && !data.conversions && !data.revenue) {
      addToast({ type: "warning", stage: "Validation", message: "Enter at least one metric value." });
      return;
    }
    setSubmitting(true);
    try {
      await recordMetrics(workspaceId, campaignId, experimentId, {
        variant: activeVariant,
        impressions: data.impressions ? parseInt(data.impressions, 10) : 0,
        clicks: data.clicks ? parseInt(data.clicks, 10) : 0,
        conversions: data.conversions ? parseInt(data.conversions, 10) : 0,
        revenue: data.revenue ? parseFloat(data.revenue) : 0,
        source: "manual",
      });
      setFormData((prev) => ({ ...prev, [activeVariant]: { ...emptyEntry } }));
      addToast({ type: "success", stage: "Metrics Saved", message: `Metrics recorded for Variant ${activeVariant}.` });
      if (onRecorded) onRecorded();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to record metrics." });
    } finally {
      setSubmitting(false);
    }
  };

  if (isViewer) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "1.5rem" }}>
        <p style={{ color: "var(--color-text-muted)" }}>
          👁 You have read-only access. Metric entry is disabled.
        </p>
      </div>
    );
  }

  const data = formData[activeVariant] || emptyEntry;

  return (
    <div className="card">
      <div className="section-header-row" style={{ marginBottom: "1rem" }}>
        <h3>📝 Record Metrics</h3>
        <SourceBadge source="manual" />
      </div>

      {/* Variant tabs */}
      <div className="exp-variant-tabs" role="tablist" aria-label="Select variant">
        {variants.map((v) => (
          <button
            key={v}
            role="tab"
            aria-selected={activeVariant === v}
            className={`exp-variant-tab${activeVariant === v ? " exp-variant-tab--active" : ""}`}
            onClick={() => setActiveVariant(v)}
          >
            Variant {v}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="exp-metric-form">
        <div className="exp-metric-form-grid">
          <label className="exp-metric-field">
            <span>Impressions</span>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="0"
              value={data.impressions}
              onChange={(e) => handleChange(activeVariant, "impressions", e.target.value)}
            />
          </label>
          <label className="exp-metric-field">
            <span>Clicks</span>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="0"
              value={data.clicks}
              onChange={(e) => handleChange(activeVariant, "clicks", e.target.value)}
            />
          </label>
          <label className="exp-metric-field">
            <span>Conversions</span>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="0"
              value={data.conversions}
              onChange={(e) => handleChange(activeVariant, "conversions", e.target.value)}
            />
          </label>
          <label className="exp-metric-field">
            <span>Revenue ($)</span>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="0.00"
              value={data.revenue}
              onChange={(e) => handleChange(activeVariant, "revenue", e.target.value)}
            />
          </label>
        </div>
        <div className="exp-metric-form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Recording…" : `Record Variant ${activeVariant} Metrics`}
          </button>
        </div>
      </form>
    </div>
  );
}
