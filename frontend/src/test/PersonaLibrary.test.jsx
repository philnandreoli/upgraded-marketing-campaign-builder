/**
 * Tests for PersonaLibrary page.
 *
 * Covers:
 *  - Renders persona list with name and description
 *  - Shows empty state when no personas exist
 *  - Create persona flow (open modal, fill form, save)
 *  - Edit persona flow (open modal, modify, save)
 *  - Delete persona flow (confirm dialog, API call)
 *  - Search filtering
 *  - RBAC: viewers cannot see write controls
 *  - Breadcrumb navigation
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import PersonaLibrary from '../pages/PersonaLibrary';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';

vi.mock('../api');

import * as api from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMeResponse({ isAdmin = false, isViewer = false } = {}) {
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

const WORKSPACE = {
  id: 'ws-1',
  name: 'Test Workspace',
  description: 'A test workspace',
  is_personal: false,
  role: 'creator',
};

const PERSONA_1 = {
  id: 'p-1',
  workspace_id: 'ws-1',
  name: 'Tech-Savvy Millennial',
  description: 'Ages 25-35, digital native, values convenience.',
  created_by: 'user-1',
  created_at: '2026-01-15T10:00:00Z',
  updated_at: '2026-01-15T10:00:00Z',
};

const PERSONA_2 = {
  id: 'p-2',
  workspace_id: 'ws-1',
  name: 'Enterprise Decision Maker',
  description: 'VP/Director level, budget authority, risk-averse.',
  created_by: 'user-1',
  created_at: '2026-02-01T10:00:00Z',
  updated_at: '2026-02-01T10:00:00Z',
};

async function renderPersonaLibrary({
  personas = [],
  workspace = WORKSPACE,
  isAdmin = false,
  isViewer = false,
} = {}) {
  api.getMe.mockResolvedValue(makeMeResponse({ isAdmin, isViewer }));
  api.listWorkspaces.mockResolvedValue([workspace]);
  api.getWorkspace.mockResolvedValue(workspace);
  api.listPersonas.mockResolvedValue({
    items: personas,
    pagination: {
      total_count: personas.length,
      offset: 0,
      limit: 50,
      returned_count: personas.length,
      has_more: false,
    },
  });

  render(
    <MemoryRouter initialEntries={[`/workspaces/${workspace.id}/personas`]}>
      <UserProvider>
        <WorkspaceProvider>
          <ConfirmDialogProvider>
            <Routes>
              <Route path="/workspaces/:id/personas" element={<PersonaLibrary />} />
            </Routes>
          </ConfirmDialogProvider>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PersonaLibrary — display', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders personas with name and description', async () => {
    await renderPersonaLibrary({ personas: [PERSONA_1, PERSONA_2] });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });
    expect(screen.getByText('Enterprise Decision Maker')).toBeInTheDocument();
    expect(screen.getByText(/Ages 25-35/)).toBeInTheDocument();
    expect(screen.getByText(/VP\/Director level/)).toBeInTheDocument();
  });

  it('shows empty state when no personas exist', async () => {
    await renderPersonaLibrary({ personas: [] });

    await waitFor(() => {
      expect(screen.getByText(/No personas in this workspace yet/i)).toBeInTheDocument();
    });
  });

  it('renders breadcrumb with workspace name', async () => {
    await renderPersonaLibrary({ personas: [] });

    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument();
    });
    expect(screen.getByText('Personas')).toBeInTheDocument();
  });

  it('renders the page heading', async () => {
    await renderPersonaLibrary({ personas: [] });

    await waitFor(() => {
      expect(screen.getByText(/Persona Library/i)).toBeInTheDocument();
    });
  });
});

describe('PersonaLibrary — search', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('filters personas by search query', async () => {
    await renderPersonaLibrary({ personas: [PERSONA_1, PERSONA_2] });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search personas/i);
    fireEvent.change(searchInput, { target: { value: 'Enterprise' } });

    expect(screen.queryByText('Tech-Savvy Millennial')).not.toBeInTheDocument();
    expect(screen.getByText('Enterprise Decision Maker')).toBeInTheDocument();
  });

  it('shows no results message when search matches nothing', async () => {
    await renderPersonaLibrary({ personas: [PERSONA_1] });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search personas/i);
    fireEvent.change(searchInput, { target: { value: 'zzzzz' } });

    expect(screen.getByText(/No personas match your search/i)).toBeInTheDocument();
  });
});

describe('PersonaLibrary — create', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows New Persona button for creators', async () => {
    await renderPersonaLibrary({ personas: [] });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /New Persona/i })).toBeInTheDocument();
    });
  });

  it('opens create modal and creates persona on submit', async () => {
    api.createPersona.mockResolvedValue({
      ...PERSONA_1,
      id: 'p-new',
      name: 'New Persona',
      description: 'Fresh persona',
    });

    await renderPersonaLibrary({ personas: [] });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /New Persona/i })).toBeInTheDocument();
    });

    // Click "Create your first persona" in empty state
    fireEvent.click(screen.getByRole('button', { name: /Create your first persona/i }));

    // Fill form
    await waitFor(() => {
      expect(screen.getByLabelText(/Name \*/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Name \*/i), {
      target: { value: 'New Persona' },
    });
    fireEvent.change(screen.getByLabelText(/Description \*/i), {
      target: { value: 'Fresh persona' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    await waitFor(() => {
      expect(api.createPersona).toHaveBeenCalledWith('ws-1', {
        name: 'New Persona',
        description: 'Fresh persona',
      });
    });

    // Persona should appear in the list
    await waitFor(() => {
      expect(screen.getByText('New Persona')).toBeInTheDocument();
    });
  });
});

describe('PersonaLibrary — edit', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('opens edit modal with current values and updates on submit', async () => {
    api.updatePersona.mockResolvedValue({
      ...PERSONA_1,
      name: 'Updated Name',
    });

    await renderPersonaLibrary({ personas: [PERSONA_1] });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Name \*/i)).toHaveValue('Tech-Savvy Millennial');
    });

    fireEvent.change(screen.getByLabelText(/Name \*/i), {
      target: { value: 'Updated Name' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    await waitFor(() => {
      expect(api.updatePersona).toHaveBeenCalledWith('ws-1', 'p-1', {
        name: 'Updated Name',
        description: PERSONA_1.description,
      });
    });
  });
});

describe('PersonaLibrary — delete', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls deletePersona after confirmation', async () => {
    api.deletePersona.mockResolvedValue(undefined);

    await renderPersonaLibrary({ personas: [PERSONA_1] });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });

    // Click the delete button on the persona card
    const personaCard = screen.getByTestId('persona-card-p-1');
    const cardDeleteBtn = Array.from(personaCard.querySelectorAll('button')).find(
      (btn) => btn.textContent === 'Delete',
    );
    fireEvent.click(cardDeleteBtn);

    // Confirm dialog should appear
    await waitFor(() => {
      expect(screen.getByText(/Delete this persona/i)).toBeInTheDocument();
    });

    // The confirm dialog renders a btn-danger button — click it
    const dangerBtn = document.querySelector('.btn-danger');
    fireEvent.click(dangerBtn);

    await waitFor(() => {
      expect(api.deletePersona).toHaveBeenCalledWith('ws-1', 'p-1');
    });
  });
});

describe('PersonaLibrary — RBAC', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('hides New Persona button and action buttons for viewers', async () => {
    await renderPersonaLibrary({
      personas: [PERSONA_1],
      isViewer: true,
      workspace: { ...WORKSPACE, role: 'viewer' },
    });

    await waitFor(() => {
      expect(screen.getByText('Tech-Savvy Millennial')).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /New Persona/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete/i })).not.toBeInTheDocument();
  });
});
