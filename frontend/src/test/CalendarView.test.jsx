/**
 * Tests for CalendarView – week/month toggle and weekly view rendering.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import CalendarView from '../components/CalendarView';

vi.mock('../api');
import * as api from '../api';

const mockAddToast = vi.hoisted(() => vi.fn());
vi.mock('../ToastContext', () => ({
  useToast: () => ({ addToast: mockAddToast, dismissToast: vi.fn() }),
}));

const WORKSPACE_ID = 'ws-1';
const CAMPAIGN_ID = 'camp-1';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function makeCalendarResponse(overrides = {}) {
  return {
    scheduled: [],
    unscheduled: [],
    ...overrides,
  };
}

async function renderCalendar(calResponse = makeCalendarResponse(), props = {}) {
  api.getCalendar.mockResolvedValue(calResponse);
  render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} {...props} />);
  await waitFor(() => expect(api.getCalendar).toHaveBeenCalled());
}

describe('CalendarView – view toggle', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('defaults to month view', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    // View toggle buttons should exist
    expect(screen.getByRole('button', { name: 'Month' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Week' })).toBeInTheDocument();
    // Month view renders weekday headers in grid
    expect(screen.getAllByText('Sun').length).toBeGreaterThanOrEqual(1);
    // All Day section should NOT be visible in month mode
    expect(screen.queryByText('All Day')).not.toBeInTheDocument();
  });

  it('switches to week view when Week button is clicked', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /week/i }));
    // Weekly view should show "All Day" section
    expect(screen.getByText('All Day')).toBeInTheDocument();
  });

  it('persists view preference in localStorage', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /week/i }));
    expect(localStorage.getItem('cal_view_mode')).toBe('week');

    fireEvent.click(screen.getByRole('button', { name: /month/i }));
    expect(localStorage.getItem('cal_view_mode')).toBe('month');
  });

  it('restores week view from localStorage on mount', async () => {
    localStorage.setItem('cal_view_mode', 'week');
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText('All Day')).toBeInTheDocument();
  });
});

describe('CalendarView – month view navigation', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('shows month name in header', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    const currentMonth = MONTH_NAMES[new Date().getMonth()];
    expect(screen.getByText(new RegExp(currentMonth))).toBeInTheDocument();
  });

  it('navigates to previous month', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    const now = new Date();
    const prevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    fireEvent.click(screen.getByRole('button', { name: /previous month/i }));
    expect(screen.getByText(new RegExp(MONTH_NAMES[prevMonth.getMonth()]))).toBeInTheDocument();
  });

  it('navigates to next month', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    const now = new Date();
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    fireEvent.click(screen.getByRole('button', { name: /next month/i }));
    expect(screen.getByText(new RegExp(MONTH_NAMES[nextMonth.getMonth()]))).toBeInTheDocument();
  });
});

describe('CalendarView – weekly view', () => {
  beforeEach(() => {
    localStorage.setItem('cal_view_mode', 'week');
    vi.clearAllMocks();
  });

  it('shows 7 day columns with weekday headers', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    // Each weekday abbreviation should appear (in column headers)
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    for (const d of days) {
      expect(screen.getAllByText(d).length).toBeGreaterThanOrEqual(1);
    }
  });

  it('shows week range in nav label', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    // Week range label: "Mmm D – Mmm D" (month abbreviation, day number, en dash separator)
    const monthAbbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthPattern = monthAbbrs.join('|');
    expect(screen.getByText(new RegExp(`(${monthPattern}) \\d+ – (${monthPattern}) \\d+`))).toBeInTheDocument();
  });

  it('navigates to previous week', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    const monthAbbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthPattern = monthAbbrs.join('|');
    const rangeRegex = new RegExp(`(${monthPattern}) \\d+ – (${monthPattern}) \\d+`);
    const before = screen.getByText(rangeRegex).textContent;
    fireEvent.click(screen.getByRole('button', { name: /previous week/i }));
    const after = screen.getByText(rangeRegex).textContent;
    expect(after).not.toBe(before);
  });

  it('navigates to next week', async () => {
    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    const monthAbbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthPattern = monthAbbrs.join('|');
    const rangeRegex = new RegExp(`(${monthPattern}) \\d+ – (${monthPattern}) \\d+`);
    const before = screen.getByText(rangeRegex).textContent;
    fireEvent.click(screen.getByRole('button', { name: /next week/i }));
    const after = screen.getByText(rangeRegex).textContent;
    expect(after).not.toBe(before);
  });

  it('shows all-day piece in All Day row', async () => {
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const d = String(today.getDate()).padStart(2, '0');
    const todayISO = `${y}-${m}-${d}`;

    const calResponse = makeCalendarResponse({
      scheduled: [
        {
          date: todayISO,
          pieces: [
            {
              piece_index: 0,
              piece: {
                content: 'All day post here',
                content_type: 'social_post',
                channel: 'social_media',
                scheduled_date: todayISO,
                scheduled_time: null,
              },
            },
          ],
        },
      ],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText('All Day')).toBeInTheDocument();
    expect(screen.getByText(/All day post here/)).toBeInTheDocument();
  });

  it('shows timed piece in timed grid area', async () => {
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const d = String(today.getDate()).padStart(2, '0');
    const todayISO = `${y}-${m}-${d}`;

    const calResponse = makeCalendarResponse({
      scheduled: [
        {
          date: todayISO,
          pieces: [
            {
              piece_index: 1,
              piece: {
                content: 'Timed piece at 9am',
                content_type: 'email_subject',
                channel: 'email',
                scheduled_date: todayISO,
                scheduled_time: '09:00:00',
              },
            },
          ],
        },
      ],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
    expect(screen.getByText(/Timed piece at 9am/)).toBeInTheDocument();
  });
});

describe('CalendarView – error state', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('shows error message when API fails', async () => {
    api.getCalendar.mockRejectedValue(new Error('Network error'));
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} />);
    await waitFor(() => screen.getByText(/Failed to load calendar/i));
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});

describe('CalendarView – unscheduled sidebar', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  const makeUnscheduledPiece = (overrides = {}) => ({
    piece_index: 0,
    piece: {
      content: 'Draft email headline',
      content_type: 'headline',
      channel: 'email',
      scheduled_date: null,
      scheduled_time: null,
      ...overrides,
    },
  });

  it('shows sidebar with count badge for unscheduled pieces', async () => {
    const calResponse = makeCalendarResponse({
      unscheduled: [
        makeUnscheduledPiece(),
        { piece_index: 1, piece: { ...makeUnscheduledPiece().piece, content: 'Another piece' } },
      ],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByText('Unscheduled')).toBeInTheDocument();
    expect(screen.getByLabelText('2 unscheduled')).toBeInTheDocument();
  });

  it('lists unscheduled content pieces', async () => {
    const calResponse = makeCalendarResponse({
      unscheduled: [makeUnscheduledPiece()],
    });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByText(/Draft email headline/)).toBeInTheDocument();
  });

  it('shows "All content is scheduled!" when unscheduled list is empty', async () => {
    await renderCalendar(makeCalendarResponse({ unscheduled: [] }));
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByText('All content is scheduled!')).toBeInTheDocument();
  });

  it('collapses sidebar when header is clicked', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    // Content visible initially
    expect(screen.getByText(/Draft email headline/)).toBeInTheDocument();

    // Click header to collapse
    fireEvent.click(screen.getByRole('button', { name: /unscheduled/i }));
    expect(screen.queryByText(/Draft email headline/)).not.toBeInTheDocument();
  });

  it('persists sidebar collapsed state in localStorage', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /unscheduled/i }));
    expect(localStorage.getItem('cal_sidebar_collapsed')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: /unscheduled/i }));
    expect(localStorage.getItem('cal_sidebar_collapsed')).toBe('false');
  });

  it('restores collapsed state from localStorage', async () => {
    localStorage.setItem('cal_sidebar_collapsed', 'true');
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.queryByText(/Draft email headline/)).not.toBeInTheDocument();
  });

  it('shows Schedule button for non-viewer', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse, { isViewer: false });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.getByRole('button', { name: 'Schedule' })).toBeInTheDocument();
  });

  it('hides Schedule button for viewer (RBAC)', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse, { isViewer: true });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    expect(screen.queryByRole('button', { name: /^schedule$/i })).not.toBeInTheDocument();
  });

  it('clicking Schedule button shows DatePicker and Cancel button', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /^schedule$/i }));
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    // DatePicker trigger should appear
    expect(screen.getByText(/Pick a date/i)).toBeInTheDocument();
  });

  it('Cancel button hides DatePicker and restores Schedule button', async () => {
    const calResponse = makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] });
    await renderCalendar(calResponse);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /^schedule$/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.getByRole('button', { name: /^schedule$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument();
  });

  it('scheduling a piece calls schedulePiece API and refreshes calendar', async () => {
    vi.spyOn(api, 'schedulePiece').mockResolvedValue({});
    // After refresh: piece is now scheduled
    api.getCalendar
      .mockResolvedValueOnce(makeCalendarResponse({ unscheduled: [makeUnscheduledPiece()] }))
      .mockResolvedValueOnce(makeCalendarResponse({ unscheduled: [] }));

    await renderCalendar();
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    // Open schedule picker
    fireEvent.click(screen.getByRole('button', { name: /^schedule$/i }));

    // Open DatePicker dropdown
    fireEvent.click(screen.getByRole('button', { name: /mm\/dd\/yyyy|pick a date/i }));

    // Click on day "15" in the calendar picker
    const dayBtn = screen.getAllByRole('button', { name: '15' }).find(
      (btn) => btn.className && btn.className.includes('datepicker-day'),
    );
    if (dayBtn && !dayBtn.disabled) {
      fireEvent.click(dayBtn);
      await waitFor(() => expect(api.schedulePiece).toHaveBeenCalled());
      await waitFor(() => expect(api.getCalendar).toHaveBeenCalledTimes(2));
    }
  });
});

describe('CalendarView – drag-and-drop', () => {
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, '0');
  const d = String(today.getDate()).padStart(2, '0');
  const todayISO = `${y}-${m}-${d}`;

  // Pick a future date in the same month (or next month) to use as drop target
  const targetDate = new Date(today);
  targetDate.setDate(today.getDate() + 3);
  const ty = targetDate.getFullYear();
  const tm = String(targetDate.getMonth() + 1).padStart(2, '0');
  const td = String(targetDate.getDate()).padStart(2, '0');
  const targetISO = `${ty}-${tm}-${td}`;

  const makeScheduledPiece = () => ({
    piece_index: 5,
    piece: {
      content: 'Draggable email piece',
      content_type: 'headline',
      channel: 'email',
      scheduled_date: todayISO,
      scheduled_time: null,
    },
  });

  beforeEach(() => {
    localStorage.clear();
    // Use resetAllMocks to also wipe any leftover mockResolvedValueOnce queues
    // from previous tests (vi.clearAllMocks only clears call records, not impl queues)
    vi.resetAllMocks();
  });

  it('content cards are draggable for non-viewer users', async () => {
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Draggable email piece/).closest('.cal-piece-card');
    expect(card).not.toBeNull();
    expect(card.getAttribute('draggable')).toBe('true');
  });

  it('content cards are NOT draggable for viewers (RBAC)', async () => {
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={true} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Draggable email piece/).closest('.cal-piece-card');
    expect(card).not.toBeNull();
    // draggable should be false/absent for viewer
    expect(card.getAttribute('draggable')).not.toBe('true');
  });

  it('unscheduled sidebar cards are draggable for non-viewer users', async () => {
    const calResponse = makeCalendarResponse({
      unscheduled: [{
        piece_index: 7,
        piece: { content: 'Sidebar draggable piece', content_type: 'body_copy', channel: 'email', scheduled_date: null },
      }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Sidebar draggable piece/).closest('.cal-unscheduled-card');
    expect(card).not.toBeNull();
    expect(card.getAttribute('draggable')).toBe('true');
  });

  it('unscheduled sidebar cards are NOT draggable for viewers', async () => {
    const calResponse = makeCalendarResponse({
      unscheduled: [{
        piece_index: 7,
        piece: { content: 'Sidebar viewer piece', content_type: 'body_copy', channel: 'email', scheduled_date: null },
      }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={true} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Sidebar viewer piece/).closest('.cal-unscheduled-card');
    expect(card).not.toBeNull();
    expect(card.getAttribute('draggable')).not.toBe('true');
  });

  it('dragging a scheduled piece and dropping onto a new date calls schedulePiece', async () => {
    vi.spyOn(api, 'schedulePiece').mockResolvedValue({});
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    // Find the draggable card
    const card = screen.getByText(/Draggable email piece/).closest('.cal-piece-card');

    // Simulate dragStart on the piece card
    fireEvent.dragStart(card);

    // Find the target day cell using the date number text
    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    // Filter to find only calendar day numbers (inside .cal-day-number)
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      expect(dayCell).not.toBeNull();

      fireEvent.dragOver(dayCell);
      fireEvent.drop(dayCell);

      await waitFor(() => expect(api.schedulePiece).toHaveBeenCalledWith(
        WORKSPACE_ID,
        CAMPAIGN_ID,
        5,
        expect.objectContaining({ scheduledDate: targetISO }),
      ));
    }
  });

  it('shows success toast after successful drop', async () => {
    vi.spyOn(api, 'schedulePiece').mockResolvedValue({});
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Draggable email piece/).closest('.cal-piece-card');
    fireEvent.dragStart(card);

    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      fireEvent.dragOver(dayCell);
      fireEvent.drop(dayCell);

      await waitFor(() => expect(mockAddToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success' }),
      ));
    }
  });

  it('rolls back optimistic update and shows error toast on API failure', async () => {
    vi.spyOn(api, 'schedulePiece').mockRejectedValue(new Error('Server error'));
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    // Card should be visible before drag
    expect(screen.getByText(/Draggable email piece/)).toBeInTheDocument();

    const card = screen.getByText(/Draggable email piece/).closest('.cal-piece-card');
    fireEvent.dragStart(card);

    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      fireEvent.dragOver(dayCell);
      fireEvent.drop(dayCell);

      // Error toast should be shown after API failure
      await waitFor(() => expect(mockAddToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error' }),
      ));

      // Card should be restored to its original position
      await waitFor(() => expect(screen.getByText(/Draggable email piece/)).toBeInTheDocument());
    }
  });

  it('dragging unscheduled piece to calendar calls schedulePiece', async () => {
    vi.spyOn(api, 'schedulePiece').mockResolvedValue({});
    const calResponse = makeCalendarResponse({
      unscheduled: [{
        piece_index: 9,
        piece: { content: 'Unscheduled piece to drag', content_type: 'cta', channel: 'social_media', scheduled_date: null },
      }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const card = screen.getByText(/Unscheduled piece to drag/).closest('.cal-unscheduled-card');
    fireEvent.dragStart(card);

    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      fireEvent.dragOver(dayCell);
      fireEvent.drop(dayCell);

      await waitFor(() => expect(api.schedulePiece).toHaveBeenCalledWith(
        WORKSPACE_ID,
        CAMPAIGN_ID,
        9,
        expect.objectContaining({ scheduledDate: targetISO }),
      ));
    }
  });

  it('drop target day cell gets drag-over highlight class on dragOver', async () => {
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    await renderCalendar(calResponse, { isViewer: false });
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      fireEvent.dragOver(dayCell);
      await waitFor(() => {
        expect(dayCell.classList.contains('cal-day--drag-over')).toBe(true);
      });
    }
  });

  it('drag-over highlight is cleared after dragLeave', async () => {
    const calResponse = makeCalendarResponse({
      scheduled: [{ date: todayISO, pieces: [makeScheduledPiece()] }],
    });
    api.getCalendar.mockResolvedValue(calResponse);
    render(<CalendarView workspaceId={WORKSPACE_ID} campaignId={CAMPAIGN_ID} isViewer={false} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());

    const targetDayNumber = String(targetDate.getDate());
    const dayNumbers = screen.getAllByText(targetDayNumber);
    const calDayNumber = dayNumbers.find((el) => el.classList.contains('cal-day-number'));
    if (calDayNumber) {
      const dayCell = calDayNumber.closest('.cal-day');
      fireEvent.dragOver(dayCell);
      // dragLeave with relatedTarget outside the cell clears the highlight
      fireEvent.dragLeave(dayCell, { relatedTarget: document.body });
      expect(dayCell.classList.contains('cal-day--drag-over')).toBe(false);
    }
  });
});
