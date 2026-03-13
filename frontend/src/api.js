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

export async function createCampaign(brief, workspaceId = null) {
  const body = workspaceId !== null ? { ...brief, workspace_id: workspaceId } : brief;
  const res = await fetch(`${API_BASE}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Create failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = `Create failed: ${res.status} — ${body.detail}`;
    } catch { /* response wasn't JSON */ }
    throw new Error(detail);
  }
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

export async function getCampaignEvents(campaignId, { limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset });
  const res = await fetch(
    `${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/events?${params}`,
    { headers: await authHeaders() }
  );
  if (!res.ok) throw new Error(`Get events failed: ${res.status}`);
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
  const url = `${API_BASE}/api/campaigns/${campaignId}/content-approve`;
  const payload = {
    campaign_id: campaignId,
    pieces,
    reject_campaign: rejectCampaign,
  };
  console.log("[submitContentApproval] URL:", url);
  console.log("[submitContentApproval] Payload:", JSON.stringify(payload, null, 2));
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(payload),
  });
  console.log("[submitContentApproval] Response status:", res.status);
  if (!res.ok) {
    const errorBody = await res.text();
    console.error("[submitContentApproval] Error response body:", errorBody);
    throw new Error(`Content approval failed: ${res.status} - ${errorBody}`);
  }
  return res.json();
}

export async function updatePieceNotes(campaignId, pieceIndex, notes) {
  const res = await fetch(
    `${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/content/${pieceIndex}/notes`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ notes }),
    }
  );
  if (!res.ok) throw new Error(`Update notes failed: ${res.status}`);
  return res.json();
}

export async function updatePieceDecision(campaignId, pieceIndex, { approved, editedContent = null, notes = "" }) {
  const res = await fetch(
    `${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/content/${pieceIndex}/decision`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ approved, edited_content: editedContent, notes }),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Update decision failed: ${res.status}`);
  }
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

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export async function listUsers(search = "") {
  const params = search ? `?search=${encodeURIComponent(search)}` : "";
  const res = await fetch(`${API_BASE}/api/admin/users${params}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List users failed: ${res.status}`);
  return res.json();
}

export async function updateUserRoles(userId, roles) {
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(userId)}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ roles }),
  });
  if (!res.ok) throw new Error(`Update roles failed: ${res.status}`);
  return res.json();
}

export async function deactivateUser(userId) {
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!res.ok && res.status !== 204)
    throw new Error(`Deactivate user failed: ${res.status}`);
}

export async function listAllCampaigns() {
  const res = await fetch(`${API_BASE}/api/admin/campaigns`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List all campaigns failed: ${res.status}`);
  return res.json();
}

export async function moveCampaign(campaignId, workspaceId) {
  const res = await fetch(`${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/workspace`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
  if (!res.ok) throw new Error(`Move campaign failed: ${res.status}`);
  return res.json();
}

export async function searchEntraUsers(search) {
  const res = await fetch(
    `${API_BASE}/api/admin/entra/users?search=${encodeURIComponent(search)}`,
    { headers: await authHeaders() },
  );
  if (!res.ok) throw new Error(`Entra search failed: ${res.status}`);
  return res.json();
}

export async function provisionUser(entraId, email, displayName, roles) {
  const res = await fetch(`${API_BASE}/api/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ entra_id: entraId, email, display_name: displayName, roles }),
  });
  if (!res.ok) throw new Error(`Provision user failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Campaign member management API
// ---------------------------------------------------------------------------

export async function listCampaignMembers(campaignId) {
  const res = await fetch(`${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/members`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List members failed: ${res.status}`);
  return res.json();
}

export async function addCampaignMember(campaignId, userId, role) {
  const res = await fetch(`${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ user_id: userId, role }),
  });
  if (!res.ok) throw new Error(`Add member failed: ${res.status}`);
  return res.json();
}

export async function removeCampaignMember(campaignId, userId) {
  const res = await fetch(
    `${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE", headers: await authHeaders() }
  );
  if (!res.ok && res.status !== 204)
    throw new Error(`Remove member failed: ${res.status}`);
}

export async function updateCampaignMemberRole(campaignId, userId, role) {
  const res = await fetch(
    `${API_BASE}/api/campaigns/${encodeURIComponent(campaignId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ role }),
    }
  );
  if (!res.ok) throw new Error(`Update member role failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Workspace API
// ---------------------------------------------------------------------------

export async function listWorkspaces() {
  const res = await fetch(`${API_BASE}/api/workspaces`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List workspaces failed: ${res.status}`);
  return res.json();
}

export async function getWorkspace(id) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`Get workspace failed: ${res.status}`);
  return res.json();
}

export async function createWorkspace(name, description) {
  const res = await fetch(`${API_BASE}/api/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error(`Create workspace failed: ${res.status}`);
  return res.json();
}

export async function updateWorkspace(id, { name, description }) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error(`Update workspace failed: ${res.status}`);
  return res.json();
}

export async function deleteWorkspace(id) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!res.ok && res.status !== 204)
    throw new Error(`Delete workspace failed: ${res.status}`);
}

export async function listWorkspaceCampaigns(id) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}/campaigns`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List workspace campaigns failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Workspace membership API
// ---------------------------------------------------------------------------

export async function listWorkspaceMembers(id) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}/members`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List workspace members failed: ${res.status}`);
  return res.json();
}

export async function addWorkspaceMember(id, userId, role) {
  const res = await fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ user_id: userId, role }),
  });
  if (!res.ok) throw new Error(`Add workspace member failed: ${res.status}`);
  return res.json();
}

export async function updateWorkspaceMemberRole(id, userId, role) {
  const res = await fetch(
    `${API_BASE}/api/workspaces/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ role }),
    }
  );
  if (!res.ok) throw new Error(`Update workspace member role failed: ${res.status}`);
  return res.json();
}

export async function removeWorkspaceMember(id, userId) {
  const res = await fetch(
    `${API_BASE}/api/workspaces/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE", headers: await authHeaders() }
  );
  if (!res.ok && res.status !== 204)
    throw new Error(`Remove workspace member failed: ${res.status}`);
}

export async function getWsUrl(campaignId = null) {
  let base;
  if (import.meta.env.VITE_API_URL) {
    // Explicit API URL configured — derive WebSocket URL from it
    base = import.meta.env.VITE_API_URL.replace(/^http/, "ws");
  } else {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    base = `${proto}://${window.location.host}`;
  }
  const path = campaignId ? `${base}/ws/${campaignId}` : `${base}/ws`;
  const token = await getBearerToken();
  return token ? `${path}?token=${encodeURIComponent(token)}` : path;
}
