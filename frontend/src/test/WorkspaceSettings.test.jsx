/**
 * Tests for WorkspaceSettings page.
 */

import { render, screen, waitFor, fireEvent, act, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import WorkspaceSettings from '../pages/WorkspaceSettings';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';
import { ToastProvider } from '../ToastContext';

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
          <ConfirmDialogProvider>
            <ToastProvider>
              <Routes>
                <Route path="/workspaces/:id/settings" element={<WorkspaceSettings />} />
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
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

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

  it('shows undo toast after confirm and calls deleteWorkspace after 5 seconds', async () => {
    api.deleteWorkspace.mockResolvedValue(undefined);

    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /delete workspace/i }));
    });

    // Confirm via the modal — enable fake timers BEFORE clicking confirm
    const dialog = await waitFor(() => screen.getByRole('dialog'));
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /^delete workspace$/i }));
    });

    // Undo toast should appear; API should NOT have been called yet
    expect(screen.getByText('Workspace deleted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();
    expect(api.deleteWorkspace).not.toHaveBeenCalled();

    // Advance past the 5-second grace period and drain async operations
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.deleteWorkspace).toHaveBeenCalledWith('ws-1');

    // Allow the navigate to happen after the mocked async deleteWorkspace resolves
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/workspaces');

    vi.clearAllTimers();
    api.deleteWorkspace.mockClear();
  }, 10000);

  it('cancels delete when Undo is clicked', async () => {
    api.deleteWorkspace.mockResolvedValue(undefined);

    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /delete workspace/i }));
    });

    // Confirm via the modal
    const dialog = await waitFor(() => screen.getByRole('dialog'));
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /^delete workspace$/i }));
    });

    // Click Undo
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });

    // Advance past the grace period — API should NOT be called
    await act(async () => {
      vi.advanceTimersByTime(6000);
      await Promise.resolve();
    });

    expect(api.deleteWorkspace).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();

    vi.clearAllTimers();
  });

  it('does not delete when confirm is cancelled', async () => {
    await renderSettings('ws-1', ws, []);
    await waitFor(() => screen.getByRole('button', { name: /delete workspace/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /delete workspace/i }));
    });

    // Cancel via the modal
    await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    });

    expect(api.deleteWorkspace).not.toHaveBeenCalled();
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
