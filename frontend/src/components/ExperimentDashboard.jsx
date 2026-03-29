import { useState, useEffect, useCallback } from "react";
import {
  listExperiments,
  createExperiment,
  getExperiment,
  getExperimentReport,
  listMetrics,
  selectWinner,
  concludeExperiment,
  exportExperiment,
} from "../api";
import { useToast } from "../ToastContext";
import ExperimentCharts from "./ExperimentCharts.jsx";
import StatisticalResults from "./StatisticalResults.jsx";
import MetricEntryPanel from "./MetricEntryPanel.jsx";
import VariantComparison from "./VariantComparison.jsx";
import AutoWinnerConfig from "./AutoWinnerConfig.jsx";
import AIInsightsPanel from "./AIInsightsPanel.jsx";
import CSVImportDialog from "./CSVImportDialog.jsx";
import SampleSizeCalculator from "./SampleSizeCalculator.jsx";

/**
 * ExperimentDashboard — main tab-section component for A/B testing on CampaignDetail.
 *
 * Shows:
 *   - List of experiments with status badges
 *   - "Create Experiment" button
 *   - Experiment detail with sub-tabs: Overview, Metrics, Results, Insights, Settings
 */

const STATUS_COLORS = {
  draft: "var(--color-text-dim)",
  running: "var(--color-primary)",
  paused: "var(--color-warning)",
  concluded: "var(--color-success)",
};

function ExperimentStatusBadge({ status }) {
  const color = STATUS_COLORS[status] || "var(--color-text-muted)";
  return (
    <span
      className="badge"
      style={{
        background: `${color}22`,
        color,
        fontSize: "0.72rem",
        textTransform: "capitalize",
      }}
    >
      {status || "draft"}
    </span>
  );
}

function formatDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

const DETAIL_TABS = [
  { key: "overview", label: "Overview", icon: "📊" },
  { key: "metrics", label: "Metrics", icon: "📝" },
  { key: "results", label: "Results", icon: "📐" },
  { key: "insights", label: "Insights", icon: "🤖" },
  { key: "settings", label: "Settings", icon: "⚙️" },
];

export default function ExperimentDashboard({ workspaceId, campaignId, contentPieces = [], isViewer = false }) {
  const { addToast } = useToast();

  // List state
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Selected experiment detail
  const [selectedExpId, setSelectedExpId] = useState(null);
  const [expDetail, setExpDetail] = useState(null);
  const [expReport, setExpReport] = useState(null);
  const [expMetrics, setExpMetrics] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeDetailTab, setActiveDetailTab] = useState("overview");

  // Create form
  const [createFormOpen, setCreateFormOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", variant_count: 2 });
  const [creating, setCreating] = useState(false);

  // CSV import dialog
  const [csvDialogOpen, setCsvDialogOpen] = useState(false);

  // Winner selection
  const [selectingWinner, setSelectingWinner] = useState(false);
  const [concluding, setConcluding] = useState(false);

  // ─── Load experiments list ───────────────────────────────────────
  const loadExperiments = useCallback(async () => {
    if (!workspaceId || !campaignId) return;
    try {
      const data = await listExperiments(workspaceId, campaignId);
      const items = Array.isArray(data) ? data : data?.items ?? [];
      setExperiments(items);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId]);

  useEffect(() => {
    loadExperiments();
  }, [loadExperiments]);

  // ─── Load experiment detail ──────────────────────────────────────
  const loadDetail = useCallback(async (expId) => {
    if (!expId || !workspaceId || !campaignId) return;
    setDetailLoading(true);
    try {
      const [detail, report, metrics] = await Promise.all([
        getExperiment(workspaceId, campaignId, expId),
        getExperimentReport(workspaceId, campaignId, expId).catch(() => null),
        listMetrics(workspaceId, campaignId, expId).catch(() => []),
      ]);
      setExpDetail(detail);
      setExpReport(report);
      setExpMetrics(Array.isArray(metrics) ? metrics : metrics?.items ?? []);
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to load experiment." });
    } finally {
      setDetailLoading(false);
    }
  }, [workspaceId, campaignId, addToast]);

  useEffect(() => {
    if (selectedExpId) loadDetail(selectedExpId);
  }, [selectedExpId, loadDetail]);

  // ─── Create experiment ───────────────────────────────────────────
  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.name.trim()) return;
    setCreating(true);
    try {
      const exp = await createExperiment(workspaceId, campaignId, {
        name: createForm.name,
        variant_count: createForm.variant_count,
      });
      addToast({ type: "success", stage: "Created", message: `Experiment "${createForm.name}" created.` });
      setCreateForm({ name: "", variant_count: 2 });
      setCreateFormOpen(false);
      await loadExperiments();
      setSelectedExpId(exp.id);
      setActiveDetailTab("overview");
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to create experiment." });
    } finally {
      setCreating(false);
    }
  };

  // ─── Select winner ──────────────────────────────────────────────
  const handleSelectWinner = async (variant) => {
    if (!selectedExpId) return;
    setSelectingWinner(true);
    try {
      await selectWinner(workspaceId, campaignId, selectedExpId, variant);
      addToast({ type: "success", stage: "Winner Selected", message: `Variant ${variant} selected as winner!` });
      await loadDetail(selectedExpId);
      await loadExperiments();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to select winner." });
    } finally {
      setSelectingWinner(false);
    }
  };

  // ─── Conclude experiment ────────────────────────────────────────
  const handleConclude = async () => {
    if (!selectedExpId) return;
    setConcluding(true);
    try {
      await concludeExperiment(workspaceId, campaignId, selectedExpId);
      addToast({ type: "success", stage: "Concluded", message: "Experiment has been concluded." });
      await loadDetail(selectedExpId);
      await loadExperiments();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to conclude experiment." });
    } finally {
      setConcluding(false);
    }
  };

  // ─── Export ─────────────────────────────────────────────────────
  const handleExport = async () => {
    if (!selectedExpId) return;
    try {
      const data = await exportExperiment(workspaceId, campaignId, selectedExpId, "csv");
      // If response is text/csv, download it
      const content = typeof data === "string" ? data : JSON.stringify(data, null, 2);
      const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `experiment-${selectedExpId}-report.csv`;
      a.click();
      URL.revokeObjectURL(url);
      addToast({ type: "success", stage: "Exported", message: "Report downloaded." });
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: err.message || "Failed to export." });
    }
  };

  // ─── Derive variants from experiment detail ─────────────────────
  const variants = [];
  if (expDetail) {
    const count = expDetail.variant_count || 2;
    for (let i = 0; i < count; i++) {
      variants.push(String.fromCharCode(65 + i)); // A, B, C, …
    }
  }

  // Build per-variant metrics map for VariantComparison
  const metricsPerVariant = {};
  for (const m of expMetrics) {
    const v = m.variant || "A";
    if (!metricsPerVariant[v]) {
      metricsPerVariant[v] = { impressions: 0, clicks: 0, conversions: 0, revenue: 0 };
    }
    metricsPerVariant[v].impressions += Number(m.impressions || 0);
    metricsPerVariant[v].clicks += Number(m.clicks || 0);
    metricsPerVariant[v].conversions += Number(m.conversions || 0);
    metricsPerVariant[v].revenue += Number(m.revenue || 0);
  }
  // Compute CTR for display
  for (const v of Object.keys(metricsPerVariant)) {
    const d = metricsPerVariant[v];
    d.ctr = d.impressions > 0 ? d.clicks / d.impressions : 0;
  }

  // ─── Loading state ──────────────────────────────────────────────
  if (loading) {
    return (
      <div className="card">
        <h2>🧪 A/B Testing</h2>
        <div className="loading"><span className="spinner" /> Loading experiments…</div>
      </div>
    );
  }

  if (error && experiments.length === 0) {
    return (
      <div className="card stage-error-card">
        <h2>🧪 A/B Testing</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Failed to load experiments</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // ─── Render experiment detail ───────────────────────────────────
  const renderDetailContent = () => {
    if (detailLoading) {
      return (
        <div className="loading" style={{ padding: "2rem 0" }}>
          <span className="spinner" /> Loading experiment data…
        </div>
      );
    }
    if (!expDetail) return null;

    switch (activeDetailTab) {
      case "overview":
        return (
          <div className="exp-detail-overview">
            <VariantComparison
              pieces={contentPieces}
              winner={expDetail.winner}
              metricsPerVariant={metricsPerVariant}
            />
            {expMetrics.length > 0 && (
              <div style={{ marginTop: "0.75rem" }}>
                <ExperimentCharts metrics={expMetrics} report={expReport} />
              </div>
            )}
            {expMetrics.length === 0 && (
              <div className="card" style={{ textAlign: "center", padding: "2rem", marginTop: "0.75rem" }}>
                <p style={{ color: "var(--color-text-muted)" }}>
                  No metrics recorded yet. Go to the Metrics tab to start recording data.
                </p>
              </div>
            )}
          </div>
        );

      case "metrics":
        return (
          <div className="exp-detail-metrics">
            <MetricEntryPanel
              workspaceId={workspaceId}
              campaignId={campaignId}
              experimentId={selectedExpId}
              variants={variants}
              isViewer={isViewer}
              onRecorded={() => loadDetail(selectedExpId)}
            />
            <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {!isViewer && (
                <button
                  type="button"
                  className="btn btn-outline"
                  style={{ fontSize: "0.8rem" }}
                  onClick={() => setCsvDialogOpen(true)}
                >
                  📥 Import CSV
                </button>
              )}
            </div>
            {expMetrics.length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <div className="card">
                  <h3 style={{ marginBottom: "0.75rem" }}>📋 Recorded Metrics</h3>
                  <div style={{ overflowX: "auto" }}>
                    <table className="exp-stats-table">
                      <thead>
                        <tr>
                          <th>Variant</th>
                          <th>Impressions</th>
                          <th>Clicks</th>
                          <th>Conversions</th>
                          <th>Revenue</th>
                          <th>Source</th>
                          <th>Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {expMetrics.map((m, i) => (
                          <tr key={m.id || i}>
                            <td><strong>{m.variant || "A"}</strong></td>
                            <td>{Number(m.impressions || 0).toLocaleString()}</td>
                            <td>{Number(m.clicks || 0).toLocaleString()}</td>
                            <td>{Number(m.conversions || 0).toLocaleString()}</td>
                            <td>${Number(m.revenue || 0).toFixed(2)}</td>
                            <td>
                              <span className="badge" style={{
                                fontSize: "0.68rem",
                                background: "rgba(99,102,241,0.15)",
                                color: "var(--color-primary-hover)",
                              }}>
                                {m.source || "manual"}
                              </span>
                            </td>
                            <td style={{ fontSize: "0.78rem", color: "var(--color-text-muted)" }}>
                              {m.created_at ? new Date(m.created_at).toLocaleDateString() : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
            <CSVImportDialog
              isOpen={csvDialogOpen}
              onClose={() => setCsvDialogOpen(false)}
              workspaceId={workspaceId}
              campaignId={campaignId}
              experimentId={selectedExpId}
              onImported={() => loadDetail(selectedExpId)}
            />
          </div>
        );

      case "results":
        return (
          <div className="exp-detail-results">
            <StatisticalResults report={expReport} experiment={expDetail} />
            {!isViewer && expDetail.status !== "concluded" && variants.length > 0 && (
              <div className="card" style={{ marginTop: "0.75rem" }}>
                <h3 style={{ marginBottom: "0.75rem" }}>🏆 Select Winner</h3>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  {variants.map((v) => (
                    <button
                      key={v}
                      type="button"
                      className={`btn ${expDetail.winner === v ? "btn-primary" : "btn-outline"}`}
                      disabled={selectingWinner}
                      onClick={() => handleSelectWinner(v)}
                    >
                      {selectingWinner ? "…" : `Select Variant ${v}`}
                    </button>
                  ))}
                  <span style={{ margin: "0 0.5rem", color: "var(--color-text-dim)" }}>|</span>
                  <button
                    type="button"
                    className="btn btn-outline"
                    style={{ borderColor: "var(--color-success)", color: "var(--color-success)" }}
                    disabled={concluding}
                    onClick={handleConclude}
                  >
                    {concluding ? "Concluding…" : "✓ Conclude Experiment"}
                  </button>
                </div>
              </div>
            )}
            <div style={{ marginTop: "0.75rem" }}>
              <SampleSizeCalculator />
            </div>
          </div>
        );

      case "insights":
        return (
          <AIInsightsPanel
            workspaceId={workspaceId}
            campaignId={campaignId}
            experimentId={selectedExpId}
          />
        );

      case "settings":
        return (
          <AutoWinnerConfig
            workspaceId={workspaceId}
            campaignId={campaignId}
            experimentId={selectedExpId}
            config={expDetail.config || {}}
            isViewer={isViewer}
            onSaved={() => loadDetail(selectedExpId)}
          />
        );

      default:
        return null;
    }
  };

  // ─── Main render ────────────────────────────────────────────────
  return (
    <div className="exp-dashboard">
      {/* Header row */}
      <div className="card">
        <div className="section-header-row">
          <h2>🧪 A/B Testing</h2>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {selectedExpId && (
              <button
                type="button"
                className="btn btn-outline"
                style={{ fontSize: "0.8rem" }}
                onClick={handleExport}
              >
                📤 Export
              </button>
            )}
            {!isViewer && !createFormOpen && (
              <button
                className="btn btn-primary"
                style={{ fontSize: "0.82rem" }}
                onClick={() => setCreateFormOpen(true)}
              >
                + New Experiment
              </button>
            )}
          </div>
        </div>

        {/* Create form */}
        {createFormOpen && (
          <form onSubmit={handleCreate} className="exp-create-form" style={{ marginTop: "1rem" }}>
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end" }}>
              <label className="exp-metric-field" style={{ flex: 2, minWidth: "200px" }}>
                <span>Experiment Name</span>
                <input
                  type="text"
                  value={createForm.name}
                  onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. CTA wording test"
                  required
                />
              </label>
              <label className="exp-metric-field" style={{ flex: 0, minWidth: "120px" }}>
                <span>Variants</span>
                <select
                  value={createForm.variant_count}
                  onChange={(e) => setCreateForm((p) => ({ ...p, variant_count: parseInt(e.target.value, 10) }))}
                >
                  <option value={2}>A/B (2)</option>
                  <option value={3}>A/B/C (3)</option>
                  <option value={4}>A/B/C/D (4)</option>
                </select>
              </label>
            </div>
            <div className="exp-metric-form-actions" style={{ marginTop: "0.75rem" }}>
              <button type="submit" className="btn btn-primary" disabled={creating}>
                {creating ? "Creating…" : "Create Experiment"}
              </button>
              <button type="button" className="btn btn-outline" onClick={() => setCreateFormOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Experiment list */}
      {experiments.length === 0 && !selectedExpId ? (
        <div className="card" style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
          <p style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>🧪</p>
          <p style={{ color: "var(--color-text-muted)" }}>No experiments yet.{!isViewer && ' Click "New Experiment" to get started.'}</p>
        </div>
      ) : (
        <div className="exp-layout">
          {/* Sidebar: experiment list */}
          <div className="exp-list-sidebar">
            {experiments.map((exp) => (
              <button
                key={exp.id}
                className={`exp-list-item${selectedExpId === exp.id ? " exp-list-item--active" : ""}`}
                onClick={() => {
                  setSelectedExpId(exp.id);
                  setActiveDetailTab("overview");
                }}
              >
                <div className="exp-list-item-name">{exp.name || "Untitled"}</div>
                <div className="exp-list-item-meta">
                  <ExperimentStatusBadge status={exp.status} />
                  {exp.winner && <span className="exp-winner-mini-badge">👑 {exp.winner}</span>}
                  <span className="exp-list-item-date">{formatDate(exp.created_at)}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Detail panel */}
          <div className="exp-detail-panel">
            {!selectedExpId ? (
              <div className="card" style={{ textAlign: "center", padding: "3rem 1rem" }}>
                <p style={{ color: "var(--color-text-muted)" }}>Select an experiment to view details.</p>
              </div>
            ) : (
              <>
                {/* Detail header */}
                {expDetail && (
                  <div className="exp-detail-header card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div>
                        <h3 style={{ fontSize: "1.05rem" }}>{expDetail.name || "Untitled"}</h3>
                        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.25rem" }}>
                          <ExperimentStatusBadge status={expDetail.status} />
                          {expDetail.winner && (
                            <span className="badge" style={{ background: "rgba(16,185,129,0.2)", color: "var(--color-success)", fontSize: "0.72rem" }}>
                              👑 Winner: {expDetail.winner}
                            </span>
                          )}
                          <span style={{ fontSize: "0.75rem", color: "var(--color-text-dim)" }}>
                            Created {formatDate(expDetail.created_at)}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ fontSize: "0.78rem" }}
                        onClick={() => { setSelectedExpId(null); setExpDetail(null); }}
                      >
                        ← Back to List
                      </button>
                    </div>
                  </div>
                )}

                {/* Detail sub-tabs */}
                <div className="exp-detail-tabs">
                  {DETAIL_TABS.map((tab) => (
                    <button
                      key={tab.key}
                      className={`exp-detail-tab${activeDetailTab === tab.key ? " exp-detail-tab--active" : ""}`}
                      onClick={() => setActiveDetailTab(tab.key)}
                    >
                      <span aria-hidden="true">{tab.icon}</span> {tab.label}
                    </button>
                  ))}
                </div>

                {/* Detail body */}
                <div className="exp-detail-body">
                  {renderDetailContent()}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
