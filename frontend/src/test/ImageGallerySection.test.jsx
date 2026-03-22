/**
 * Tests for ImageGallerySection component.
 *
 * Covers:
 *  - Loading state shown while fetching
 *  - Empty state shown when no assets exist
 *  - Images rendered in a grid grouped by content piece
 *  - Each card shows thumbnail, prompt, dimensions, and timestamp
 *  - Error state shown when the API call fails
 *  - Lightbox opens on thumbnail click
 *  - Gallery refreshes on image_generated WebSocket events
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ImageGallerySection from '../components/ImageGallerySection.jsx';

vi.mock('../api');
import * as api from '../api';

const WORKSPACE_ID = 'ws-1';
const CAMPAIGN_ID = 'camp-1';

const ASSET_1 = {
  id: 'asset-1',
  url: 'https://example.com/img1.png',
  prompt: 'A vibrant product shot on white background',
  dimensions: '1024x1024',
  content_piece_index: 0,
  created_at: '2026-01-15T10:30:00Z',
};

const ASSET_2 = {
  id: 'asset-2',
  url: 'https://example.com/img2.png',
  prompt: 'A lifestyle scene featuring the product in a modern kitchen',
  dimensions: '1024x1024',
  content_piece_index: 1,
  created_at: '2026-01-15T11:00:00Z',
};

function renderGallery({ assets = [], error = null, events = [] } = {}) {
  if (error) {
    api.listImageAssets.mockRejectedValue(new Error(error));
  } else {
    api.listImageAssets.mockResolvedValue({ assets });
  }
  return render(
    <ImageGallerySection
      workspaceId={WORKSPACE_ID}
      campaignId={CAMPAIGN_ID}
      events={events}
    />
  );
}

describe('ImageGallerySection – loading state', () => {
  it('shows loading indicator while fetching', () => {
    api.listImageAssets.mockReturnValue(new Promise(() => {})); // never resolves
    render(
      <ImageGallerySection
        workspaceId={WORKSPACE_ID}
        campaignId={CAMPAIGN_ID}
        events={[]}
      />
    );
    expect(screen.getByText(/loading images/i)).toBeInTheDocument();
  });
});

describe('ImageGallerySection – empty state', () => {
  it('shows empty state when no assets returned', async () => {
    renderGallery({ assets: [] });
    await waitFor(() => {
      expect(screen.getByText(/no images generated yet/i)).toBeInTheDocument();
    });
  });

  it('empty state contains guidance about Generate Image button', async () => {
    renderGallery({ assets: [] });
    await waitFor(() => {
      expect(screen.getByText(/generate image/i)).toBeInTheDocument();
    });
  });
});

describe('ImageGallerySection – populated state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders image thumbnails for each asset', async () => {
    renderGallery({ assets: [ASSET_1, ASSET_2] });
    await waitFor(() => {
      const imgs = screen.getAllByRole('img');
      expect(imgs).toHaveLength(2);
    });
  });

  it('shows prompt text for each image card', async () => {
    renderGallery({ assets: [ASSET_1] });
    await waitFor(() => {
      expect(screen.getByText(/vibrant product shot/i)).toBeInTheDocument();
    });
  });

  it('shows dimensions badge', async () => {
    renderGallery({ assets: [ASSET_1] });
    await waitFor(() => {
      expect(screen.getByText(/1024 × 1024/i)).toBeInTheDocument();
    });
  });

  it('groups images by content piece with section headers', async () => {
    renderGallery({ assets: [ASSET_1, ASSET_2] });
    await waitFor(() => {
      expect(screen.getByText('Content Piece 1')).toBeInTheDocument();
      expect(screen.getByText('Content Piece 2')).toBeInTheDocument();
    });
  });

  it('renders heading "Images"', async () => {
    renderGallery({ assets: [ASSET_1] });
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /images/i })).toBeInTheDocument();
    });
  });
});

describe('ImageGallerySection – error state', () => {
  it('shows error message when API call fails', async () => {
    renderGallery({ error: 'Network error' });
    await waitFor(() => {
      expect(screen.getByText(/failed to load images/i)).toBeInTheDocument();
    });
  });

  it('shows the error detail text', async () => {
    renderGallery({ error: 'Network error' });
    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeInTheDocument();
    });
  });
});

describe('ImageGallerySection – lightbox', () => {
  it('opens lightbox when thumbnail is clicked', async () => {
    renderGallery({ assets: [ASSET_1] });
    await waitFor(() => screen.getAllByRole('img'));
    const thumbBtn = screen.getByRole('button', { name: /view full image/i });
    fireEvent.click(thumbBtn);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes lightbox when close button is clicked', async () => {
    renderGallery({ assets: [ASSET_1] });
    await waitFor(() => screen.getAllByRole('img'));
    fireEvent.click(screen.getByRole('button', { name: /view full image/i }));
    fireEvent.click(screen.getByRole('button', { name: /close image preview/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('ImageGallerySection – refresh on WebSocket events', () => {
  it('reloads assets when image_generated event arrives', async () => {
    api.listImageAssets.mockResolvedValue({ assets: [] });
    const { rerender } = render(
      <ImageGallerySection
        workspaceId={WORKSPACE_ID}
        campaignId={CAMPAIGN_ID}
        events={[]}
      />
    );
    await waitFor(() => screen.getByText(/no images generated yet/i));

    // Simulate a new image_generated WebSocket event
    api.listImageAssets.mockResolvedValue({ assets: [ASSET_1] });
    rerender(
      <ImageGallerySection
        workspaceId={WORKSPACE_ID}
        campaignId={CAMPAIGN_ID}
        events={[{ type: 'image_generated', id: 'ev-1' }]}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText(/no images generated yet/i)).not.toBeInTheDocument();
      expect(screen.getAllByRole('img')).toHaveLength(1);
    });
  });
});
