/**
 * Tests for ProgressIndicator component.
 *
 * Validates:
 *  - Renders correct "N/M stages" label
 *  - Progress bar fill width matches percentage
 *  - Accessible progressbar role and aria attributes
 *  - Renders nothing when totalCount is 0
 *  - Shows 100% for fully completed campaigns
 */

import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ProgressIndicator from '../components/ProgressIndicator.jsx';

describe('ProgressIndicator', () => {
  it('renders the correct label for partial progress', () => {
    const { container } = render(<ProgressIndicator completedCount={3} totalCount={8} />);
    const label = container.querySelector('.progress-indicator-label');
    expect(label.textContent).toBe('3/8 stages');
  });

  it('renders the correct fill width percentage', () => {
    const { container } = render(<ProgressIndicator completedCount={3} totalCount={6} />);
    const fill = container.querySelector('.progress-indicator-fill');
    expect(fill.style.width).toBe('50%');
  });

  it('renders 100% fill when all stages are complete', () => {
    const { container } = render(<ProgressIndicator completedCount={8} totalCount={8} />);
    const fill = container.querySelector('.progress-indicator-fill');
    expect(fill.style.width).toBe('100%');
    const label = container.querySelector('.progress-indicator-label');
    expect(label.textContent).toBe('8/8 stages');
  });

  it('renders 0% fill when no stages are complete', () => {
    const { container } = render(<ProgressIndicator completedCount={0} totalCount={8} />);
    const fill = container.querySelector('.progress-indicator-fill');
    expect(fill.style.width).toBe('0%');
    const label = container.querySelector('.progress-indicator-label');
    expect(label.textContent).toBe('0/8 stages');
  });

  it('renders nothing when totalCount is 0', () => {
    const { container } = render(<ProgressIndicator completedCount={0} totalCount={0} />);
    expect(container.innerHTML).toBe('');
  });

  it('has accessible progressbar role and aria attributes', () => {
    const { container } = render(<ProgressIndicator completedCount={4} totalCount={8} />);
    const el = container.querySelector('[role="progressbar"]');
    expect(el).not.toBeNull();
    expect(el.getAttribute('aria-valuenow')).toBe('4');
    expect(el.getAttribute('aria-valuemin')).toBe('0');
    expect(el.getAttribute('aria-valuemax')).toBe('8');
    expect(el.getAttribute('aria-label')).toBe('4 of 8 stages complete');
  });

  it('rounds percentage correctly for non-even divisions', () => {
    const { container } = render(<ProgressIndicator completedCount={1} totalCount={3} />);
    const fill = container.querySelector('.progress-indicator-fill');
    expect(fill.style.width).toBe('33%');
  });
});
