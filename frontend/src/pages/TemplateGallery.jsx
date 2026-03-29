import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listTemplates, ApiError } from "../api";
import { SkeletonCard } from "../components/Skeleton";
import CloneDialog from "../components/CloneDialog";
import TemplatePreviewModal from "../components/TemplatePreviewModal";

const PAGE_SIZE = 20;

const CATEGORY_OPTIONS = [
  { value: "", label: "All Categories" },
  { value: "Product Launch", label: "Product Launch" },
  { value: "Seasonal Promo", label: "Seasonal Promo" },
  { value: "Event", label: "Event" },
  { value: "Awareness", label: "Awareness" },
  { value: "Lead Generation", label: "Lead Generation" },
  { value: "Retention", label: "Retention" },
];

const VISIBILITY_OPTIONS = [
  { value: "", label: "All Visibility" },
  { value: "workspace", label: "Workspace" },
  { value: "organization", label: "Organization" },
];

/**
 * Truncate a string to ~maxLen chars, ending at a word boundary.
 */
function truncate(str, maxLen = 100) {
  if (!str || str.length <= maxLen) return str || "";
  const truncated = str.slice(0, maxLen);
  const lastSpace = truncated.lastIndexOf(" ");
  return (lastSpace > maxLen * 0.6 ? truncated.slice(0, lastSpace) : truncated) + "…";
}

/**
 * TemplateGallery — browsable template library with search, filters & preview.
 */
export default function TemplateGallery() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const offsetRef = useRef(0);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceRef = useRef(null);
  const [category, setCategory] = useState("");
  const [visibility, setVisibility] = useState("");
  const [featuredOnly, setFeaturedOnly] = useState(false);

  // Modal state
  const [previewTemplateId, setPreviewTemplateId] = useState(null);
  const [previewTemplateName, setPreviewTemplateName] = useState("");
  const [cloneTarget, setCloneTarget] = useState(null);

  // Debounce search input
  const handleSearchChange = (value) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(value);
    }, 300);
  };

  const handleSearchClear = () => {
    setSearchQuery("");
    setDebouncedSearch("");
    if (debounceRef.current) clearTimeout(debounceRef.current);
  };

  // Cleanup debounce timer
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const fetchTemplates = useCallback(
    async (offset = 0, append = false) => {
      if (!append) setLoading(true);
      else setLoadingMore(true);

      setError(null);

      try {
        const params = {
          limit: PAGE_SIZE,
          offset,
        };
        if (category) params.category = category;
        if (visibility) params.visibility = visibility;
        if (featuredOnly) params.featured = true;
        if (debouncedSearch) params.search = debouncedSearch;

        const res = await listTemplates(params);
        const items = res.items ?? res.templates ?? res ?? [];
        const pagination = res.pagination;

        if (append) {
          setTemplates((prev) => [...prev, ...items]);
        } else {
          setTemplates(items);
        }

        if (pagination) {
          setHasMore(pagination.has_more ?? false);
          offsetRef.current =
            (pagination.offset ?? offset) +
            (pagination.returned_count ?? items.length);
        } else {
          setHasMore(items.length >= PAGE_SIZE);
          offsetRef.current = offset + items.length;
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message || "Failed to load templates.");
        } else {
          setError("Network error — please check your connection and try again.");
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [category, visibility, featuredOnly, debouncedSearch]
  );

  // Re-fetch on filter changes
  useEffect(() => {
    offsetRef.current = 0;
    fetchTemplates(0, false);
  }, [fetchTemplates]);

  const handleLoadMore = () => {
    fetchTemplates(offsetRef.current, true);
  };

  // Separate featured templates for hero section
  const { featuredTemplates, regularTemplates } = useMemo(() => {
    const featured = [];
    const regular = [];
    for (const t of templates) {
      if (t.featured) {
        featured.push(t);
      } else {
        regular.push(t);
      }
    }
    return { featuredTemplates: featured, regularTemplates: regular };
  }, [templates]);

  const openPreview = (template) => {
    setPreviewTemplateId(template.id);
    setPreviewTemplateName(template.name || "");
  };

  const closePreview = () => {
    setPreviewTemplateId(null);
    setPreviewTemplateName("");
  };

  const openCloneFromCard = (template) => {
    // Build a campaign-like object for CloneDialog
    setCloneTarget({
      id: template.source_campaign_id || template.id,
      workspace_id: template.workspace_id,
      product_or_service: template.name,
      is_template: true,
      template_parameters: template.parameters || template.template_parameters || [],
    });
  };

  const openCloneFromPreview = (previewData) => {
    closePreview();
    setCloneTarget({
      id: previewData.source_campaign_id || previewData.id,
      workspace_id: previewData.workspace_id,
      product_or_service: previewData.name,
      is_template: true,
      template_parameters:
        previewData.template_parameters || previewData.parameters || [],
    });
  };

  const closeCloneDialog = () => {
    setCloneTarget(null);
  };

  // Render card
  const renderTemplateCard = (template, isFeatured = false) => (
    <div
      key={template.id}
      className={`card template-card${isFeatured ? " template-card--featured" : ""}`}
    >
      <div className="template-card-header">
        <h3 className="template-card-name">{template.name}</h3>
        {isFeatured && (
          <span className="template-card-featured-badge">⭐ Featured</span>
        )}
      </div>

      {template.category && (
        <span className="badge badge-strategy template-card-category">
          {template.category}
        </span>
      )}

      {template.tags && template.tags.length > 0 && (
        <div className="template-card-tags">
          {template.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="template-tag-chip">
              {tag}
            </span>
          ))}
          {template.tags.length > 3 && (
            <span className="template-card-tags-more">
              +{template.tags.length - 3}
            </span>
          )}
        </div>
      )}

      {template.description && (
        <p className="template-card-desc">
          {truncate(template.description, 100)}
        </p>
      )}

      <div className="template-card-stats">
        <span className="template-card-stat" title="Times cloned">
          📋 {template.clone_count ?? 0} clones
        </span>
        {template.avg_brand_score != null && (
          <span className="template-card-stat" title="Average brand score">
            🎯 {Number(template.avg_brand_score).toFixed(1)}
          </span>
        )}
      </div>

      <div className="template-card-actions">
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => openPreview(template)}
        >
          Preview
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => openCloneFromCard(template)}
        >
          Use Template
        </button>
      </div>
    </div>
  );

  // --- Main render ---
  let content;

  if (loading && templates.length === 0) {
    content = (
      <div className="template-gallery-grid" role="status" aria-label="Loading templates">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  } else if (error) {
    content = (
      <div className="empty-state" role="alert">
        <div className="empty-state-icon">⚠️</div>
        <h2 className="empty-state-title">Something went wrong</h2>
        <p className="empty-state-body">{error}</p>
        <div className="empty-state-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => fetchTemplates(0, false)}
          >
            Retry
          </button>
        </div>
      </div>
    );
  } else if (templates.length === 0) {
    content = (
      <div className="empty-state">
        <div className="empty-state-icon">📄</div>
        <h2 className="empty-state-title">No templates yet</h2>
        <p className="empty-state-body">
          {debouncedSearch
            ? `No templates match "${debouncedSearch}". Try a different search or clear filters.`
            : "Mark an approved campaign as a template to get started."}
        </p>
        {debouncedSearch && (
          <div className="empty-state-actions">
            <button
              type="button"
              className="btn btn-outline"
              onClick={handleSearchClear}
            >
              Clear Search
            </button>
          </div>
        )}
      </div>
    );
  } else {
    content = (
      <>
        {/* Featured section */}
        {featuredTemplates.length > 0 && !featuredOnly && (
          <section aria-label="Featured templates">
            <h2 className="template-gallery-section-title">⭐ Featured</h2>
            <div className="template-gallery-grid">
              {featuredTemplates.map((t) => renderTemplateCard(t, true))}
            </div>
          </section>
        )}

        {/* All templates grid */}
        <section aria-label={featuredOnly ? "Featured templates" : "All templates"}>
          {featuredTemplates.length > 0 && !featuredOnly && (
            <h2 className="template-gallery-section-title">All Templates</h2>
          )}
          <div className="template-gallery-grid">
            {(featuredOnly ? templates : regularTemplates).map((t) =>
              renderTemplateCard(t, featuredOnly && t.featured)
            )}
          </div>
        </section>

        {/* Load More */}
        {hasMore && (
          <div className="template-gallery-load-more">
            <button
              type="button"
              className="btn btn-outline"
              onClick={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Loading…
                </>
              ) : (
                "Load More"
              )}
            </button>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="template-gallery">
      {/* Header */}
      <div className="template-gallery-header">
        <h1>Template Library</h1>
        <div className="search-bar">
          <span className="search-bar__icon" aria-hidden="true">🔍</span>
          <input
            type="search"
            className="search-bar__input"
            placeholder="Search templates..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && searchQuery) handleSearchClear();
            }}
            aria-label="Search templates"
          />
          {searchQuery && (
            <button
              type="button"
              className="search-bar__clear"
              onClick={handleSearchClear}
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div className="template-gallery-filters">
        <div className="form-group template-gallery-filter">
          <label htmlFor="tg-category">Category</label>
          <select
            id="tg-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group template-gallery-filter">
          <label htmlFor="tg-visibility">Visibility</label>
          <select
            id="tg-visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
          >
            {VISIBILITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <label className="template-gallery-featured-toggle">
          <input
            type="checkbox"
            checked={featuredOnly}
            onChange={(e) => setFeaturedOnly(e.target.checked)}
          />
          <span>Featured only</span>
        </label>
      </div>

      {/* Search result count */}
      {!loading && templates.length > 0 && debouncedSearch && (
        <p className="search-result-count">
          Showing {templates.length} template{templates.length !== 1 ? "s" : ""} for &ldquo;{debouncedSearch}&rdquo;
        </p>
      )}

      {content}

      {/* Preview modal */}
      <TemplatePreviewModal
        isOpen={!!previewTemplateId}
        onClose={closePreview}
        templateId={previewTemplateId}
        templateName={previewTemplateName}
        onUseTemplate={openCloneFromPreview}
      />

      {/* Clone dialog */}
      <CloneDialog
        isOpen={!!cloneTarget}
        onClose={closeCloneDialog}
        campaign={cloneTarget}
        sourceWorkspaceId={cloneTarget?.workspace_id}
      />
    </div>
  );
}
