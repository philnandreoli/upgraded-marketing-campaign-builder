import { useState } from "react";
import { submitContentApproval, updatePieceNotes, updatePieceDecision, generateImageAsset } from "../api";
import { useConfirm } from "../ConfirmDialogContext";
import { useToast } from "../ToastContext";
import { useNotifications } from "../NotificationContext";
import ImageAssetCard from "./ImageAssetCard";

const PLATFORM_LABELS = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  linkedin: "LinkedIn",
};

const CONTENT_TYPE_LABELS = {
  headline_cta: "Headline & CTA",
  headline: "Headline",
  cta: "CTA",
  social_post: "Social Post",
  ad_copy: "Ad Copy",
  tagline: "Tagline",
  body_copy: "Body Copy",
  email_subject: "Email Subject",
  email_body: "Email Body",
};

// Stable no-op used as onChange for readOnly textareas to satisfy React's
// controlled-component contract without recreating a function on every render.
const noop = () => {};

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
  workspaceId,
  onApprovalSubmitted,
  status,
  imageAssets = [],
  imageGenerationEnabled = false,
  isViewer = false,
  onImageGenerated,
  onViewGallery,
  onOpenComments,
  unresolvedCount = 0,
  onOpenPieceComments,
  pieceCommentCounts = {},
}) {
  const confirm = useConfirm();
  const { addToast } = useToast();
  const { addEvent } = useNotifications();
  const [editing, setEditing] = useState({});      // { [index]: editedText }
  const [notes, setNotes] = useState({});           // { [index]: noteText }
  const [decisions, setDecisions] = useState({});   // { [index]: "approved" | "rejected" }
  const [submitting, setSubmitting] = useState(false);
  const [savingNotes, setSavingNotes] = useState({});    // { [index]: boolean }
  const [savingDecision, setSavingDecision] = useState({}); // { [index]: boolean }
  const [generatingImages, setGeneratingImages] = useState({}); // { [index]: boolean }
  const [imageErrors, setImageErrors] = useState({});           // { [index]: string | null }

  const visiblePieces = data?.pieces?.filter(
    (piece) => typeof piece?.content === "string" && piece.content.trim().length > 0
  ) || [];

  const setEdit = (idx, text) => setEditing((prev) => ({ ...prev, [idx]: text }));
  const setNote = (idx, text) => setNotes((prev) => ({ ...prev, [idx]: text }));

  const pendingPieces = visiblePieces.filter((piece, i) => {
    const effApproved = piece.approval_status === "approved" || decisions[i] === "approved";
    const effRejected = piece.approval_status === "rejected" || decisions[i] === "rejected";
    return !effApproved && !effRejected;
  });
  const allDecided = visiblePieces.length > 0 && pendingPieces.length === 0;

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
      await submitContentApproval(workspaceId, campaignId, pieces);
      onApprovalSubmitted?.();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to submit content approval: " + err.message });
    } finally {
      setSubmitting(false);
    }
  };

  const handleRejectCampaign = async () => {
    const confirmed = await confirm({
      title: "Reject entire campaign?",
      message: "Are you sure you want to reject the entire campaign?",
      confirmLabel: "Reject Campaign",
      destructive: true,
    });
    if (!confirmed) return;
    setSubmitting(true);
    try {
      await submitContentApproval(workspaceId, campaignId, [], true);
      onApprovalSubmitted?.();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to reject campaign: " + err.message });
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveNotes = async (pieceIndex) => {
    setSavingNotes((prev) => ({ ...prev, [pieceIndex]: true }));
    try {
      await updatePieceNotes(workspaceId, campaignId, pieceIndex, notes[pieceIndex] || "");
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to save notes: " + err.message });
    } finally {
      setSavingNotes((prev) => ({ ...prev, [pieceIndex]: false }));
    }
  };

  const handleDecision = async (pieceIndex, approved) => {
    setSavingDecision((prev) => ({ ...prev, [pieceIndex]: true }));
    try {
      const editedContent = editing[pieceIndex] !== undefined ? editing[pieceIndex] : null;
      await updatePieceDecision(workspaceId, campaignId, pieceIndex, {
        approved,
        editedContent,
        notes: notes[pieceIndex] || "",
      });
      // Mirror the persisted decision in local state so the UI updates immediately
      setDecisions((prev) => ({ ...prev, [pieceIndex]: approved ? "approved" : "rejected" }));
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to save decision: " + err.message });
    } finally {
      setSavingDecision((prev) => ({ ...prev, [pieceIndex]: false }));
    }
  };

  const handleGenerateImage = async (pieceIndex) => {
    setGeneratingImages((prev) => ({ ...prev, [pieceIndex]: true }));
    setImageErrors((prev) => ({ ...prev, [pieceIndex]: null }));
    try {
      await generateImageAsset(workspaceId, campaignId, pieceIndex);
      onImageGenerated?.();
      addToast({ type: "success", stage: "Image Generated", message: `Image for content piece ${pieceIndex + 1} generated successfully.` });
      addEvent({
        type: "image_generated",
        stage: "image_generation",
        message: `Image for content piece ${pieceIndex + 1} generated successfully.`,
        campaign_id: campaignId,
        workspace_id: workspaceId,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      const detail = err.body?.detail ?? err.detail ?? err.message;
      const status = err.status ?? "unknown";
      console.error(`[ImageGeneration] Failed for piece ${pieceIndex}: HTTP ${status} — ${detail}`, err.body ?? err);
      setImageErrors((prev) => ({ ...prev, [pieceIndex]: `HTTP ${status}: ${detail}` }));
    } finally {
      setGeneratingImages((prev) => ({ ...prev, [pieceIndex]: false }));
    }
  };

  const contentCommentButton = onOpenComments ? (
    <button
      className="section-comment-btn"
      onClick={onOpenComments}
      aria-label="Open content comments"
      title="Comments on content"
    >
      💬
      {unresolvedCount > 0 && (
        <span className="section-comment-count" data-testid="content-comment-count">{unresolvedCount}</span>
      )}
    </button>
  ) : null;

  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <div className="section-header-row">
          <h2>✍️ Content</h2>
          {contentCommentButton}
        </div>
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
        <div className="section-header-row">
          <h2>✍️ Content</h2>
          {contentCommentButton}
        </div>
        <div className="loading"><span className="spinner" /> Generating content…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="section-header-row">
        <h2>✍️ {isApprovalMode ? "Content Approval" : "Content"}</h2>
        {contentCommentButton}
      </div>

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

            // Build email subject→body pairings so they render as one combined card.
            // Match by channel + variant; each subject pairs with the nearest following body.
            const emailBodyConsumed = new Set();
            const emailPairMap = {}; // subjectIndex → bodyIndex
            visiblePieces.forEach((piece, i) => {
              if (piece.content_type !== "email_subject") return;
              for (let j = i + 1; j < visiblePieces.length; j++) {
                if (emailBodyConsumed.has(j)) continue;
                const candidate = visiblePieces[j];
                if (
                  candidate.content_type === "email_body" &&
                  candidate.channel === piece.channel &&
                  (candidate.variant || "A") === (piece.variant || "A")
                ) {
                  emailPairMap[i] = j;
                  emailBodyConsumed.add(j);
                  break;
                }
              }
            });

            return visiblePieces.map((piece, i) => {
              // Skip email_body pieces that are rendered inside a combined card
              if (emailBodyConsumed.has(i)) return null;
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

              // ── Combined Email Subject + Body card ──
              const pairedBodyIndex = emailPairMap[i];
              if (pairedBodyIndex !== undefined) {
                const bodyPiece = visiblePieces[pairedBodyIndex];
                const bodyApprovalStatus = bodyPiece.approval_status || "pending";
                const bodyIsPending = bodyApprovalStatus === "pending";
                const bodyIsAlreadyApproved = bodyApprovalStatus === "approved";
                const bodyIsAlreadyRejected = bodyApprovalStatus === "rejected";
                const bodyCurrentDecision = decisions[pairedBodyIndex];
                const bodyEffectiveApproved = bodyIsAlreadyApproved || bodyCurrentDecision === "approved";
                const bodyEffectiveRejected = bodyIsAlreadyRejected || bodyCurrentDecision === "rejected";

                // Combined card is approved only when both are approved
                const combinedApproved = effectiveApproved && bodyEffectiveApproved;
                const combinedRejected = effectiveRejected || bodyEffectiveRejected;
                const combinedPending = !combinedApproved && !combinedRejected;
                const combinedBorderColor = combinedApproved
                  ? "var(--color-success)"
                  : combinedRejected
                    ? "var(--color-danger)"
                    : "var(--color-border)";

                const handleCombinedDecision = async (approved) => {
                  // Fire decisions for both subject and body
                  await Promise.all([
                    handleDecision(i, approved),
                    handleDecision(pairedBodyIndex, approved),
                  ]);
                };
                const combinedSaving = savingDecision[i] || savingDecision[pairedBodyIndex];
                const combinedDecision = currentDecision || bodyCurrentDecision;
                const combinedIsPending = isPending && bodyIsPending;

                return (
                  <div
                    key={i}
                    className="content-piece content-piece-email-combined"
                    style={isApprovalMode ? { borderColor: combinedBorderColor, borderWidth: "2px" } : {}}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div className="piece-type">
                        📧 Email
                        {piece.variant && piece.variant !== "A" && (
                          <span style={{ marginLeft: "0.4rem", opacity: 0.7 }}>
                            (Variant {piece.variant})
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        {isApprovalMode && (
                          <span className={`badge badge-${combinedApproved ? "approved" : combinedRejected ? "rejected" : "pending"}`}>
                            {combinedApproved ? "🔒 Approved" : combinedRejected ? "❌ Rejected" : "⏳ Pending"}
                          </span>
                        )}
                        {onOpenPieceComments && (
                          <button
                            className="piece-comment-btn"
                            onClick={() => onOpenPieceComments(i)}
                            aria-label={`Open comments for content piece ${i + 1}`}
                            title={`Comments on piece ${i + 1}`}
                            data-testid={`piece-comment-btn-${i}`}
                          >
                            💬
                            {((pieceCommentCounts[i] ?? 0) + (pieceCommentCounts[pairedBodyIndex] ?? 0)) > 0 && (
                              <span className="piece-comment-count" data-testid={`piece-comment-count-${i}`}>
                                {(pieceCommentCounts[i] ?? 0) + (pieceCommentCounts[pairedBodyIndex] ?? 0)}
                              </span>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                    {piece.channel && <div className="piece-channel">📢 {piece.channel}</div>}

                    {/* Subject field */}
                    <div className="email-combined-field">
                      <label className="email-combined-label">Subject</label>
                      {isApprovalMode ? (
                        <input
                          type="text"
                          className={`email-combined-subject-input${(!isPending || effectiveApproved) ? " piece-edit-textarea-locked" : ""}`}
                          value={editing[i] !== undefined ? editing[i] : (piece.human_edited_content || piece.content)}
                          onChange={isPending && !effectiveApproved ? (e) => setEdit(i, e.target.value) : noop}
                          readOnly={!isPending || effectiveApproved}
                        />
                      ) : (
                        <div className="email-combined-subject-display">{piece.human_edited_content || piece.content}</div>
                      )}
                    </div>

                    {/* Body field */}
                    <div className="email-combined-field">
                      <label className="email-combined-label">Body</label>
                      {isApprovalMode ? (
                        <textarea
                          className={`piece-edit-textarea${(!bodyIsPending || bodyEffectiveApproved) ? " piece-edit-textarea-locked" : ""}`}
                          value={editing[pairedBodyIndex] !== undefined ? editing[pairedBodyIndex] : (bodyPiece.human_edited_content || bodyPiece.content)}
                          onChange={bodyIsPending && !bodyEffectiveApproved ? (e) => setEdit(pairedBodyIndex, e.target.value) : noop}
                          readOnly={!bodyIsPending || bodyEffectiveApproved}
                        />
                      ) : (
                        <div className="piece-body">{bodyPiece.human_edited_content || bodyPiece.content}</div>
                      )}
                    </div>

                    {/* Notes from either piece */}
                    {(piece.notes || bodyPiece.notes) && (
                      <p style={{ fontSize: "0.75rem", color: "var(--color-text-dim)", marginTop: "0.5rem" }}>
                        💡 {piece.notes || bodyPiece.notes}
                      </p>
                    )}

                    {/* Post-approval notes */}
                    {isApprovalMode && (isAlreadyApproved && bodyIsAlreadyApproved) ? (
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
                      (piece.human_notes || bodyPiece.human_notes) && (
                        <p style={{ fontSize: "0.75rem", color: "var(--color-warning)", marginTop: "0.25rem" }}>
                          📝 Reviewer: {piece.human_notes || bodyPiece.human_notes}
                        </p>
                      )
                    )}

                    {/* Combined approval buttons */}
                    {isApprovalMode && combinedIsPending && (
                      <div style={{ marginTop: "0.75rem" }}>
                        <div style={{ marginBottom: "0.5rem" }}>
                          <input
                            type="text"
                            placeholder="Notes (optional)…"
                            value={notes[i] || ""}
                            onChange={(e) => {
                              setNote(i, e.target.value);
                              setNote(pairedBodyIndex, e.target.value);
                            }}
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
                            className={`btn btn-sm ${combinedDecision === "approved" ? "btn-success" : "btn-outline"}`}
                            disabled={combinedSaving}
                            onClick={() => handleCombinedDecision(true)}
                          >
                            {combinedSaving ? "Saving…" : "✅ Approve"}
                          </button>
                          <button
                            className={`btn btn-sm ${combinedDecision === "rejected" ? "btn-danger" : "btn-outline"}`}
                            disabled={combinedSaving}
                            onClick={() => handleCombinedDecision(false)}
                          >
                            {combinedSaving ? "Saving…" : "❌ Reject"}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Image generation — use body piece's image_brief */}
                    {imageGenerationEnabled && (() => {
                      const imgIdx = pairedBodyIndex;
                      const imgPiece = bodyPiece;
                      const pieceImages = imageAssets.filter((a) => a.content_piece_index === imgIdx);
                      const hasPieceImage = pieceImages.length > 0;
                      const latestImage = hasPieceImage ? pieceImages[pieceImages.length - 1] : null;
                      return (
                        <div style={{ marginTop: "0.75rem" }}>
                          {imgPiece.image_brief && (
                            <details style={{ marginBottom: "0.5rem", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
                              <summary style={{ cursor: "pointer" }}>🎨 Image Brief</summary>
                              <p style={{ marginTop: "0.25rem", paddingLeft: "0.75rem" }}>
                                {imgPiece.image_brief?.prompt || (typeof imgPiece.image_brief === "string" ? imgPiece.image_brief : null)}
                              </p>
                            </details>
                          )}
                          {hasPieceImage ? (
                            <div className="piece-image-preview" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                              <ImageAssetCard
                                asset={latestImage}
                                workspaceId={workspaceId}
                                campaignId={campaignId}
                                canEdit={!isViewer && !(imgPiece.approval_status === "approved" && status === "approved")}
                                compact
                                onRegenerated={onImageGenerated}
                              />
                              {onViewGallery && (
                                <button
                                  className="btn btn-sm btn-outline"
                                  onClick={onViewGallery}
                                  style={{ alignSelf: "flex-start" }}
                                >
                                  🖼️ View in Gallery
                                </button>
                              )}
                            </div>
                          ) : imgPiece.image_brief ? (
                            <button
                              className="btn btn-sm btn-outline"
                              disabled={isViewer || !!generatingImages[imgIdx] || (imgPiece.approval_status === "approved" && status === "approved")}
                              onClick={() => handleGenerateImage(imgIdx)}
                              aria-label={generatingImages[imgIdx] ? `Generating image for piece ${imgIdx + 1}` : `Generate image for piece ${imgIdx + 1}`}
                            >
                              {generatingImages[imgIdx] ? (
                                <><span className="spinner" aria-hidden="true" /> Generating…</>
                              ) : (
                                <>🖼️ Generate Image</>
                              )}
                            </button>
                          ) : null}
                          {imageErrors[imgIdx] && (
                            <p style={{ fontSize: "0.75rem", color: "var(--color-danger)", marginTop: "0.25rem" }}>
                              ⚠️ {imageErrors[imgIdx]}
                            </p>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                );
              }
              // ── End combined email card ──

              return (
                <div
                  key={i}
                  className="content-piece"
                  style={isApprovalMode ? { borderColor, borderWidth: "2px" } : {}}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="piece-type">
                      {CONTENT_TYPE_LABELS[piece.content_type] || piece.content_type}
                      {piece.variant && piece.variant !== "A" && (
                        <span style={{ marginLeft: "0.4rem", opacity: 0.7 }}>
                          (Variant {piece.variant})
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      {isApprovalMode && (
                        <span className={`badge badge-${effectiveApproved ? "approved" : effectiveRejected ? "rejected" : "pending"}`}>
                          {effectiveApproved ? "🔒 Approved" : effectiveRejected ? "❌ Rejected" : "⏳ Pending"}
                        </span>
                      )}
                      {onOpenPieceComments && (
                        <button
                          className="piece-comment-btn"
                          onClick={() => onOpenPieceComments(i)}
                          aria-label={`Open comments for content piece ${i + 1}`}
                          title={`Comments on piece ${i + 1}`}
                          data-testid={`piece-comment-btn-${i}`}
                        >
                          💬
                          {(pieceCommentCounts[i] ?? 0) > 0 && (
                            <span className="piece-comment-count" data-testid={`piece-comment-count-${i}`}>
                              {pieceCommentCounts[i]}
                            </span>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                  {piece.channel && <div className="piece-channel">📢 {piece.channel}</div>}
                  {isSocialPost && socialPlatformLabel && (
                    <div className="piece-platform">📱 Platform: {socialPlatformLabel}</div>
                  )}

                  {/* Content body: editable textarea for pending pieces, readOnly textarea
                      when approved (locally or server-confirmed) so content stays
                      clearly visible while locked, plain div outside approval mode. */}
                  {isApprovalMode ? (
                    <textarea
                      className={`piece-edit-textarea${(!isPending || effectiveApproved) ? " piece-edit-textarea-locked" : ""}`}
                      value={editing[i] !== undefined ? editing[i] : (piece.human_edited_content || piece.content)}
                      onChange={isPending && !effectiveApproved ? (e) => setEdit(i, e.target.value) : noop}
                      readOnly={!isPending || effectiveApproved}
                    />
                  ) : piece.content_type === "headline_cta" ? (
                    (() => {
                      const displayContent = piece.human_edited_content || piece.content;
                      const parts = displayContent.split("\n---\n");
                      const headlinePart = parts[0] || "";
                      const ctaPart = parts[1] || "";
                      return (
                        <div className="piece-body piece-body-headline-cta">
                          <div className="headline-cta-headline">{headlinePart}</div>
                          {ctaPart && (
                            <>
                              <div className="headline-cta-divider" />
                              <div className="headline-cta-cta">{ctaPart}</div>
                            </>
                          )}
                        </div>
                      );
                    })()
                  ) : (
                    <div className="piece-body">
                      {piece.human_edited_content || piece.content}
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
                          disabled={savingDecision[i]}
                          onClick={() => handleDecision(i, true)}
                        >
                          {savingDecision[i] ? "Saving…" : "✅ Approve"}
                        </button>
                        <button
                          className={`btn btn-sm ${currentDecision === "rejected" ? "btn-danger" : "btn-outline"}`}
                          disabled={savingDecision[i]}
                          onClick={() => handleDecision(i, false)}
                        >
                          {savingDecision[i] ? "Saving…" : "❌ Reject"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Image generation controls — only when feature is enabled for this campaign */}
                  {imageGenerationEnabled && (() => {
                    const pieceImages = imageAssets.filter((a) => a.content_piece_index === i);
                    const hasPieceImage = pieceImages.length > 0;
                    const latestImage = hasPieceImage ? pieceImages[pieceImages.length - 1] : null;
                    return (
                      <div style={{ marginTop: "0.75rem" }}>
                        {piece.image_brief && (
                          <details style={{ marginBottom: "0.5rem", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
                            <summary style={{ cursor: "pointer" }}>🎨 Image Brief</summary>
                            <p style={{ marginTop: "0.25rem", paddingLeft: "0.75rem" }}>
                              {piece.image_brief?.prompt || (typeof piece.image_brief === "string" ? piece.image_brief : null)}
                            </p>
                          </details>
                        )}
                        {hasPieceImage ? (
                          <div className="piece-image-preview" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            <ImageAssetCard
                              asset={latestImage}
                              workspaceId={workspaceId}
                              campaignId={campaignId}
                              canEdit={!isViewer && !(piece.approval_status === "approved" && status === "approved")}
                              compact
                              onRegenerated={onImageGenerated}
                            />
                            {onViewGallery && (
                              <button
                                className="btn btn-sm btn-outline"
                                onClick={onViewGallery}
                                style={{ alignSelf: "flex-start" }}
                              >
                                🖼️ View in Gallery
                              </button>
                            )}
                          </div>
                        ) : piece.image_brief ? (
                          <button
                            className="btn btn-sm btn-outline"
                            disabled={isViewer || !!generatingImages[i] || (piece.approval_status === "approved" && status === "approved")}
                            onClick={() => handleGenerateImage(i)}
                            aria-label={generatingImages[i] ? `Generating image for piece ${i + 1}` : `Generate image for piece ${i + 1}`}
                          >
                            {generatingImages[i] ? (
                              <><span className="spinner" aria-hidden="true" /> Generating…</>
                            ) : (
                              <>🖼️ Generate Image</>
                            )}
                          </button>
                        ) : null}
                        {imageErrors[i] && (
                          <p style={{ fontSize: "0.75rem", color: "var(--color-danger)", marginTop: "0.25rem" }}>
                            ⚠️ {imageErrors[i]}
                          </p>
                        )}
                      </div>
                    );
                  })()}
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
