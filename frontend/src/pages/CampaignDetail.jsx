import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { getCampaign } from "../api";
import useWebSocket from "../hooks/useWebSocket";
import StrategySection from "../components/StrategySection.jsx";
import ContentSection from "../components/ContentSection.jsx";
import ChannelPlanSection from "../components/ChannelPlanSection.jsx";
import AnalyticsSection from "../components/AnalyticsSection.jsx";
import ReviewSection from "../components/ReviewSection.jsx";
import ClarificationSection from "../components/ClarificationSection.jsx";
import EventLog from "../components/EventLog.jsx";
import TeamMembersSection, { TeamMembersCompact } from "../components/TeamMembersSection.jsx";
import { useUser } from "../UserContext";

const TERMINAL_STATES = ["approved", "rejected", "content_approval"];
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

export default function CampaignDetail() {
  const { id } = useParams();
  const [campaign, setCampaign] = useState(null);
  const [error, setError] = useState(null);
  const [userTab, setUserTab] = useState(null);
  const [viewMode, setViewMode] = useState(
    () => localStorage.getItem(VIEW_MODE_KEY) || "focus"
  );
  const { events } = useWebSocket(id);
  const { isViewer, isAdmin, user } = useUser();

  // canManage: admins always can; campaign owners can too
  const canManage = isAdmin || (campaign?.owner_id != null && user?.id === campaign.owner_id);

  const handleViewMode = (mode) => {
    setViewMode(mode);
    localStorage.setItem(VIEW_MODE_KEY, mode);
  };
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      setCampaign(await getCampaign(id));
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  // Set up polling; defer initial fetch so setState isn't synchronous in the effect
  useEffect(() => {
    const immediate = setTimeout(load, 0);
    pollRef.current = setInterval(load, 3000);
    return () => {
      clearTimeout(immediate);
      clearInterval(pollRef.current);
    };
  }, [load]);

  // Refresh on WebSocket events (deferred to avoid synchronous setState)
  useEffect(() => {
    if (events.length === 0) return;
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [events.length, load]);

  // Stop polling once campaign reaches a terminal state
  const status = campaign?.status;
  useEffect(() => {
    if (status && TERMINAL_STATES.includes(status)) {
      clearInterval(pollRef.current);
    }
  }, [status]);

  // Derive stage states: completed / active / pending / error for each pipeline stage
  const stageStates = useMemo(() => {
    if (!campaign) return {};
    const cs = campaign.status;
    const isTerminal = cs === "approved" || cs === "rejected";
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
    return cs !== "approved" && cs !== "rejected" && !PAUSE_STATES.includes(cs);
  }, [campaign]);

  // At approval stage, hide content & revision tabs (approval tab shows the content)
  const isAtApproval = campaign?.status === "content_approval" || campaign?.status === "approved" || campaign?.status === "rejected";
  const HIDDEN_AT_APPROVAL = ["content", "content_revision"];

  // Clickable tabs: completed stages + the currently active stage + event log
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
            if (campaign.status === "content_approval" || campaign.status === "approved" || campaign.status === "rejected") {
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
      t.push("events");
    }
    return t;
  }, [campaign, stageStates, isAtApproval]);

  // Derive the active tab: honour explicit user click, otherwise show the latest pipeline tab
  const activeTab = useMemo(() => {
    if (clickableTabs.length === 0) return null;
    if (userTab && clickableTabs.includes(userTab)) return userTab;
    // Auto-select the last data tab (skip "events" if there's a pipeline tab)
    return clickableTabs.length > 1
      ? clickableTabs[clickableTabs.length - 2]
      : clickableTabs[0];
  }, [clickableTabs, userTab]);

  if (error) {
    return <div className="card" style={{ color: "var(--color-danger)" }}>Error: {error}</div>;
  }

  if (!campaign) {
    return (
      <div className="loading">
        <span className="spinner" /> Loading campaign…
      </div>
    );
  }

  const renderTabContent = () => {
    const errors = campaign.stage_errors || {};
    switch (activeTab) {
      case "clarify":
        return (
          <ClarificationSection
            questions={campaign.clarification_questions}
            savedAnswers={campaign.clarification_answers}
            campaignId={campaign.id}
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
            onApprovalSubmitted={load}
            status={campaign.status}
          />
        );
      case "events":
        return <EventLog events={events} isPipelineRunning={isPipelineRunning} />;
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
            {stage.label}
          </button>
        );
      })}
      <button
        className={`pipeline-tab completed${activeTab === "events" ? " selected" : ""}`}
        onClick={() => setUserTab("events")}
      >
        Event Log
      </button>
    </div>
  );

  return (
    <div>
      <nav className="breadcrumb">
        <Link to="/">Dashboard</Link>
        <span className="breadcrumb-divider">/</span>
        <span>{campaign?.brief?.product_or_service}</span>
      </nav>
      <div className="section-header">
        <div>
          {viewMode === "focus" && (
            <>
              <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
                {campaign.brief.goal}
              </p>
              {campaign.brief.selected_channels?.length > 0 && (
                <div style={{ marginTop: "0.4rem", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                  {campaign.brief.selected_channels.map((ch) => (
                    <span
                      key={ch}
                      className="badge"
                      style={{
                        background: "rgba(99,102,241,0.15)",
                        color: "var(--color-primary-hover)",
                        fontSize: "0.7rem",
                      }}
                    >
                      {ch.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
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

      {viewMode === "focus" && <TeamMembersSection campaignId={id} canManage={canManage} />}

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
            <div className="detail-tab-content">{renderTabContent()}</div>
          </div>

          {/* Sticky sidebar */}
          <aside className="detail-split-sidebar">
            {/* Campaign metadata */}
            <div className="card sidebar-meta">
              <h3 style={{ marginBottom: "0.5rem" }}>Campaign</h3>
              <p className="sidebar-meta-goal">
                {campaign.brief.goal}
              </p>
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
              </div>
            </div>

            {/* Team members (compact) */}
            <TeamMembersCompact campaignId={id} canManage={canManage} />

            {/* Event log */}
            <div className="card sidebar-events">
              <h3 style={{ marginBottom: "0.6rem" }}>Event Log</h3>
              <EventLog events={events} isPipelineRunning={isPipelineRunning} />
            </div>
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
          {renderPipelineTabs()}
          <div className="detail-tab-content">{renderTabContent()}</div>
        </>
      )}
    </div>
  );
}
