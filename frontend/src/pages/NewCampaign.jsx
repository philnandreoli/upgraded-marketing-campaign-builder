import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createCampaign, getCampaign, updateCampaignDraft, launchCampaign, listPersonas, getTemplateRecommendations } from "../api";
import DatePicker from "../components/DatePicker";
import CloneDialog from "../components/CloneDialog";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";

const CHANNEL_OPTIONS = [
  { value: "email", label: "Email", icon: "✉️" },
  { value: "social_media", label: "Social Media", icon: "📱" },
  { value: "paid_ads", label: "Paid Ads", icon: "💰" },
  { value: "content_marketing", label: "Content Marketing", icon: "✍️" },
  { value: "seo", label: "SEO", icon: "🔍" },
  { value: "influencer", label: "Influencer", icon: "🌟" },
  { value: "events", label: "Events", icon: "🎪" },
  { value: "pr", label: "PR", icon: "📰" },
];

const SOCIAL_MEDIA_PLATFORMS = [
  { value: "facebook", label: "Facebook" },
  { value: "instagram", label: "Instagram" },
  { value: "x", label: "X" },
  { value: "linkedin", label: "LinkedIn" },
];

const WIZARD_STEPS = [
  { id: 0, title: "Workspace", shortLabel: "Workspace", optional: false },
  { id: 1, title: "What are you promoting?", shortLabel: "Product", optional: false },
  { id: 2, title: "Budget & Timeline", shortLabel: "Budget", optional: true },
  { id: 3, title: "Pick Your Channels", shortLabel: "Channels", optional: true },
  { id: 4, title: "Anything else?", shortLabel: "Context", optional: true },
  { id: 5, title: "Review & Launch", shortLabel: "Review", optional: false },
];

function WorkspaceDropdown({ value, options, onChange, labelId }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (ref.current && !ref.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const selectedOption = options.find((option) => option.id === value);

  return (
    <div className="custom-select custom-select--full" ref={ref}>
      <button
        type="button"
        id="workspace-select"
        className="custom-select-trigger custom-select-trigger--full"
        onClick={() => setOpen((current) => !current)}
        aria-labelledby={labelId}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span>
          {selectedOption
            ? selectedOption.is_personal
              ? `${selectedOption.name} (Personal)`
              : selectedOption.name
            : "Select a workspace..."}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {open && (
        <ul className="custom-select-menu custom-select-menu--full" role="listbox" aria-labelledby={labelId}>
          {options.map((ws) => {
            const optionLabel = ws.is_personal ? `${ws.name} (Personal)` : ws.name;
            const isSelected = ws.id === value;
            return (
              <li
                key={ws.id}
                role="option"
                aria-selected={isSelected}
                className={`custom-select-option${isSelected ? " selected" : ""}`}
                onClick={() => { onChange(ws.id); setOpen(false); }}
              >
                {optionLabel}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function WizardProgress({ currentStep, hasWorkspaceStep }) {
  // Total visual steps = workspace step (if shown) + content steps (1-4) + review = 5 or 6
  const firstContentStep = hasWorkspaceStep ? 0 : 1;
  const lastStep = 5;
  const adjustedCurrent = currentStep - firstContentStep;
  const adjustedTotal = lastStep - firstContentStep;
  const pct = Math.min(100, Math.round((adjustedCurrent / adjustedTotal) * 100));

  const dots = [];
  for (let i = firstContentStep; i <= lastStep; i++) {
    const step = WIZARD_STEPS.find((s) => s.id === i);
    let dotCls = "wizard-step-dot";
    let labelCls = "wizard-dot-label";
    if (i < currentStep) {
      dotCls += " wizard-step-dot--done";
      labelCls += " wizard-dot-label--done";
    } else if (i === currentStep) {
      dotCls += " wizard-step-dot--active";
      labelCls += " wizard-dot-label--active";
    }
    dots.push(
      <div key={i} className="wizard-dot-group">
        <span className={dotCls} aria-hidden="true" />
        <span className={labelCls}>
          {i < currentStep ? "✓ " : ""}{step?.shortLabel}
        </span>
      </div>
    );
  }

  const stepInfo = WIZARD_STEPS.find((s) => s.id === currentStep);

  return (
    <div className="wizard-progress">
      <div className="wizard-progress-header">
        <span className="wizard-progress-label">{stepInfo?.title}</span>
        <span className="wizard-progress-step-count">
          Step {currentStep - firstContentStep + 1} of {adjustedTotal + 1}
        </span>
      </div>
      <div className="wizard-progress-bar-track">
        <div className="wizard-progress-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="wizard-step-dots">{dots}</div>
    </div>
  );
}

export default function NewCampaign() {
  const navigate = useNavigate();
  const { workspaceId: routeWorkspaceId, campaignId: routeCampaignId } = useParams();
  const [searchParams] = useSearchParams();
  const workspaceLabelId = useId();
  const { isAdmin, imageGenerationAvailable } = useUser();
  const { workspaces, personalWorkspace } = useWorkspace();

  // Wizard step state
  const [currentStep, setCurrentStep] = useState(routeWorkspaceId ? 1 : 0);

  // Form state
  const [form, setForm] = useState({
    product_or_service: "",
    goal: "",
    budget: "",
    currency: "USD",
    start_date: "",
    end_date: "",
    additional_context: "",
  });
  const [selectedChannels, setSelectedChannels] = useState([]);
  const [selectedPlatforms, setSelectedPlatforms] = useState([]);
  const [generateImages, setGenerateImages] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(routeWorkspaceId ?? "");
  const [selectedPersonaIds, setSelectedPersonaIds] = useState([]);
  const [availablePersonas, setAvailablePersonas] = useState([]);

  // Draft state
  const [campaignId, setCampaignId] = useState(routeCampaignId ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [autoSaveState, setAutoSaveState] = useState("idle"); // "idle" | "saving" | "saved"
  const autoSaveTimer = useRef(null);
  const isResuming = !!routeCampaignId;

  // Template recommendation state
  const [recommendations, setRecommendations] = useState([]);
  const [recsLoading, setRecsLoading] = useState(false);
  const [recsOpen, setRecsOpen] = useState(true);
  const [cloneTemplate, setCloneTemplate] = useState(null);
  const recsTimer = useRef(null);

  const creatableWorkspaces = useMemo(
    () => (isAdmin ? workspaces : workspaces.filter((ws) => ws.role === "creator")),
    [isAdmin, workspaces]
  );

  // Pre-select workspace
  useEffect(() => {
    if (routeWorkspaceId) {
      setSelectedWorkspaceId(routeWorkspaceId);
      return;
    }
    if (creatableWorkspaces.length === 0) return;
    const paramId = searchParams.get("workspace");
    if (paramId && creatableWorkspaces.some((ws) => ws.id === paramId)) {
      setSelectedWorkspaceId(paramId);
    } else if (personalWorkspace && creatableWorkspaces.some((ws) => ws.id === personalWorkspace.id)) {
      setSelectedWorkspaceId(personalWorkspace.id);
    } else {
      setSelectedWorkspaceId(creatableWorkspaces[0].id);
    }
  }, [creatableWorkspaces, personalWorkspace, routeWorkspaceId, searchParams]);

  // Load personas for the selected workspace
  useEffect(() => {
    if (!selectedWorkspaceId) {
      setAvailablePersonas([]);
      return;
    }
    listPersonas(selectedWorkspaceId)
      .then((res) => setAvailablePersonas(res.items ?? []))
      .catch(() => setAvailablePersonas([]));
  }, [selectedWorkspaceId]);

  // Resume an existing draft
  useEffect(() => {
    if (!routeCampaignId || !routeWorkspaceId) return;
    (async () => {
      try {
        const campaign = await getCampaign(routeWorkspaceId, routeCampaignId);
        if (campaign.status !== "draft") {
          navigate(`/workspaces/${encodeURIComponent(routeWorkspaceId)}/campaigns/${encodeURIComponent(routeCampaignId)}`);
          return;
        }
        const b = campaign.brief ?? {};
        setForm({
          product_or_service: b.product_or_service ?? "",
          goal: b.goal ?? "",
          budget: b.budget != null ? String(b.budget) : "",
          currency: b.currency ?? "USD",
          start_date: b.start_date ?? "",
          end_date: b.end_date ?? "",
          additional_context: b.additional_context ?? "",
        });
        setSelectedChannels(b.selected_channels ?? []);
        setSelectedPlatforms(b.social_media_platforms ?? []);
        setGenerateImages(b.generate_images ?? false);
        setSelectedPersonaIds(b.persona_ids ?? []);
        setCurrentStep(campaign.wizard_step > 0 ? campaign.wizard_step : 1);
      } catch {
        setError("Failed to load draft campaign.");
      }
    })();
  }, [routeCampaignId, routeWorkspaceId, navigate]);

  // Debounced template recommendations when product + goal both have values
  useEffect(() => {
    if (recsTimer.current) clearTimeout(recsTimer.current);
    const product = form.product_or_service.trim();
    const goal = form.goal.trim();
    if (!product || !goal) {
      setRecommendations([]);
      return;
    }
    setRecsLoading(true);
    recsTimer.current = setTimeout(async () => {
      try {
        const data = await getTemplateRecommendations({ product, goal });
        setRecommendations(Array.isArray(data) ? data.slice(0, 3) : []);
      } catch {
        setRecommendations([]);
      } finally {
        setRecsLoading(false);
      }
    }, 500);
    return () => {
      if (recsTimer.current) clearTimeout(recsTimer.current);
    };
  }, [form.product_or_service, form.goal]);

  // Auto-save: debounced PATCH on form changes (steps 2-4 only)
  const scheduleAutoSave = useCallback(
    (fields) => {
      if (!campaignId || !selectedWorkspaceId) return;
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
      setAutoSaveState("saving");
      autoSaveTimer.current = setTimeout(async () => {
        try {
          await updateCampaignDraft(selectedWorkspaceId, campaignId, fields);
          setAutoSaveState("saved");
          setTimeout(() => setAutoSaveState("idle"), 2000);
        } catch {
          setAutoSaveState("idle");
        }
      }, 2000);
    },
    [campaignId, selectedWorkspaceId]
  );

  useEffect(() => {
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    };
  }, []);

  const set = (field) => (e) => {
    const value = e.target.value;
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      if (currentStep >= 2 && currentStep <= 4) {
        scheduleAutoSave({ [field]: value });
      }
      return next;
    });
  };

  const toggleChannel = (ch) => {
    setSelectedChannels((prev) => {
      const next = prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch];
      scheduleAutoSave({ selected_channels: next });
      return next;
    });
    if (ch === "social_media" && selectedChannels.includes(ch)) {
      setSelectedPlatforms([]);
    }
  };

  const togglePlatform = (pl) => {
    setSelectedPlatforms((prev) => {
      const next = prev.includes(pl) ? prev.filter((p) => p !== pl) : [...prev, pl];
      scheduleAutoSave({ social_media_platforms: next });
      return next;
    });
  };

  const selectAllChannels = () => {
    const next = selectedChannels.length === CHANNEL_OPTIONS.length
      ? []
      : CHANNEL_OPTIONS.map((c) => c.value);
    setSelectedChannels(next);
    scheduleAutoSave({ selected_channels: next });
    if (!next.includes("social_media")) setSelectedPlatforms([]);
  };

  // Navigate to a specific step (for edit links in review)
  const goToStep = useCallback(async (step) => {
    if (campaignId && selectedWorkspaceId) {
      try {
        await updateCampaignDraft(selectedWorkspaceId, campaignId, { wizard_step: step });
      } catch { /* non-blocking */ }
    }
    setCurrentStep(step);
    setError(null);
  }, [campaignId, selectedWorkspaceId]);

  // Step 0 → 1: just advance (workspace already selected)
  const handleStep0Next = () => {
    if (!selectedWorkspaceId) {
      setError("Please select a workspace.");
      return;
    }
    setError(null);
    setCurrentStep(1);
  };

  // Step 1 → 2: create draft campaign
  const handleStep1Next = async () => {
    if (!form.product_or_service.trim()) {
      setError("Product or Service is required.");
      return;
    }
    if (!form.goal.trim()) {
      setError("Campaign Goal is required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (campaignId) {
        // Resuming draft — just patch and advance
        await updateCampaignDraft(selectedWorkspaceId, campaignId, {
          product_or_service: form.product_or_service,
          goal: form.goal,
          wizard_step: 2,
        });
      } else {
        // First time — create the draft
        const res = await createCampaign(
          { product_or_service: form.product_or_service, goal: form.goal },
          selectedWorkspaceId
        );
        setCampaignId(res.id);
        await updateCampaignDraft(selectedWorkspaceId, res.id, { wizard_step: 2 });
      }
      setCurrentStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Steps 2-4: advance and save wizard_step
  const handleStepNext = async (step) => {
    // Validate step 2 date range
    if (step === 2 && form.start_date && form.end_date && form.end_date < form.start_date) {
      setError("End date must be on or after the start date.");
      return;
    }
    // Validate step 3 social platforms
    if (step === 3 && selectedChannels.includes("social_media") && selectedPlatforms.length === 0) {
      setError("Please select at least one social media platform.");
      return;
    }
    setError(null);

    if (campaignId && selectedWorkspaceId) {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
      setLoading(true);
      try {
        const patchBody = { wizard_step: step + 1 };
        if (step === 2) {
          Object.assign(patchBody, {
            budget: form.budget ? parseFloat(form.budget) : null,
            currency: form.currency,
            start_date: form.start_date || null,
            end_date: form.end_date || null,
          });
        } else if (step === 3) {
          Object.assign(patchBody, {
            selected_channels: selectedChannels,
            social_media_platforms: selectedChannels.includes("social_media") ? selectedPlatforms : [],
            generate_images: generateImages,
          });
        } else if (step === 4) {
          Object.assign(patchBody, {
            additional_context: form.additional_context,
            persona_ids: selectedPersonaIds,
          });
        }
        await updateCampaignDraft(selectedWorkspaceId, campaignId, patchBody);
      } catch (err) {
        setError(err.message);
        setLoading(false);
        return;
      } finally {
        setLoading(false);
      }
    }
    setCurrentStep(step + 1);
  };

  const handleBack = () => {
    setError(null);
    setCurrentStep((s) => Math.max(routeWorkspaceId ? 1 : 0, s - 1));
  };

  const handleSkip = async (step) => {
    setError(null);
    if (campaignId && selectedWorkspaceId) {
      try {
        await updateCampaignDraft(selectedWorkspaceId, campaignId, { wizard_step: step + 1 });
      } catch { /* non-blocking */ }
    }
    setCurrentStep(step + 1);
  };

  // Step 5 → Launch
  const handleLaunch = async () => {
    if (!campaignId || !selectedWorkspaceId) {
      setError("Campaign draft not found. Please go back and complete step 1.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await launchCampaign(selectedWorkspaceId, campaignId);
      navigate(`/workspaces/${encodeURIComponent(selectedWorkspaceId)}/campaigns/${encodeURIComponent(campaignId)}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const selectedWorkspace = creatableWorkspaces.find((ws) => ws.id === selectedWorkspaceId)
    ?? (workspaces.find((ws) => ws.id === selectedWorkspaceId));

  const hasWorkspaceStep = !routeWorkspaceId;

  const autoSaveLabel = autoSaveState === "saving"
    ? "⏳ Saving…"
    : autoSaveState === "saved"
    ? "✓ Saved"
    : null;

  const autoSaveCls = `wizard-autosave${autoSaveState === "saving" ? " wizard-autosave--saving" : autoSaveState === "saved" ? " wizard-autosave--saved" : ""}`;

  // ---- Render helpers ----

  const renderNav = (onNext, canNext = true, showSkip = false, skipStep = currentStep, showBack = true) => (
    <div className="wizard-nav" style={{ marginTop: "1.5rem" }}>
      {showBack && currentStep > (hasWorkspaceStep ? 0 : 1) ? (
        <button type="button" className="btn btn-outline" onClick={handleBack}>
          ← Back
        </button>
      ) : <span />}
      <div className="wizard-nav-right">
        {autoSaveLabel && <span className={autoSaveCls}>{autoSaveLabel}</span>}
        {showSkip && (
          <button type="button" className="btn btn-outline" onClick={() => handleSkip(skipStep)}>
            Skip
          </button>
        )}
        <button
          type="button"
          className="btn btn-primary"
          disabled={loading || !canNext}
          onClick={onNext}
        >
          {loading ? <><span className="spinner" /> Working…</> : "Next →"}
        </button>
      </div>
    </div>
  );

  // ---- Step renderers ----

  const renderStep0 = () => (
    <div className="wizard-step-card">
      <h2 className="wizard-step-title">Choose a workspace</h2>
      <p className="wizard-step-subtitle">Where should this campaign live?</p>
      {creatableWorkspaces.length === 0 ? (
        <p style={{ color: "var(--color-danger)", fontSize: "0.85rem" }}>
          You don&apos;t have Creator access to any workspace. Contact an admin to get started.
        </p>
      ) : (
        <div className="form-group">
          <label id={workspaceLabelId} htmlFor="workspace-select">Create in workspace *</label>
          <WorkspaceDropdown
            value={selectedWorkspaceId}
            options={creatableWorkspaces}
            onChange={setSelectedWorkspaceId}
            labelId={workspaceLabelId}
          />
        </div>
      )}
      {renderNav(handleStep0Next, !!selectedWorkspaceId, false, 0, false)}
    </div>
  );

  const renderStep1 = () => (
    <div className="wizard-step-card">
      <h2 className="wizard-step-title">What are you promoting?</h2>
      <p className="wizard-step-subtitle">Tell us about your product or service and what you want to achieve.</p>
      <div className="form-group">
        <label>Product or Service *</label>
        <input
          required
          placeholder="e.g. CloudSync — a cloud storage platform"
          value={form.product_or_service}
          onChange={set("product_or_service")}
        />
      </div>
      <div className="form-group">
        <label>Campaign Goal *</label>
        <textarea
          required
          placeholder="e.g. Increase free-trial signups by 30% in Q2 2026"
          value={form.goal}
          onChange={set("goal")}
        />
      </div>

      {/* Suggested Templates widget */}
      {(recsLoading || recommendations.length > 0) && (
        <div className="suggested-templates" role="region" aria-label="Suggested templates">
          <div className="suggested-templates__header">
            <h3 className="suggested-templates__title">✨ Suggested Templates</h3>
            <button
              type="button"
              className="suggested-templates__toggle"
              onClick={() => setRecsOpen((prev) => !prev)}
              aria-expanded={recsOpen}
              aria-label={recsOpen ? "Collapse suggested templates" : "Expand suggested templates"}
            >
              {recsOpen ? "▲" : "▼"}
            </button>
          </div>
          {recsOpen && (
            <div className="suggested-templates__body">
              {recsLoading ? (
                <div className="suggested-templates__loading">
                  <span className="spinner" style={{ width: 16, height: 16 }} /> Finding templates…
                </div>
              ) : (
                <>
                  <div className="suggested-templates__list">
                    {recommendations.map((tpl) => (
                      <div key={tpl.template_id ?? tpl.id} className="suggested-templates__card">
                        <div className="suggested-templates__card-name">{tpl.template_name ?? tpl.name}</div>
                        {tpl.match_reason && (
                          <div className="suggested-templates__reason">{tpl.match_reason}</div>
                        )}
                        <button
                          type="button"
                          className="btn btn-outline suggested-templates__use-btn"
                          onClick={() => setCloneTemplate({
                            id: tpl.template_id ?? tpl.id,
                            workspace_id: tpl.workspace_id ?? selectedWorkspaceId,
                            is_template: true,
                            template_parameters: tpl.template_parameters ?? [],
                            brief: { product_or_service: tpl.template_name ?? tpl.name },
                          })}
                        >
                          Use This Template
                        </button>
                      </div>
                    ))}
                  </div>
                  <Link to="/templates" className="suggested-templates__browse">
                    Browse All Templates →
                  </Link>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {renderNav(handleStep1Next, !!(form.product_or_service.trim() && form.goal.trim()), false, 1, hasWorkspaceStep)}
    </div>
  );

  const renderStep2 = () => (
    <div className="wizard-step-card">
      <h2 className="wizard-step-title">
        Budget &amp; Timeline
        <span className="wizard-optional-badge">optional</span>
      </h2>
      <p className="wizard-step-subtitle">Set a budget and timeline, or skip and let the agents work with what&apos;s available.</p>
      <div className="form-row">
        <div className="form-group">
          <label>Budget</label>
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="50000"
            value={form.budget}
            onChange={set("budget")}
          />
        </div>
        <div className="form-group">
          <label>Currency</label>
          <select value={form.currency} onChange={set("currency")}>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Start Date</label>
          <DatePicker value={form.start_date} onChange={set("start_date")} />
        </div>
        <div className="form-group">
          <label>End Date</label>
          <DatePicker value={form.end_date} min={form.start_date || undefined} onChange={set("end_date")} />
        </div>
      </div>
      {renderNav(() => handleStepNext(2), true, true, 2)}
    </div>
  );

  const renderStep3 = () => (
    <div className="wizard-step-card">
      <h2 className="wizard-step-title">
        Pick Your Channels
        <span className="wizard-optional-badge">optional</span>
      </h2>
      <p className="wizard-step-subtitle">Choose which channels to deploy. Leave empty to let the agents decide.</p>
      <div className="form-group">
        <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>Channels to Deploy</span>
          <button
            type="button"
            className="btn btn-outline"
            style={{ padding: "0.2rem 0.6rem", fontSize: "0.75rem" }}
            onClick={selectAllChannels}
          >
            {selectedChannels.length === CHANNEL_OPTIONS.length ? "Clear All" : "Select All"}
          </button>
        </label>
        <div className="channel-picker">
          {CHANNEL_OPTIONS.map((ch) => (
            <button
              key={ch.value}
              type="button"
              className={`channel-chip${selectedChannels.includes(ch.value) ? " selected" : ""}`}
              onClick={() => toggleChannel(ch.value)}
            >
              <span className="channel-chip-icon" aria-hidden="true">{ch.icon}</span>
              {ch.label}
            </button>
          ))}
        </div>
        {selectedChannels.length > 0 && (
          <p style={{ fontSize: "0.78rem", color: "var(--color-primary-hover)", marginTop: "0.4rem" }}>
            {selectedChannels.length} channel{selectedChannels.length !== 1 ? "s" : ""} selected
          </p>
        )}
        {selectedChannels.includes("social_media") && (
          <div className="platform-sub-picker">
            <label style={{ fontSize: "0.82rem", fontWeight: 500, color: "var(--color-text-muted)", marginBottom: "0.3rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Select Social Media Platforms *</span>
              <button
                type="button"
                className="btn btn-outline"
                style={{ padding: "0.2rem 0.6rem", fontSize: "0.7rem" }}
                onClick={() => setSelectedPlatforms(
                  selectedPlatforms.length === SOCIAL_MEDIA_PLATFORMS.length
                    ? []
                    : SOCIAL_MEDIA_PLATFORMS.map((p) => p.value)
                )}
              >
                {selectedPlatforms.length === SOCIAL_MEDIA_PLATFORMS.length ? "Clear All" : "Select All"}
              </button>
            </label>
            <div className="channel-picker">
              {SOCIAL_MEDIA_PLATFORMS.map((pl) => (
                <button
                  key={pl.value}
                  type="button"
                  className={`channel-chip platform-chip${selectedPlatforms.includes(pl.value) ? " selected" : ""}`}
                  onClick={() => togglePlatform(pl.value)}
                >
                  {pl.label}
                </button>
              ))}
            </div>
            {selectedPlatforms.length === 0 && (
              <p style={{ fontSize: "0.75rem", color: "var(--color-warning)", marginTop: "0.3rem" }}>
                Please choose at least one platform.
              </p>
            )}
          </div>
        )}
      </div>
      {imageGenerationAvailable && (
        <div className="form-check" style={{ marginTop: "1rem" }}>
          <input
            type="checkbox"
            id="generate-images"
            checked={generateImages}
            onChange={(e) => {
              const value = e.target.checked;
              setGenerateImages(value);
              scheduleAutoSave({ generate_images: value });
            }}
          />
          <label htmlFor="generate-images">
            Generate AI images for this campaign
            <span
              className="info-hint"
              title="When enabled, the AI pipeline will generate images for your campaign content."
              aria-label="More info about AI image generation"
            >
              ℹ
            </span>
          </label>
        </div>
      )}
      {renderNav(() => handleStepNext(3), !(selectedChannels.includes("social_media") && selectedPlatforms.length === 0), true, 3)}
    </div>
  );

  const togglePersona = (personaId) => {
    setSelectedPersonaIds((prev) => {
      const next = prev.includes(personaId)
        ? prev.filter((id) => id !== personaId)
        : [...prev, personaId];
      scheduleAutoSave({ persona_ids: next });
      return next;
    });
  };

  const renderStep4 = () => (
    <div className="wizard-step-card">
      <h2 className="wizard-step-title">
        Anything else?
        <span className="wizard-optional-badge">optional</span>
      </h2>
      <p className="wizard-step-subtitle">Add extra context — target markets, brand guidelines, constraints, or competitors.</p>

      {availablePersonas.length > 0 && (
        <div className="form-group">
          <label>Target Personas</label>
          <p style={{ fontSize: "0.78rem", color: "var(--color-text-muted)", margin: "0 0 0.5rem" }}>
            Optionally select personas from your library to guide the AI pipeline.
          </p>
          <div className="channel-picker">
            {availablePersonas.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`channel-chip${selectedPersonaIds.includes(p.id) ? " selected" : ""}`}
                onClick={() => togglePersona(p.id)}
                title={p.description}
              >
                <span className="channel-chip-icon" aria-hidden="true">👤</span>
                {p.name}
              </button>
            ))}
          </div>
          {selectedPersonaIds.length > 0 && (
            <p style={{ fontSize: "0.78rem", color: "var(--color-primary-hover)", marginTop: "0.4rem" }}>
              {selectedPersonaIds.length} persona{selectedPersonaIds.length !== 1 ? "s" : ""} selected
            </p>
          )}
        </div>
      )}

      <div className="form-group">
        <label>Additional Context</label>
        <textarea
          style={{ minHeight: 120 }}
          placeholder="Target market, brand guidelines, constraints, competitors…"
          value={form.additional_context}
          onChange={set("additional_context")}
        />
      </div>
      {renderNav(() => handleStepNext(4), true, true, 4)}
    </div>
  );

  const renderStep5 = () => {
    const budgetDisplay = form.budget
      ? `${form.currency} ${parseFloat(form.budget).toLocaleString()}`
      : null;
    const timelineDisplay = form.start_date && form.end_date
      ? `${form.start_date} → ${form.end_date}`
      : form.start_date
      ? `From ${form.start_date}`
      : form.end_date
      ? `Until ${form.end_date}`
      : null;
    const channelsDisplay = selectedChannels.length > 0
      ? selectedChannels.map((c) => CHANNEL_OPTIONS.find((o) => o.value === c)?.label ?? c).join(", ")
      : null;
    const platformsDisplay = selectedChannels.includes("social_media") && selectedPlatforms.length > 0
      ? selectedPlatforms.map((p) => SOCIAL_MEDIA_PLATFORMS.find((o) => o.value === p)?.label ?? p).join(", ")
      : null;
    const personasDisplay = selectedPersonaIds.length > 0
      ? selectedPersonaIds.map((pid) => availablePersonas.find((p) => p.id === pid)?.name ?? pid).join(", ")
      : null;

    return (
      <div className="wizard-step-card">
        <h2 className="wizard-step-title">Review &amp; Launch</h2>
        <p className="wizard-step-subtitle">Everything look good? Hit Launch to start the AI pipeline.</p>

        <div className="wizard-review-section">
          <div className="wizard-review-section-header">
            <span className="wizard-review-section-title">Campaign</span>
            <button className="wizard-review-edit-btn" onClick={() => goToStep(1)}>Edit</button>
          </div>
          <div className="wizard-review-field">
            <span className="wizard-review-field-label">Product</span>
            <span className="wizard-review-field-value">{form.product_or_service}</span>
          </div>
          <div className="wizard-review-field">
            <span className="wizard-review-field-label">Goal</span>
            <span className="wizard-review-field-value">{form.goal}</span>
          </div>
        </div>

        <div className="wizard-review-section">
          <div className="wizard-review-section-header">
            <span className="wizard-review-section-title">Budget &amp; Timeline</span>
            <button className="wizard-review-edit-btn" onClick={() => goToStep(2)}>Edit</button>
          </div>
          {budgetDisplay || timelineDisplay ? (
            <>
              {budgetDisplay && (
                <div className="wizard-review-field">
                  <span className="wizard-review-field-label">Budget</span>
                  <span className="wizard-review-field-value">{budgetDisplay}</span>
                </div>
              )}
              {timelineDisplay && (
                <div className="wizard-review-field">
                  <span className="wizard-review-field-label">Timeline</span>
                  <span className="wizard-review-field-value">{timelineDisplay}</span>
                </div>
              )}
            </>
          ) : (
            <span className="wizard-review-empty">Not specified — agents will decide</span>
          )}
        </div>

        <div className="wizard-review-section">
          <div className="wizard-review-section-header">
            <span className="wizard-review-section-title">Channels</span>
            <button className="wizard-review-edit-btn" onClick={() => goToStep(3)}>Edit</button>
          </div>
          {channelsDisplay ? (
            <>
              <div className="wizard-review-field">
                <span className="wizard-review-field-label">Channels</span>
                <span className="wizard-review-field-value">{channelsDisplay}</span>
              </div>
              {platformsDisplay && (
                <div className="wizard-review-field">
                  <span className="wizard-review-field-label">Platforms</span>
                  <span className="wizard-review-field-value">{platformsDisplay}</span>
                </div>
              )}
            </>
          ) : (
            <span className="wizard-review-empty">Not specified — agents will decide</span>
          )}
          {imageGenerationAvailable && (
            <div className="wizard-review-field">
              <span className="wizard-review-field-label">AI Images</span>
              <span className="wizard-review-field-value">{generateImages ? "Enabled ✓" : "Not selected"}</span>
            </div>
          )}
        </div>

        {personasDisplay && (
          <div className="wizard-review-section">
            <div className="wizard-review-section-header">
              <span className="wizard-review-section-title">Personas</span>
              <button className="wizard-review-edit-btn" onClick={() => goToStep(4)}>Edit</button>
            </div>
            <div className="wizard-review-field">
              <span className="wizard-review-field-label">Selected</span>
              <span className="wizard-review-field-value">{personasDisplay}</span>
            </div>
          </div>
        )}

        <div className="wizard-review-section">
          <div className="wizard-review-section-header">
            <span className="wizard-review-section-title">Additional Context</span>
            <button className="wizard-review-edit-btn" onClick={() => goToStep(4)}>Edit</button>
          </div>
          {form.additional_context ? (
            <p style={{ fontSize: "var(--text-sm)", color: "var(--color-text)", whiteSpace: "pre-wrap" }}>
              {form.additional_context}
            </p>
          ) : (
            <span className="wizard-review-empty">None provided</span>
          )}
        </div>

        <div className="wizard-nav" style={{ marginTop: "1.5rem" }}>
          <button type="button" className="btn btn-outline" onClick={handleBack}>
            ← Back
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={loading}
            onClick={handleLaunch}
          >
            {loading ? <><span className="spinner" /> Launching…</> : "🚀 Launch Campaign"}
          </button>
        </div>
      </div>
    );
  };

  const steps = [renderStep0, renderStep1, renderStep2, renderStep3, renderStep4, renderStep5];

  return (
    <div className="wizard-container">
      <nav className="breadcrumb">
        <Link to="/">Dashboard</Link>
        {selectedWorkspace && (
          <>
            <span className="breadcrumb-divider">/</span>
            <Link to={`/workspaces/${selectedWorkspace.id}`}>{selectedWorkspace.name}</Link>
          </>
        )}
        <span className="breadcrumb-divider">/</span>
        <span>{isResuming ? "Resume Draft" : "New Campaign"}</span>
      </nav>

      <h2 className="page-title">{isResuming ? "Resume Draft Campaign" : "Create New Campaign"}</h2>

      {isResuming && campaignId && (
        <div className="wizard-draft-banner">
          📝 Resuming draft — your progress is auto-saved as you go.
        </div>
      )}

      <WizardProgress
        currentStep={currentStep}
        hasWorkspaceStep={hasWorkspaceStep}
      />

      {error && (
        <p style={{ color: "var(--color-danger)", marginBottom: "0.75rem", fontSize: "0.85rem" }}>
          {error}
        </p>
      )}

      {steps[currentStep]?.()}

      {/* Clone from template dialog */}
      <CloneDialog
        isOpen={!!cloneTemplate}
        onClose={() => setCloneTemplate(null)}
        campaign={cloneTemplate}
        sourceWorkspaceId={cloneTemplate?.workspace_id ?? selectedWorkspaceId}
      />
    </div>
  );
}

