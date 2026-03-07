/**
 * Tests for WorkspaceContext — WorkspaceProvider and useWorkspace hook.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { WorkspaceProvider, useWorkspace } from '../WorkspaceContext';

// api.js is mocked at the module level
vi.mock('../api');

import * as api from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * A simple consumer component that renders workspace context values.
 */
function WorkspaceConsumer() {
  const { workspaces, loading, personalWorkspace, refreshWorkspaces } = useWorkspace();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="count">{workspaces.length}</span>
      <span data-testid="personal">{personalWorkspace ? personalWorkspace.id : 'none'}</span>
      <button onClick={refreshWorkspaces}>Refresh</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <WorkspaceProvider>
      <WorkspaceConsumer />
    </WorkspaceProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('WorkspaceProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches workspaces on mount and exposes them', async () => {
    api.listWorkspaces.mockResolvedValue([
      { id: 'ws-1', name: 'Personal', is_personal: true, role: 'creator' },
      { id: 'ws-2', name: 'Team', is_personal: false, role: 'member' },
    ]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });

    expect(screen.getByTestId('count').textContent).toBe('2');
    expect(api.listWorkspaces).toHaveBeenCalledTimes(1);
  });

  it('identifies personalWorkspace via is_personal flag', async () => {
    api.listWorkspaces.mockResolvedValue([
      { id: 'ws-personal', name: 'Personal', is_personal: true, role: 'creator' },
      { id: 'ws-team', name: 'Team', is_personal: false, role: 'member' },
    ]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('personal').textContent).toBe('ws-personal');
    });
  });

  it('returns null for personalWorkspace when none is marked is_personal', async () => {
    api.listWorkspaces.mockResolvedValue([
      { id: 'ws-1', name: 'Team', is_personal: false, role: 'member' },
    ]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('personal').textContent).toBe('none');
    });
  });

  it('handles fetch errors gracefully — returns empty array', async () => {
    api.listWorkspaces.mockRejectedValue(new Error('Network error'));

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });

    expect(screen.getByTestId('count').textContent).toBe('0');
    expect(screen.getByTestId('personal').textContent).toBe('none');
  });

  it('refreshWorkspaces re-fetches the workspace list', async () => {
    api.listWorkspaces
      .mockResolvedValueOnce([{ id: 'ws-1', name: 'First', is_personal: false, role: 'creator' }])
      .mockResolvedValueOnce([
        { id: 'ws-1', name: 'First', is_personal: false, role: 'creator' },
        { id: 'ws-2', name: 'Second', is_personal: false, role: 'member' },
      ]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('1');
    });

    await act(async () => {
      screen.getByRole('button', { name: 'Refresh' }).click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('2');
    });

    expect(api.listWorkspaces).toHaveBeenCalledTimes(2);
  });
});
