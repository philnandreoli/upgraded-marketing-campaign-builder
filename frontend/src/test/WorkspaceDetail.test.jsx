/**
 * Tests for WorkspaceDetail page.
 */

import { render, screen, waitFor, fireEvent, act, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkspaceDetail from '../pages/WorkspaceDetail';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';
import { ToastProvider } from '../ToastContext';

vi.mock('../api');

import * as api from '../api';

function makeMeResponse({ isViewer = false, isAdmin = false, userId = 'user-1' } = {}) {
  return {
    id: userId,
    email: 'test@example.com',
    display_name: 'Test User',
    roles: isAdmin ? ['admin'] : isViewer ? ['viewer'] : ['campaign_builder'],
    is_admin: isAdmin,
    can_build: !isViewer,
    is_viewer: isViewer,
  };
}

async function renderDetail(
  wsId = 'ws-1',
  workspace = {},
  campaigns = [],
  members = [],
  { isViewer = false, isAdmin = false, userId = 'user-1' } = {},
) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin, userId }));
  api.listWorkspaces.mockResolvedValue([workspace]);
  api.getWorkspace.mockResolvedValue(workspace);
  api.listWorkspaceCampaigns.mockResolvedValue({
    items: campaigns,
    pagination: {
      total_count: campaigns.length,
      offset: 0,
      limit: 50,
      returned_count: campaigns.length,
      has_more: false,
    },
  });
  api.listWorkspaceMembers.mockResolvedValue(members);

  render(
    <MemoryRouter initialEntries={[`/workspaces/${wsId}`]}>
      <UserProvider>
        <WorkspaceProvider>
          <ConfirmDialogProvider>
            <ToastProvider>
              <Routes>
                <Route path="/workspaces/:id" element={<WorkspaceDetail events={[]} />} />
              </Routes>
            </ToastProvider>
          </ConfirmDialogProvider>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(api.getWorkspace).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
});

const ws = { id: 'ws-1', name: 'Team Workspace', is_personal: false, role: 'creator', description: 'A team workspace', owner_display_name: 'Owner Person' };
const wsPersonal = { id: 'ws-personal', name: 'My Space', is_personal: true, role: 'creator', description: '' };

const campaign = { id: 'c1', product_or_service: 'ProductA', goal: 'Grow fast', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-1' };
const campaignApproved = { id: 'c2', product_or_service: 'ProductB', goal: 'Scale', status: 'approved', owner_id: 'user-2', workspace_id: 'ws-1' };

describe('WorkspaceDetail – header', () => {
  it('shows workspace name', async () => {
    await renderDetail('ws-1', ws);
    await waitFor(() => screen.getByText('Team Workspace'));
    expect(screen.getByText('Team Workspace')).toBeInTheDocument();
  });

  it('shows description', async () => {
    await renderDetail('ws-1', ws);
    await waitFor(() => screen.getByText('A team workspace'));
    expect(screen.getByText('A team workspace')).toBeInTheDocument();
  });

  it('shows Personal badge for personal workspace', async () => {
    await renderDetail('ws-personal', wsPersonal);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('Personal')).toBeInTheDocument();
  });

  it('shows role badge', async () => {
    await renderDetail('ws-1', ws);
    await waitFor(() => screen.getAllByText('Creator'));
    expect(screen.getAllByText('Creator').length).toBeGreaterThanOrEqual(1);
  });

  it('shows Create Campaign and Settings links for creator', async () => {
    // Pass a campaign so the empty state (which also has a Create Campaign link) is not shown
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('Team Workspace'));
    // Create Campaign is now in the Campaigns section header
    expect(screen.getByRole('link', { name: /create campaign/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
  });

  it('hides Settings link for contributor', async () => {
    const wsContrib = { ...ws, role: 'contributor' };
    await renderDetail('ws-1', wsContrib);
    await waitFor(() => screen.getByText('Team Workspace'));
    expect(screen.queryByRole('link', { name: /settings/i })).not.toBeInTheDocument();
  });
});

describe('WorkspaceDetail – campaigns', () => {
  it('shows campaigns grouped by status', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(screen.getByText('ProductB')).toBeInTheDocument();
    // "In Progress" appears as both a filter tab and status group label
    expect(screen.getAllByText('In Progress').length).toBeGreaterThanOrEqual(2);
    // "Approved" appears as a filter tab, status group label, and campaign badge
    expect(screen.getAllByText('Approved').length).toBeGreaterThanOrEqual(3);
  });

  it('shows empty state when no campaigns', async () => {
    await renderDetail('ws-1', ws, []);
    await waitFor(() => screen.getByText(/no campaigns in this workspace/i));
    expect(screen.getByText(/no campaigns in this workspace/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Undo delete
// ---------------------------------------------------------------------------

describe('WorkspaceDetail – undo delete', () => {
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('optimistically removes campaign and shows undo toast on delete confirmation', async () => {
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm via the modal (must happen before fake timers)
    const dialog1 = await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(within(dialog1).getByRole('button', { name: /^delete$/i }));
    });

    // Enable fake timers only after the confirm dialog is resolved
    vi.useFakeTimers();

    // Campaign should be removed immediately (optimistic)
    expect(screen.queryByText('ProductA')).not.toBeInTheDocument();
    // Undo toast should appear
    expect(screen.getByText('Campaign deleted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();

    vi.clearAllTimers();
  });

  it('restores campaign when Undo is clicked', async () => {
    api.listWorkspaceCampaigns.mockResolvedValue({
      items: [campaign],
      pagination: { total_count: 1, offset: 0, limit: 50, returned_count: 1, has_more: false },
    });
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm via the modal
    const dialog2 = await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(within(dialog2).getByRole('button', { name: /^delete$/i }));
    });

    vi.useFakeTimers();

    // Click Undo
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });

    // Campaign should be restored
    expect(screen.getByText('ProductA')).toBeInTheDocument();
    // deleteCampaign API should NOT have been called
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    vi.clearAllTimers();
  });

  it('calls deleteCampaign API after 5 seconds if Undo is not clicked', async () => {
    api.deleteCampaign.mockResolvedValue(undefined);
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm via the modal — enable fake timers BEFORE clicking confirm
    // so that the setTimeout in handleDelete is captured by fake timers
    const dialog3 = await waitFor(() => screen.getByRole('dialog'));
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(within(dialog3).getByRole('button', { name: /^delete$/i }));
    });

    // deleteCampaign should not be called yet
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    // Advance past the 5-second undo window and drain all resulting async ops
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.deleteCampaign).toHaveBeenCalledWith('ws-1', 'c1');

    // Ensure no timers or mock state leaks into the next test
    vi.clearAllTimers();
    api.deleteCampaign.mockClear();
  });

  it('does not delete when confirm is cancelled', async () => {
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Cancel via the modal
    await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    });

    // Campaign should still be visible
    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(api.deleteCampaign).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Tests: Filter tabs
// ---------------------------------------------------------------------------

const campaignStrategy = { id: 'c3', product_or_service: 'StrategyCampaign', goal: 'Launch', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-1' };
const campaignAwaiting = { id: 'c4', product_or_service: 'AwaitingCampaign', goal: 'Review', status: 'content_approval', owner_id: 'user-1', workspace_id: 'ws-1' };

describe('WorkspaceDetail – Filter tabs', () => {
  it('renders filter tabs when campaigns exist', async () => {
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'In Progress' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Approved' })).toBeInTheDocument();
  });

  it('does not render filter tabs when no campaigns', async () => {
    await renderDetail('ws-1', ws, []);
    await waitFor(() => screen.getByText(/no campaigns in this workspace/i));
    expect(screen.queryByRole('tab', { name: 'All' })).not.toBeInTheDocument();
  });

  it('defaults to "All" tab and shows all campaigns', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy, campaignApproved]);
    await waitFor(() => screen.getByText('StrategyCampaign'));
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('StrategyCampaign')).toBeInTheDocument();
    expect(screen.getByText('ProductB')).toBeInTheDocument();
  });

  it('"In Progress" tab shows only in-progress campaigns', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy, campaignApproved]);
    await waitFor(() => screen.getByText('StrategyCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'In Progress' }));
    expect(screen.getByText('StrategyCampaign')).toBeInTheDocument();
    expect(screen.queryByText('ProductB')).not.toBeInTheDocument();
  });

  it('"Approved" tab shows only approved campaigns', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy, campaignApproved]);
    await waitFor(() => screen.getByText('StrategyCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(screen.queryByText('StrategyCampaign')).not.toBeInTheDocument();
    expect(screen.getByText('ProductB')).toBeInTheDocument();
  });

  it('shows empty state when no campaigns match filter', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy]);
    await waitFor(() => screen.getByText('StrategyCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(screen.getByText(/no campaigns match this filter/i)).toBeInTheDocument();
  });

  it('"Needs Approval" tab shows awaiting campaigns', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy, campaignAwaiting]);
    await waitFor(() => screen.getByText('StrategyCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Needs Approval' }));
    expect(screen.getByText('AwaitingCampaign')).toBeInTheDocument();
    expect(screen.queryByText('StrategyCampaign')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Search bar
// ---------------------------------------------------------------------------

/** Helper: fire a search change and advance fake timers to trigger the debounce. */
async function typeSearch(inputValue) {
  vi.useFakeTimers();
  fireEvent.change(screen.getByPlaceholderText('Search campaigns...'), {
    target: { value: inputValue },
  });
  await act(async () => vi.advanceTimersByTime(300));
  vi.useRealTimers();
}

describe('WorkspaceDetail – Search bar', () => {
  it('renders search bar when campaigns exist', async () => {
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.getByPlaceholderText('Search campaigns...')).toBeInTheDocument();
  });

  it('filters campaigns by product name (debounced)', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('ProductA');

    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(screen.queryByText('ProductB')).not.toBeInTheDocument();
  });

  it('filters campaigns by goal', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('Scale');

    expect(screen.queryByText('ProductA')).not.toBeInTheDocument();
    expect(screen.getByText('ProductB')).toBeInTheDocument();
  });

  it('is case-insensitive', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('producta');

    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(screen.queryByText('ProductB')).not.toBeInTheDocument();
  });

  it('shows result count when search is active', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('ProductA');

    expect(screen.getByText(/showing 1 of 2 campaigns/i)).toBeInTheDocument();
  });

  it('does not show result count when search is empty', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument();
  });

  it('shows empty state when search yields no results', async () => {
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('nomatch-xyz');

    expect(screen.getByText(/no campaigns match your search/i)).toBeInTheDocument();
  });

  it('clear button resets search and shows all campaigns', async () => {
    await renderDetail('ws-1', ws, [campaign, campaignApproved]);
    await waitFor(() => screen.getByText('ProductA'));

    await typeSearch('ProductA');
    expect(screen.queryByText('ProductB')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /clear search/i }));

    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(screen.getByText('ProductB')).toBeInTheDocument();
  });

  it('search composes with active filter tab', async () => {
    await renderDetail('ws-1', ws, [campaignStrategy, campaignApproved]);
    await waitFor(() => screen.getByText('StrategyCampaign'));

    // Activate "Approved" tab — only campaignApproved is visible
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    await waitFor(() => expect(screen.queryByText('StrategyCampaign')).not.toBeInTheDocument());

    // Search for "strategy" while on Approved tab should yield no results
    await typeSearch('strategy');

    expect(screen.getByText(/no campaigns match your search/i)).toBeInTheDocument();
  });
});

