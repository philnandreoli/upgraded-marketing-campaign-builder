/**
 * Tests for the SavedViews system:
 *   - "Save view" button appears when filter/search is non-default
 *   - Saving a view persists to localStorage and renders as a chip
 *   - Clicking a saved view applies filter + search
 *   - Deleting a saved view removes it
 *   - Renaming a saved view updates its label
 *   - Max 10 user-created views enforced
 *   - URL params restore filter state on navigation
 *   - Saved views survive page refresh (localStorage persistence)
 */

import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, it, expect, beforeEach } from "vitest";
import Dashboard from "../pages/Dashboard";
import { UserProvider } from "../UserContext";
import { WorkspaceProvider } from "../WorkspaceContext";
import { ConfirmDialogProvider } from "../ConfirmDialogContext";
import { ToastProvider } from "../ToastContext";
import { SAVED_VIEWS_STORAGE_KEY, MAX_SAVED_VIEWS } from "../hooks/useSavedViews";

vi.mock("../api");
import * as api from "../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMeResponse({ userId = "user-sv" } = {}) {
  return {
    id: userId,
    email: "sv@example.com",
    display_name: "Saved Views User",
    roles: ["campaign_builder"],
    is_admin: false,
    can_build: true,
    is_viewer: false,
  };
}

const WS = {
  id: "ws-sv",
  name: "SV Workspace",
  is_personal: true,
  role: "creator",
};

const campaignDraft = {
  id: "c-draft",
  product_or_service: "DraftProduct",
  goal: "Draft goal",
  status: "strategy",
  owner_id: "user-sv",
  workspace_id: "ws-sv",
  workspace_name: "SV Workspace",
};

const campaignApproved = {
  id: "c-approved",
  product_or_service: "ApprovedProduct",
  goal: "Approved goal",
  status: "approved",
  owner_id: "user-sv",
  workspace_id: "ws-sv",
  workspace_name: "SV Workspace",
};

async function renderDashboard({ initialUrl = "/" } = {}, campaigns = [], workspaces = [WS]) {
  api.getMe.mockResolvedValue(makeMeResponse());
  api.listCampaigns.mockResolvedValue(campaigns);
  api.deleteCampaign.mockResolvedValue(undefined);
  api.listWorkspaces.mockResolvedValue(workspaces);

  render(
    <MemoryRouter initialEntries={[initialUrl]}>
      <UserProvider>
        <WorkspaceProvider>
          <ConfirmDialogProvider>
            <ToastProvider>
              <Dashboard events={[]} />
            </ToastProvider>
          </ConfirmDialogProvider>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>
  );

  await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
}

/** Advance fake timers by 300ms to trigger search debounce. */
async function typeSearch(value) {
  vi.useFakeTimers();
  fireEvent.change(screen.getByPlaceholderText("Search campaigns..."), {
    target: { value },
  });
  await act(async () => vi.advanceTimersByTime(300));
  vi.useRealTimers();
}

// ---------------------------------------------------------------------------
// Tests: Save current view button visibility
// ---------------------------------------------------------------------------

describe("SavedViews – Save button visibility", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('does not show "Save view" button when filter is "all" and search is empty', async () => {
    await renderDashboard({}, [campaignDraft]);
    await waitFor(() => screen.getByText("DraftProduct"));

    expect(screen.queryByRole("button", { name: /save current view/i })).not.toBeInTheDocument();
  });

  it('shows "Save view" button when a non-default filter is active', async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));

    expect(screen.getByRole("button", { name: /save current view/i })).toBeInTheDocument();
  });

  it('shows "Save view" button when search query is non-empty', async () => {
    await renderDashboard({}, [campaignDraft]);
    await waitFor(() => screen.getByText("DraftProduct"));

    await typeSearch("draft");

    expect(screen.getByRole("button", { name: /save current view/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Creating a saved view
// ---------------------------------------------------------------------------

describe("SavedViews – Creating views", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("opens a save dialog when the save button is clicked", async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

    expect(screen.getByRole("dialog", { name: /save current view/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("persists the saved view to localStorage and renders it as a chip", async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

    // Clear pre-filled name and type our own
    const nameInput = screen.getByRole("textbox", { name: /view name/i });
    fireEvent.change(nameInput, { target: { value: "My Approved View" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    // Dialog should close
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // New chip should appear
    expect(screen.getByRole("button", { name: /apply saved view: my approved view/i })).toBeInTheDocument();

    // Check localStorage
    const stored = JSON.parse(localStorage.getItem(SAVED_VIEWS_STORAGE_KEY));
    expect(stored).toHaveLength(1);
    expect(stored[0].name).toBe("My Approved View");
    expect(stored[0].filter).toBe("approved");
  });

  it("shows an error when attempting to save with an empty name", async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

    const nameInput = screen.getByRole("textbox", { name: /view name/i });
    fireEvent.change(nameInput, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/please enter a name/i);
  });

  it("cancel button closes the dialog without saving", async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
  });

  it("saves view via Enter key press", async () => {
    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

    const nameInput = screen.getByRole("textbox", { name: /view name/i });
    fireEvent.change(nameInput, { target: { value: "Keyboard Saved View" } });
    fireEvent.keyDown(nameInput, { key: "Enter" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply saved view: keyboard saved view/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Applying a saved view
// ---------------------------------------------------------------------------

describe("SavedViews – Applying views", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("clicking a saved view sets filter tab and search simultaneously", async () => {
    // Pre-populate localStorage with a saved view
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-1", name: "My Draft Search", filter: "in_progress", search: "draft" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("button", { name: /apply saved view: my draft search/i }));

    // Filter tab should be "In Progress"
    expect(screen.getByRole("tab", { name: "In Progress" })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    // Search input should contain "draft"
    expect(screen.getByPlaceholderText("Search campaigns...")).toHaveValue("draft");
  });
});

// ---------------------------------------------------------------------------
// Tests: Deleting a saved view
// ---------------------------------------------------------------------------

describe("SavedViews – Deleting views", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("delete button removes a saved view from localStorage and DOM", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([{ id: "sv-del", name: "To Delete", filter: "approved", search: "" }])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    expect(screen.getByRole("button", { name: /apply saved view: to delete/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete saved view: to delete/i }));

    expect(screen.queryByRole("button", { name: /apply saved view: to delete/i })).not.toBeInTheDocument();

    const stored = JSON.parse(localStorage.getItem(SAVED_VIEWS_STORAGE_KEY));
    expect(stored).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Tests: Renaming a saved view
// ---------------------------------------------------------------------------

describe("SavedViews – Renaming views", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("rename button puts the chip into edit mode and saves on Enter", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([{ id: "sv-ren", name: "Old Name", filter: "approved", search: "" }])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    fireEvent.click(screen.getByRole("button", { name: /rename view: old name/i }));

    const renameInput = screen.getByRole("textbox", { name: /rename view/i });
    fireEvent.change(renameInput, { target: { value: "New Name" } });
    fireEvent.keyDown(renameInput, { key: "Enter" });

    expect(screen.getByRole("button", { name: /apply saved view: new name/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply saved view: old name/i })).not.toBeInTheDocument();

    const stored = JSON.parse(localStorage.getItem(SAVED_VIEWS_STORAGE_KEY));
    expect(stored[0].name).toBe("New Name");
  });
});

// ---------------------------------------------------------------------------
// Tests: Max views limit
// ---------------------------------------------------------------------------

describe("SavedViews – Max views limit", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it(`hides the save button and shows a limit message at ${MAX_SAVED_VIEWS} saved views`, async () => {
    const maxViews = Array.from({ length: MAX_SAVED_VIEWS }, (_, i) => ({
      id: `sv-${i}`,
      name: `View ${i + 1}`,
      filter: "approved",
      search: "",
    }));
    localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, JSON.stringify(maxViews));

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Activate a non-default filter so save button would appear if limit not reached
    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));

    expect(screen.queryByRole("button", { name: /save current view/i })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/max 10 views reached/i);
  });
});

// ---------------------------------------------------------------------------
// Tests: URL state
// ---------------------------------------------------------------------------

describe("SavedViews – URL state", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("restores filter from URL ?status= param on load", async () => {
    await renderDashboard({ initialUrl: "/?status=approved" }, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("ApprovedProduct"));

    expect(screen.getByRole("tab", { name: "Approved" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("restores search query from URL ?q= param on load", async () => {
    await renderDashboard({ initialUrl: "/?q=draft" }, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    expect(screen.getByPlaceholderText("Search campaigns...")).toHaveValue("draft");
    // ApprovedProduct should be filtered out
    expect(screen.queryByText("ApprovedProduct")).not.toBeInTheDocument();
  });

  it("restores both filter and search from URL params", async () => {
    await renderDashboard(
      { initialUrl: "/?status=approved&q=approved" },
      [campaignDraft, campaignApproved]
    );
    await waitFor(() => screen.getByText("ApprovedProduct"));

    expect(screen.getByRole("tab", { name: "Approved" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByPlaceholderText("Search campaigns...")).toHaveValue("approved");
    expect(screen.queryByText("DraftProduct")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: localStorage persistence
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Tests: Active highlight
// ---------------------------------------------------------------------------

describe("SavedViews – Active highlight", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("highlights the saved view chip whose filter+search matches the current state", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-h1", name: "Approved View", filter: "approved", search: "" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Switch to the Approved tab — now matches the saved view
    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));

    const chip = screen.getByRole("button", { name: /apply saved view: approved view/i }).closest(".saved-view-chip--user");
    expect(chip).toHaveClass("saved-view-chip--active");
  });

  it("does not highlight a saved view when the current state does not match any view", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-h2", name: "Approved View", filter: "approved", search: "" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Default state is "all" + empty search — does not match the saved view
    const chip = screen.getByRole("button", { name: /apply saved view: approved view/i }).closest(".saved-view-chip--user");
    expect(chip).not.toHaveClass("saved-view-chip--active");
  });

  it("updates highlight when the user changes the filter to match a different saved view", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-h3", name: "Approved View", filter: "approved", search: "" },
        { id: "sv-h4", name: "In Progress View", filter: "in_progress", search: "" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Activate Approved tab
    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));

    const approvedChip = screen.getByRole("button", { name: /apply saved view: approved view/i }).closest(".saved-view-chip--user");
    const progressChip = screen.getByRole("button", { name: /apply saved view: in progress view/i }).closest(".saved-view-chip--user");

    expect(approvedChip).toHaveClass("saved-view-chip--active");
    expect(progressChip).not.toHaveClass("saved-view-chip--active");

    // Now switch to In Progress tab
    fireEvent.click(screen.getByRole("tab", { name: "In Progress" }));

    expect(approvedChip).not.toHaveClass("saved-view-chip--active");
    expect(progressChip).toHaveClass("saved-view-chip--active");
  });

  it("clears highlight when the user modifies the search away from any saved view", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-h5", name: "Approved View", filter: "approved", search: "" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Match the saved view
    fireEvent.click(screen.getByRole("tab", { name: "Approved" }));
    const chip = screen.getByRole("button", { name: /apply saved view: approved view/i }).closest(".saved-view-chip--user");
    expect(chip).toHaveClass("saved-view-chip--active");

    // Type a search query — now it no longer matches
    await typeSearch("something");
    expect(chip).not.toHaveClass("saved-view-chip--active");
  });

  it("highlights a saved view that includes a search query when both filter and search match", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([
        { id: "sv-h6", name: "Draft Search", filter: "all", search: "draft" },
      ])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    // Initially no highlight (search is empty)
    const chip = screen.getByRole("button", { name: /apply saved view: draft search/i }).closest(".saved-view-chip--user");
    expect(chip).not.toHaveClass("saved-view-chip--active");

    // Type the matching search query
    await typeSearch("draft");
    expect(chip).toHaveClass("saved-view-chip--active");
  });
});

describe("SavedViews – Persistence across refresh", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("saved views persisted in localStorage are rendered on next load", async () => {
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify([{ id: "persist-1", name: "Persisted View", filter: "approved", search: "" }])
    );

    await renderDashboard({}, [campaignDraft, campaignApproved]);
    await waitFor(() => screen.getByText("DraftProduct"));

    expect(screen.getByRole("button", { name: /apply saved view: persisted view/i })).toBeInTheDocument();
  });
});
