/**
 * Tests for PipelineProgress component.
 *
 * Key behaviours verified:
 *  - Stage completion is determined by output data existing on the campaign,
 *    not solely by the current status index.
 *  - The "Review" stage is NOT marked completed just because the status has
 *    advanced to "content_revision" — it requires campaign.review to be set.
 *  - Terminal statuses (approved / rejected / manual_review_required) mark
 *    every stage as completed.
 */

import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import PipelineProgress from '../components/PipelineProgress.jsx';

// Helper: render the component and return each stage div by its text label.
function renderStages(campaign) {
  const { container } = render(<PipelineProgress campaign={campaign} />);
  return Array.from(container.querySelectorAll('.pipeline-step'));
}

function classesOf(stageEl) {
  return stageEl.className.split(' ').filter(Boolean);
}

describe('PipelineProgress – data-based completion', () => {
  it('marks Review as active (not completed) when status=content_revision but campaign.review is null', () => {
    const campaign = {
      status: 'content_revision',
      strategy: { id: 1 },
      content: { body: 'x' },
      channel_plan: { channels: [] },
      analytics_plan: { kpis: [] },
      review: null,            // review output not yet available
      content_revision_count: 0,
    };

    const stages = renderStages(campaign);
    const reviewEl = stages.find(el => el.textContent === 'Review');
    const revisionEl = stages.find(el => el.textContent === 'Revision');

    // Review has no output — must NOT be completed
    expect(classesOf(reviewEl)).not.toContain('completed');

    // Revision is the current stage with no output yet — should be active
    expect(classesOf(revisionEl)).toContain('active');
  });

  it('marks Review as completed when campaign.review is populated (even if status is content_revision)', () => {
    const campaign = {
      status: 'content_revision',
      strategy: { id: 1 },
      content: { body: 'x' },
      channel_plan: { channels: [] },
      analytics_plan: { kpis: [] },
      review: { brand_consistency_score: 8, approved: true, issues: [], suggestions: [] },
      content_revision_count: 0,
    };

    const stages = renderStages(campaign);
    const reviewEl = stages.find(el => el.textContent === 'Review');

    expect(classesOf(reviewEl)).toContain('completed');
  });

  it('marks Revision as completed when content_revision_count > 0', () => {
    const campaign = {
      status: 'content_approval',
      strategy: { id: 1 },
      content: { body: 'revised' },
      channel_plan: { channels: [] },
      analytics_plan: { kpis: [] },
      review: { brand_consistency_score: 8, approved: true, issues: [], suggestions: [] },
      content_revision_count: 1,
    };

    const stages = renderStages(campaign);
    const revisionEl = stages.find(el => el.textContent === 'Revision');

    expect(classesOf(revisionEl)).toContain('completed');
  });

  it('does NOT mark Revision as completed when content_revision_count is 0', () => {
    const campaign = {
      status: 'content_revision',
      strategy: { id: 1 },
      content: { body: 'x' },
      channel_plan: { channels: [] },
      analytics_plan: { kpis: [] },
      review: { brand_consistency_score: 8, approved: false, issues: [], suggestions: [] },
      content_revision_count: 0,
    };

    const stages = renderStages(campaign);
    const revisionEl = stages.find(el => el.textContent === 'Revision');

    expect(classesOf(revisionEl)).not.toContain('completed');
  });
});

describe('PipelineProgress – terminal statuses', () => {
  ['approved', 'rejected', 'manual_review_required'].forEach((terminalStatus) => {
    it(`marks all stages as completed when status is "${terminalStatus}"`, () => {
      const campaign = { status: terminalStatus };

      const stages = renderStages(campaign);
      stages.forEach((stage) => {
        expect(classesOf(stage)).toContain('completed');
      });
    });
  });
});

describe('PipelineProgress – pending stages', () => {
  it('marks stages after the current status as pending (no completed/active class)', () => {
    const campaign = {
      status: 'strategy',
      strategy: null,
    };

    const stages = renderStages(campaign);
    // Stages after strategy (content, channel_planning, analytics_setup, review, content_revision, content_approval)
    // should be neither completed nor active
    const labelsAfterStrategy = ['Content', 'Channels', 'Analytics', 'Review', 'Revision', 'Approval'];
    labelsAfterStrategy.forEach((label) => {
      const el = stages.find(s => s.textContent === label);
      const classes = classesOf(el);
      expect(classes).not.toContain('completed');
      expect(classes).not.toContain('active');
    });
  });
});

describe('PipelineProgress – draft startup', () => {
  it('marks Draft as active and all pipeline stages as pending when status is "draft"', () => {
    const campaign = { status: 'draft' };

    const stages = renderStages(campaign);
    const draftEl = stages.find(el => el.textContent === 'Draft');
    const pipelineLabels = ['Strategy', 'Content', 'Channels', 'Analytics', 'Review', 'Revision', 'Approval'];

    // Draft stage is the current stage — should be active
    expect(classesOf(draftEl)).toContain('active');

    // All pipeline stages have not started yet — should be neither completed nor active
    pipelineLabels.forEach((label) => {
      const el = stages.find(s => s.textContent === label);
      const classes = classesOf(el);
      expect(classes).not.toContain('completed');
      expect(classes).not.toContain('active');
    });
  });
});
