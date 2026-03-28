/**
 * Tests for StrategySection "Save as Persona" feature.
 *
 * Covers:
 *  - Renders "Save as Persona" button when canSavePersona is true
 *  - Does not render button when canSavePersona is false
 *  - Opens persona form with prefilled audience data
 *  - Calls onSavePersona on form submit
 *  - Shows success message after saving
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import StrategySection from '../components/StrategySection';

vi.mock('../api');

const STRATEGY_DATA = {
  value_proposition: 'Best cloud storage',
  positioning: 'Enterprise-grade security',
  objectives: ['Increase signups'],
  key_messages: ['Secure and fast'],
  target_audience: {
    demographics: 'Ages 25-45, professionals',
    psychographics: 'Values productivity and security',
    pain_points: ['Data loss', 'Slow uploads'],
    personas: ['IT Manager', 'Startup Founder'],
  },
  competitive_landscape: 'Competing with AWS and Azure',
};

describe('StrategySection — Save as Persona', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders "Save as Persona" button when canSavePersona is true', () => {
    render(
      <StrategySection
        data={STRATEGY_DATA}
        canSavePersona={true}
        onSavePersona={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /Save as Persona/i })).toBeInTheDocument();
  });

  it('does not render "Save as Persona" button when canSavePersona is false', () => {
    render(<StrategySection data={STRATEGY_DATA} />);

    expect(screen.queryByRole('button', { name: /Save as Persona/i })).not.toBeInTheDocument();
  });

  it('does not render button when there is no target audience', () => {
    const dataWithoutAudience = { ...STRATEGY_DATA, target_audience: {} };
    render(
      <StrategySection
        data={dataWithoutAudience}
        canSavePersona={true}
        onSavePersona={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /Save as Persona/i })).not.toBeInTheDocument();
  });

  it('opens persona form when button is clicked', async () => {
    render(
      <StrategySection
        data={STRATEGY_DATA}
        canSavePersona={true}
        onSavePersona={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Save as Persona/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Name \*/i)).toBeInTheDocument();
    });

    // Description should be prefilled with audience data
    const descField = screen.getByLabelText(/Description \*/i);
    expect(descField.value).toContain('Ages 25-45');
    expect(descField.value).toContain('productivity and security');
  });

  it('calls onSavePersona with form values on submit', async () => {
    const mockSave = vi.fn().mockResolvedValue({});

    render(
      <StrategySection
        data={STRATEGY_DATA}
        canSavePersona={true}
        onSavePersona={mockSave}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Save as Persona/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Name \*/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Name \*/i), {
      target: { value: 'My Persona' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Save$/i }));

    await waitFor(() => {
      expect(mockSave).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'My Persona',
          description: expect.stringContaining('Ages 25-45'),
        }),
      );
    });
  });

  it('shows success message after saving', async () => {
    const mockSave = vi.fn().mockResolvedValue({});

    render(
      <StrategySection
        data={STRATEGY_DATA}
        canSavePersona={true}
        onSavePersona={mockSave}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Save as Persona/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Name \*/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Name \*/i), {
      target: { value: 'My Persona' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Persona "My Persona" saved!/)).toBeInTheDocument();
    });
  });
});
