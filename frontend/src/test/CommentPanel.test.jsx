/**
 * Tests for the CommentPanel component.
 *
 * Covers:
 *  - Comments load and display on mount
 *  - Empty state shown when no comments exist
 *  - Error state shown when fetch fails
 *  - Users can create new top-level comments
 *  - Users can reply to top-level comments
 *  - Users can resolve/unresolve top-level comments
 *  - Authors can edit their own comments
 *  - Authors can delete their own comments
 *  - Edit/delete/resolve buttons hidden for read-only users
 *  - Real-time updates via WebSocket events trigger a re-fetch
 */

import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import CommentPanel from "../components/CommentPanel.jsx";

vi.mock("../api");
import * as api from "../api";

vi.mock("../ToastContext", () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));

vi.mock("../UserContext", () => ({
  useUser: () => ({ user: { id: "user-1" } }),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const WS_ID = "ws-123";
const CAMP_ID = "camp-456";

const TOP_COMMENT = {
  id: "cmt-1",
  campaign_id: CAMP_ID,
  parent_id: null,
  section: "strategy",
  content_piece_index: null,
  body: "Top-level comment body",
  author_id: "user-1",
  author_display_name: "Alice",
  is_resolved: false,
  created_at: new Date(Date.now() - 60_000).toISOString(),
  updated_at: null,
};

const OTHER_COMMENT = {
  id: "cmt-2",
  campaign_id: CAMP_ID,
  parent_id: null,
  section: "strategy",
  content_piece_index: null,
  body: "Another comment",
  author_id: "user-2",
  author_display_name: "Bob",
  is_resolved: false,
  created_at: new Date(Date.now() - 30_000).toISOString(),
  updated_at: null,
};

const REPLY_COMMENT = {
  id: "cmt-3",
  campaign_id: CAMP_ID,
  parent_id: "cmt-1",
  section: "strategy",
  content_piece_index: null,
  body: "A reply",
  author_id: "user-2",
  author_display_name: "Bob",
  is_resolved: false,
  created_at: new Date(Date.now() - 10_000).toISOString(),
  updated_at: null,
};

function renderPanel(props = {}) {
  const defaults = {
    campaignId: CAMP_ID,
    workspaceId: WS_ID,
    isReadOnly: false,
    events: [],
    isOpen: true,
  };
  return render(<CommentPanel {...defaults} {...props} />);
}

// ---------------------------------------------------------------------------
// beforeEach — reset mocks
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.resetAllMocks();
  // Default: member-related APIs resolve to empty arrays so existing tests
  // don't break due to the new member-fetch side-effect.
  api.listCampaignMembers.mockResolvedValue([]);
  api.listWorkspaceMembers.mockResolvedValue([]);
});

// ---------------------------------------------------------------------------
// Loading / display
// ---------------------------------------------------------------------------

describe("CommentPanel – loading state", () => {
  it("shows loading indicator while fetching", async () => {
    let resolve;
    api.listComments.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderPanel();
    expect(screen.getByText(/loading comments/i)).toBeInTheDocument();
    resolve([]);
  });
});

describe("CommentPanel – empty state", () => {
  it("shows empty state message when no comments", async () => {
    api.listComments.mockResolvedValue([]);
    renderPanel();
    await waitFor(() => expect(screen.getByText(/no comments yet/i)).toBeInTheDocument());
  });
});

describe("CommentPanel – error state", () => {
  it("shows error when fetch fails", async () => {
    api.listComments.mockRejectedValue(new Error("Network error"));
    renderPanel();
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument());
  });
});

describe("CommentPanel – comment display", () => {
  it("renders top-level comments", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    renderPanel();
    await waitFor(() => expect(screen.getByText("Top-level comment body")).toBeInTheDocument());
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders replies nested under their parent", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT, REPLY_COMMENT]);
    renderPanel();
    await waitFor(() => expect(screen.getByText("A reply")).toBeInTheDocument());
    expect(screen.getByText("Top-level comment body")).toBeInTheDocument();
  });

  it("shows the panel header title", async () => {
    api.listComments.mockResolvedValue([]);
    renderPanel();
    await waitFor(() => expect(screen.getByText("💬 Comments")).toBeInTheDocument());
  });
});

// ---------------------------------------------------------------------------
// Create comment
// ---------------------------------------------------------------------------

describe("CommentPanel – create comment", () => {
  it("submits a new comment when form is filled and Post clicked", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    api.createComment.mockResolvedValue({ id: "new-1", body: "Hello world", author_id: "user-1", parent_id: null, is_resolved: false });

    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));

    const textarea = screen.getByPlaceholderText(/add a comment/i);
    fireEvent.change(textarea, { target: { value: "Hello world" } });

    api.listComments.mockResolvedValue([TOP_COMMENT, { ...TOP_COMMENT, id: "new-1", body: "Hello world" }]);

    fireEvent.click(screen.getByRole("button", { name: /post/i }));

    await waitFor(() => expect(api.createComment).toHaveBeenCalledWith(
      WS_ID,
      CAMP_ID,
      expect.objectContaining({ body: "Hello world" })
    ));
  });

  it("Post button is disabled when textarea is empty", async () => {
    api.listComments.mockResolvedValue([]);
    renderPanel();
    await waitFor(() => screen.getByText(/no comments yet/i));
    const postBtn = screen.getByRole("button", { name: /post/i });
    expect(postBtn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Reply
// ---------------------------------------------------------------------------

describe("CommentPanel – reply", () => {
  it("shows reply form when Reply is clicked", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /reply to comment/i }));
    expect(screen.getByPlaceholderText(/write a reply/i)).toBeInTheDocument();
  });

  it("submits a reply with correct parent_id", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    api.createComment.mockResolvedValue({ id: "reply-1", body: "My reply", parent_id: TOP_COMMENT.id, is_resolved: false });
    api.listComments.mockResolvedValue([TOP_COMMENT, { ...REPLY_COMMENT, body: "My reply" }]);

    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /reply to comment/i }));
    fireEvent.change(screen.getByPlaceholderText(/write a reply/i), { target: { value: "My reply" } });
    fireEvent.click(screen.getByRole("button", { name: /^reply$/i }));

    await waitFor(() => expect(api.createComment).toHaveBeenCalledWith(
      WS_ID,
      CAMP_ID,
      expect.objectContaining({ parent_id: TOP_COMMENT.id, body: "My reply" })
    ));
  });
});

// ---------------------------------------------------------------------------
// Resolve / unresolve
// ---------------------------------------------------------------------------

describe("CommentPanel – resolve/unresolve", () => {
  it("calls resolveComment when Resolve is clicked", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    api.resolveComment.mockResolvedValue({});
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /resolve comment/i }));
    expect(api.resolveComment).toHaveBeenCalledWith(WS_ID, CAMP_ID, TOP_COMMENT.id, true);
  });

  it("calls resolveComment with false when Unresolve is clicked", async () => {
    const resolved = { ...TOP_COMMENT, is_resolved: true };
    api.listComments.mockResolvedValue([resolved]);
    api.resolveComment.mockResolvedValue({});
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /unresolve comment/i }));
    expect(api.resolveComment).toHaveBeenCalledWith(WS_ID, CAMP_ID, resolved.id, false);
  });
});

// ---------------------------------------------------------------------------
// Edit
// ---------------------------------------------------------------------------

describe("CommentPanel – edit", () => {
  it("shows edit form when Edit is clicked on own comment", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /edit comment/i }));
    expect(screen.getByDisplayValue("Top-level comment body")).toBeInTheDocument();
  });

  it("calls updateComment when edit is saved", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    api.updateComment.mockResolvedValue({});
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /edit comment/i }));
    const editArea = screen.getByDisplayValue("Top-level comment body");
    fireEvent.change(editArea, { target: { value: "Edited text" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(api.updateComment).toHaveBeenCalledWith(
      WS_ID,
      CAMP_ID,
      TOP_COMMENT.id,
      { body: "Edited text" }
    ));
  });

  it("edit button not shown for another user's comment", async () => {
    api.listComments.mockResolvedValue([OTHER_COMMENT]);
    renderPanel();
    await waitFor(() => screen.getByText("Another comment"));
    expect(screen.queryByRole("button", { name: /edit comment/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

describe("CommentPanel – delete", () => {
  it("calls deleteComment when delete is clicked on own comment", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    api.deleteComment.mockResolvedValue({});
    renderPanel();
    await waitFor(() => screen.getByText("Top-level comment body"));
    fireEvent.click(screen.getByRole("button", { name: /delete comment/i }));
    await waitFor(() => expect(api.deleteComment).toHaveBeenCalledWith(WS_ID, CAMP_ID, TOP_COMMENT.id));
  });

  it("delete button not shown for another user's comment", async () => {
    api.listComments.mockResolvedValue([OTHER_COMMENT]);
    renderPanel();
    await waitFor(() => screen.getByText("Another comment"));
    expect(screen.queryByRole("button", { name: /delete comment/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Read-only
// ---------------------------------------------------------------------------

describe("CommentPanel – read-only mode", () => {
  it("hides the compose form for read-only users", async () => {
    api.listComments.mockResolvedValue([]);
    renderPanel({ isReadOnly: true });
    await waitFor(() => screen.getByText(/no comments yet/i));
    expect(screen.queryByPlaceholderText(/add a comment/i)).not.toBeInTheDocument();
  });

  it("hides resolve/reply/edit/delete buttons for read-only users", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    renderPanel({ isReadOnly: true });
    await waitFor(() => screen.getByText("Top-level comment body"));
    expect(screen.queryByRole("button", { name: /resolve comment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reply to comment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit comment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete comment/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WebSocket events
// ---------------------------------------------------------------------------

describe("CommentPanel – WebSocket events", () => {
  it("re-fetches comments when a comment_added event is received", async () => {
    api.listComments.mockResolvedValue([TOP_COMMENT]);
    const { rerender } = renderPanel({ events: [] });
    await waitFor(() => screen.getByText("Top-level comment body"));

    const newComment = { ...OTHER_COMMENT, id: "cmt-new", body: "WebSocket new comment" };
    api.listComments.mockResolvedValue([TOP_COMMENT, newComment]);

    const newEvent = { event: "comment_added", comment: { id: "cmt-new" }, id: "evt-1", timestamp: "2024-01-01T00:00:00Z" };
    await act(async () => {
      rerender(
        <CommentPanel
          campaignId={CAMP_ID}
          workspaceId={WS_ID}
          isReadOnly={false}
          events={[newEvent]}
          isOpen
        />
      );
    });

    await waitFor(() => expect(api.listComments).toHaveBeenCalledTimes(2));
  });
});

// ---------------------------------------------------------------------------
// Close button
// ---------------------------------------------------------------------------

describe("CommentPanel – close button", () => {
  it("calls onClose when close button is clicked", async () => {
    api.listComments.mockResolvedValue([]);
    const onClose = vi.fn();
    renderPanel({ onClose });
    await waitFor(() => screen.getByText(/no comments yet/i));
    fireEvent.click(screen.getByRole("button", { name: /close comments panel/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// @mention autocomplete
// ---------------------------------------------------------------------------

const CAMPAIGN_MEMBERS = [
  { campaign_id: "camp-456", user_id: "u-alice", role: "editor", added_at: "2024-01-01T00:00:00Z" },
  { campaign_id: "camp-456", user_id: "u-bob", role: "viewer", added_at: "2024-01-01T00:00:00Z" },
];

const WORKSPACE_MEMBERS = [
  { workspace_id: "ws-123", user_id: "u-alice", role: "admin", added_at: "2024-01-01T00:00:00Z", display_name: "Alice Smith", email: "alice@example.com" },
  { workspace_id: "ws-123", user_id: "u-bob", role: "member", added_at: "2024-01-01T00:00:00Z", display_name: "Bob Jones", email: "bob@example.com" },
  { workspace_id: "ws-123", user_id: "u-charlie", role: "member", added_at: "2024-01-01T00:00:00Z", display_name: "Charlie", email: "charlie@example.com" },
];

function renderPanelWithMembers(props = {}) {
  api.listComments.mockResolvedValue([]);
  api.listCampaignMembers.mockResolvedValue(CAMPAIGN_MEMBERS);
  api.listWorkspaceMembers.mockResolvedValue(WORKSPACE_MEMBERS);
  return renderPanel(props);
}

describe("CommentPanel – @mention autocomplete", () => {
  it("fetches campaign members and workspace members on mount", async () => {
    renderPanelWithMembers();
    await waitFor(() => {
      expect(api.listCampaignMembers).toHaveBeenCalledWith("ws-123", "camp-456");
      expect(api.listWorkspaceMembers).toHaveBeenCalledWith("ws-123");
    });
  });

  it("shows autocomplete dropdown when @ is typed", async () => {
    renderPanelWithMembers();
    await waitFor(() => screen.getByText(/no comments yet/i));
    // Wait for members to load
    await waitFor(() => expect(api.listCampaignMembers).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(/add a comment/i);
    fireEvent.change(textarea, { target: { value: "@", selectionStart: 1 } });

    await waitFor(() => {
      expect(screen.getByRole("listbox", { name: /mention suggestions/i })).toBeInTheDocument();
    });
    // Only campaign members should appear (Alice and Bob, not Charlie)
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();
  });

  it("filters members as the user types after @", async () => {
    renderPanelWithMembers();
    await waitFor(() => screen.getByText(/no comments yet/i));
    await waitFor(() => expect(api.listCampaignMembers).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(/add a comment/i);
    fireEvent.change(textarea, { target: { value: "@ali", selectionStart: 4 } });

    await waitFor(() => {
      expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    });
    expect(screen.queryByText("Bob Jones")).not.toBeInTheDocument();
  });

  it("inserts mention token when a member is selected", async () => {
    renderPanelWithMembers();
    await waitFor(() => screen.getByText(/no comments yet/i));
    await waitFor(() => expect(api.listCampaignMembers).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(/add a comment/i);
    fireEvent.change(textarea, { target: { value: "@", selectionStart: 1 } });

    await waitFor(() => screen.getByText("Alice Smith"));
    fireEvent.mouseDown(screen.getByText("Alice Smith"));

    // Textarea should now contain the mention token
    await waitFor(() => {
      expect(textarea.value).toContain("@[u-alice:Alice Smith]");
    });
  });

  it("dismisses autocomplete when Escape is pressed", async () => {
    renderPanelWithMembers();
    await waitFor(() => screen.getByText(/no comments yet/i));
    await waitFor(() => expect(api.listCampaignMembers).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(/add a comment/i);
    fireEvent.change(textarea, { target: { value: "@", selectionStart: 1 } });

    await waitFor(() => screen.getByRole("listbox", { name: /mention suggestions/i }));

    fireEvent.keyDown(textarea, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: /mention suggestions/i })).not.toBeInTheDocument();
  });

  it("renders mentions in comment bodies as highlighted spans", async () => {
    const commentWithMention = {
      ...TOP_COMMENT,
      body: "Hey @[u-alice:Alice Smith] check this out",
    };
    api.listComments.mockResolvedValue([commentWithMention]);
    api.listCampaignMembers.mockResolvedValue(CAMPAIGN_MEMBERS);
    api.listWorkspaceMembers.mockResolvedValue(WORKSPACE_MEMBERS);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("@Alice Smith")).toBeInTheDocument();
    });
    const mentionSpan = screen.getByText("@Alice Smith");
    expect(mentionSpan).toHaveClass("mention-highlight");
    // Verify surrounding text renders alongside the mention
    const body = screen.getByText((_, el) =>
      el?.classList?.contains("comment-item-body") &&
      el.textContent.includes("Hey") &&
      el.textContent.includes("check this out")
    );
    expect(body).toBeInTheDocument();
  });
});
