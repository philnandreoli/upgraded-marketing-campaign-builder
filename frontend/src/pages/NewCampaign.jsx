import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createCampaign } from "../api";
import DatePicker from "../components/DatePicker";
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
      if (event.key === "Escape") {
        setOpen(false);
      }
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
                onClick={() => {
                  onChange(ws.id);
                  setOpen(false);
                }}
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

export default function NewCampaign() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const workspaceLabelId = useId();
  const { isAdmin } = useUser();
  const { workspaces, personalWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
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
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");

  // Workspaces where the current user can create campaigns:
  // admins see all workspaces; others see only those where their role is "creator".
  const creatableWorkspaces = useMemo(
    () => (isAdmin ? workspaces : workspaces.filter((ws) => ws.role === "creator")),
    [isAdmin, workspaces]
  );

  // Pre-select workspace from ?workspace= query param, then personal workspace,
  // then the first available creatable workspace.
  useEffect(() => {
    if (creatableWorkspaces.length === 0) return;
    const paramId = searchParams.get("workspace");
    if (paramId && creatableWorkspaces.some((ws) => ws.id === paramId)) {
      setSelectedWorkspaceId(paramId);
    } else if (personalWorkspace && creatableWorkspaces.some((ws) => ws.id === personalWorkspace.id)) {
      setSelectedWorkspaceId(personalWorkspace.id);
    } else {
      setSelectedWorkspaceId(creatableWorkspaces[0].id);
    }
  }, [creatableWorkspaces, personalWorkspace, searchParams]);

  const set = (field) => (e) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const toggleChannel = (ch) => {
    setSelectedChannels((prev) =>
      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
    );
    // Clear platform selections when social_media is deselected
    if (ch === "social_media" && selectedChannels.includes(ch)) {
      setSelectedPlatforms([]);
    }
  };

  const togglePlatform = (pl) => {
    setSelectedPlatforms((prev) =>
      prev.includes(pl) ? prev.filter((p) => p !== pl) : [...prev, pl]
    );
  };

  const selectAllChannels = () => {
    if (selectedChannels.length === CHANNEL_OPTIONS.length) {
      setSelectedChannels([]);
      setSelectedPlatforms([]);
    } else {
      setSelectedChannels(CHANNEL_OPTIONS.map((c) => c.value));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedWorkspaceId) {
      setError("Please select a workspace.");
      return;
    }
    if (selectedChannels.includes("social_media") && selectedPlatforms.length === 0) {
      setError("Please select at least one social media platform.");
      return;
    }
    if (form.start_date && form.end_date && form.end_date < form.start_date) {
      setError("End date must be on or after the start date.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const brief = {
        ...form,
        budget: form.budget ? parseFloat(form.budget) : null,
        selected_channels: selectedChannels,
        social_media_platforms: selectedChannels.includes("social_media")
          ? selectedPlatforms
          : [],
      };
      const res = await createCampaign(brief, selectedWorkspaceId);
      navigate(`/campaign/${res.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="page-title">Create New Campaign</h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 640 }}>
        {/* Workspace picker — shown before Step 1 */}
        <fieldset className="form-section">
          <legend className="form-section-title">Workspace</legend>

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
        </fieldset>

        <fieldset className="form-section">
          <legend className="form-section-title">
            <span className="form-section-number">1</span>
            Campaign Basics
          </legend>

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
        </fieldset>

        <fieldset className="form-section">
          <legend className="form-section-title">
            <span className="form-section-number">2</span>
            Budget & Timeline
          </legend>

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
              <DatePicker
                value={form.start_date}
                onChange={set("start_date")}
              />
            </div>
            <div className="form-group">
              <label>End Date</label>
              <DatePicker
                value={form.end_date}
                min={form.start_date || undefined}
                onChange={set("end_date")}
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend className="form-section-title">
            <span className="form-section-number">3</span>
            Channels
          </legend>

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
            <p style={{ fontSize: "0.78rem", color: "var(--color-text-dim)", marginBottom: "0.5rem" }}>
              Choose channels to focus on. Leave empty to let the agents decide.
            </p>
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

            {/* Social-media platform sub-picker */}
            {selectedChannels.includes("social_media") && (
              <div className="platform-sub-picker">
                <label style={{ fontSize: "0.82rem", fontWeight: 500, color: "var(--color-text-muted)", marginBottom: "0.3rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span>Select Social Media Platforms *</span>
                  <button
                    type="button"
                    className="btn btn-outline"
                    style={{ padding: "0.2rem 0.6rem", fontSize: "0.7rem" }}
                    onClick={() =>
                      setSelectedPlatforms(
                        selectedPlatforms.length === SOCIAL_MEDIA_PLATFORMS.length
                          ? []
                          : SOCIAL_MEDIA_PLATFORMS.map((p) => p.value)
                      )
                    }
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
        </fieldset>

        <fieldset className="form-section">
          <legend className="form-section-title">
            <span className="form-section-number">4</span>
            Additional Details
          </legend>

          <div className="form-group">
            <label>Additional Context</label>
            <textarea
              placeholder="Target market, brand guidelines, constraints, competitors…"
              value={form.additional_context}
              onChange={set("additional_context")}
            />
          </div>
        </fieldset>

        {error && (
          <p style={{ color: "var(--color-danger)", marginBottom: "0.75rem", fontSize: "0.85rem" }}>
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? (
            <>
              <span className="spinner" /> Creating…
            </>
          ) : (
            "🚀 Launch Campaign"
          )}
        </button>
      </form>
    </div>
  );
}
