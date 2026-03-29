import { request, requestWithHeaders } from "./lib/apiClient.js";
import { authEnabled } from "./lib/auth.js";

export { ApiError, RateLimitError } from "./lib/apiClient.js";

export const getMe = () => request("GET", "/api/me");

export const getMeSettings = () => request("GET", "/api/me/settings");

export const patchMeSettings = (patch) =>
  request("PATCH", "/api/me/settings", { body: patch });

export const createCampaign = (brief, workspaceId) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns`, { body: brief });

export const updateCampaignDraft = (workspaceId, campaignId, fields) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}`, { body: fields });

export const launchCampaign = (workspaceId, campaignId) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/launch`);

export const listCampaigns = (workspaceId, { includeDrafts = false, limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams();
  if (includeDrafts) params.set("include_drafts", "true");
  params.set("limit", limit);
  params.set("offset", offset);
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns?${params}`);
};

export const getCampaign = (workspaceId, id) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(id)}`);

export const getCampaignEvents = (workspaceId, campaignId, { limit = 100, offset = 0 } = {}) => {
  const params = new URLSearchParams({ limit, offset });
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/events?${params}`);
};

export const deleteCampaign = (workspaceId, id) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(id)}`);

export const submitContentApproval = (workspaceId, campaignId, pieces, rejectCampaign = false) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/content-approve`, {
    body: { campaign_id: campaignId, pieces, reject_campaign: rejectCampaign },
  });

export const updatePieceNotes = (workspaceId, campaignId, pieceIndex, notes) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/content/${pieceIndex}/notes`, {
    body: { notes },
  });

export const updatePieceDecision = (workspaceId, campaignId, pieceIndex, { approved, editedContent = null, notes = "" }) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/content/${pieceIndex}/decision`, {
    body: { approved, edited_content: editedContent, notes },
  });

export const schedulePiece = (
  workspaceId,
  campaignId,
  pieceIndex,
  { scheduledDate = null, scheduledTime = null, platformTarget = null } = {},
) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/content/${pieceIndex}/schedule`, {
    body: {
      scheduled_date: scheduledDate,
      scheduled_time: scheduledTime,
      platform_target: platformTarget,
    },
  });

export const getCalendar = (workspaceId, campaignId) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/calendar`);

export const getWorkspaceCalendar = (workspaceId, month) => {
  const params = month ? `?month=${encodeURIComponent(month)}` : "";
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/calendar${params}`);
};

export const bulkSchedule = (workspaceId, campaignId, schedules) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/content/bulk-schedule`, {
    body: { schedules },
  });

export const submitClarification = (workspaceId, campaignId, answers) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/clarify`, {
    body: { campaign_id: campaignId, answers },
  });

export const listImageAssets = (workspaceId, campaignId) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/assets`);

export const generateImageAsset = (workspaceId, campaignId, contentPieceIndex, promptOverride = null) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/assets/generate`, {
    body: { content_piece_index: contentPieceIndex, prompt_override: promptOverride },
  });

// ---------------------------------------------------------------------------
// Campaign comment API
// ---------------------------------------------------------------------------

export const listComments = (workspaceId, campaignId, { section, pieceIndex } = {}) => {
  const params = new URLSearchParams();
  if (section !== undefined && section !== null) params.set("section", section);
  if (pieceIndex !== undefined && pieceIndex !== null) params.set("piece_index", pieceIndex);
  const qs = params.toString();
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments${qs ? `?${qs}` : ""}`);
};

export const createComment = (workspaceId, campaignId, body) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments`, {
    body,
  });

export const updateComment = (workspaceId, campaignId, commentId, body) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments/${encodeURIComponent(commentId)}`, {
    body,
  });

export const deleteComment = (workspaceId, campaignId, commentId) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments/${encodeURIComponent(commentId)}`);

export const resolveComment = (workspaceId, campaignId, commentId, resolved) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments/${encodeURIComponent(commentId)}/resolve?resolved=${encodeURIComponent(resolved)}`);

export const getUnresolvedCommentCount = (workspaceId, campaignId) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/comments/count`);

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export const listUsers = async (search = "", { page = 1, pageSize = 25 } = {}) => {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("page", page);
  params.set("page_size", pageSize);
  const { data, headers } = await requestWithHeaders("GET", `/api/admin/users?${params}`);
  return {
    users: data,
    totalCount: parseInt(headers.get("X-Total-Count") ?? "0", 10),
  };
};

export const updateUserRoles = (userId, roles) =>
  request("PATCH", `/api/admin/users/${encodeURIComponent(userId)}/role`, { body: { roles } });

export const deactivateUser = (userId) =>
  request("DELETE", `/api/admin/users/${encodeURIComponent(userId)}`);

export const reactivateUser = (userId) =>
  request("POST", `/api/admin/users/${encodeURIComponent(userId)}/reactivate`);

export const listAllCampaigns = async ({ limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams();
  params.set("limit", limit);
  params.set("offset", offset);
  const { data, headers } = await requestWithHeaders("GET", `/api/admin/campaigns?${params}`);
  return {
    campaigns: data,
    totalCount: parseInt(headers.get("X-Total-Count") ?? "0", 10),
  };
};

export const searchEntraUsers = (search) =>
  request("GET", `/api/admin/entra/users?search=${encodeURIComponent(search)}`);

export const provisionUser = (entraId, email, displayName, roles) =>
  request("POST", "/api/admin/users", {
    body: { entra_id: entraId, email, display_name: displayName, roles },
  });

export const getUserWorkspaces = (userId) =>
  request("GET", `/api/admin/users/${encodeURIComponent(userId)}/workspaces`);

// ---------------------------------------------------------------------------
// Campaign member management API
// ---------------------------------------------------------------------------

export const listCampaignMembers = (workspaceId, campaignId) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/members`);

export const addCampaignMember = (workspaceId, campaignId, userId, role) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/members`, {
    body: { user_id: userId, role },
  });

export const removeCampaignMember = (workspaceId, campaignId, userId) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/members/${encodeURIComponent(userId)}`);

export const updateCampaignMemberRole = (workspaceId, campaignId, userId, role) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/members/${encodeURIComponent(userId)}`, {
    body: { role },
  });

// ---------------------------------------------------------------------------
// Workspace API
// ---------------------------------------------------------------------------

export const listWorkspaces = () => request("GET", "/api/workspaces");

export const getWorkspace = (id) => request("GET", `/api/workspaces/${encodeURIComponent(id)}`);

export const createWorkspace = (name, description) =>
  request("POST", "/api/workspaces", { body: { name, description } });

export const updateWorkspace = (id, { name, description }) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(id)}`, { body: { name, description } });

export const deleteWorkspace = (id) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(id)}`);

export const listWorkspaceCampaigns = (id, { includeDrafts = false, limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams();
  if (includeDrafts) params.set("include_drafts", "true");
  params.set("limit", limit);
  params.set("offset", offset);
  return request("GET", `/api/workspaces/${encodeURIComponent(id)}/campaigns?${params}`);
};

// ---------------------------------------------------------------------------
// Workspace membership API
// ---------------------------------------------------------------------------

export const listWorkspaceMembers = (id) =>
  request("GET", `/api/workspaces/${encodeURIComponent(id)}/members`);

export const addWorkspaceMember = (id, userId, role) =>
  request("POST", `/api/workspaces/${encodeURIComponent(id)}/members`, {
    body: { user_id: userId, role },
  });

export const updateWorkspaceMemberRole = (id, userId, role) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`, {
    body: { role },
  });

export const removeWorkspaceMember = (id, userId) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`);

// ---------------------------------------------------------------------------
// Budget API
// ---------------------------------------------------------------------------

export const createBudgetEntry = (workspaceId, campaignId, body) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/budget-entries`, {
    body,
  });

export const listBudgetEntries = (workspaceId, campaignId, { entryType } = {}) => {
  const params = new URLSearchParams();
  if (entryType) params.set("entry_type", entryType);
  const qs = params.toString();
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/budget-entries${qs ? `?${qs}` : ""}`);
};

export const updateBudgetEntry = (workspaceId, campaignId, entryId, body) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/budget-entries/${encodeURIComponent(entryId)}`, {
    body,
  });

export const deleteBudgetEntry = (workspaceId, campaignId, entryId) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/budget-entries/${encodeURIComponent(entryId)}`);

export const getCampaignBudgetSummary = (workspaceId, campaignId, { alertThresholdPct = 0.8 } = {}) => {
  const params = new URLSearchParams();
  params.set("alert_threshold_pct", alertThresholdPct);
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/budget-summary?${params}`);
};

export const getWorkspaceBudgetOverview = (workspaceId, { alertThresholdPct = 0.8 } = {}) => {
  const params = new URLSearchParams();
  params.set("alert_threshold_pct", alertThresholdPct);
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/budget-overview?${params}`);
};

// ---------------------------------------------------------------------------
// Persona API
// ---------------------------------------------------------------------------

export const listPersonas = (workspaceId, { limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams();
  params.set("limit", limit);
  params.set("offset", offset);
  return request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas?${params}`);
};

export const getPersona = (workspaceId, personaId) =>
  request("GET", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas/${encodeURIComponent(personaId)}`);

export const createPersona = (workspaceId, { name, description, source_text = "" }) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas`, {
    body: { name, description, source_text },
  });

export const updatePersona = (workspaceId, personaId, { name, description }) =>
  request("PATCH", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas/${encodeURIComponent(personaId)}`, {
    body: { name, description },
  });

export const deletePersona = (workspaceId, personaId) =>
  request("DELETE", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas/${encodeURIComponent(personaId)}`);

export const parsePersona = (workspaceId, { name, description }) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/personas/parse`, {
    body: { name, description },
  });

// ---------------------------------------------------------------------------
// Clone & Template API
// ---------------------------------------------------------------------------

export const cloneCampaign = (workspaceId, campaignId, { depth = "brief", targetWorkspaceId = null, parameterOverrides = null } = {}) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/clone`, {
    body: { depth, target_workspace_id: targetWorkspaceId, parameter_overrides: parameterOverrides },
  });

export const markAsTemplate = (workspaceId, campaignId, config) =>
  request("POST", `/api/workspaces/${encodeURIComponent(workspaceId)}/campaigns/${encodeURIComponent(campaignId)}/mark-template`, { body: config });

export const updateTemplate = (templateId, config) =>
  request("PATCH", `/api/templates/${encodeURIComponent(templateId)}`, { body: config });

export const unmarkTemplate = (templateId) =>
  request("DELETE", `/api/templates/${encodeURIComponent(templateId)}`);

export const listTemplates = ({ category, tags, featured, visibility, search, limit = 20, offset = 0 } = {}) => {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (tags) params.set("tags", tags);
  if (featured !== undefined) params.set("featured", featured);
  if (visibility) params.set("visibility", visibility);
  if (search) params.set("search", search);
  params.set("limit", limit);
  params.set("offset", offset);
  return request("GET", `/api/templates?${params}`);
};

export const getTemplatePreview = (id) =>
  request("GET", `/api/templates/${encodeURIComponent(id)}/preview`);

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
  if (!authEnabled) {
    // Auth disabled (local-dev) — connect without a ticket
    return path;
  }
  // Exchange the JWT for a short-lived, single-use opaque ticket so that the
  // full JWT never appears in the WebSocket upgrade URL (OWASP A07:2021).
  const { ticket } = await request("POST", "/api/ws/ticket");
  return `${path}?ticket=${encodeURIComponent(ticket)}`;
}
