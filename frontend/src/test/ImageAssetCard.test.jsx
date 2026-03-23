/**
 * Tests for ImageAssetCard component.
 *
 * Covers:
 *  - Download button is rendered
 *  - Regenerate button is rendered and enabled for editors
 *  - Regenerate button is disabled for viewers (canEdit=false)
 *  - Clicking Regenerate opens the prompt-edit modal
 *  - Modal is pre-filled with the asset's original prompt
 *  - Submitting the modal calls generateImageAsset with the edited prompt
 *  - After successful regeneration, onRegenerated callback is invoked
 *  - Modal closes after successful regeneration
 *  - Error message shown when regeneration API call fails
 *  - Cancel button closes the modal
 *  - Compact mode renders the thumbnail and action bar
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ImageAssetCard from '../components/ImageAssetCard.jsx';

vi.mock('../api');
import * as api from '../api';

const WORKSPACE_ID = 'ws-1';
const CAMPAIGN_ID = 'camp-1';

const ASSET = {
  id: 'asset-1',
  url: 'https://example.com/img1.png',
  prompt: 'A vibrant product shot on white background',
  dimensions: '1024x1024',
  content_piece_index: 0,
  created_at: '2026-01-15T10:30:00Z',
};

function renderCard(overrides = {}) {
  const defaults = {
    asset: ASSET,
    workspaceId: WORKSPACE_ID,
    campaignId: CAMPAIGN_ID,
    canEdit: true,
    compact: false,
    onRegenerated: vi.fn(),
  };
  return render(<ImageAssetCard {...defaults} {...overrides} />);
}

describe('ImageAssetCard – download button', () => {
  it('renders a Download button', () => {
    renderCard();
    expect(screen.getByRole('button', { name: /download image/i })).toBeInTheDocument();
  });
});

describe('ImageAssetCard – regenerate button', () => {
  it('renders a Regenerate button', () => {
    renderCard();
    expect(screen.getByRole('button', { name: /edit prompt and regenerate/i })).toBeInTheDocument();
  });

  it('Regenerate button is enabled when canEdit=true', () => {
    renderCard({ canEdit: true });
    expect(screen.getByRole('button', { name: /edit prompt and regenerate/i })).not.toBeDisabled();
  });

  it('Regenerate button is disabled when canEdit=false (viewer)', () => {
    renderCard({ canEdit: false });
    expect(screen.getByRole('button', { name: /edit prompt and regenerate/i })).toBeDisabled();
  });
});

describe('ImageAssetCard – regenerate modal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens modal when Regenerate is clicked', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    expect(screen.getByRole('dialog', { name: /edit prompt and regenerate/i })).toBeInTheDocument();
  });

  it('modal textarea is pre-filled with the original prompt', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    const textarea = screen.getByRole('textbox', { name: /image prompt/i });
    expect(textarea.value).toBe(ASSET.prompt);
  });

  it('Cancel button closes the modal', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog', { name: /edit prompt and regenerate/i })).not.toBeInTheDocument();
  });

  it('clicking Regenerate in modal calls generateImageAsset with edited prompt', async () => {
    api.generateImageAsset.mockResolvedValue({ id: 'new-asset' });
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));

    const textarea = screen.getByRole('textbox', { name: /image prompt/i });
    fireEvent.change(textarea, { target: { value: 'Updated product shot on blue background' } });

    fireEvent.click(screen.getByRole('button', { name: /^regenerate image$/i }));

    await waitFor(() => {
      expect(api.generateImageAsset).toHaveBeenCalledWith(
        WORKSPACE_ID,
        CAMPAIGN_ID,
        ASSET.content_piece_index,
        'Updated product shot on blue background',
      );
    });
  });

  it('calls onRegenerated after successful regeneration', async () => {
    api.generateImageAsset.mockResolvedValue({ id: 'new-asset' });
    const onRegenerated = vi.fn();
    renderCard({ onRegenerated });
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    fireEvent.click(screen.getByRole('button', { name: /^regenerate image$/i }));

    await waitFor(() => {
      expect(onRegenerated).toHaveBeenCalled();
    });
  });

  it('modal closes after successful regeneration', async () => {
    api.generateImageAsset.mockResolvedValue({ id: 'new-asset' });
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    fireEvent.click(screen.getByRole('button', { name: /^regenerate image$/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /edit prompt and regenerate/i })).not.toBeInTheDocument();
    });
  });

  it('shows error message when regeneration API call fails', async () => {
    api.generateImageAsset.mockRejectedValue(new Error('Service unavailable'));
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    fireEvent.click(screen.getByRole('button', { name: /^regenerate image$/i }));

    await waitFor(() => {
      expect(screen.getByText(/service unavailable/i)).toBeInTheDocument();
    });
  });

  it('modal stays open after a failed regeneration', async () => {
    api.generateImageAsset.mockRejectedValue(new Error('Error'));
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: /edit prompt and regenerate/i }));
    fireEvent.click(screen.getByRole('button', { name: /^regenerate image$/i }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /edit prompt and regenerate/i })).toBeInTheDocument();
    });
  });
});

describe('ImageAssetCard – compact mode', () => {
  it('renders thumbnail image in compact mode', () => {
    renderCard({ compact: true });
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('renders Download and Regenerate buttons in compact mode', () => {
    renderCard({ compact: true });
    expect(screen.getByRole('button', { name: /download image/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit prompt and regenerate/i })).toBeInTheDocument();
  });
});
