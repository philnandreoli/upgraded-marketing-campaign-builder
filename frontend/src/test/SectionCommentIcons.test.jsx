/**
 * Tests for per-section comment icons and inline indicators.
 *
 * Covers:
 *  - Each section renders a clickable comment icon button
 *  - Comment icon shows unresolved count badge when count > 0
 *  - Comment icon hides badge when count is 0
 *  - Clicking the icon calls the onOpenComments handler
 *  - ContentSection renders per-piece comment indicators
 *  - Per-piece indicators show count badges when count > 0
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import StrategySection from "../components/StrategySection.jsx";
import ChannelPlanSection from "../components/ChannelPlanSection.jsx";
import AnalyticsSection from "../components/AnalyticsSection.jsx";
import ContentSection from "../components/ContentSection.jsx";

// Mock context hooks used by ContentSection
vi.mock("../ConfirmDialogContext", () => ({
  useConfirm: () => vi.fn(),
}));
vi.mock("../ToastContext", () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));
vi.mock("../NotificationContext", () => ({
  useNotifications: () => ({ addEvent: vi.fn() }),
}));
vi.mock("../api");

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const STRATEGY_DATA = {
  value_proposition: "Best product ever",
  objectives: ["Increase awareness"],
};

const CHANNEL_DATA = {
  total_budget: 10000,
  currency: "USD",
  recommendations: [
    { channel: "social_media", budget_pct: 60, rationale: "High reach" },
  ],
};

const ANALYTICS_DATA = {
  reporting_cadence: "Weekly",
  kpis: [{ name: "CTR", target_value: "5%" }],
};

const CONTENT_DATA = {
  theme: "Summer Sale",
  tone_of_voice: "Energetic",
  pieces: [
    { content_type: "social_post", content: "Check out our new product!" },
    { content_type: "headline", content: "Big Sale This Weekend" },
  ],
};

// ---------------------------------------------------------------------------
// beforeEach
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.resetAllMocks();
});

// ---------------------------------------------------------------------------
// StrategySection comment icon
// ---------------------------------------------------------------------------

describe("StrategySection – comment icon", () => {
  it("renders a comment icon button when onOpenComments is provided", () => {
    render(<StrategySection data={STRATEGY_DATA} onOpenComments={() => {}} />);
    expect(screen.getByRole("button", { name: /open strategy comments/i })).toBeInTheDocument();
  });

  it("does not render a comment icon when onOpenComments is not provided", () => {
    render(<StrategySection data={STRATEGY_DATA} />);
    expect(screen.queryByRole("button", { name: /open strategy comments/i })).not.toBeInTheDocument();
  });

  it("shows unresolved count badge when unresolvedCount > 0", () => {
    render(<StrategySection data={STRATEGY_DATA} onOpenComments={() => {}} unresolvedCount={3} />);
    expect(screen.getByTestId("strategy-comment-count")).toHaveTextContent("3");
  });

  it("hides count badge when unresolvedCount is 0", () => {
    render(<StrategySection data={STRATEGY_DATA} onOpenComments={() => {}} unresolvedCount={0} />);
    expect(screen.queryByTestId("strategy-comment-count")).not.toBeInTheDocument();
  });

  it("calls onOpenComments when icon is clicked", () => {
    const handler = vi.fn();
    render(<StrategySection data={STRATEGY_DATA} onOpenComments={handler} />);
    fireEvent.click(screen.getByRole("button", { name: /open strategy comments/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it("renders comment icon in loading state", () => {
    render(<StrategySection data={null} onOpenComments={() => {}} unresolvedCount={1} />);
    expect(screen.getByRole("button", { name: /open strategy comments/i })).toBeInTheDocument();
    expect(screen.getByTestId("strategy-comment-count")).toHaveTextContent("1");
  });

  it("renders comment icon in error state", () => {
    render(<StrategySection data={null} error="Something went wrong" onOpenComments={() => {}} />);
    expect(screen.getByRole("button", { name: /open strategy comments/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ChannelPlanSection comment icon
// ---------------------------------------------------------------------------

describe("ChannelPlanSection – comment icon", () => {
  it("renders a comment icon button when onOpenComments is provided", () => {
    render(<ChannelPlanSection data={CHANNEL_DATA} onOpenComments={() => {}} />);
    expect(screen.getByRole("button", { name: /open channel plan comments/i })).toBeInTheDocument();
  });

  it("does not render a comment icon when onOpenComments is not provided", () => {
    render(<ChannelPlanSection data={CHANNEL_DATA} />);
    expect(screen.queryByRole("button", { name: /open channel plan comments/i })).not.toBeInTheDocument();
  });

  it("shows unresolved count badge when unresolvedCount > 0", () => {
    render(<ChannelPlanSection data={CHANNEL_DATA} onOpenComments={() => {}} unresolvedCount={5} />);
    expect(screen.getByTestId("channel_plan-comment-count")).toHaveTextContent("5");
  });

  it("hides count badge when unresolvedCount is 0", () => {
    render(<ChannelPlanSection data={CHANNEL_DATA} onOpenComments={() => {}} unresolvedCount={0} />);
    expect(screen.queryByTestId("channel_plan-comment-count")).not.toBeInTheDocument();
  });

  it("calls onOpenComments when icon is clicked", () => {
    const handler = vi.fn();
    render(<ChannelPlanSection data={CHANNEL_DATA} onOpenComments={handler} />);
    fireEvent.click(screen.getByRole("button", { name: /open channel plan comments/i }));
    expect(handler).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// AnalyticsSection comment icon
// ---------------------------------------------------------------------------

describe("AnalyticsSection – comment icon", () => {
  it("renders a comment icon button when onOpenComments is provided", () => {
    render(<AnalyticsSection data={ANALYTICS_DATA} onOpenComments={() => {}} />);
    expect(screen.getByRole("button", { name: /open analytics comments/i })).toBeInTheDocument();
  });

  it("does not render a comment icon when onOpenComments is not provided", () => {
    render(<AnalyticsSection data={ANALYTICS_DATA} />);
    expect(screen.queryByRole("button", { name: /open analytics comments/i })).not.toBeInTheDocument();
  });

  it("shows unresolved count badge when unresolvedCount > 0", () => {
    render(<AnalyticsSection data={ANALYTICS_DATA} onOpenComments={() => {}} unresolvedCount={2} />);
    expect(screen.getByTestId("analytics-comment-count")).toHaveTextContent("2");
  });

  it("hides count badge when unresolvedCount is 0", () => {
    render(<AnalyticsSection data={ANALYTICS_DATA} onOpenComments={() => {}} unresolvedCount={0} />);
    expect(screen.queryByTestId("analytics-comment-count")).not.toBeInTheDocument();
  });

  it("calls onOpenComments when icon is clicked", () => {
    const handler = vi.fn();
    render(<AnalyticsSection data={ANALYTICS_DATA} onOpenComments={handler} />);
    fireEvent.click(screen.getByRole("button", { name: /open analytics comments/i }));
    expect(handler).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// ContentSection comment icon (section-level)
// ---------------------------------------------------------------------------

describe("ContentSection – section comment icon", () => {
  it("renders a section comment icon when onOpenComments is provided", () => {
    render(<ContentSection data={CONTENT_DATA} onOpenComments={() => {}} />);
    expect(screen.getByRole("button", { name: /open content comments/i })).toBeInTheDocument();
  });

  it("does not render a section comment icon when onOpenComments is not provided", () => {
    render(<ContentSection data={CONTENT_DATA} />);
    expect(screen.queryByRole("button", { name: /open content comments/i })).not.toBeInTheDocument();
  });

  it("shows section unresolved count badge when unresolvedCount > 0", () => {
    render(<ContentSection data={CONTENT_DATA} onOpenComments={() => {}} unresolvedCount={4} />);
    expect(screen.getByTestId("content-comment-count")).toHaveTextContent("4");
  });

  it("hides section count badge when unresolvedCount is 0", () => {
    render(<ContentSection data={CONTENT_DATA} onOpenComments={() => {}} unresolvedCount={0} />);
    expect(screen.queryByTestId("content-comment-count")).not.toBeInTheDocument();
  });

  it("calls onOpenComments when section icon is clicked", () => {
    const handler = vi.fn();
    render(<ContentSection data={CONTENT_DATA} onOpenComments={handler} />);
    fireEvent.click(screen.getByRole("button", { name: /open content comments/i }));
    expect(handler).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// ContentSection per-piece comment indicators
// ---------------------------------------------------------------------------

describe("ContentSection – per-piece comment indicators", () => {
  it("renders a comment button for each piece when onOpenPieceComments is provided", () => {
    render(
      <ContentSection
        data={CONTENT_DATA}
        onOpenPieceComments={() => {}}
        pieceCommentCounts={{}}
      />
    );
    expect(screen.getByTestId("piece-comment-btn-0")).toBeInTheDocument();
    expect(screen.getByTestId("piece-comment-btn-1")).toBeInTheDocument();
  });

  it("does not render piece comment buttons when onOpenPieceComments is not provided", () => {
    render(<ContentSection data={CONTENT_DATA} />);
    expect(screen.queryByTestId("piece-comment-btn-0")).not.toBeInTheDocument();
  });

  it("shows per-piece count badge when pieceCommentCounts > 0", () => {
    render(
      <ContentSection
        data={CONTENT_DATA}
        onOpenPieceComments={() => {}}
        pieceCommentCounts={{ 0: 3, 1: 0 }}
      />
    );
    expect(screen.getByTestId("piece-comment-count-0")).toHaveTextContent("3");
    expect(screen.queryByTestId("piece-comment-count-1")).not.toBeInTheDocument();
  });

  it("calls onOpenPieceComments with piece index when clicked", () => {
    const handler = vi.fn();
    render(
      <ContentSection
        data={CONTENT_DATA}
        onOpenPieceComments={handler}
        pieceCommentCounts={{}}
      />
    );
    fireEvent.click(screen.getByTestId("piece-comment-btn-0"));
    expect(handler).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByTestId("piece-comment-btn-1"));
    expect(handler).toHaveBeenCalledWith(1);
  });
});
