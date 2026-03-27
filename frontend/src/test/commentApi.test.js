/**
 * Unit tests for the comment API client functions.
 *
 * Tests cover:
 *  - All 6 comment API functions call the correct endpoints
 *  - URL parameters are properly encoded with encodeURIComponent
 *  - Query string filters (section, piece_index) are passed as URL params on list
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/auth.js", () => ({
  authHeaders: vi.fn().mockResolvedValue({}),
  authEnabled: false,
  redirectToLogin: vi.fn(),
}));

import {
  listComments,
  createComment,
  updateComment,
  deleteComment,
  resolveComment,
  getUnresolvedCommentCount,
} from "../api.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeResponse(status, body = null) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    headers: { get: () => null },
    json: body !== null
      ? vi.fn().mockResolvedValue(body)
      : vi.fn().mockRejectedValue(new SyntaxError("no body")),
  };
}

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();
});

const WS = "ws-123";
const CAMP = "camp-456";
const COMMENT = "cmt-789";

// ---------------------------------------------------------------------------
// listComments
// ---------------------------------------------------------------------------
describe("listComments", () => {
  it("calls GET on the comments endpoint with no filters", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments(WS, CAMP);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments`,
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("passes section as a query param", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments(WS, CAMP, { section: "strategy" });
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("section=strategy");
  });

  it("passes piece_index as a query param", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments(WS, CAMP, { pieceIndex: 2 });
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("piece_index=2");
  });

  it("passes both section and piece_index", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments(WS, CAMP, { section: "content", pieceIndex: 0 });
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("section=content");
    expect(url).toContain("piece_index=0");
  });

  it("omits query string when filters are undefined", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments(WS, CAMP, {});
    const url = mockFetch.mock.calls[0][0];
    expect(url).toBe(`/api/workspaces/${WS}/campaigns/${CAMP}/comments`);
  });

  it("encodes workspace and campaign IDs", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));
    await listComments("ws/special", "camp&id");
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("ws%2Fspecial");
    expect(url).toContain("camp%26id");
  });
});

// ---------------------------------------------------------------------------
// createComment
// ---------------------------------------------------------------------------
describe("createComment", () => {
  it("calls POST with the body payload", async () => {
    const payload = { body: "Hello", section: "strategy" };
    mockFetch.mockResolvedValue(makeResponse(201, { id: "new-1", ...payload }));
    await createComment(WS, CAMP, payload);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// updateComment
// ---------------------------------------------------------------------------
describe("updateComment", () => {
  it("calls PATCH with the body payload", async () => {
    const payload = { body: "Updated text" };
    mockFetch.mockResolvedValue(makeResponse(200, { id: COMMENT, ...payload }));
    await updateComment(WS, CAMP, COMMENT, payload);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments/${COMMENT}`,
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    );
  });

  it("encodes comment ID in the URL", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, {}));
    await updateComment(WS, CAMP, "cmt/special", { body: "x" });
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("cmt%2Fspecial");
  });
});

// ---------------------------------------------------------------------------
// deleteComment
// ---------------------------------------------------------------------------
describe("deleteComment", () => {
  it("calls DELETE on the comment endpoint", async () => {
    mockFetch.mockResolvedValue(makeResponse(204));
    await deleteComment(WS, CAMP, COMMENT);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments/${COMMENT}`,
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("returns undefined on 204", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: vi.fn(),
    });
    const result = await deleteComment(WS, CAMP, COMMENT);
    expect(result).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// resolveComment
// ---------------------------------------------------------------------------
describe("resolveComment", () => {
  it("calls PATCH on the resolve endpoint with resolved=true", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { id: COMMENT, is_resolved: true }));
    await resolveComment(WS, CAMP, COMMENT, true);
    const url = mockFetch.mock.calls[0][0];
    expect(url).toBe(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments/${COMMENT}/resolve?resolved=true`,
    );
    expect(mockFetch).toHaveBeenCalledWith(
      url,
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("calls PATCH with resolved=false to unresolve", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { id: COMMENT, is_resolved: false }));
    await resolveComment(WS, CAMP, COMMENT, false);
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain("resolved=false");
  });
});

// ---------------------------------------------------------------------------
// getUnresolvedCommentCount
// ---------------------------------------------------------------------------
describe("getUnresolvedCommentCount", () => {
  it("calls GET on the count endpoint", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { unresolved: 5 }));
    const result = await getUnresolvedCommentCount(WS, CAMP);
    expect(mockFetch).toHaveBeenCalledWith(
      `/api/workspaces/${WS}/campaigns/${CAMP}/comments/count`,
      expect.objectContaining({ method: "GET" }),
    );
    expect(result).toEqual({ unresolved: 5 });
  });
});
