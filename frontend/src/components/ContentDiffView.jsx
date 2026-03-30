import { useState, useMemo } from "react";

// ---------------------------------------------------------------------------
// Simple word-level diff algorithm (LCS-based)
// ---------------------------------------------------------------------------

/**
 * Compute the Longest Common Subsequence table for two arrays.
 */
function lcsTable(a, b) {
  const m = a.length;
  const n = b.length;
  // Use flat array for efficiency
  const dp = new Uint16Array((m + 1) * (n + 1));
  const cols = n + 1;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i * cols + j] = dp[(i - 1) * cols + (j - 1)] + 1;
      } else {
        dp[i * cols + j] = Math.max(dp[(i - 1) * cols + j], dp[i * cols + (j - 1)]);
      }
    }
  }
  return { dp, cols };
}

/**
 * Back-track the LCS table to produce a diff.
 * Returns array of { type: 'equal'|'add'|'remove', value: string }
 */
function computeDiff(origTokens, revTokens) {
  const { dp, cols } = lcsTable(origTokens, revTokens);
  const result = [];

  let i = origTokens.length;
  let j = revTokens.length;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && origTokens[i - 1] === revTokens[j - 1]) {
      result.push({ type: "equal", value: origTokens[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i * cols + (j - 1)] >= dp[(i - 1) * cols + j])) {
      result.push({ type: "add", value: revTokens[j - 1] });
      j--;
    } else {
      result.push({ type: "remove", value: origTokens[i - 1] });
      i--;
    }
  }

  return result.reverse();
}

/**
 * Split text into tokens, preserving whitespace as separate tokens.
 */
function tokenize(text) {
  return (text || "").split(/(\s+)/).filter((t) => t.length > 0);
}

/**
 * Compute word diff between original and revised text.
 */
function wordDiff(original, revised) {
  const origTokens = tokenize(original);
  const revTokens = tokenize(revised);
  return computeDiff(origTokens, revTokens);
}

// ---------------------------------------------------------------------------
// DiffSegment — renders a single diff token
// ---------------------------------------------------------------------------

function DiffSegment({ segment }) {
  if (segment.type === "equal") {
    return <span className="content-diff-equal">{segment.value}</span>;
  }
  if (segment.type === "add") {
    return <ins className="content-diff-add">{segment.value}</ins>;
  }
  if (segment.type === "remove") {
    return <del className="content-diff-remove">{segment.value}</del>;
  }
  return null;
}

// ---------------------------------------------------------------------------
// ContentDiffView
// ---------------------------------------------------------------------------

export default function ContentDiffView({ original = "", revised = "", mode: initialMode = "side-by-side" }) {
  const [mode, setMode] = useState(initialMode);

  const diff = useMemo(() => wordDiff(original, revised), [original, revised]);

  // For side-by-side view, split into original-only and revised-only segments
  const originalSegments = useMemo(
    () => diff.filter((s) => s.type === "equal" || s.type === "remove"),
    [diff],
  );
  const revisedSegments = useMemo(
    () => diff.filter((s) => s.type === "equal" || s.type === "add"),
    [diff],
  );

  const toggleMode = () => setMode((m) => (m === "side-by-side" ? "inline" : "side-by-side"));

  if (!original && !revised) {
    return null;
  }

  return (
    <div className="content-diff" data-testid="content-diff-view">
      <div className="content-diff-header">
        <span className="content-diff-title">Diff View</span>
        <button
          type="button"
          className="btn btn-sm btn-outline content-diff-toggle"
          onClick={toggleMode}
          aria-label={`Switch to ${mode === "side-by-side" ? "inline" : "side-by-side"} diff`}
        >
          {mode === "side-by-side" ? "Inline" : "Side-by-Side"}
        </button>
      </div>

      {mode === "side-by-side" ? (
        <div className="content-diff-side-by-side" role="group" aria-label="Side-by-side diff">
          <div className="content-diff-pane content-diff-pane--original" aria-label="Original content">
            <div className="content-diff-pane-label">Original</div>
            <div className="content-diff-pane-body">
              {originalSegments.map((seg, idx) => (
                <DiffSegment key={idx} segment={seg} />
              ))}
            </div>
          </div>
          <div className="content-diff-pane content-diff-pane--revised" aria-label="Revised content">
            <div className="content-diff-pane-label">Revised</div>
            <div className="content-diff-pane-body">
              {revisedSegments.map((seg, idx) => (
                <DiffSegment key={idx} segment={seg} />
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="content-diff-inline" role="group" aria-label="Inline diff">
          {diff.map((seg, idx) => (
            <DiffSegment key={idx} segment={seg} />
          ))}
        </div>
      )}
    </div>
  );
}
