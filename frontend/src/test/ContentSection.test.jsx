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
  it('shows Generate Image button for each piece when imageGenerationEnabled=true and no assets', () => {
    renderSection({ imageGenerationEnabled: true, imageAssets: [] });
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    expect(buttons).toHaveLength(2);
  });

  it('button is disabled for viewer-role users', () => {
    renderSection({ imageGenerationEnabled: true, isViewer: true, imageAssets: [] });
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it('button is enabled for non-viewer users', () => {
    renderSection({ imageGenerationEnabled: true, isViewer: false, imageAssets: [] });
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
    // Piece 0 has an image → button should NOT appear for piece 0
    // Piece 1 still has no image → button should appear for piece 1
    const buttons = screen.getAllByRole('button', { name: /generate image for piece/i });
    expect(buttons).toHaveLength(1);
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
