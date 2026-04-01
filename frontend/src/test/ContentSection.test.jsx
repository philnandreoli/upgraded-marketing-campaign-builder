/**
 * Tests for ContentSection component — image generation feature.
 *
 * Covers:
 *  - "Generate Image" button hidden when imageGenerationEnabled=false
 *  - "Generate Image" button visible when imageGenerationEnabled=true and no image exists
 *  - Button is disabled for viewer-role users
 *  - Clicking the button calls generateImageAsset and triggers onImageGenerated
 *  - Loading spinner shown while generating
 *  - Error state shown when generation fails
 *  - Image preview thumbnail shown when an image asset exists for the piece
 *  - "View in Gallery" button calls onViewGallery when provided
 *  - Image brief shown as expandable section when available
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ContentSection from '../components/ContentSection.jsx';

vi.mock('../api');
import * as api from '../api';

// Provide stub implementations for context hooks used inside ContentSection
vi.mock('../ConfirmDialogContext', () => ({
  useConfirm: () => vi.fn(),
}));
vi.mock('../ToastContext', () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));
vi.mock('../NotificationContext', () => ({
  useNotifications: () => ({ notifications: [], dismiss: vi.fn(), dismissAll: vi.fn(), addEvent: vi.fn() }),
}));

const WORKSPACE_ID = 'ws-1';
const CAMPAIGN_ID = 'camp-1';

const PIECE_WITH_BRIEF = {
  content_type: 'social_post',
  content: 'Check out our amazing new product!',
  image_brief: { prompt: 'A vibrant product shot on white background' },
};

const PIECE_NO_BRIEF = {
  content_type: 'headline',
  content: 'Big Sale This Weekend',
};

const CONTENT_DATA = {
  theme: 'Summer Sale',
  tone_of_voice: 'Energetic',
  pieces: [PIECE_WITH_BRIEF, PIECE_NO_BRIEF],
};

const ASSET_PIECE_0 = {
  id: 'asset-1',
  content_piece_index: 0,
  url: 'https://example.com/img1.png',
  image_url: null,
  prompt: 'A vibrant product shot on white background',
  dimensions: '1024x1024',
};

function renderSection(overrides = {}) {
  const defaults = {
    data: CONTENT_DATA,
    error: null,
    socialPlatforms: [],
    status: 'content',
    campaignId: CAMPAIGN_ID,
    workspaceId: WORKSPACE_ID,
    imageAssets: [],
    imageGenerationEnabled: false,
    isViewer: false,
    onImageGenerated: vi.fn(),
    onViewGallery: vi.fn(),
  };
  return render(<ContentSection {...defaults} {...overrides} />);
}

describe('ContentSection – image generation hidden by default', () => {
  it('does not show Generate Image button when imageGenerationEnabled=false', () => {
    renderSection({ imageGenerationEnabled: false });
    expect(screen.queryByRole('button', { name: /generate image/i })).not.toBeInTheDocument();
  });

  it('does not show image preview when imageGenerationEnabled=false even if assets exist', () => {
    renderSection({ imageGenerationEnabled: false, imageAssets: [ASSET_PIECE_0] });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});

describe('ContentSection – Generate Image button visible', () => {
  it('shows Generate Image button only for pieces with image_brief when imageGenerationEnabled=true and no assets', () => {
    renderSection({ imageGenerationEnabled: true, imageAssets: [] });
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    expect(buttons).toHaveLength(1);
  });

  it('does not show Generate Image button for pieces without image_brief', () => {
    const dataOnlyNoBrief = { theme: null, tone_of_voice: null, pieces: [PIECE_NO_BRIEF] };
    renderSection({ imageGenerationEnabled: true, imageAssets: [], data: dataOnlyNoBrief });
    expect(screen.queryByRole('button', { name: /generate image/i })).not.toBeInTheDocument();
  });

  it('button is disabled for viewer-role users', () => {
    const dataWithBrief = { theme: null, tone_of_voice: null, pieces: [PIECE_WITH_BRIEF] };
    renderSection({ imageGenerationEnabled: true, isViewer: true, imageAssets: [], data: dataWithBrief });
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it('button is enabled for non-viewer users', () => {
    const dataWithBrief = { theme: null, tone_of_voice: null, pieces: [PIECE_WITH_BRIEF] };
    renderSection({ imageGenerationEnabled: true, isViewer: false, imageAssets: [], data: dataWithBrief });
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    buttons.forEach((btn) => expect(btn).not.toBeDisabled());
  });
});

describe('ContentSection – clicking Generate Image', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls generateImageAsset with correct args when button clicked', async () => {
    api.generateImageAsset.mockResolvedValue({ id: 'asset-new' });
    const onImageGenerated = vi.fn();
    renderSection({ imageGenerationEnabled: true, imageAssets: [], onImageGenerated });

    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(api.generateImageAsset).toHaveBeenCalledWith(WORKSPACE_ID, CAMPAIGN_ID, 0);
    });
  });

  it('calls onImageGenerated after successful generation', async () => {
    api.generateImageAsset.mockResolvedValue({ id: 'asset-new' });
    const onImageGenerated = vi.fn();
    renderSection({ imageGenerationEnabled: true, imageAssets: [], onImageGenerated });

    fireEvent.click(screen.getAllByRole('button', { name: /generate image for piece/i })[0]);

    await waitFor(() => {
      expect(onImageGenerated).toHaveBeenCalled();
    });
  });

  it('shows spinner while generating', async () => {
    // Never resolves so we can observe the loading state
    api.generateImageAsset.mockReturnValue(new Promise(() => {}));
    renderSection({ imageGenerationEnabled: true, imageAssets: [] });

    fireEvent.click(screen.getAllByRole('button', { name: /generate image for piece/i })[0]);

    await waitFor(() => {
      expect(screen.getByText(/generating…/i)).toBeInTheDocument();
    });
  });

  it('shows error message when generation fails', async () => {
    api.generateImageAsset.mockRejectedValue(new Error('Service unavailable'));
    renderSection({ imageGenerationEnabled: true, imageAssets: [] });

    fireEvent.click(screen.getAllByRole('button', { name: /generate image for piece/i })[0]);

    await waitFor(() => {
      expect(screen.getByText(/service unavailable/i)).toBeInTheDocument();
    });
  });
});

describe('ContentSection – image preview', () => {
  it('shows thumbnail image when asset exists for a piece', () => {
    renderSection({ imageGenerationEnabled: true, imageAssets: [ASSET_PIECE_0] });
    const imgs = screen.getAllByRole('img');
    expect(imgs.length).toBeGreaterThanOrEqual(1);
  });

  it('hides Generate Image button for pieces that already have an image', () => {
    renderSection({ imageGenerationEnabled: true, imageAssets: [ASSET_PIECE_0] });
    // Piece 0 has an image → shows ImageAssetCard, no Generate button
    // Piece 1 has no image_brief → no Generate button shown
    expect(screen.queryByRole('button', { name: /generate image for piece/i })).not.toBeInTheDocument();
  });

  it('shows View in Gallery button when onViewGallery is provided and image exists', () => {
    const onViewGallery = vi.fn();
    renderSection({ imageGenerationEnabled: true, imageAssets: [ASSET_PIECE_0], onViewGallery });
    expect(screen.getByRole('button', { name: /view in gallery/i })).toBeInTheDocument();
  });

  it('calls onViewGallery when View in Gallery is clicked', () => {
    const onViewGallery = vi.fn();
    renderSection({ imageGenerationEnabled: true, imageAssets: [ASSET_PIECE_0], onViewGallery });
    fireEvent.click(screen.getByRole('button', { name: /view in gallery/i }));
    expect(onViewGallery).toHaveBeenCalled();
  });
});

describe('ContentSection – image brief', () => {
  it('shows image brief as expandable section when available', () => {
    renderSection({ imageGenerationEnabled: true, imageAssets: [] });
    expect(screen.getByText(/image brief/i)).toBeInTheDocument();
  });

  it('does not show image brief section for pieces without image_brief', () => {
    const dataOnlyNoBrief = {
      theme: null,
      tone_of_voice: null,
      pieces: [PIECE_NO_BRIEF],
    };
    renderSection({ imageGenerationEnabled: true, imageAssets: [], data: dataOnlyNoBrief });
    expect(screen.queryByText(/image brief/i)).not.toBeInTheDocument();
  });
});

/* ───── Combined Email Subject + Body card ───── */

const EMAIL_SUBJECT_PIECE = {
  content_type: 'email_subject',
  content: 'Don\'t miss our summer sale!',
  channel: 'email',
  variant: 'A',
};

const EMAIL_BODY_PIECE = {
  content_type: 'email_body',
  content: 'Shop now and save 30% on all items this weekend only.',
  channel: 'email',
  variant: 'A',
  image_brief: { prompt: 'Email hero banner' },
};

const EMAIL_DATA = {
  theme: 'Summer Sale',
  tone_of_voice: 'Energetic',
  pieces: [EMAIL_SUBJECT_PIECE, EMAIL_BODY_PIECE],
};

describe('ContentSection – combined email card', () => {
  it('renders Email Subject and Email Body as a single combined card', () => {
    renderSection({ data: EMAIL_DATA });
    // The combined card shows "Email" as the type, not separate "Email Subject" / "Email Body"
    expect(screen.getByText(/📧 Email/)).toBeInTheDocument();
    expect(screen.queryByText('Email Subject')).not.toBeInTheDocument();
    expect(screen.queryByText('Email Body')).not.toBeInTheDocument();
  });

  it('shows Subject and Body labels inside the combined card', () => {
    renderSection({ data: EMAIL_DATA });
    expect(screen.getByText('Subject')).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
  });

  it('renders subject content and body content together', () => {
    renderSection({ data: EMAIL_DATA });
    expect(screen.getByText(EMAIL_SUBJECT_PIECE.content)).toBeInTheDocument();
    expect(screen.getByText(EMAIL_BODY_PIECE.content)).toBeInTheDocument();
  });

  it('shows rendered preview by default in approval mode and can toggle raw markdown editing', () => {
    renderSection({ data: EMAIL_DATA, isApprovalMode: true, status: 'content_approval' });

    expect(screen.getByText(EMAIL_SUBJECT_PIECE.content)).toBeInTheDocument();
    expect(screen.getByText(EMAIL_BODY_PIECE.content)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(EMAIL_SUBJECT_PIECE.content)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(EMAIL_BODY_PIECE.content)).not.toBeInTheDocument();

    const editButtons = screen.getAllByRole('button', { name: /edit markdown/i });
    expect(editButtons).toHaveLength(2);

    fireEvent.click(editButtons[0]);
    fireEvent.click(editButtons[1]);

    expect(screen.getByDisplayValue(EMAIL_SUBJECT_PIECE.content)).toBeInTheDocument();
    expect(screen.getByDisplayValue(EMAIL_BODY_PIECE.content)).toBeInTheDocument();
  });

  it('shows rendered markdown preview for approval-mode content cards', () => {
    const markdownData = {
      theme: 'Markdown Approval',
      tone_of_voice: 'Clear',
      pieces: [
        {
          content_type: 'social_post',
          content: '## Approval Preview\n\n- First bullet\n- Second bullet',
        },
      ],
    };

    const { container } = renderSection({ data: markdownData, isApprovalMode: true, status: 'content_approval' });

    expect(screen.getByRole('heading', { level: 2, name: 'Approval Preview' })).toBeInTheDocument();
    expect(screen.getByText('First bullet')).toBeInTheDocument();
    expect(container.querySelector('.approval-piece-preview ul')).not.toBeNull();
  });

  it('shows single set of approve/reject buttons for combined card', () => {
    renderSection({ data: EMAIL_DATA, isApprovalMode: true, status: 'content_approval' });
    const approveButtons = screen.getAllByRole('button', { name: /approve/i });
    const rejectButtons = screen.getAllByRole('button', { name: /reject/i });
    // One pair of approve/reject for the combined card (plus the "Reject Entire Campaign" button)
    expect(approveButtons).toHaveLength(1);
    expect(rejectButtons).toHaveLength(2); // piece reject + campaign reject
  });

  it('calls updatePieceDecision for both subject and body when approving', async () => {
    api.updatePieceDecision.mockResolvedValue({});
    renderSection({ data: EMAIL_DATA, isApprovalMode: true, status: 'content_approval' });

    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() => {
      // Called for subject (index 0) and body (index 1)
      expect(api.updatePieceDecision).toHaveBeenCalledTimes(2);
      expect(api.updatePieceDecision).toHaveBeenCalledWith(WORKSPACE_ID, CAMPAIGN_ID, 0, expect.objectContaining({ approved: true }));
      expect(api.updatePieceDecision).toHaveBeenCalledWith(WORKSPACE_ID, CAMPAIGN_ID, 1, expect.objectContaining({ approved: true }));
    });
  });

  it('still renders non-email pieces normally alongside combined card', () => {
    const mixedData = {
      theme: 'Mixed',
      tone_of_voice: 'Casual',
      pieces: [
        PIECE_WITH_BRIEF,
        EMAIL_SUBJECT_PIECE,
        EMAIL_BODY_PIECE,
      ],
    };
    renderSection({ data: mixedData });
    // Should see: social_post card + combined email card (not 3 separate cards)
    expect(screen.getByText(PIECE_WITH_BRIEF.content)).toBeInTheDocument();
    expect(screen.getByText(/📧 Email/)).toBeInTheDocument();
    expect(screen.getByText('Subject')).toBeInTheDocument();
  });

  it('renders markdown formatting for read-only content pieces', () => {
    const markdownData = {
      theme: 'Markdown Campaign',
      tone_of_voice: 'Clear',
      pieces: [
        {
          content_type: 'body_copy',
          content: '## Launch Checklist\n\n- Final QA\n- Publish campaign',
        },
      ],
    };

    const { container } = renderSection({ data: markdownData });

    expect(screen.getByRole('heading', { level: 2, name: 'Launch Checklist' })).toBeInTheDocument();
    expect(screen.getByText('Final QA')).toBeInTheDocument();
    expect(screen.getByText('Publish campaign')).toBeInTheDocument();
    expect(container.querySelector('.piece-body ul')).not.toBeNull();
  });
});
