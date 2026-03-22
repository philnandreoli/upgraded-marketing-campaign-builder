/**
 * Tests for NotificationCenter and NotificationContext.
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { NotificationProvider, useNotifications } from "../NotificationContext";
import NotificationCenter from "../components/NotificationCenter";

// ---------------------------------------------------------------------------
// Navigate mock (hoisted so the vi.mock factory can reference it)
// ---------------------------------------------------------------------------

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importActual) => {
  const actual = await importActual();
  return { ...actual, useNavigate: () => navigateMock };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Helper that renders NotificationCenter inside the provider (with router). */
function renderNotificationCenter() {
  return render(
    <MemoryRouter>
      <NotificationProvider>
        <NotificationCenter />
      </NotificationProvider>
    </MemoryRouter>
  );
}

/** Helper component that pushes events via useNotifications. */
function EventPusher({ events }) {
  const { addEvent } = useNotifications();
  return (
    <button
      data-testid="push-events"
      onClick={() => events.forEach((e) => addEvent(e))}
    >
      Push
    </button>
  );
}

function renderWithEvents(events = []) {
  return render(
    <MemoryRouter>
      <NotificationProvider>
        <EventPusher events={events} />
        <NotificationCenter />
      </NotificationProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  navigateMock.mockReset();
});

describe("NotificationCenter", () => {
  it("renders a bell icon button", () => {
    renderNotificationCenter();
    expect(screen.getByRole("button", { name: /notifications/i })).toBeInTheDocument();
  });

  it("does not show badge when there are no notifications", () => {
    renderNotificationCenter();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    // No element with the badge class should exist
    const bell = screen.getByRole("button", { name: /notifications/i });
    expect(bell.querySelector(".notification-badge")).toBeNull();
  });

  it("shows dropdown with empty state when clicked with no events", () => {
    renderNotificationCenter();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByText("No notifications yet")).toBeInTheDocument();
  });

  it("shows unread badge after events are pushed", () => {
    const events = [
      { event: "stage_started", stage: "strategy", message: "Starting strategy", timestamp: new Date().toISOString() },
      { event: "stage_completed", stage: "strategy", message: "Strategy done", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    // Push the events
    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    const bell = screen.getByRole("button", { name: /notifications.*2 unread/i });
    expect(bell).toBeInTheDocument();
    expect(bell.querySelector(".notification-badge")).toHaveTextContent("2");
  });

  it("shows events in the dropdown with stage, message, and timestamp", () => {
    const events = [
      { event: "stage_started", stage: "content_generation", message: "Generating content", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    // Open the dropdown
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("Content Generation")).toBeInTheDocument();
    expect(screen.getByText("Generating content")).toBeInTheDocument();
    expect(screen.getByText("just now")).toBeInTheDocument();
  });

  it("shows correct event icons", () => {
    const events = [
      { event: "stage_error", stage: "review", message: "Failed", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("❌")).toBeInTheDocument();
  });

  it("marks all notifications as read when dropdown is opened", () => {
    const events = [
      { event: "stage_started", stage: "strategy", message: "Starting", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    // Badge should show 1
    expect(screen.getByRole("button", { name: /1 unread/i })).toBeInTheDocument();

    // Open the dropdown — should reset the count
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    // Badge should disappear
    const bell = screen.getByRole("button", { name: /notifications/i });
    expect(bell.querySelector(".notification-badge")).toBeNull();
  });

  it("closes dropdown when clicking outside", () => {
    renderNotificationCenter();

    // Open
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByText("No notifications yet")).toBeInTheDocument();

    // Click outside
    fireEvent.mouseDown(document.body);

    expect(screen.queryByText("No notifications yet")).not.toBeInTheDocument();
  });

  it("closes dropdown on Escape key", () => {
    renderNotificationCenter();

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByText("No notifications yet")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByText("No notifications yet")).not.toBeInTheDocument();
  });

  it("deduplicates events by key", () => {
    const events = [
      { event: "stage_started", stage: "strategy", message: "Starting", timestamp: "2026-03-20T10:00:00Z" },
      { event: "stage_started", stage: "strategy", message: "Starting", timestamp: "2026-03-20T10:00:00Z" },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    // Should only have 1 unread
    const bell = screen.getByRole("button", { name: /1 unread/i });
    expect(bell).toBeInTheDocument();
  });

  it("limits stored notifications to 20", () => {
    const events = Array.from({ length: 25 }, (_, i) => ({
      event: "stage_started",
      stage: `stage_${i}`,
      message: `Message ${i}`,
      timestamp: new Date(Date.now() + i * 1000).toISOString(),
    }));
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    const items = screen.getAllByRole("listitem");
    expect(items.length).toBe(20);
  });

  it("marks individual notification as read on click", () => {
    const events = [
      { event: "stage_started", stage: "strategy", message: "Starting", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    const item = screen.getByRole("listitem");
    expect(item.classList.contains("notification-item--unread")).toBe(false); // already marked read by opening panel
  });
  // -----------------------------------------------------------------------
  // Backend event shape coverage (event field, not type)
  // -----------------------------------------------------------------------

  it("shows fallback message for pipeline_started event with no explicit message", () => {
    const events = [
      { event: "pipeline_started", campaign_id: "abc123", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("Pipeline started")).toBeInTheDocument();
  });

  it("shows fallback message for pipeline_completed event with no explicit message", () => {
    const events = [
      { event: "pipeline_completed", campaign_id: "abc123", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("Pipeline completed")).toBeInTheDocument();
  });

  it("derives 'Started {Stage}' fallback for stage_started with no message", () => {
    const events = [
      { event: "stage_started", event_type: "stage_started", campaign_id: "abc", stage: "strategy", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("Started Strategy")).toBeInTheDocument();
  });

  it("resolves event kind from event field and shows correct icon", () => {
    const events = [
      { event: "stage_completed", stage: "strategy", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("✅")).toBeInTheDocument();
  });

  it("shows 🚀 icon for pipeline_started event", () => {
    const events = [
      { event: "pipeline_started", campaign_id: "abc", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("🚀")).toBeInTheDocument();
  });

  it("shows clarification_requested notification with correct text and icon", () => {
    const events = [
      { event: "clarification_requested", campaign_id: "abc", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("❓")).toBeInTheDocument();
    expect(screen.getByText("Clarification requested")).toBeInTheDocument();
  });

  it("never renders a blank notification item (no empty body)", () => {
    // Minimal backend-shape event with no stage, no message, no detail
    const events = [
      { event: "pipeline_started", campaign_id: "abc", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    const body = document.querySelector(".notification-item-body");
    expect(body).not.toBeNull();
    expect(body.textContent.trim()).not.toBe("");
  });

  // -----------------------------------------------------------------------
  // Navigation behaviour
  // -----------------------------------------------------------------------

  it("navigates to campaign route when clicking a notification with both IDs", () => {
    const events = [
      {
        event: "pipeline_completed",
        campaign_id: "camp-42",
        workspace_id: "ws-7",
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    fireEvent.click(screen.getByRole("listitem"));

    expect(navigateMock).toHaveBeenCalledWith("/workspaces/ws-7/campaigns/camp-42");
  });

  it("closes the dropdown after navigating", () => {
    const events = [
      {
        event: "pipeline_completed",
        campaign_id: "camp-42",
        workspace_id: "ws-7",
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByRole("region", { name: /notification history/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("listitem"));

    expect(screen.queryByRole("region", { name: /notification history/i })).not.toBeInTheDocument();
  });

  it("does not navigate when notification is missing workspace_id", () => {
    const events = [
      {
        event: "pipeline_started",
        campaign_id: "camp-1",
        // no workspace_id
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    fireEvent.click(screen.getByRole("listitem"));

    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("does not navigate when notification is missing campaign_id", () => {
    const events = [
      {
        event: "pipeline_started",
        workspace_id: "ws-1",
        // no campaign_id
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    fireEvent.click(screen.getByRole("listitem"));

    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("marks notification as read even when no navigation occurs", () => {
    const events = [
      {
        event: "pipeline_started",
        campaign_id: "camp-1",
        // no workspace_id — no navigation
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithEvents(events);

    act(() => { fireEvent.click(screen.getByTestId("push-events")); });

    // Open panel — this marks all as read via markAllRead
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    const item = screen.getByRole("listitem");
    // After opening, unread styling should be gone
    expect(item.classList.contains("notification-item--unread")).toBe(false);
  });
});
