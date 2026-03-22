import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { getCampaign } from "../api";
import useWebSocket from "../hooks/useWebSocket";
import usePolling from "../hooks/usePolling";
import StrategySection from "../components/StrategySection.jsx";
import ContentSection from "../components/ContentSection.jsx";
import ChannelPlanSection from "../components/ChannelPlanSection.jsx";
import AnalyticsSection from "../components/AnalyticsSection.jsx";
import ReviewSection from "../components/ReviewSection.jsx";
import ClarificationSection from "../components/ClarificationSection.jsx";
import ImageGallerySection from "../components/ImageGallerySection.jsx";
import TeamMembersSection, { TeamMembersCompact } from "../components/TeamMembersSection.jsx";
import ProgressIndicator from "../components/ProgressIndicator.jsx";
import Toast from "../components/Toast.jsx";
import WorkspaceBadge from "../components/WorkspaceBadge.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useUser } from "../UserContext";
import { SkeletonCard } from "../components/Skeleton.jsx";

const TERMINAL_STATES = ["approved", "rejected", "manual_review_required"];
const PAUSE_STATES = ["clarification", "content_approval"];  // pipeline paused but will resume

// Pipeline stages in order — each maps to a tab key and campaign data field
const PIPELINE_STAGES = [
  { key: "clarify",           label: "Clarify",       statusKey: "clarification",          dataField: "clarification_questions" },
  { key: "strategy",          label: "Strategy",      statusKey: "strategy",               dataField: "strategy" },
  { key: "content",           label: "Content",       statusKey: "content",                dataField: "content" },
  { key: "channel_plan",      label: "Channels",      statusKey: "channel_planning",       dataField: "channel_plan" },
  { key: "analytics",         label: "Analytics",     statusKey: "analytics_setup",        dataField: "analytics_plan" },
  { key: "review",            label: "Review",        statusKey: "review",                 dataField: "review" },
  { key: "content_revision",  label: "Revision",      statusKey: "content_revision",       dataField: "content" },
  { key: "content_approval",  label: "Approval",      statusKey: "content_approval",       dataField: null },
];

const STATUS_ORDER = ["draft", ...PIPELINE_STAGES.map((s) => s.statusKey)];

const VIEW_MODE_KEY = "campaign_detail_view_mode";

function formatBudget(amount, currency) {
  return amount.toLocaleString(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 0,
  });
}

function getTabIcon(state, isPipelineRunning) {
  if (state === "completed") return "✓";
  if (state === "active") return isPipelineRunning ? "●" : "○";
  if (state === "error") return "✕";
  return "○"; // pending
}

export default function CampaignDetail() {
  const { workspaceId, id } = useParams();
  // For backward compat with old /campaign/:id route: derive workspaceId from loaded campaign
  const [campaign, setCampaign] = useState(null);
  const [error, setError] = useState(null);
  const [userTab, setUserTab] = useState(null);
  const [viewMode, setViewMode] = useState(
    () => localStorage.getItem(VIEW_MODE_KEY) || "focus"
  );
  const [badgePulse, setBadgePulse] = useState(false);
  const { events, connected, connectionFailed } = useWebSocket(id);
  const { isViewer, isAdmin, user, imageGenerationAvailable } = useUser();
  const prevStatusRef = useRef(null);

  // canManage: admins always can; campaign owners can too
  const canManage = isAdmin || (campaign?.owner_id != null && user?.id === campaign.owner_id);

  // Effective workspace ID: from URL params if present, else from loaded campaign
  const effectiveWorkspaceId = workspaceId || campaign?.workspace_id;

  const handleViewMode = (mode) => {
    setViewMode(mode);
    localStorage.setItem(VIEW_MODE_KEY, mode);
  };
  const isFetchingRef = useRef(false);

  const load = useCallback(async () => {
    if (!workspaceId || isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      setCampaign(await getCampaign(workspaceId, id));
    } catch (err) {
      setError(err.message);
    } finally {
      isFetchingRef.current = false;
    }
  }, [id, workspaceId]);

  // Set up visibility-aware polling; stops entirely for terminal states.
  const status = campaign?.status;
  const isTerminal = status && TERMINAL_STATES.includes(status);

  useEffect(() => {
    if (isTerminal) return;
    const immediate = setTimeout(load, 0);
    return () => clearTimeout(immediate);
  }, [load, isTerminal]);

  usePolling(load, isTerminal ? null : 15000);

  // Refresh on WebSocket events (deferred to avoid synchronous setState).
  // Skip if campaign is already in a terminal state.
  useEffect(() => {
    if (events.length === 0) return;
    if (status && TERMINAL_STATES.includes(status)) return;
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [events.length, load, status]);

  // Pulse the status badge whenever the campaign status changes
  useEffect(() => {
    if (!status) return;
    if (prevStatusRef.current !== null && prevStatusRef.current !== status) {
      prevStatusRef.current = status;
      const tOn = setTimeout(() => setBadgePulse(true), 0);
      const tOff = setTimeout(() => setBadgePulse(false), 400);
      return () => { clearTimeout(tOn); clearTimeout(tOff); };
    }
    prevStatusRef.current = status;
  }, [status]);

  // Derive stage states: completed / active / pending / error for each pipeline stage
  const stageStates = useMemo(() => {
    if (!campaign) return {};
    const cs = campaign.status;
    const isTerminal = TERMINAL_STATES.includes(cs);
    const currentIdx = STATUS_ORDER.indexOf(cs);
    const errors = campaign.stage_errors || {};
    const states = {};
    PIPELINE_STAGES.forEach((stage) => {
      const stageIdx = STATUS_ORDER.indexOf(stage.statusKey);
      const hasData = stage.dataField
        ? Array.isArray(campaign[stage.dataField])
          ? campaign[stage.dataField].length > 0
          : !!campaign[stage.dataField]
        : false;
      const hasError = stage.dataField ? !!errors[stage.dataField] : false;
      if (hasError && !hasData) {
        states[stage.key] = "error";
      } else if (isTerminal) {
        states[stage.key] = "completed";
      } else if (stageIdx < currentIdx || hasData) {
        states[stage.key] = "completed";
      } else if (stageIdx === currentIdx) {
        states[stage.key] = "active";
      } else {
        states[stage.key] = "pending";
      }
    });
    return states;
  }, [campaign]);

  // Is the pipeline actively running (not paused, not terminal)?
  const isPipelineRunning = useMemo(() => {
    if (!campaign) return false;
    const cs = campaign.status;
    return !TERMINAL_STATES.includes(cs) && !PAUSE_STATES.includes(cs);
  }, [campaign]);

  // Compute overall progress from stage states
  const { completedCount, totalCount } = useMemo(() => {
    const entries = Object.values(stageStates);
    return {
      completedCount: entries.filter((s) => s === "completed").length,
      totalCount: entries.length,
    };
  }, [stageStates]);

  // At approval stage, hide content & revision tabs (approval tab shows the content)
  const isAtApproval = campaign?.status === "content_approval" || campaign?.status === "approved" || campaign?.status === "rejected" || campaign?.status === "manual_review_required";
  const HIDDEN_AT_APPROVAL = ["content", "content_revision"];

  // Whether the Images tab should be shown
  const showImagesTab = imageGenerationAvailable && campaign?.brief?.generate_images === true;

  // Clickable tabs: completed stages + the currently active stage
  const clickableTabs = useMemo(() => {
    const t = [];
    if (campaign) {
      for (const stage of PIPELINE_STAGES) {
        // Hide content & revision tabs once we reach approval
        if (isAtApproval && HIDDEN_AT_APPROVAL.includes(stage.key)) continue;
        const state = stageStates[stage.key];
        if (state === "completed" || state === "active" || state === "error") {
          // content_approval stage is only clickable when content_approval and has content data
          if (stage.key === "content_approval") {
            if (campaign.status === "content_approval" || campaign.status === "approved" || campaign.status === "rejected" || campaign.status === "manual_review_required") {
              t.push(stage.key);
            }
          // content_revision tab only visible when content_revision_count > 0 or currently in revision
          } else if (stage.key === "content_revision") {
            if (campaign.content_revision_count > 0 || campaign.status === "content_revision") {
              t.push(stage.key);
            }
          } else {
            t.push(stage.key);
          }
        }
      }
      // Images tab is always clickable when shown
      if (showImagesTab) {
        t.push("images");
      }
    }
    return t;
  }, [campaign, stageStates, isAtApproval, showImagesTab]);

  // Derive the active tab: honour explicit user click, otherwise show the latest pipeline tab
  const activeTab = useMemo(() => {
    if (clickableTabs.length === 0) return null;
    if (userTab && clickableTabs.includes(userTab)) return userTab;
    // Auto-select the last pipeline tab
    return clickableTabs[clickableTabs.length - 1];
  }, [clickableTabs, userTab]);

  if (error) {
    return <div className="card" style={{ color: "var(--color-danger)" }}>Error: {error}</div>;
  }

  if (!campaign) {
    return (
      <div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const manualReviewBanner = campaign.status === "manual_review_required" ? (
    <div className="manual-review-banner">
      <span>⚠️</span>
      <span>This campaign requires <strong>manual review</strong> before it can proceed. Please escalate to an administrator.</span>
    </div>
  ) : null;

  const renderTabContent = () => {
    const errors = campaign.stage_errors || {};
    switch (activeTab) {
      case "clarify":
        return (
          <ClarificationSection
            questions={campaign.clarification_questions}
            savedAnswers={campaign.clarification_answers}
            campaignId={campaign.id}
            workspaceId={effectiveWorkspaceId}
            status={campaign.status}
            onSubmitted={load}
            readOnly={isViewer}
          />
        );
      case "strategy":
        return <StrategySection data={campaign.strategy} error={errors.strategy} />;
      case "content":
        return (
          <ContentSection
            data={campaign.content}
            error={errors.content}
            socialPlatforms={campaign.brief?.social_media_platforms || []}
            status={campaign.status}
          />
        );
      case "channel_plan":
        return <ChannelPlanSection data={campaign.channel_plan} error={errors.channel_plan} />;
      case "analytics":
        return <AnalyticsSection data={campaign.analytics_plan} error={errors.analytics_plan} />;
      case "review":
        return (
          <ReviewSection
            data={campaign.review}
            campaignId={campaign.id}
            status={campaign.status}
            error={errors.review}
          />
        );
      case "content_revision":
        return (
          <ContentSection
            data={campaign.content}
            error={errors.content_revision}
            socialPlatforms={campaign.brief?.social_media_platforms || []}
            status={campaign.status}
          />
        );
      case "content_approval":
        return (
          <ContentSection
            data={campaign.content}
            error={errors.content}
            socialPlatforms={campaign.brief?.social_media_platforms || []}
            isApprovalMode={!isViewer}
            campaignId={campaign.id}
            workspaceId={effectiveWorkspaceId}
            onApprovalSubmitted={load}
            status={campaign.status}
          />
        );
      case "images":
        return (
          <ImageGallerySection
            workspaceId={effectiveWorkspaceId}
            campaignId={campaign.id}
            events={events}
          />
        );
      default:
        return (
          <div className="card empty-state">
            <p>Waiting for pipeline to generate results…</p>
          </div>
        );
    }
  };

  const renderPipelineTabs = () => (
    <div className="pipeline-tabs">
      {PIPELINE_STAGES.filter((stage) => !(isAtApproval && HIDDEN_AT_APPROVAL.includes(stage.key))).map((stage) => {
        const state = stageStates[stage.key] || "pending";
        const isClickable = clickableTabs.includes(stage.key);
        return (
          <button
            key={stage.key}
            className={`pipeline-tab ${state}${activeTab === stage.key ? " selected" : ""}${state === "active" && isPipelineRunning ? " running" : ""}`}
            disabled={!isClickable}
            onClick={() => isClickable && setUserTab(stage.key)}
          >
            <span className="pipeline-tab-icon" aria-hidden="true">{getTabIcon(state, isPipelineRunning)}</span>
            {stage.label}
          </button>
        );
      })}
      {showImagesTab && (
        <button
          className={`pipeline-tab completed${activeTab === "images" ? " selected" : ""}`}
          onClick={() => setUserTab("images")}
        >
          <span className="pipeline-tab-icon" aria-hidden="true">🖼️</span>
          Images
        </button>
      )}
    </div>
  );

  return (
    <div>
      <Toast events={events} />
      <nav className="breadcrumb">
        <Link to="/">Dashboard</Link>
        {campaign?.workspace && (
          <>
            <span className="breadcrumb-divider">/</span>
            <Link to={`/workspaces/${campaign.workspace.id}`}>{campaign.workspace.name}</Link>
          </>
        )}
        <span className="breadcrumb-divider">/</span>
        <span>{campaign?.brief?.product_or_service}</span>
      </nav>

      {/* Campaign banner */}
      <div className={`campaign-banner campaign-banner--${campaign.status}`} data-status={campaign.status}>
        <div className="campaign-banner-main">
          <h1 className="campaign-banner-title">{campaign.brief.product_or_service}</h1>
          <p className="campaign-banner-goal">{campaign.brief.goal}</p>
          {viewMode !== "split" && (
            <div className="campaign-banner-meta">
              {campaign.brief.budget != null && (
                <span className="campaign-banner-meta-item">
                  💰 {formatBudget(campaign.brief.budget, campaign.brief.currency)}
                </span>
              )}
              {campaign.brief.start_date && campaign.brief.end_date && (
                <span className="campaign-banner-meta-item">
                  📅 {campaign.brief.start_date} → {campaign.brief.end_date}
                </span>
              )}
              {campaign.brief.selected_channels?.length > 0 && (
                <span className="campaign-banner-meta-item">
                  📡 {campaign.brief.selected_channels.length} channel{campaign.brief.selected_channels.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="campaign-banner-side">
          <span className={`ws-badge${connected ? " ws-badge--live" : connectionFailed ? " ws-badge--failed" : " ws-badge--reconnecting"}`}>
            <span className="ws-badge-dot" aria-hidden="true" />
            {connected ? "Live" : connectionFailed ? "Disconnected" : "Reconnecting…"}
          </span>
          <StatusBadge status={campaign.status} pulse={badgePulse} />
          {totalCount > 0 && (
            <ProgressIndicator completedCount={completedCount} totalCount={totalCount} />
          )}
          {isViewer && (
            <span className="badge" style={{ background: "rgba(148,163,184,0.2)", color: "var(--color-text-muted)", fontSize: "0.75rem" }}>
              👁 Read-only
            </span>
          )}
          <div className="view-toggle" role="group" aria-label="Layout view">
            <button
              className={`view-toggle-btn${viewMode === "focus" ? " active" : ""}`}
              onClick={() => handleViewMode("focus")}
              title="Focus view — single column, active stage front and center"
            >
              Focus
            </button>
            <button
              className={`view-toggle-btn${viewMode === "split" ? " active" : ""}`}
              onClick={() => handleViewMode("split")}
              title="Split view — two-column layout with persistent sidebar"
            >
              Split
            </button>
          </div>
        </div>
      </div>

      {viewMode === "focus" && <TeamMembersSection campaignId={id} workspaceId={effectiveWorkspaceId} canManage={canManage} />}

      {viewMode === "split" ? (
        <div className="detail-split-layout">
          {/* Main column */}
          <div className="detail-split-main">
            {isPipelineRunning && (
              <div className="pipeline-running-banner">
                <span className="spinner" />
                <span>Pipeline is running — {campaign.status === "draft" ? "starting up…" : <><strong>{PIPELINE_STAGES.find(s => s.statusKey === campaign.status)?.label || campaign.status}</strong> in progress…</>}</span>
              </div>
            )}
            {manualReviewBanner}
            <div key={activeTab} className="detail-tab-content">{renderTabContent()}</div>
          </div>

          {/* Sticky sidebar */}
          <aside className="detail-split-sidebar">
            {/* Campaign metadata */}
            <div className="card sidebar-meta">
              <h3 style={{ marginBottom: "0.5rem" }}>Campaign</h3>
              <div className="sidebar-meta-details">
                {campaign.brief.budget != null && (
                  <p className="sidebar-meta-item">
                    <span className="sidebar-meta-label">💰 Budget</span>
                    <span className="sidebar-meta-value">{formatBudget(campaign.brief.budget, campaign.brief.currency)}</span>
                  </p>
                )}
                {campaign.brief.start_date && campaign.brief.end_date && (
                  <p className="sidebar-meta-item">
                    <span className="sidebar-meta-label">📅 Dates</span>
                    <span className="sidebar-meta-value">{campaign.brief.start_date} → {campaign.brief.end_date}</span>
                  </p>
                )}
                {campaign.brief.additional_context && (
                  <p className="sidebar-meta-item sidebar-meta-item--context">
                    <span className="sidebar-meta-label">📝 Context</span>
                    <span className="sidebar-meta-value">{campaign.brief.additional_context}</span>
                  </p>
                )}
              </div>
              {campaign.brief.selected_channels?.length > 0 && (
                <div className="sidebar-meta-channels">
                  {campaign.brief.selected_channels.map((ch) => (
                    <span
                      key={ch}
                      className="badge"
                      style={{ background: "rgba(99,102,241,0.15)", color: "var(--color-primary-hover)", fontSize: "0.68rem" }}
                    >
                      {ch.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Pipeline progress overview */}
            <div className="card sidebar-pipeline">
              <h3 style={{ marginBottom: "0.6rem" }}>Pipeline Progress</h3>
              <div className="sidebar-stages">
                {PIPELINE_STAGES.filter((stage) => !(isAtApproval && HIDDEN_AT_APPROVAL.includes(stage.key))).map((stage) => {
                  const state = stageStates[stage.key] || "pending";
                  const isClickable = clickableTabs.includes(stage.key);
                  return (
                    <button
                      key={stage.key}
                      className={`sidebar-stage sidebar-stage-${state}${activeTab === stage.key ? " sidebar-stage-selected" : ""}${isClickable ? " sidebar-stage-clickable" : ""}`}
                      disabled={!isClickable}
                      onClick={() => setUserTab(stage.key)}
                    >
                      <span className="sidebar-stage-dot" />
                      <span className="sidebar-stage-label">{stage.label}</span>
                    </button>
                  );
                })}
                {showImagesTab && (
                  <button
                    className={`sidebar-stage sidebar-stage-completed${activeTab === "images" ? " sidebar-stage-selected" : ""} sidebar-stage-clickable`}
                    onClick={() => setUserTab("images")}
                  >
                    <span className="sidebar-stage-dot" />
                    <span className="sidebar-stage-label">Images</span>
                  </button>
                )}
              </div>
            </div>

            {/* Team members (compact) */}
            <TeamMembersCompact workspaceId={effectiveWorkspaceId} campaignId={id} canManage={canManage} />
          </aside>
        </div>
      ) : (
        <>
          {/* Pipeline running banner */}
          {isPipelineRunning && (
            <div className="pipeline-running-banner">
              <span className="spinner" />
              <span>Pipeline is running — {campaign.status === "draft" ? "starting up…" : <><strong>{PIPELINE_STAGES.find(s => s.statusKey === campaign.status)?.label || campaign.status}</strong> in progress…</>}</span>
            </div>
          )}
          {manualReviewBanner}
          {renderPipelineTabs()}
          <div key={activeTab} className="detail-tab-content">{renderTabContent()}</div>
        </>
      )}
    </div>
  );
}
