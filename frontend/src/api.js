const API_BASE = "";

export async function createCampaign(brief) {
  const res = await fetch(`${API_BASE}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brief),
  });
  if (!res.ok) throw new Error(`Create failed: ${res.status}`);
  return res.json();
}

export async function listCampaigns() {
  const res = await fetch(`${API_BASE}/api/campaigns`);
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  return res.json();
}

export async function getCampaign(id) {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`);
  if (!res.ok) throw new Error(`Get failed: ${res.status}`);
  return res.json();
}

export async function deleteCampaign(id) {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204)
    throw new Error(`Delete failed: ${res.status}`);
}

export async function submitReview(campaignId, approved, notes = "") {
  // Legacy — no longer used. Use submitContentApproval instead.
  throw new Error("submitReview is deprecated. Use submitContentApproval.");
}

export async function submitContentApproval(campaignId, pieces, rejectCampaign = false) {
  const res = await fetch(`${API_BASE}/api/campaigns/${campaignId}/content-approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      campaign_id: campaignId,
      pieces,
      reject_campaign: rejectCampaign,
    }),
  });
  if (!res.ok) throw new Error(`Content approval failed: ${res.status}`);
  return res.json();
}

export async function submitClarification(campaignId, answers) {
  const res = await fetch(`${API_BASE}/api/campaigns/${campaignId}/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ campaign_id: campaignId, answers }),
  });
  if (!res.ok) throw new Error(`Clarification failed: ${res.status}`);
  return res.json();
}

export async function submitReviewClarification(campaignId, answers) {
  // Legacy — no longer used.
  throw new Error("submitReviewClarification is deprecated.");
}

export function getWsUrl(campaignId = null) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const base = `${proto}://${window.location.host}`;
  return campaignId ? `${base}/ws/${campaignId}` : `${base}/ws`;
}
