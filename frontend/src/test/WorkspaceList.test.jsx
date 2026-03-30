/**
 * Tests for WorkspaceList page.
 */

import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import WorkspaceList from '../pages/WorkspaceList';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

vi.mock('../api');
// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useNavigate: () => mockNavigate };
});

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

async function renderWorkspaceList({ isViewer = false, isAdmin = false } = {}, workspaces = []) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin }));
  api.listWorkspaces.mockResolvedValue(workspaces);

  render(
    <MemoryRouter>
      <UserProvider>
        <WorkspaceProvider>
          <WorkspaceList />
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(api.listWorkspaces).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
  mockNavigate.mockReset();
});

const personalWs = {
  id: 'ws-personal', name: 'My Space', is_personal: true, role: 'creator',
  member_count: 1, campaign_count: 2,
  draft_count: 1, in_progress_count: 0, awaiting_approval_count: 0, approved_count: 1,
};
const teamWs = {
  id: 'ws-team', name: 'Team Space', is_personal: false, role: 'contributor',
  member_count: 3, campaign_count: 5,
  draft_count: 1, in_progress_count: 2, awaiting_approval_count: 1, approved_count: 1,
};

describe('WorkspaceList – rendering', () => {
  it('shows all workspaces as cards', async () => {
    await renderWorkspaceList({}, [personalWs, teamWs]);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('My Space')).toBeInTheDocument();
    expect(screen.getByText('Team Space')).toBeInTheDocument();
  });

  it('shows Personal badge for personal workspace', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('Personal')).toBeInTheDocument();
  });

  it('shows role badge on workspace card', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByText('Creator')).toBeInTheDocument();
  });

  it('shows empty state when no workspaces', async () => {
    await renderWorkspaceList({}, []);
    await waitFor(() => screen.getByText(/no workspaces yet/i));
    expect(screen.getByText(/no workspaces yet/i)).toBeInTheDocument();
  });

  it('shows Create Workspace button for non-viewers', async () => {
    await renderWorkspaceList({ isViewer: false }, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.getByRole('button', { name: /create workspace/i })).toBeInTheDocument();
  });

  it('hides Create Workspace button for viewers', async () => {
    await renderWorkspaceList({ isViewer: true }, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    expect(screen.queryByRole('button', { name: /create workspace/i })).not.toBeInTheDocument();
  });

  it('shows member and campaign counts on card', async () => {
    await renderWorkspaceList({}, [teamWs]);
    await waitFor(() => screen.getByText('Team Space'));
    // Use the card link to scope queries (avoid matching summary strip values)
    const card = screen.getByLabelText('Open workspace Team Space');
    expect(within(card).getByText('3')).toBeInTheDocument(); // member_count
    expect(within(card).getByText('5')).toBeInTheDocument(); // campaign_count
  });
});

describe('WorkspaceList – summary strip', () => {
  it('shows aggregate totals in the summary strip', async () => {
    await renderWorkspaceList({}, [personalWs, teamWs]);
    await waitFor(() => screen.getByText('My Space'));

    // Total campaigns: 2 + 5 = 7
    expect(screen.getByTestId('summary-campaigns')).toHaveTextContent('7');
    // Total drafts: 1 + 1 = 2
    expect(screen.getByTestId('summary-drafts')).toHaveTextContent('2');
    // Total in progress: 0 + 2 = 2
    expect(screen.getByTestId('summary-in-progress')).toHaveTextContent('2');
    // Total awaiting: 0 + 1 = 1
    expect(screen.getByTestId('summary-awaiting')).toHaveTextContent('1');
    // Total approved: 1 + 1 = 2
    expect(screen.getByTestId('summary-approved')).toHaveTextContent('2');
  });

  it('does not show summary strip when there are no workspaces', async () => {
    await renderWorkspaceList({}, []);
    await waitFor(() => screen.getByText(/no workspaces yet/i));
    expect(screen.queryByTestId('summary-campaigns')).not.toBeInTheDocument();
  });
});

describe('WorkspaceList – status breakdown badges', () => {
  it('shows status badges on cards with non-zero counts', async () => {
    await renderWorkspaceList({}, [teamWs]);
    await waitFor(() => screen.getByText('Team Space'));

    expect(screen.getByText('1 Draft')).toBeInTheDocument();
    expect(screen.getByText('2 In Progress')).toBeInTheDocument();
    expect(screen.getByText('1 Awaiting Approval')).toBeInTheDocument();
    expect(screen.getByText('1 Approved')).toBeInTheDocument();
  });

  it('hides status badges for zero counts', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));

    // personalWs has in_progress_count: 0 and awaiting_approval_count: 0
    // The summary strip shows "In Progress" and "Awaiting Approval" labels,
    // so scope assertions to the card itself.
    const card = screen.getByLabelText('Open workspace My Space');
    expect(within(card).queryByText(/In Progress/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Awaiting Approval/)).not.toBeInTheDocument();
    // But should show draft and approved
    expect(screen.getByText('1 Draft')).toBeInTheDocument();
    expect(screen.getByText('1 Approved')).toBeInTheDocument();
  });
});

describe('WorkspaceList – awaiting approval action badge', () => {
  it('shows "Needs Action" badge when awaiting_approval_count > 0', async () => {
    await renderWorkspaceList({}, [teamWs]);
    await waitFor(() => screen.getByText('Team Space'));

    expect(screen.getByText(/Needs Action/)).toBeInTheDocument();
  });

  it('does not show "Needs Action" badge when awaiting_approval_count is 0', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));

    expect(screen.queryByText(/Needs Action/)).not.toBeInTheDocument();
  });

  it('"Needs Action" badge has an accessible label', async () => {
    await renderWorkspaceList({}, [teamWs]);
    await waitFor(() => screen.getByText('Team Space'));

    expect(screen.getByLabelText('Awaiting your action')).toBeInTheDocument();
  });
});

describe('WorkspaceList – create workspace modal', () => {
  it('opens modal when Create Workspace is clicked', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it('closes modal on Cancel click', async () => {
    await renderWorkspaceList({}, [personalWs]);
    await waitFor(() => screen.getByText('My Space'));
    fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('calls createWorkspace and navigates on submit', async () => {
    const created = { id: 'ws-new', name: 'New WS', is_personal: false, role: 'creator' };
    api.createWorkspace.mockResolvedValue(created);
    api.listWorkspaces.mockResolvedValue([]);

    await renderWorkspaceList({}, []);
    await waitFor(() => screen.getByText(/no workspaces yet/i));

    // Trigger empty-state button to open modal
    fireEvent.click(screen.getByRole('button', { name: /create your first workspace/i }));
    const nameInput = screen.getByLabelText(/name/i);
    fireEvent.change(nameInput, { target: { value: 'New WS' } });
    // Click the submit button inside the form (inside the dialog)
    const dialog = screen.getByRole('dialog');
    const submitBtn = dialog.querySelector('button[type="submit"]');
    fireEvent.click(submitBtn);

    await waitFor(() => expect(api.createWorkspace).toHaveBeenCalledWith('New WS', undefined));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/workspaces/ws-new'));
  });
});
