/**
 * Tests for the landing page at "/" which now renders WorkspaceList.
 *
 * The Dashboard page has been removed. The "/" route now renders WorkspaceList,
 * and "/workspaces" redirects to "/".
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import WorkspaceList from '../pages/WorkspaceList';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

vi.mock('../api');

import * as api from '../api';

function makeMeResponse({ isViewer = false, isAdmin = false } = {}) {
  return {
    id: 'user-1',
    email: 'test@example.com',
    display_name: 'Test User',
    roles: isAdmin ? ['admin'] : isViewer ? ['viewer'] : ['campaign_builder'],
    is_admin: isAdmin,
    can_build: !isViewer,
    is_viewer: isViewer,
  };
}

const personalWs = {
  id: 'ws-personal', name: 'My Space', is_personal: true, role: 'creator',
  member_count: 1, campaign_count: 3,
  draft_count: 1, in_progress_count: 1, awaiting_approval_count: 0, approved_count: 1,
};

const teamWs = {
  id: 'ws-team', name: 'Team Space', is_personal: false, role: 'contributor',
  member_count: 5, campaign_count: 8,
  draft_count: 2, in_progress_count: 3, awaiting_approval_count: 2, approved_count: 1,
};

async function renderAtRoute(path, workspaces = [personalWs, teamWs]) {
  api.getMe.mockResolvedValue(makeMeResponse());
  api.listWorkspaces.mockResolvedValue(workspaces);

  render(
    <MemoryRouter initialEntries={[path]}>
      <UserProvider>
        <WorkspaceProvider>
          <Routes>
            <Route path="/" element={<WorkspaceList />} />
            <Route path="/workspaces" element={<Navigate to="/" replace />} />
          </Routes>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(api.listWorkspaces).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Landing page – "/" renders WorkspaceList', () => {
  it('shows workspace cards at "/"', async () => {
    await renderAtRoute('/');
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('My Space')).toBeInTheDocument();
    expect(screen.getByText('Team Space')).toBeInTheDocument();
  });

  it('shows summary strip with aggregate totals', async () => {
    await renderAtRoute('/');
    await waitFor(() => screen.getByText('My Space'));
    // Total campaigns: 3 + 8 = 11
    expect(screen.getByTestId('summary-campaigns')).toHaveTextContent('11');
    // Total drafts: 1 + 2 = 3
    expect(screen.getByTestId('summary-drafts')).toHaveTextContent('3');
  });
});

describe('Landing page – "/workspaces" redirects to "/"', () => {
  it('redirects /workspaces to / and shows workspace cards', async () => {
    await renderAtRoute('/workspaces');
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('My Space')).toBeInTheDocument();
  });
});
