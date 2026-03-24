/**
 * Tests for WorkspaceCalendar page.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import WorkspaceCalendar from '../pages/WorkspaceCalendar';

vi.mock('../api');
import * as api from '../api';

const WORKSPACE_ID = 'ws-1';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// Helper to get a date in the current month (for rendering in the visible grid)
function currentMonthDate(day = 10) {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function makeWsCalResponse(overrides = {}) {
  return {
    scheduled: [],
    ...overrides,
  };
}

function makeWsPiece({ campaignId = 'camp-1', campaignName = 'Alpha Campaign', pieceIndex = 0, content = 'Test post', channel = 'social_media', contentType = 'social_post', scheduledDate = null } = {}) {
  return {
    campaign_id: campaignId,
    campaign_name: campaignName,
    piece_index: pieceIndex,
    piece: {
      content_type: contentType,
      channel,
      content,
      variant: 'A',
      notes: '',
      approval_status: 'pending',
      scheduled_date: scheduledDate ?? currentMonthDate(10),
      scheduled_time: null,
      platform_target: null,
    },
  };
}

async function renderCalendar(calResponse = makeWsCalResponse()) {
  api.getWorkspaceCalendar.mockResolvedValue(calResponse);
  render(
    <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE_ID}/calendar`]}>
      <Routes>
        <Route path="/workspaces/:id/calendar" element={<WorkspaceCalendar />} />
        <Route path="/workspaces/:id" element={<div>Workspace Detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(api.getWorkspaceCalendar).toHaveBeenCalled());
}

describe('WorkspaceCalendar – basic rendering', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the calendar heading', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText(/Workspace Calendar/i)).toBeInTheDocument();
  });

  it('shows month navigation controls', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /previous month/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next month/i })).toBeInTheDocument();
  });

  it('shows weekday headers in the grid', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText('Sun')).toBeInTheDocument();
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Sat')).toBeInTheDocument();
  });

  it('shows the current month label', async () => {
    const today = new Date();
    const expectedLabel = `${MONTH_NAMES[today.getMonth()]} ${today.getFullYear()}`;
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it('renders a back link to the workspace', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByRole('link', { name: /back to workspace/i })).toBeInTheDocument();
  });
});

describe('WorkspaceCalendar – content pieces', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders scheduled content pieces with campaign name badge', async () => {
    const piece = makeWsPiece({ campaignName: 'Alpha Campaign', content: 'Summer sale post' });
    const calResponse = makeWsCalResponse({
      scheduled: [{ date: currentMonthDate(10), pieces: [piece] }],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByText('Summer sale post')).toBeInTheDocument();
    expect(screen.getByText('Alpha Campaign')).toBeInTheDocument();
  });

  it('renders pieces from multiple campaigns on the same day', async () => {
    const pieces = [
      makeWsPiece({ campaignId: 'camp-1', campaignName: 'Campaign A', content: 'Post A', pieceIndex: 0 }),
      makeWsPiece({ campaignId: 'camp-2', campaignName: 'Campaign B', content: 'Post B', pieceIndex: 0 }),
    ];
    const calResponse = makeWsCalResponse({
      scheduled: [{ date: currentMonthDate(10), pieces }],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByText('Post A')).toBeInTheDocument();
    expect(screen.getByText('Post B')).toBeInTheDocument();
    expect(screen.getByText('Campaign A')).toBeInTheDocument();
    expect(screen.getByText('Campaign B')).toBeInTheDocument();
  });

  it('shows empty grid when no pieces are scheduled', async () => {
    await renderCalendar(makeWsCalResponse({ scheduled: [] }));
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    // Grid should still render with weekday headers
    expect(screen.getByText('Sun')).toBeInTheDocument();
  });
});

describe('WorkspaceCalendar – month navigation', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('navigates to next month when Next button is clicked', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const today = new Date();
    const nextMonthIdx = today.getMonth() === 11 ? 0 : today.getMonth() + 1;
    const nextYear = today.getMonth() === 11 ? today.getFullYear() + 1 : today.getFullYear();

    fireEvent.click(screen.getByRole('button', { name: /next month/i }));

    await waitFor(() => {
      expect(screen.getByText(`${MONTH_NAMES[nextMonthIdx]} ${nextYear}`)).toBeInTheDocument();
    });
  });

  it('navigates to previous month when Prev button is clicked', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const today = new Date();
    const prevMonthIdx = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
    const prevYear = today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();

    fireEvent.click(screen.getByRole('button', { name: /previous month/i }));

    await waitFor(() => {
      expect(screen.getByText(`${MONTH_NAMES[prevMonthIdx]} ${prevYear}`)).toBeInTheDocument();
    });
  });

  it('re-fetches data when month changes', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const initialCallCount = api.getWorkspaceCalendar.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: /next month/i }));

    await waitFor(() => {
      expect(api.getWorkspaceCalendar.mock.calls.length).toBeGreaterThan(initialCallCount);
    });
  });
});

describe('WorkspaceCalendar – error state', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows error message when API call fails', async () => {
    api.getWorkspaceCalendar.mockRejectedValue(new Error('Network error'));
    render(
      <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE_ID}/calendar`]}>
        <Routes>
          <Route path="/workspaces/:id/calendar" element={<WorkspaceCalendar />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText(/Failed to load calendar/i));
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});
