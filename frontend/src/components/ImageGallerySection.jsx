import { useEffect, useState, useCallback } from "react";
import { listImageAssets } from "../api";
import ImageAssetCard from "./ImageAssetCard";

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
  // e.g. "1024x1024" → "1024 × 1024"
  return dimensions.replace("x", " × ");
}

function truncatePrompt(prompt, maxLen = 120) {
  if (!prompt) return "";
  return prompt.length > maxLen ? prompt.slice(0, maxLen) + "…" : prompt;
}

export default function ImageGallerySection({ workspaceId, campaignId, events, isViewer = false, status, contentPieces }) {
  const [assets, setAssets] = useState(null);
  const [error, setError] = useState(null);
  const [lightbox, setLightbox] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await listImageAssets(workspaceId, campaignId);
      setAssets(data?.items ?? []);
    } catch (err) {
      setError(err.message);
    }
  }, [workspaceId, campaignId]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  // Refresh when new image-related WebSocket events arrive
  useEffect(() => {
    if (!events || events.length === 0) return;
    const hasImageEvent = events.some(
      (e) => e.type === "image_generated" || e.type === "asset_created"
    );
    if (!hasImageEvent) return;
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [events, load]);

  if (error) {
    return (
      <div className="card stage-error-card">
        <h2>🖼️ Images</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Failed to load images</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (assets === null) {
    return (
      <div className="card">
        <h2>🖼️ Images</h2>
        <div className="loading"><span className="spinner" /> Loading images…</div>
      </div>
    );
  }

  if (assets.length === 0) {
    return (
      <div className="card empty-state">
        <h2>🖼️ Images</h2>
        <p style={{ color: "var(--color-text-muted)", marginTop: "0.5rem" }}>No images generated yet.</p>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
          Use the <strong>Generate Image</strong> button on individual content pieces to create AI-generated images for this campaign.
        </p>
      </div>
    );
  }

  // Group assets by content_piece_index
  const groups = new Map();
  for (const asset of assets) {
    const key = asset.content_piece_index ?? -1;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(asset);
  }
  // Sort groups: numbered pieces first (ascending), then ungrouped (-1) last
  const sortedKeys = [...groups.keys()].sort((a, b) => {
    if (a === -1) return 1;
    if (b === -1) return -1;
    return a - b;
  });

  return (
    <div className="card">
      <h2>🖼️ Images</h2>

      <div className="image-gallery-grid">
        {sortedKeys.flatMap((pieceIndex) => {
          const groupAssets = groups.get(pieceIndex);
          return groupAssets.map((asset) => {
            const pieceApproved = contentPieces?.[asset.content_piece_index]?.approval_status === "approved";
            const locked = pieceApproved && status === "approved";
            const label = pieceIndex >= 0 ? `Piece ${pieceIndex + 1}` : null;
            return (
              <ImageAssetCard
                key={asset.id}
                asset={asset}
                workspaceId={workspaceId}
                campaignId={campaignId}
                canEdit={!isViewer && !locked}
                onOpenLightbox={setLightbox}
                onRegenerated={load}
                pieceLabel={label}
              />
            );
          });
        })}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="image-gallery-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Image preview"
          onClick={() => setLightbox(null)}
        >
          <div className="image-gallery-lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <button
              className="image-gallery-lightbox-close"
              onClick={() => setLightbox(null)}
              aria-label="Close image preview"
            >
              ✕
            </button>
            <img
              src={lightbox.image_url || lightbox.url}
              alt={lightbox.prompt ? truncatePrompt(lightbox.prompt, 80) : "Generated image"}
              className="image-gallery-lightbox-img"
            />
            {lightbox.prompt && (
              <p className="image-gallery-lightbox-prompt">{lightbox.prompt}</p>
            )}
            <div className="image-gallery-lightbox-meta">
              {lightbox.dimensions && (
                <span className="image-gallery-badge">{formatDimensions(lightbox.dimensions)}</span>
              )}
              {lightbox.content_piece_index != null && (
                <span className="image-gallery-badge">Content Piece {lightbox.content_piece_index + 1}</span>
              )}
              {lightbox.created_at && (
                <span className="image-gallery-timestamp">{formatTimestamp(lightbox.created_at)}</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
