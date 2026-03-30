import { useCallback, useEffect, useRef, useState } from "react";
import {
  sendContentChat,
  getContentChatHistory,
  getContentChatSuggestions,
  revertContentChat,
  applyAndApproveFromChat,
  getContentChatVersions,
} from "../api";
import { useToast } from "../ToastContext";
import QuickActionChips from "./QuickActionChips";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONTENT_TYPE_LABELS = {
  headline_cta: "Headline & CTA",
  headline: "Headline",
  cta: "CTA",
  social_post: "Social Post",
  ad_copy: "Ad Copy",
  tagline: "Tagline",
  body_copy: "Body Copy",
  email_subject: "Email Subject",
  email_body: "Email Body",
};

function formatRelativeTime(dateStr) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// ChatMessage — renders a single message bubble
// ---------------------------------------------------------------------------

function ChatMessage({ message, onApply, onRevert, onApprove, isLatestAssistant }) {
  const isUser = message.role === "user";

  return (
    <div
      className={`chat-panel-message ${isUser ? "chat-panel-message--user" : "chat-panel-message--assistant"}`}
      data-testid="chat-message"
    >
      <div className="chat-panel-message-bubble">
        <div className="chat-panel-message-text">{message.content}</div>
        <div className="chat-panel-message-time">{formatRelativeTime(message.created_at)}</div>
      </div>

      {/* Action buttons for AI messages */}
      {!isUser && isLatestAssistant && (
        <div className="chat-panel-message-actions">
          {onApply && (
            <button
              type="button"
              className="btn btn-sm btn-outline chat-panel-action-btn"
              onClick={() => onApply(message)}
              aria-label="Apply this version"
            >
              ✅ Apply
            </button>
          )}
          {onRevert && (
            <button
              type="button"
              className="btn btn-sm btn-outline chat-panel-action-btn"
              onClick={() => onRevert(message)}
              aria-label="Revert changes"
            >
              ↩ Revert
            </button>
          )}
          {onApprove && (
            <button
              type="button"
              className="btn btn-sm btn-primary chat-panel-action-btn"
              onClick={() => onApprove(message)}
              aria-label="Approve with this version"
            >
              🔒 Approve
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ContentChatPanel — main exported component
// ---------------------------------------------------------------------------

export default function ContentChatPanel({
  campaignId,
  workspaceId,
  pieceIndex,
  piece,
  isOpen = false,
  onClose,
  onContentUpdated,
  events = [],
}) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [versions, setVersions] = useState([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingMessageId, setStreamingMessageId] = useState(null);
  const [customChips, setCustomChips] = useState([]);

  const { addToast } = useToast();
  const listEndRef = useRef(null);
  const textareaRef = useRef(null);
  const processedEventsRef = useRef(new Set());

  const pieceTypeLabel = CONTENT_TYPE_LABELS[piece?.content_type] || piece?.content_type || "Content";

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchHistory = useCallback(async () => {
    if (!workspaceId || !campaignId || pieceIndex == null) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getContentChatHistory(workspaceId, campaignId, pieceIndex);
      setMessages(Array.isArray(data) ? data : data?.messages ?? []);
    } catch (err) {
      setError(err.message || "Failed to load chat history.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId, pieceIndex]);

  const fetchSuggestions = useCallback(async () => {
    if (!workspaceId || !campaignId || pieceIndex == null) return;
    try {
      const data = await getContentChatSuggestions(workspaceId, campaignId, pieceIndex);
      setSuggestions(Array.isArray(data) ? data : data?.suggestions ?? []);
      setShowSuggestions(true);
    } catch {
      // Suggestions are non-critical — silently ignore errors
    }
  }, [workspaceId, campaignId, pieceIndex]);

  // Fetch on open
  useEffect(() => {
    if (isOpen) {
      fetchHistory();
      fetchSuggestions();
    }
  }, [isOpen, fetchHistory, fetchSuggestions]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (isOpen) {
      listEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingContent, isOpen]);

  // ---------------------------------------------------------------------------
  // WebSocket streaming events
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!isOpen) return;

    const chatEvents = events.filter((e) => {
      const kind = e.event ?? e.type;
      return ["chat_stream", "chat_stream_end", "chat_stream_error"].includes(kind);
    });

    const newEvents = chatEvents.filter((e) => {
      const key = e.id ?? `${e.event ?? e.type}-${e.message_id ?? ""}-${e.timestamp ?? ""}`;
      if (processedEventsRef.current.has(key)) return false;
      processedEventsRef.current.add(key);
      return true;
    });

    for (const evt of newEvents) {
      const kind = evt.event ?? evt.type;

      if (kind === "chat_stream" && evt.piece_index === pieceIndex) {
        setStreamingMessageId(evt.message_id || "streaming");
        setStreamingContent((prev) => prev + (evt.token ?? evt.content ?? ""));
      }

      if (kind === "chat_stream_end" && evt.piece_index === pieceIndex) {
        const finalContent = streamingContent + (evt.token ?? evt.content ?? "");
        if (finalContent) {
          setMessages((prev) => [
            ...prev,
            {
              id: evt.message_id || `msg-${Date.now()}`,
              role: "assistant",
              content: finalContent,
              created_at: evt.timestamp || new Date().toISOString(),
              metadata: evt.metadata ?? {},
            },
          ]);
        }
        setStreamingContent("");
        setStreamingMessageId(null);
        setIsLoading(false);
      }

      if (kind === "chat_stream_error" && evt.piece_index === pieceIndex) {
        addToast({ type: "error", stage: "Chat Error", message: evt.error || evt.message || "Streaming error" });
        setStreamingContent("");
        setStreamingMessageId(null);
        setIsLoading(false);
      }
    }
  }, [events, isOpen, pieceIndex, streamingContent, addToast]);

  // ---------------------------------------------------------------------------
  // Send message
  // ---------------------------------------------------------------------------

  const sendMessage = useCallback(async (instruction) => {
    const text = instruction || inputText.trim();
    if (!text || isLoading) return;

    setInputText("");
    setIsLoading(true);

    // Add user message optimistically
    const userMsg = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response = await sendContentChat(workspaceId, campaignId, pieceIndex, {
        instruction: text,
        stream: false,
      });

      // Add assistant response
      if (response) {
        const assistantMsg = {
          id: response.id || response.message_id || `assistant-${Date.now()}`,
          role: "assistant",
          content: response.content || response.message || response.refined_content || "",
          created_at: response.created_at || new Date().toISOString(),
          metadata: response.metadata ?? {},
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }
    } catch (err) {
      addToast({ type: "error", stage: "Chat Error", message: "Failed to send message: " + err.message });
    } finally {
      setIsLoading(false);
    }
  }, [inputText, isLoading, workspaceId, campaignId, pieceIndex, addToast]);

  // ---------------------------------------------------------------------------
  // Apply / Revert / Approve actions
  // ---------------------------------------------------------------------------

  const handleApply = useCallback(async (message) => {
    const newContent = message.metadata?.version?.after ?? message.content;
    try {
      onContentUpdated?.(pieceIndex, newContent);
      addToast({ type: "success", stage: "Applied", message: "Content updated from chat refinement." });
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to apply content: " + err.message });
    }
  }, [pieceIndex, onContentUpdated, addToast]);

  const handleRevert = useCallback(async () => {
    try {
      const result = await revertContentChat(workspaceId, campaignId, pieceIndex);
      const revertedContent = result?.content || result?.reverted_content;
      if (revertedContent) {
        onContentUpdated?.(pieceIndex, revertedContent);
      }
      addToast({ type: "success", stage: "Reverted", message: "Content reverted to previous version." });
      // Re-fetch history after revert
      await fetchHistory();
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to revert: " + err.message });
    }
  }, [workspaceId, campaignId, pieceIndex, onContentUpdated, addToast, fetchHistory]);

  const handleApprove = useCallback(async (message) => {
    try {
      await applyAndApproveFromChat(workspaceId, campaignId, pieceIndex, {
        messageId: message.id,
      });
      const newContent = message.metadata?.version?.after ?? message.content;
      onContentUpdated?.(pieceIndex, newContent);
      addToast({ type: "success", stage: "Approved", message: "Content approved with chat refinement." });
    } catch (err) {
      addToast({ type: "error", stage: "Error", message: "Failed to approve: " + err.message });
    }
  }, [workspaceId, campaignId, pieceIndex, onContentUpdated, addToast]);

  // ---------------------------------------------------------------------------
  // Suggestion chip click
  // ---------------------------------------------------------------------------

  const handleSuggestionClick = useCallback((suggestion) => {
    const instruction = typeof suggestion === "string" ? suggestion : suggestion.instruction;
    if (instruction) {
      sendMessage(instruction);
    }
  }, [sendMessage]);

  // ---------------------------------------------------------------------------
  // Custom chips
  // ---------------------------------------------------------------------------

  const handleSaveCustomChip = useCallback((text) => {
    setCustomChips((prev) => (prev.includes(text) ? prev : [...prev, text]));
  }, []);

  const handleDeleteCustomChip = useCallback((text) => {
    setCustomChips((prev) => prev.filter((c) => c !== text));
  }, []);

  // ---------------------------------------------------------------------------
  // Auto-expanding textarea
  // ---------------------------------------------------------------------------

  const handleTextareaInput = useCallback((e) => {
    setInputText(e.target.value);
    // Auto-resize
    const el = e.target;
    el.style.height = "auto";
    const maxRows = 4;
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 20;
    const maxHeight = lineHeight * maxRows;
    el.style.height = Math.min(el.scrollHeight, maxHeight) + "px";
  }, []);

  const handleKeyDown = useCallback((e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [sendMessage]);

  // ---------------------------------------------------------------------------
  // Lazy load versions
  // ---------------------------------------------------------------------------

  const fetchVersions = useCallback(async () => {
    if (!workspaceId || !campaignId || pieceIndex == null) return;
    try {
      const data = await getContentChatVersions(workspaceId, campaignId, pieceIndex);
      setVersions(Array.isArray(data) ? data : data?.versions ?? []);
    } catch {
      // Non-critical
    }
  }, [workspaceId, campaignId, pieceIndex]);

  useEffect(() => {
    if (isOpen && versions.length === 0) {
      fetchVersions();
    }
  }, [isOpen, versions.length, fetchVersions]);

  // Determine current version number
  const versionNumber = versions.length > 0 ? versions.length : messages.filter((m) => m.role === "assistant").length + 1;

  // Find the latest assistant message for action buttons
  const latestAssistantId = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  })();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="chat-panel-backdrop"
          onClick={onClose}
          aria-hidden="true"
          data-testid="chat-panel-backdrop"
        />
      )}

      <aside
        className={`chat-panel${isOpen ? " chat-panel--open" : ""}`}
        aria-label="AI Refine chat panel"
        data-testid="chat-panel"
      >
        {/* Header */}
        <div className="chat-panel-header">
          <div className="chat-panel-header-left">
            <span className="chat-panel-title">🤖 AI Refine: {pieceTypeLabel}</span>
            <span className="chat-panel-version">v{versionNumber}</span>
          </div>
          {onClose && (
            <button
              className="chat-panel-close"
              onClick={onClose}
              aria-label="Close chat panel"
            >
              ✕
            </button>
          )}
        </div>

        {/* Proactive suggestions banner */}
        {showSuggestions && suggestions.length > 0 && (
          <div className="chat-panel-suggestions" data-testid="chat-suggestions">
            <div className="chat-panel-suggestions-header">
              <span className="chat-panel-suggestions-label">💡 Suggestions</span>
              <button
                className="chat-panel-suggestions-dismiss"
                onClick={() => setShowSuggestions(false)}
                aria-label="Dismiss suggestions"
              >
                ✕
              </button>
            </div>
            <div className="chat-panel-suggestions-chips">
              {suggestions.slice(0, 3).map((suggestion, idx) => {
                const title = typeof suggestion === "string" ? suggestion : suggestion.title || suggestion.instruction;
                return (
                  <button
                    key={idx}
                    type="button"
                    className="chat-panel-suggestion-chip"
                    onClick={() => handleSuggestionClick(suggestion)}
                    title={typeof suggestion === "string" ? suggestion : suggestion.instruction}
                  >
                    {title}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Message list */}
        <div className="chat-panel-body">
          {loading && (
            <div className="chat-panel-loading">
              <span className="spinner" /> Loading chat…
            </div>
          )}

          {!loading && error && (
            <div className="chat-panel-error">⚠ {error}</div>
          )}

          {!loading && !error && messages.length === 0 && !streamingMessageId && (
            <div className="chat-panel-empty">
              Start a conversation to refine this content
            </div>
          )}

          {!loading &&
            !error &&
            messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                isLatestAssistant={msg.role === "assistant" && msg.id === latestAssistantId}
                onApply={handleApply}
                onRevert={handleRevert}
                onApprove={handleApprove}
              />
            ))}

          {/* Streaming message bubble */}
          {streamingMessageId && streamingContent && (
            <div className="chat-panel-message chat-panel-message--assistant" data-testid="chat-streaming">
              <div className="chat-panel-message-bubble">
                <div className="chat-panel-message-text">{streamingContent}</div>
                <div className="chat-panel-message-time">
                  <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
                </div>
              </div>
            </div>
          )}

          <div ref={listEndRef} />
        </div>

        {/* Quick action chips */}
        <div className="chat-panel-chips">
          <QuickActionChips
            contentType={piece?.content_type}
            onChipClick={(instruction) => sendMessage(instruction)}
            customChips={customChips}
            onSaveCustomChip={handleSaveCustomChip}
            onDeleteCustomChip={handleDeleteCustomChip}
          />
        </div>

        {/* Input area */}
        <form
          className="chat-panel-compose"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
        >
          <div className="chat-panel-input-wrap">
            <textarea
              ref={textareaRef}
              className="chat-panel-textarea"
              placeholder="Describe how to refine this content…"
              value={inputText}
              onChange={handleTextareaInput}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isLoading}
              aria-label="Chat message input"
            />
            <button
              type="submit"
              className="chat-panel-send-btn"
              disabled={!inputText.trim() || isLoading}
              aria-label="Send message"
            >
              {isLoading ? (
                <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
              ) : (
                "↑"
              )}
            </button>
          </div>
        </form>
      </aside>
    </>
  );
}
