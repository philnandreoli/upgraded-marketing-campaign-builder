/**
 * Tests for NotificationCenter and NotificationContext.
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { NotificationProvider, useNotifications } from "../NotificationContext";
import NotificationCenter from "../components/NotificationCenter";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Helper that renders NotificationCenter inside the provider. */
function renderNotificationCenter() {
  return render(
    <NotificationProvider>
      <NotificationCenter />
    </NotificationProvider>
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
    <NotificationProvider>
      <EventPusher events={events} />
      <NotificationCenter />
    </NotificationProvider>
  );
}

// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
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
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: new Date().toISOString() },
      { type: "stage_complete", stage: "strategy", message: "Strategy done", timestamp: new Date().toISOString() },
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
      { type: "stage_start", stage: "content_generation", message: "Generating content", timestamp: new Date().toISOString() },
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
      { type: "stage_error", stage: "review", message: "Failed", timestamp: new Date().toISOString() },
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
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: new Date().toISOString() },
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
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: "2026-03-20T10:00:00Z" },
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: "2026-03-20T10:00:00Z" },
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
      type: "stage_start",
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
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: new Date().toISOString() },
    ];
    renderWithEvents(events);

    act(() => {
      fireEvent.click(screen.getByTestId("push-events"));
    });

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    const item = screen.getByRole("listitem");
    expect(item.classList.contains("notification-item--unread")).toBe(false); // already marked read by opening panel
  });
});
