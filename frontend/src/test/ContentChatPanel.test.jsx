import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ContentChatPanel from '../components/ContentChatPanel.jsx';

vi.mock('../api');
import * as api from '../api';

vi.mock('../ToastContext', () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));

vi.mock('../components/QuickActionChips.jsx', () => ({
  default: () => null,
}));

vi.mock('../components/ContentScoreBadge.jsx', () => ({
  default: () => null,
}));

describe('ContentChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    api.getContentChatHistory.mockResolvedValue({
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '### Revision Notes\n\n- Tighten intro\n- Add CTA',
          created_at: '2026-03-31T10:00:00Z',
          metadata: {},
        },
      ],
    });
    api.getContentChatSuggestions.mockResolvedValue({ suggestions: [] });
    api.getContentChatVersions.mockResolvedValue({ versions: [] });
    api.getContentScore.mockResolvedValue(null);
  });

  it('renders assistant messages as markdown', async () => {
    const { container } = render(
      <ContentChatPanel
        campaignId="camp-1"
        workspaceId="ws-1"
        pieceIndex={0}
        piece={{ content_type: 'body_copy' }}
        isOpen
        onClose={vi.fn()}
        onContentUpdated={vi.fn()}
        events={[]}
        otherUsers={[]}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 3, name: 'Revision Notes' })).toBeInTheDocument();
    });

    expect(screen.getByText('Tighten intro')).toBeInTheDocument();
    expect(screen.getByText('Add CTA')).toBeInTheDocument();
    expect(container.querySelector('.chat-panel-message-text ul')).not.toBeNull();
  });
});