import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { msalInstance, loginRequest } from "./authConfig.js";

const API_BASE = "";

/**
 * Acquire a bearer token silently.
 * Returns an empty string when auth is not configured (no client ID set).
 *
 * If interactive consent is needed (e.g. a new scope was added), we use a
 * popup so that the current page is NOT navigated away — preserving any
 * in-progress form data.
 */
async function getBearerToken() {
  const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;
  if (!clientId) return "";

  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) return "";

  try {
    const result = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account,
    });
    return result.accessToken;
  } catch (error) {
    // Only prompt interactively when the error actually requires it
    // (consent, MFA, expired refresh token, etc.)
    if (error instanceof InteractionRequiredAuthError) {
      try {
        const result = await msalInstance.acquireTokenPopup({
          ...loginRequest,
          account,
        });
        return result.accessToken;
      } catch (popupError) {
        console.error("Interactive token acquisition failed", popupError);
        return "";
      }
    }
    console.error("Silent token acquisition failed", error);
    return "";
  }
}

async function authHeaders() {
  const token = await getBearerToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getMe() {
  const res = await fetch(`${API_BASE}/api/me`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`Get profile failed: ${res.status}`);
  return res.json();
}

export async function createCampaign(brief) {
  const res = await fetch(`${API_BASE}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(brief),
  });
  if (!res.ok) throw new Error(`Create failed: ${res.status}`);
  return res.json();
}

export async function listCampaigns() {
  const res = await fetch(`${API_BASE}/api/campaigns`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  return res.json();
}

export async function getCampaign(id) {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`Get failed: ${res.status}`);
  return res.json();
}

export async function deleteCampaign(id) {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!res.ok && res.status !== 204)
    throw new Error(`Delete failed: ${res.status}`);
}

export async function submitReview() {
  // Legacy — no longer used. Use submitContentApproval instead.
  throw new Error("submitReview is deprecated. Use submitContentApproval.");
}

export async function submitContentApproval(campaignId, pieces, rejectCampaign = false) {
  const res = await fetch(`${API_BASE}/api/campaigns/${campaignId}/content-approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
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
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ campaign_id: campaignId, answers }),
  });
  if (!res.ok) throw new Error(`Clarification failed: ${res.status}`);
  return res.json();
}

export async function submitReviewClarification() {
  // Legacy — no longer used.
  throw new Error("submitReviewClarification is deprecated.");
}

export function getWsUrl(campaignId = null) {
  let base;
  if (import.meta.env.VITE_API_URL) {
    // Explicit API URL configured — derive WebSocket URL from it
    base = import.meta.env.VITE_API_URL.replace(/^http/, "ws");
  } else {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    base = `${proto}://${window.location.host}`;
  }
  return campaignId ? `${base}/ws/${campaignId}` : `${base}/ws`;
}
