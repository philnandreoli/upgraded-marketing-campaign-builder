import { useMemo } from "react";

/**
 * ExperimentCharts — CSS-based bar charts for experiment metric visualization.
 *
 * Renders:
 *   - Per-variant totals bar chart (impressions, clicks, conversions, revenue)
 *   - Rate comparison bars (CTR, conversion rate)
 */

const VARIANT_COLORS = {
  A: "var(--color-primary)",
  B: "#8B5CF6",
  C: "#F49D37",
  D: "#EC4899",
};

function variantColor(variant) {
  return VARIANT_COLORS[variant] || "var(--color-text-muted)";
}

function formatNumber(n) {
  if (n == null) return "0";
  return Number(n).toLocaleString();
}

function formatPercent(n) {
  if (n == null) return "0.00%";
  return `${(Number(n) * 100).toFixed(2)}%`;
}

function formatCurrency(n) {
  if (n == null) return "$0";
  return Number(n).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

function BarGroup({ label, variants, getValue, formatValue, maxOverride }) {
  const max = maxOverride ?? Math.max(...variants.map((v) => getValue(v) || 0), 1);
  return (
    <div className="exp-chart-group">
      <div className="exp-chart-group-label">{label}</div>
      {variants.map((v) => {
        const val = getValue(v) || 0;
        const pct = Math.min((val / max) * 100, 100);
        return (
          <div key={v.variant} className="exp-chart-bar-row">
            <span className="exp-chart-bar-variant" style={{ color: variantColor(v.variant) }}>
              {v.variant}
            </span>
            <div className="exp-chart-bar-track">
              <div
                className="exp-chart-bar-fill"
                style={{ width: `${pct}%`, background: variantColor(v.variant) }}
              />
            </div>
            <span className="exp-chart-bar-value">{formatValue(val)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ExperimentCharts({ metrics, report }) {
  // Build per-variant aggregated data from metrics
  const variantData = useMemo(() => {
    if (!metrics || metrics.length === 0) return [];
    const byVariant = {};
    for (const m of metrics) {
      const v = m.variant || "A";
      if (!byVariant[v]) {
        byVariant[v] = { variant: v, impressions: 0, clicks: 0, conversions: 0, revenue: 0 };
      }
      byVariant[v].impressions += Number(m.impressions || 0);
      byVariant[v].clicks += Number(m.clicks || 0);
      byVariant[v].conversions += Number(m.conversions || 0);
      byVariant[v].revenue += Number(m.revenue || 0);
    }
    return Object.values(byVariant).sort((a, b) => a.variant.localeCompare(b.variant));
  }, [metrics]);

  // Compute rates
  const rateData = useMemo(() => {
    return variantData.map((v) => ({
      ...v,
      ctr: v.impressions > 0 ? v.clicks / v.impressions : 0,
      conversionRate: v.clicks > 0 ? v.conversions / v.clicks : 0,
    }));
  }, [variantData]);

  // If report has variant_results, merge them
  const reportVariants = useMemo(() => {
    if (!report?.variant_results) return null;
    return Object.entries(report.variant_results).map(([key, val]) => ({
      variant: key,
      ...val,
    })).sort((a, b) => a.variant.localeCompare(b.variant));
  }, [report]);

  const displayVariants = reportVariants || rateData;

  if (displayVariants.length === 0) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
        <p style={{ color: "var(--color-text-muted)" }}>No metrics data to chart yet.</p>
      </div>
    );
  }

  return (
    <div className="exp-charts">
      <div className="card">
        <h3 style={{ marginBottom: "1rem" }}>📊 Performance Comparison</h3>

        <div className="exp-charts-grid">
          <BarGroup
            label="Impressions"
            variants={displayVariants}
            getValue={(v) => v.impressions || v.total_impressions}
            formatValue={formatNumber}
          />
          <BarGroup
            label="Clicks"
            variants={displayVariants}
            getValue={(v) => v.clicks || v.total_clicks}
            formatValue={formatNumber}
          />
          <BarGroup
            label="Conversions"
            variants={displayVariants}
            getValue={(v) => v.conversions || v.total_conversions}
            formatValue={formatNumber}
          />
          <BarGroup
            label="Revenue"
            variants={displayVariants}
            getValue={(v) => v.revenue || v.total_revenue}
            formatValue={formatCurrency}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: "0.75rem" }}>
        <h3 style={{ marginBottom: "1rem" }}>📈 Rate Comparison</h3>
        <div className="exp-charts-grid">
          <BarGroup
            label="Click-Through Rate"
            variants={displayVariants}
            getValue={(v) => v.ctr ?? v.click_through_rate ?? 0}
            formatValue={formatPercent}
            maxOverride={1}
          />
          <BarGroup
            label="Conversion Rate"
            variants={displayVariants}
            getValue={(v) => v.conversionRate ?? v.conversion_rate ?? 0}
            formatValue={formatPercent}
            maxOverride={1}
          />
        </div>
      </div>
    </div>
  );
}
