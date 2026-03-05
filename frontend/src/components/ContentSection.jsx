import { useState } from "react";
import { submitContentApproval, updatePieceNotes } from "../api";

const PLATFORM_LABELS = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  linkedin: "LinkedIn",
};

function detectSocialPlatform(piece, index, socialPlatforms = [], socialPostIndexMap = []) {
  const normalized = `${piece?.notes || ""} ${piece?.content || ""}`.toLowerCase();

  if (/(^|\W)instagram(\W|$)/.test(normalized)) return "instagram";
  if (/(^|\W)facebook(\W|$)/.test(normalized)) return "facebook";
  if (/(^|\W)linkedin(\W|$)/.test(normalized)) return "linkedin";
  if (/(^|\W)x(\W|$)|twitter|x post/.test(normalized)) return "x";

  const fallbackPlatforms = socialPlatforms.filter((p) => PLATFORM_LABELS[p]);
  if (fallbackPlatforms.length === 0) return "";

  const socialIndex = socialPostIndexMap.indexOf(index);
  if (socialIndex === -1) return "";

  return fallbackPlatforms[socialIndex % fallbackPlatforms.length];
}

export default function ContentSection({
  data,
  error,
  socialPlatforms = [],
  isApprovalMode = false,
  campaignId,
  onApprovalSubmitted,
  status,
}) {
  const [editing, setEditing] = useState({});      // { [index]: editedText }
  const [notes, setNotes] = useState({});           // { [index]: noteText }
  const [decisions, setDecisions] = useState({});   // { [index]: "approved" | "rejected" }
  const [submitting, setSubmitting] = useState(false);
  const [savingNotes, setSavingNotes] = useState({});  // { [index]: boolean }

  const visiblePieces = data?.pieces?.filter(
    (piece) => typeof piece?.content === "string" && piece.content.trim().length > 0
  ) || [];

  const setEdit = (idx, text) => setEditing((prev) => ({ ...prev, [idx]: text }));
  const setNote = (idx, text) => setNotes((prev) => ({ ...prev, [idx]: text }));
  const setDecision = (idx, dec) => setDecisions((prev) => ({ ...prev, [idx]: dec }));

  const pendingPieces = visiblePieces.filter(
    (p) => !p.approval_status || p.approval_status === "pending"
  );
  const allDecided = pendingPieces.length > 0 && pendingPieces.every((_, i) => {
    const realIdx = visiblePieces.indexOf(pendingPieces[i]);
    return decisions[realIdx] === "approved" || decisions[realIdx] === "rejected";
  });

  const handleSubmitApprovals = async () => {
    setSubmitting(true);
    try {
      const pieces = visiblePieces.map((piece, i) => {
        // Already approved pieces stay approved
        if (piece.approval_status === "approved") {
          return { piece_index: i, approved: true, edited_content: null, notes: "" };
        }
        const isApproved = decisions[i] === "approved";
        const editedContent = editing[i] !== undefined ? editing[i] : null;
        return {
          piece_index: i,
          approved: isApproved,
          edited_content: editedContent,
          notes: notes[i] || "",
        };
      });
      await submitContentApproval(campaignId, pieces);
      onApprovalSubmitted?.();
    } catch (err) {
      alert("Failed to submit content approval: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRejectCampaign = async () => {
    if (!confirm("Are you sure you want to reject the entire campaign?")) return;
    setSubmitting(true);
    try {
      await submitContentApproval(campaignId, [], true);
      onApprovalSubmitted?.();
    } catch (err) {
      alert("Failed to reject campaign: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveNotes = async (pieceIndex) => {
    setSavingNotes((prev) => ({ ...prev, [pieceIndex]: true }));
    try {
      await updatePieceNotes(campaignId, pieceIndex, notes[pieceIndex] || "");
    } catch (err) {
      alert("Failed to save notes: " + err.message);
    } finally {
      setSavingNotes((prev) => ({ ...prev, [pieceIndex]: false }));
    }
  };

  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <h2>✍️ Content</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Content generation failed</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <h2>✍️ Content</h2>
        <div className="loading"><span className="spinner" /> Generating content…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>✍️ {isApprovalMode ? "Content Approval" : "Content"}</h2>

      {isApprovalMode && (
        <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: "1rem" }}>
          Review each content piece below. You can edit the text, then approve or reject each piece individually.
          Rejected pieces will be revised by AI and presented again.
        </p>
      )}

      {data.theme && (
        <p style={{ fontSize: "0.9rem", marginBottom: "0.5rem" }}>
          <strong>Theme:</strong> {data.theme}
        </p>
      )}
      {data.tone_of_voice && (
        <p style={{ fontSize: "0.9rem", marginBottom: "1rem" }}>
          <strong>Tone:</strong> {data.tone_of_voice}
        </p>
      )}

      {visiblePieces.length > 0 && (
        <div className="content-grid">
          {(() => {
            const socialPostIndexMap = visiblePieces
              .map((piece, idx) => ({ piece, idx }))
              .filter(({ piece }) => piece.content_type === "social_post")
              .map(({ idx }) => idx);

            return visiblePieces.map((piece, i) => {
              const isSocialPost = piece.content_type === "social_post";
              const socialPlatformKey = isSocialPost
                ? detectSocialPlatform(piece, i, socialPlatforms, socialPostIndexMap)
                : "";
              const socialPlatformLabel = socialPlatformKey
                ? PLATFORM_LABELS[socialPlatformKey] || socialPlatformKey
                : "";

              const approvalStatus = piece.approval_status || "pending";
              const isPending = approvalStatus === "pending";
              const isAlreadyApproved = approvalStatus === "approved";
              const isAlreadyRejected = approvalStatus === "rejected";
              const currentDecision = decisions[i];

              // Reflect local staging decisions in visual state even before final submit
              const effectiveApproved = isAlreadyApproved || currentDecision === "approved";
              const effectiveRejected = isAlreadyRejected || currentDecision === "rejected";

              const borderColor = effectiveApproved
                ? "var(--color-success)"
                : effectiveRejected
                  ? "var(--color-danger)"
                  : "var(--color-border)";

              return (
                <div
                  key={i}
                  className="content-piece"
                  style={isApprovalMode ? { borderColor, borderWidth: "2px" } : {}}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="piece-type">
                      {piece.content_type}
                      {piece.variant && piece.variant !== "A" && (
                        <span style={{ marginLeft: "0.4rem", opacity: 0.7 }}>
                          (Variant {piece.variant})
                        </span>
                      )}
                    </div>
                    {isApprovalMode && (
                      <span className={`badge badge-${effectiveApproved ? "approved" : effectiveRejected ? "rejected" : "pending"}`}>
                        {effectiveApproved ? "🔒 Approved" : effectiveRejected ? "❌ Rejected" : "⏳ Pending"}
                      </span>
                    )}
                  </div>
                  {piece.channel && <div className="piece-channel">📢 {piece.channel}</div>}
                  {isSocialPost && socialPlatformLabel && (
                    <div className="piece-platform">📱 Platform: {socialPlatformLabel}</div>
                  )}

                  {/* Show editable textarea in approval mode for pending pieces not yet locally approved */}
                  {isApprovalMode && isPending && !effectiveApproved ? (
                    <textarea
                      className="piece-edit-textarea"
                      value={editing[i] !== undefined ? editing[i] : (piece.human_edited_content || piece.content)}
                      onChange={(e) => setEdit(i, e.target.value)}
                    />
                  ) : (
                    <div className="piece-body">
                      {editing[i] !== undefined ? editing[i] : (piece.human_edited_content || piece.content)}
                    </div>
                  )}

                  {piece.notes && (
                    <p style={{ fontSize: "0.75rem", color: "var(--color-text-dim)", marginTop: "0.5rem" }}>
                      💡 {piece.notes}
                    </p>
                  )}

                  {/* For approved pieces: show editable notes field wired to PATCH endpoint */}
                  {isApprovalMode && isAlreadyApproved ? (
                    <div style={{ marginTop: "0.75rem" }}>
                      <div style={{ marginBottom: "0.25rem", fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                        📝 Reviewer notes
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        <input
                          type="text"
                          placeholder="Add post-approval notes…"
                          value={notes[i] !== undefined ? notes[i] : (piece.human_notes || "")}
                          onChange={(e) => setNote(i, e.target.value)}
                          style={{
                            flex: 1,
                            padding: "0.3rem 0.5rem",
                            fontSize: "0.8rem",
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius)",
                            background: "var(--color-bg)",
                            color: "var(--color-text)",
                          }}
                        />
                        <button
                          className="btn btn-sm btn-outline"
                          disabled={savingNotes[i]}
                          onClick={() => handleSaveNotes(i)}
                        >
                          {savingNotes[i] ? "Saving…" : "Save"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    piece.human_notes && (
                      <p style={{ fontSize: "0.75rem", color: "var(--color-warning)", marginTop: "0.25rem" }}>
                        📝 Reviewer: {piece.human_notes}
                      </p>
                    )
                  )}

                  {/* Per-piece approval buttons */}
                  {isApprovalMode && isPending && (
                    <div style={{ marginTop: "0.75rem" }}>
                      <div style={{ marginBottom: "0.5rem" }}>
                        <input
                          type="text"
                          placeholder="Notes (optional)…"
                          value={notes[i] || ""}
                          onChange={(e) => setNote(i, e.target.value)}
                          style={{
                            width: "100%",
                            padding: "0.3rem 0.5rem",
                            fontSize: "0.8rem",
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius)",
                            background: "var(--color-bg)",
                            color: "var(--color-text)",
                          }}
                        />
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          className={`btn btn-sm ${currentDecision === "approved" ? "btn-success" : "btn-outline"}`}
                          onClick={() => setDecision(i, "approved")}
                        >
                          ✅ Approve
                        </button>
                        <button
                          className={`btn btn-sm ${currentDecision === "rejected" ? "btn-danger" : "btn-outline"}`}
                          onClick={() => setDecision(i, "rejected")}
                        >
                          ❌ Reject
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            });
          })()}
        </div>
      )}

      {/* Submit bar for approval mode */}
      {isApprovalMode && status === "content_approval" && (
        <div style={{
          marginTop: "1.5rem",
          padding: "1rem",
          background: "var(--color-surface-2)",
          borderRadius: "var(--radius)",
          border: "1px solid var(--color-border)",
        }}>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              className="btn btn-success"
              disabled={submitting || !allDecided}
              onClick={handleSubmitApprovals}
            >
              {submitting ? "Submitting…" : "Submit Decisions"}
            </button>
            <button
              className="btn btn-danger"
              disabled={submitting}
              onClick={handleRejectCampaign}
            >
              {submitting ? "Submitting…" : "❌ Reject Entire Campaign"}
            </button>
          </div>
          {!allDecided && pendingPieces.length > 0 && (
            <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginTop: "0.5rem" }}>
              Please approve or reject all pending pieces before submitting.
            </p>
          )}
        </div>
      )}

      {/* Show final approved state */}
      {status === "approved" && (
        <div style={{
          marginTop: "1rem",
          padding: "1rem",
          background: "rgba(34,197,94,0.1)",
          borderRadius: "var(--radius)",
          border: "1px solid var(--color-success)",
          textAlign: "center",
          fontWeight: 600,
          color: "var(--color-success)",
        }}>
          ✅ All Content Approved — Campaign Complete
        </div>
      )}

      {status === "rejected" && (
        <div style={{
          marginTop: "1rem",
          padding: "1rem",
          background: "rgba(239,68,68,0.1)",
          borderRadius: "var(--radius)",
          border: "1px solid var(--color-danger)",
          textAlign: "center",
          fontWeight: 600,
          color: "var(--color-danger)",
        }}>
          ❌ Campaign Rejected
        </div>
      )}
    </div>
  );
}
