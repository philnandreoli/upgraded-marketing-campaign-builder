import { useState } from "react";
import { generateImageAsset } from "../api";

function truncatePrompt(prompt, maxLen = 120) {
  if (!prompt) return "";
  return prompt.length > maxLen ? prompt.slice(0, maxLen) + "…" : prompt;
}

function formatTimestamp(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function formatDimensions(dimensions) {
  if (!dimensions) return "";
  return dimensions.replace("x", " × ");
}

async function downloadImage(url, filename) {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objectUrl);
  } catch {
    // Fallback: direct link (may not work across origins, but best-effort)
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

/**
 * ImageAssetCard – renders a single image asset card with download and
 * regenerate actions.
 *
 * Props:
 *   asset         – image asset object (url/image_url, prompt, dimensions, etc.)
 *   workspaceId   – workspace ID for API calls
 *   campaignId    – campaign ID for API calls
 *   canEdit       – whether the current user can regenerate (false for viewers)
 *   compact       – compact mode for inline content-section previews
 *   onOpenLightbox – optional callback(asset) to open a lightbox
 *   onRegenerated – optional callback() called after a successful regeneration
 */
export default function ImageAssetCard({
  asset,
  workspaceId,
  campaignId,
  canEdit = true,
  compact = false,
  onOpenLightbox,
  onRegenerated,
  pieceLabel,
}) {
  const [showModal, setShowModal] = useState(false);
  const [editedPrompt, setEditedPrompt] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState(null);

  const imageUrl = asset.url || asset.image_url;
  const filename = `image-${asset.id || "asset"}.png`;

  const handleDownload = () => downloadImage(imageUrl, filename);

  const openRegenerate = () => {
    setEditedPrompt(asset.prompt || "");
    setRegenError(null);
    setShowModal(true);
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenError(null);
    try {
      await generateImageAsset(
        workspaceId,
        campaignId,
        asset.content_piece_index,
        editedPrompt || null,
      );
      setShowModal(false);
      onRegenerated?.();
    } catch (err) {
      setRegenError(err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const actionBar = (
    <div className="image-asset-card-actions">
      <button
        className="btn btn-sm btn-outline"
        onClick={handleDownload}
        aria-label="Download image"
        title="Download image"
      >
        ⬇ Download
      </button>
      <button
        className="btn btn-sm btn-outline"
        onClick={openRegenerate}
        disabled={!canEdit}
        aria-label="Edit prompt and regenerate"
        title={canEdit ? "Edit prompt and regenerate" : "Viewer role cannot regenerate"}
      >
        🔄 Regenerate
      </button>
    </div>
  );

  const regenerateModal = showModal && (
    <div
      className="image-asset-regen-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Edit prompt and regenerate"
      onClick={(e) => {
        if (e.target === e.currentTarget) setShowModal(false);
      }}
    >
      <div className="image-asset-regen-modal">
        <h3 className="image-asset-regen-title">Edit Prompt &amp; Regenerate</h3>
        <p className="image-asset-regen-hint">
          Edit the prompt below and click <strong>Regenerate</strong> to create a new image. The original image will be kept.
        </p>
        <textarea
          className="image-asset-regen-textarea"
          value={editedPrompt}
          onChange={(e) => setEditedPrompt(e.target.value)}
          rows={4}
          aria-label="Image prompt"
          placeholder="Describe the image you want to generate…"
        />
        {regenError && (
          <p className="image-asset-regen-error">⚠️ {regenError}</p>
        )}
        <div className="image-asset-regen-actions">
          <button
            className="btn btn-outline"
            onClick={() => setShowModal(false)}
            disabled={regenerating}
          >
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleRegenerate}
            disabled={regenerating || !editedPrompt.trim()}
            aria-label={regenerating ? "Regenerating…" : "Regenerate image"}
          >
            {regenerating ? (
              <><span className="spinner" aria-hidden="true" /> Regenerating…</>
            ) : (
              "Regenerate"
            )}
          </button>
        </div>
      </div>
    </div>
  );

  if (compact) {
    const thumb = onOpenLightbox ? (
      <button
        className="image-gallery-thumb-btn"
        onClick={() => onOpenLightbox(asset)}
        aria-label={`View full image: ${asset.prompt ? truncatePrompt(asset.prompt, 60) : "generated image"}`}
        style={{ display: "block", lineHeight: 0 }}
      >
        <img
          src={imageUrl}
          alt={asset.prompt ? truncatePrompt(asset.prompt, 80) : "Generated image"}
          className="image-asset-compact-thumb"
        />
      </button>
    ) : (
      <img
        src={imageUrl}
        alt={asset.prompt ? truncatePrompt(asset.prompt, 80) : "Generated image"}
        className="image-asset-compact-thumb"
      />
    );

    return (
      <div className="image-asset-card image-asset-card--compact">
        {thumb}
        {actionBar}
        {regenerateModal}
      </div>
    );
  }

  return (
    <div className="image-gallery-card">
      <div className="image-gallery-thumb-wrapper">
        {pieceLabel && (
          <span className="image-gallery-piece-label">{pieceLabel}</span>
        )}
        <button
          className="image-gallery-thumb-btn"
          onClick={() => onOpenLightbox?.(asset)}
          aria-label={`View full image: ${asset.prompt ? truncatePrompt(asset.prompt, 60) : "generated image"}`}
        >
          <img
            src={imageUrl}
            alt={asset.prompt ? truncatePrompt(asset.prompt, 80) : "Generated image"}
            className="image-gallery-thumb"
            loading="lazy"
          />
        </button>
      </div>
      <div className="image-gallery-card-meta">
        {asset.prompt && (
          <p className="image-gallery-prompt" title={asset.prompt}>
            {truncatePrompt(asset.prompt)}
          </p>
        )}
        <div className="image-gallery-card-details">
          {asset.dimensions && (
            <span className="image-gallery-badge">{formatDimensions(asset.dimensions)}</span>
          )}
          {asset.created_at && (
            <span className="image-gallery-timestamp">{formatTimestamp(asset.created_at)}</span>
          )}
        </div>
        {actionBar}
      </div>
      {regenerateModal}
    </div>
  );
}
