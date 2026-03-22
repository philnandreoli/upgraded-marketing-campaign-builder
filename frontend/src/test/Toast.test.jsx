/**
 * Tests for Toast hover-to-pause behavior.
 */

import { render, screen, act, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import Toast from "../components/Toast";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast – hover pause/resume", () => {
  it("renders a toast from an event", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByText("Starting strategy")).toBeInTheDocument();
    expect(screen.getByText("Strategy")).toBeInTheDocument();
  });

  it("auto-dismisses after DISPLAY_MS + EXIT_MS", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Advance past DISPLAY_MS (3500) + EXIT_MS (200)
    act(() => vi.advanceTimersByTime(3700));

    expect(screen.queryByText("Starting strategy")).not.toBeInTheDocument();
  });

  it("pauses dismiss timer on mouse enter and resumes on mouse leave", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    const toast = screen.getByText("Starting strategy").closest(".toast");

    // Advance 2000ms (less than 3500ms)
    act(() => vi.advanceTimersByTime(2000));

    // Mouse enter to pause
    act(() => {
      fireEvent.mouseEnter(toast);
    });

    // Even after waiting a long time, the toast should still be there
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Mouse leave to resume
    act(() => {
      fireEvent.mouseLeave(toast);
    });

    // Should still be visible for the remaining time (~1500ms)
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Advance past remaining + EXIT_MS
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByText("Starting strategy")).not.toBeInTheDocument();
  });

  it("has onMouseEnter and onMouseLeave handlers on toast elements", () => {
    const events = [
      { type: "stage_complete", stage: "content", message: "Content done", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    const toastEl = screen.getByText("Content done").closest(".toast");
    expect(toastEl).toBeInTheDocument();

    // Verify it doesn't throw when we fire the events
    expect(() => {
      fireEvent.mouseEnter(toastEl);
      fireEvent.mouseLeave(toastEl);
    }).not.toThrow();
  });
});

describe("Toast – type icons and type classes", () => {
  it("applies type class and renders type icon on a manual notification", () => {
    const notifications = [
      { id: "n1", type: "warning", icon: "⚠️", stage: "Workspace deleted", message: null },
    ];

    render(<Toast events={[]} notifications={notifications} />);

    const toast = screen.getByText("Workspace deleted").closest(".toast");
    expect(toast).toHaveClass("toast--warning");
    expect(screen.getByText("⚠️")).toBeInTheDocument();
  });

  it("renders without type class when type is absent", () => {
    const notifications = [
      { id: "n2", icon: "🗑️", stage: "Item removed", message: null },
    ];

    render(<Toast events={[]} notifications={notifications} />);

    const toast = screen.getByText("Item removed").closest(".toast");
    expect(toast.className).toBe("toast");
  });
});

describe("Toast – dismiss button", () => {
  it("renders a dismiss button on each event toast", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByRole("button", { name: /dismiss notification/i })).toBeInTheDocument();
  });

  it("clicking dismiss removes an event toast immediately", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByText("Starting")).toBeInTheDocument();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /dismiss notification/i }));
    });

    // Advance past EXIT_MS
    act(() => vi.advanceTimersByTime(300));

    expect(screen.queryByText("Starting")).not.toBeInTheDocument();
  });

  it("renders a dismiss button on manual notification toasts", () => {
    const notifications = [
      { id: "n3", icon: "🗑️", stage: "Deleted", message: null },
    ];

    render(<Toast events={[]} notifications={notifications} />);

    expect(screen.getByRole("button", { name: /dismiss notification/i })).toBeInTheDocument();
  });

  it("dismiss button is keyboard-focusable", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    const dismissBtn = screen.getByRole("button", { name: /dismiss notification/i });
    expect(dismissBtn.tabIndex).not.toBe(-1);
  });
});
