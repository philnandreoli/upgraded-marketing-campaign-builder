/**
 * Tests for WorkspaceSettings page.
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import WorkspaceSettings from '../pages/WorkspaceSettings';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

vi.mock('../api');

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

async function renderSettings(
  wsId = 'ws-1',
  workspace = {},
  members = [],
  { isViewer = false, isAdmin = false } = {},
) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin }));
  api.listWorkspaces.mockResolvedValue([workspace]);
  api.getWorkspace.mockResolvedValue(workspace);
  api.listWorkspaceMembers.mockResolvedValue(members);

  render(
    <MemoryRouter initialEntries={[`/workspaces/${wsId}/settings`]}>
      <UserProvider>
        <WorkspaceProvider>
          <Routes>
            <Route path="/workspaces/:id/settings" element={<WorkspaceSettings />} />
          </Routes>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(api.getWorkspace).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
  mockNavigate.mockReset();
});

const ws = { id: 'ws-1', name: 'Team WS', is_personal: false, role: 'creator', description: 'Team desc' };
const wsPersonal = { id: 'ws-p', name: 'My Space', is_personal: true, role: 'creator', description: '' };
const member = { user_id: 'user-1', display_name: 'Alice', email: 'alice@example.com', role: 'creator' };

describe('WorkspaceSettings – edit form', () => {
  it('pre-fills name and description', async () => {
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByDisplayValue('Team WS'));
    expect(screen.getByDisplayValue('Team WS')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Team desc')).toBeInTheDocument();
  });

  it('disables name/description for personal workspace', async () => {
    await renderSettings('ws-p', wsPersonal, []);
    await waitFor(() => screen.getByDisplayValue('My Space'));
    expect(screen.getByDisplayValue('My Space')).toBeDisabled();
  });

  it('shows read-only note for personal workspace', async () => {
    await renderSettings('ws-p', wsPersonal, []);
    await waitFor(() => screen.getByDisplayValue('My Space'));
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });

  it('calls updateWorkspace on save', async () => {
    api.updateWorkspace.mockResolvedValue({ ...ws, name: 'Updated WS' });
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByDisplayValue('Team WS'));
    fireEvent.change(screen.getByDisplayValue('Team WS'), { target: { value: 'Updated WS' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(api.updateWorkspace).toHaveBeenCalledWith('ws-1', expect.objectContaining({ name: 'Updated WS' })));
  });

  it('shows success message after save', async () => {
    api.updateWorkspace.mockResolvedValue({ ...ws, name: 'Updated WS' });
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByDisplayValue('Team WS'));
    fireEvent.change(screen.getByDisplayValue('Team WS'), { target: { value: 'Updated WS' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => screen.getByText(/saved successfully/i));
    expect(screen.getByText(/saved successfully/i)).toBeInTheDocument();
  });
});

describe('WorkspaceSettings – members', () => {
  it('shows member table', async () => {
    await renderSettings('ws-1', ws, [member]);
    await waitFor(() => screen.getByText('Alice'));
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('shows add member form for non-personal workspace', async () => {
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByText(/add member/i));
    expect(screen.getByText(/add member/i)).toBeInTheDocument();
  });

  it('hides add member form for personal workspace', async () => {
    await renderSettings('ws-p', wsPersonal, []);
    await waitFor(() => screen.getByDisplayValue('My Space'));
    expect(screen.queryByText(/add member/i)).not.toBeInTheDocument();
  });
});

describe('WorkspaceSettings – danger zone', () => {
  it('shows Delete Workspace button', async () => {
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    expect(screen.getByRole('button', { name: /delete workspace/i })).toBeInTheDocument();
  });

  it('disables delete button for personal workspace', async () => {
    await renderSettings('ws-p', wsPersonal, []);
    await waitFor(() => screen.getByDisplayValue('My Space'));
    expect(screen.getByRole('button', { name: /delete workspace/i })).toBeDisabled();
  });

  it('shows "cannot be deleted" note for personal workspace', async () => {
    await renderSettings('ws-p', wsPersonal, []);
    await waitFor(() => screen.getByDisplayValue('My Space'));
    expect(screen.getByText(/personal workspaces cannot be deleted/i)).toBeInTheDocument();
  });

  it('shows orphan warning text', async () => {
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    expect(screen.getByText(/orphaned/i)).toBeInTheDocument();
    expect(screen.getByText(/will not be deleted/i)).toBeInTheDocument();
  });

  it('calls deleteWorkspace and navigates on confirm', async () => {
    api.deleteWorkspace.mockResolvedValue(undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    fireEvent.click(screen.getByRole('button', { name: /delete workspace/i }));

    await waitFor(() => expect(api.deleteWorkspace).toHaveBeenCalledWith('ws-1'));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/workspaces'));

    window.confirm.mockRestore();
  });

  it('does not delete when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    fireEvent.click(screen.getByRole('button', { name: /delete workspace/i }));

    expect(api.deleteWorkspace).not.toHaveBeenCalled();

    window.confirm.mockRestore();
  });
});

describe('WorkspaceSettings – access control', () => {
  it('shows permission denied for contributor role', async () => {
    const wsContrib = { ...ws, role: 'contributor' };
    await renderSettings('ws-1', wsContrib, []);
    await waitFor(() => screen.getByText(/do not have permission/i));
    expect(screen.getByText(/do not have permission/i)).toBeInTheDocument();
  });
});
