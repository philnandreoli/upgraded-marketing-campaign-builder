/**
 * Tests for ReviewSection component.
 *
 * Key behaviours verified:
 *  - Spinner is shown ONLY when status === "review" and data is absent.
 *  - Spinner is NOT shown when status has moved past "review" (e.g. content_revision),
 *    even if campaign.review data is still null.
 *  - Review results are rendered whenever data is provided, regardless of status.
 *  - Error card is shown when error is present and data is absent (non-terminal status).
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ReviewSection from '../components/ReviewSection.jsx';

const sampleReview = {
  brand_consistency_score: 8.5,
  approved: true,
  issues: ['Minor tone issue'],
  suggestions: ['Add a CTA'],
  human_notes: null,
};

describe('ReviewSection – spinner behaviour', () => {
  it('shows spinner when data is null and status is "review"', () => {
    render(<ReviewSection data={null} status="review" error={null} />);
    expect(screen.getByText(/running review/i)).toBeInTheDocument();
  });

  it('does NOT show spinner when data is null and status is "content_revision"', () => {
    render(<ReviewSection data={null} status="content_revision" error={null} />);
    expect(screen.queryByText(/running review/i)).not.toBeInTheDocument();
  });

  it('does NOT show spinner when data is null and status is "approved"', () => {
    render(<ReviewSection data={null} status="approved" error={null} />);
    expect(screen.queryByText(/running review/i)).not.toBeInTheDocument();
  });

  it('does NOT show spinner when data is null and status is "rejected"', () => {
    render(<ReviewSection data={null} status="rejected" error={null} />);
    expect(screen.queryByText(/running review/i)).not.toBeInTheDocument();
  });

  it('does NOT show spinner when data is null and status is "content_approval"', () => {
    render(<ReviewSection data={null} status="content_approval" error={null} />);
    expect(screen.queryByText(/running review/i)).not.toBeInTheDocument();
  });
});

describe('ReviewSection – review results rendering', () => {
  it('renders review score and verdict when data is provided', () => {
    render(<ReviewSection data={sampleReview} status="content_revision" error={null} />);
    expect(screen.getByText(/brand consistency/i)).toBeInTheDocument();
    expect(screen.getByText(/ai verdict/i)).toBeInTheDocument();
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
  });

  it('renders review results when data is provided and status is still "review"', () => {
    render(<ReviewSection data={sampleReview} status="review" error={null} />);
    expect(screen.getByText(/brand consistency/i)).toBeInTheDocument();
  });

  it('renders issues list when data contains issues', () => {
    render(<ReviewSection data={sampleReview} status="content_revision" error={null} />);
    expect(screen.getByText('Minor tone issue')).toBeInTheDocument();
  });

  it('renders suggestions list when data contains suggestions', () => {
    render(<ReviewSection data={sampleReview} status="content_revision" error={null} />);
    expect(screen.getByText('Add a CTA')).toBeInTheDocument();
  });
});

describe('ReviewSection – error state', () => {
  it('shows error card when error is set and data is null (non-terminal status)', () => {
    render(<ReviewSection data={null} status="review" error="Review agent timed out" />);
    expect(screen.getByText(/review generation failed/i)).toBeInTheDocument();
    expect(screen.getByText(/review agent timed out/i)).toBeInTheDocument();
  });
});
