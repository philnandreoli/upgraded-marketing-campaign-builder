import { useState, useEffect } from "react";
import { updateExperiment } from "../api";
import { useToast } from "../ToastContext";

/**
 * AutoWinnerConfig — configuration form for automatic winner selection.
 *
 * Controls:
 *   - Toggle to enable/disable auto-winner
 *   - Confidence threshold slider (0.80 - 0.99)
 *   - Min sample size input
 *   - Statistical method selector (Bayesian / Frequentist)
 */

export default function AutoWinnerConfig({ workspaceId, campaignId, experimentId, config = {}, onSaved, isViewer = false }) {
  const { addToast } = useToast();
  const [enabled, setEnabled] = useState(config.auto_winner_enabled ?? false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(config.confidence_threshold ?? 0.95);
  const [minSampleSize, setMinSampleSize] = useState(config.min_sample_size ?? 100);
  const [method, setMethod] = useState(config.statistical_method ?? "bayesian");
  const [saving, setSaving] = useState(false);

  // Sync with incoming config prop
  useEffect(() => {
    setEnabled(config.auto_winner_enabled ?? false);
    setConfidenceThreshold(config.confidence_threshold ?? 0.95);
    setMinSampleSize(config.min_sample_size ?? 100);
    setMethod(config.statistical_method ?? "bayesian");
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateExperiment(workspaceId, campaignId, experimentId, {
        config: {
          auto_winner_enabled: enabled,
          confidence_threshold: confidenceThreshold,
          min_sample_size: minSampleSize,
          statistical_method: method,
        },
      });
      addToast({ type: "success", stage: "Saved", message: "Auto-winner settings updated." });
      if (onSaved) onSaved();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to save settings." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <h3 style={{ marginBottom: "1rem" }}>⚙️ Auto-Winner Configuration</h3>

      <div className="exp-config-form">
        {/* Enable toggle */}
        <div className="exp-config-row">
          <label className="exp-config-toggle-label">
            <span>Enable Auto-Winner Selection</span>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              className={`exp-toggle ${enabled ? "exp-toggle--on" : ""}`}
              onClick={() => !isViewer && setEnabled(!enabled)}
              disabled={isViewer}
            >
              <span className="exp-toggle-knob" />
            </button>
          </label>
          <p className="exp-config-hint">
            When enabled, the system will automatically select a winner when the configured thresholds are met.
          </p>
        </div>

        {/* Confidence threshold slider */}
        <div className="exp-config-row">
          <label className="exp-config-field">
            <span>Confidence Threshold</span>
            <div className="exp-slider-container">
              <input
                type="range"
                min="0.80"
                max="0.99"
                step="0.01"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                disabled={isViewer || !enabled}
                className="exp-slider"
                aria-label="Confidence threshold"
              />
              <span className="exp-slider-value">{(confidenceThreshold * 100).toFixed(0)}%</span>
            </div>
          </label>
        </div>

        {/* Min sample size */}
        <div className="exp-config-row">
          <label className="exp-config-field">
            <span>Minimum Sample Size per Variant</span>
            <input
              type="number"
              min="10"
              step="10"
              value={minSampleSize}
              onChange={(e) => setMinSampleSize(parseInt(e.target.value, 10) || 100)}
              disabled={isViewer || !enabled}
              placeholder="100"
              className="exp-config-input"
            />
          </label>
        </div>

        {/* Statistical method */}
        <div className="exp-config-row">
          <label className="exp-config-field">
            <span>Statistical Method</span>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              disabled={isViewer || !enabled}
              className="exp-config-select"
            >
              <option value="bayesian">Bayesian</option>
              <option value="frequentist">Frequentist</option>
            </select>
          </label>
        </div>

        {/* Save */}
        {!isViewer && (
          <div className="exp-config-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={handleSave}
            >
              {saving ? "Saving…" : "Save Settings"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
