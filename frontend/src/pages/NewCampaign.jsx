import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createCampaign } from "../api";
import DatePicker from "../components/DatePicker";

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

export default function NewCampaign() {
  const navigate = useNavigate();
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
      const res = await createCampaign(brief);
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
