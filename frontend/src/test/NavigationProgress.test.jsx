/**
 * Tests for NavigationProgress — animated route-change progress bar.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import NavigationProgress from '../components/NavigationProgress.jsx';

/** Utility: render NavigationProgress inside a router with a changeable location. */
function renderWithRouter(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <NavigationProgress />
    </MemoryRouter>,
  );
}

describe('NavigationProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a progress bar element with the correct role', () => {
    renderWithRouter();
    expect(screen.getByRole('progressbar', { name: /page loading/i })).toBeInTheDocument();
  });

  it('starts with the base class only (invisible)', () => {
    renderWithRouter();
    const bar = screen.getByRole('progressbar');
    expect(bar.className).toBe('nav-progress');
  });

  it('does not show active classes on initial render', () => {
    renderWithRouter();
    const bar = screen.getByRole('progressbar');
    expect(bar.className).not.toContain('nav-progress--growing');
    expect(bar.className).not.toContain('nav-progress--complete');
    expect(bar.className).not.toContain('nav-progress--fadeout');
  });
});
