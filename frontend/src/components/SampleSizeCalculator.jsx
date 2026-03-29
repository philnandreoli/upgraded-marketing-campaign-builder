import { useState, useEffect, useRef } from "react";
import { getSampleSizeCalculator } from "../api";

/**
 * SampleSizeCalculator — interactive tool that calls the backend calculator
 * to determine the required sample size for an A/B test.
 *
 * Inputs: baseline conversion rate, MDE, confidence level, power, daily traffic
 * Outputs: required sample per variant, total sample, estimated days
 */

export default function SampleSizeCalculator() {
  const [baselineRate, setBaselineRate] = useState(10);
  const [mde, setMde] = useState(5);
  const [confidenceLevel, setConfidenceLevel] = useState(95);
  const [power, setPower] = useState(80);
  const [dailyTraffic, setDailyTraffic] = useState(1000);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getSampleSizeCalculator({
          baseline_rate: baselineRate / 100,
          mde: mde / 100,
          confidence_level: confidenceLevel / 100,
          power: power / 100,
          daily_traffic: dailyTraffic,
        });
        setResult(data);
      } catch (err) {
        setError(err.message || "Calculator error");
        setResult(null);
      } finally {
        setLoading(false);
      }
    }, 400);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [baselineRate, mde, confidenceLevel, power, dailyTraffic]);

  return (
    <div className="card">
      <h3 style={{ marginBottom: "1rem" }}>🧮 Sample Size Calculator</h3>

      <div className="exp-calc-grid">
        <label className="exp-calc-field">
          <span>Baseline Conversion Rate (%)</span>
          <input
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            value={baselineRate}
            onChange={(e) => setBaselineRate(parseFloat(e.target.value) || 0)}
          />
        </label>
        <label className="exp-calc-field">
          <span>Minimum Detectable Effect (%)</span>
          <input
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            value={mde}
            onChange={(e) => setMde(parseFloat(e.target.value) || 0)}
          />
        </label>
        <label className="exp-calc-field">
          <span>Confidence Level (%)</span>
          <input
            type="number"
            min="80"
            max="99"
            step="1"
            value={confidenceLevel}
            onChange={(e) => setConfidenceLevel(parseInt(e.target.value, 10) || 95)}
          />
        </label>
        <label className="exp-calc-field">
          <span>Statistical Power (%)</span>
          <input
            type="number"
            min="50"
            max="99"
            step="1"
            value={power}
            onChange={(e) => setPower(parseInt(e.target.value, 10) || 80)}
          />
        </label>
        <label className="exp-calc-field">
          <span>Daily Traffic</span>
          <input
            type="number"
            min="1"
            step="100"
            value={dailyTraffic}
            onChange={(e) => setDailyTraffic(parseInt(e.target.value, 10) || 100)}
          />
        </label>
      </div>

      {/* Results */}
      <div className="exp-calc-results" style={{ marginTop: "1.25rem" }}>
        {loading && (
          <div className="loading" style={{ padding: "0.75rem 0" }}>
            <span className="spinner" /> Calculating…
          </div>
        )}
        {error && (
          <p style={{ color: "var(--color-danger)", padding: "0.5rem 0" }}>{error}</p>
        )}
        {!loading && !error && result && (
          <div className="exp-calc-result-cards">
            <div className="exp-calc-result-card">
              <span className="exp-calc-result-label">Sample per Variant</span>
              <span className="exp-calc-result-value">
                {(result.sample_size_per_variant ?? result.sample_per_variant ?? 0).toLocaleString()}
              </span>
            </div>
            <div className="exp-calc-result-card">
              <span className="exp-calc-result-label">Total Sample Needed</span>
              <span className="exp-calc-result-value">
                {(result.total_sample ?? result.total_sample_needed ?? 0).toLocaleString()}
              </span>
            </div>
            <div className="exp-calc-result-card">
              <span className="exp-calc-result-label">Estimated Days</span>
              <span className="exp-calc-result-value">
                {result.estimated_days ?? result.days_to_complete ?? "—"}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
