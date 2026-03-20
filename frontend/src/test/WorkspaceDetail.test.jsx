/**
 * Tests for WorkspaceDetail page.
 */

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkspaceDetail from '../pages/WorkspaceDetail';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

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
  api.listWorkspaceCampaigns.mockResolvedValue(campaigns);
  api.listWorkspaceMembers.mockResolvedValue(members);

  render(
    <MemoryRouter initialEntries={[`/workspaces/${wsId}`]}>
      <UserProvider>
        <WorkspaceProvider>
          <Routes>
            <Route path="/workspaces/:id" element={<WorkspaceDetail events={[]} />} />
          </Routes>
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
    expect(screen.getByText('In Progress')).toBeInTheDocument();
    // "Approved" appears as both the status group label and the campaign badge
    expect(screen.getAllByText('Approved')).toHaveLength(2);
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
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    // Enable fake timers only after the initial render is settled
    vi.useFakeTimers();

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Campaign should be removed immediately (optimistic)
    expect(screen.queryByText('ProductA')).not.toBeInTheDocument();
    // Undo toast should appear
    expect(screen.getByText('Campaign deleted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();

    window.confirm.mockRestore();
    vi.clearAllTimers();
  });

  it('restores campaign when Undo is clicked', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    api.listWorkspaceCampaigns.mockResolvedValue([campaign]);
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    vi.useFakeTimers();

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Click Undo
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });

    // Campaign should be restored
    expect(screen.getByText('ProductA')).toBeInTheDocument();
    // deleteCampaign API should NOT have been called
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    window.confirm.mockRestore();
    vi.clearAllTimers();
  });

  it('calls deleteCampaign API after 5 seconds if Undo is not clicked', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    api.deleteCampaign.mockResolvedValue(undefined);
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    vi.useFakeTimers();

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
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

    window.confirm.mockRestore();
    // Ensure no timers or mock state leaks into the next test
    vi.clearAllTimers();
    api.deleteCampaign.mockClear();
  });

  it('does not delete when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    await renderDetail('ws-1', ws, [campaign]);
    await waitFor(() => screen.getByText('ProductA'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    fireEvent.click(deleteBtn);

    // Campaign should still be visible
    expect(screen.getByText('ProductA')).toBeInTheDocument();
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    window.confirm.mockRestore();
  });
});

