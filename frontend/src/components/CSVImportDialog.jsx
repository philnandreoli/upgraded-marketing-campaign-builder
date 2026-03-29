import { useState, useRef } from "react";
import { importMetrics } from "../api";
import { useToast } from "../ToastContext";

/**
 * CSVImportDialog — modal dialog for importing metrics via CSV data.
 *
 * Supports pasting CSV text or uploading a .csv file.
 * Shows a preview of the first few rows before submission.
 */

export default function CSVImportDialog({ isOpen, onClose, workspaceId, campaignId, experimentId, onImported }) {
  const { addToast } = useToast();
  const [csvData, setCsvData] = useState("");
  const [preview, setPreview] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const parsePreview = (text) => {
    const lines = text.trim().split("\n").slice(0, 6); // header + 5 rows
    return lines.map((line) => line.split(",").map((c) => c.trim()));
  };

  const handleTextChange = (e) => {
    const val = e.target.value;
    setCsvData(val);
    setPreview(parsePreview(val));
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result || "";
      setCsvData(text);
      setPreview(parsePreview(text));
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    if (!csvData.trim()) {
      addToast({ type: "warning", stage: "Validation", message: "Please enter or upload CSV data." });
      return;
    }
    setSubmitting(true);
    try {
      await importMetrics(workspaceId, campaignId, experimentId, csvData);
      addToast({ type: "success", stage: "Import Complete", message: "CSV metrics imported successfully." });
      setCsvData("");
      setPreview([]);
      if (onImported) onImported();
      onClose();
    } catch (err) {
      addToast({ type: "error", stage: "Import Failed", message: err.message || "Failed to import CSV data." });
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setCsvData("");
    setPreview([]);
    onClose();
  };

  return (
    <div className="exp-dialog-overlay" onClick={handleClose}>
      <div className="exp-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Import CSV Metrics">
        <div className="exp-dialog-header">
          <h3>📥 Import CSV Metrics</h3>
          <button type="button" className="exp-dialog-close" onClick={handleClose} aria-label="Close dialog">✕</button>
        </div>

        <div className="exp-dialog-body">
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.82rem", marginBottom: "0.75rem" }}>
            Paste CSV data below or upload a .csv file. Expected columns: variant, impressions, clicks, conversions, revenue
          </p>

          {/* File upload */}
          <div style={{ marginBottom: "0.75rem" }}>
            <button
              type="button"
              className="btn btn-outline"
              style={{ fontSize: "0.8rem" }}
              onClick={() => fileInputRef.current?.click()}
            >
              📁 Choose File
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
          </div>

          {/* Textarea */}
          <textarea
            className="exp-csv-textarea"
            rows={8}
            placeholder={"variant,impressions,clicks,conversions,revenue\nA,1000,50,10,500\nB,1000,65,15,750"}
            value={csvData}
            onChange={handleTextChange}
          />

          {/* Preview */}
          {preview.length > 0 && (
            <div className="exp-csv-preview">
              <h4 style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginBottom: "0.5rem" }}>Preview</h4>
              <table className="exp-stats-table" style={{ fontSize: "0.75rem" }}>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} style={i === 0 ? { fontWeight: 600, color: "var(--color-text-muted)" } : {}}>
                      {row.map((cell, j) => (
                        <td key={j} style={{ padding: "0.25rem 0.5rem" }}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {preview.length >= 6 && (
                <p style={{ fontSize: "0.72rem", color: "var(--color-text-dim)", marginTop: "0.25rem" }}>
                  Showing first 5 data rows…
                </p>
              )}
            </div>
          )}
        </div>

        <div className="exp-dialog-footer">
          <button type="button" className="btn btn-outline" onClick={handleClose} disabled={submitting}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={submitting || !csvData.trim()}>
            {submitting ? "Importing…" : "Import Data"}
          </button>
        </div>
      </div>
    </div>
  );
}
