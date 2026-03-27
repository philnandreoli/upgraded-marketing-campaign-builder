import { useCallback, useEffect, useRef, useState } from "react";
import {
  createComment,
  deleteComment,
  listComments,
  resolveComment,
  updateComment,
} from "../api";
import { useToast } from "../ToastContext";
import { useUser } from "../UserContext";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
// CommentItem — renders a single comment row (top-level or reply)
// ---------------------------------------------------------------------------

function CommentItem({
  comment,
  currentUserId,
  isReadOnly,
  onReply,
  onResolve,
  onEdit,
  onDelete,
  isTopLevel = true,
}) {
  const isOwn = currentUserId && comment.author_id === currentUserId;

  return (
    <div
      className={`comment-item${comment.is_resolved ? " comment-item--resolved" : ""}${isTopLevel ? "" : " comment-item--reply"}`}
      data-testid="comment-item"
    >
      <div className="comment-item-header">
        <span className="comment-item-author">
          {comment.author_display_name || comment.author_id}
        </span>
        <span className="comment-item-time">{formatRelativeTime(comment.created_at)}</span>
        {comment.is_resolved && (
          <span className="comment-item-resolved-badge">✓ Resolved</span>
        )}
      </div>

      <div className="comment-item-body">{comment.body}</div>

      <div className="comment-item-actions">
        {isTopLevel && !isReadOnly && (
          <button
            className="comment-action-btn"
            onClick={() => onReply(comment.id)}
            aria-label="Reply to comment"
          >
            ↩ Reply
          </button>
        )}
        {isTopLevel && !isReadOnly && (
          <button
            className={`comment-action-btn${comment.is_resolved ? " comment-action-btn--resolve-active" : ""}`}
            onClick={() => onResolve(comment.id, !comment.is_resolved)}
            aria-label={comment.is_resolved ? "Unresolve comment" : "Resolve comment"}
            title={comment.is_resolved ? "Mark unresolved" : "Mark resolved"}
          >
            {comment.is_resolved ? "↺ Unresolve" : "✓ Resolve"}
          </button>
        )}
        {isOwn && !isReadOnly && (
          <>
            <button
              className="comment-action-btn"
              onClick={() => onEdit(comment)}
              aria-label="Edit comment"
            >
              ✎ Edit
            </button>
            <button
              className="comment-action-btn comment-action-btn--danger"
              onClick={() => onDelete(comment.id)}
              aria-label="Delete comment"
            >
              🗑 Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EditCommentForm — inline edit form
// ---------------------------------------------------------------------------

function EditCommentForm({ initialBody, onSave, onCancel, saving }) {
  const [body, setBody] = useState(initialBody);

  return (
    <form
      className="comment-reply-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(body.trim());
      }}
    >
      <textarea
        className="comment-textarea"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={3}
        autoFocus
      />
      <div className="comment-form-actions">
        <button
          type="submit"
          className="btn btn-primary comment-submit-btn"
          disabled={!body.trim() || saving}
        >
          {saving ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : "Save"}
        </button>
        <button
          type="button"
          className="btn comment-cancel-btn"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// ReplyForm — inline reply composer
// ---------------------------------------------------------------------------

function ReplyForm({ onSubmit, onCancel, submitting }) {
  const [body, setBody] = useState("");

  return (
    <form
      className="comment-reply-form"
      onSubmit={(e) => {
        e.preventDefault();
        const trimmed = body.trim();
        if (trimmed) {
          onSubmit(trimmed);
          setBody("");
        }
      }}
    >
      <textarea
        className="comment-textarea"
        placeholder="Write a reply…"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        autoFocus
      />
      <div className="comment-form-actions">
        <button
          type="submit"
          className="btn btn-primary comment-submit-btn"
          disabled={!body.trim() || submitting}
        >
          {submitting ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : "Reply"}
        </button>
        <button type="button" className="btn comment-cancel-btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// CommentPanel — main exported component
// ---------------------------------------------------------------------------

export default function CommentPanel({
  campaignId,
  workspaceId,
  section,
  contentPieceIndex,
  isReadOnly = false,
  events = [],
  isOpen = false,
  onClose,
}) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newBody, setNewBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [replyingToId, setReplyingToId] = useState(null);
  const [replySubmitting, setReplySubmitting] = useState(false);
  const [editingComment, setEditingComment] = useState(null); // { id, body }
  const [editSaving, setEditSaving] = useState(false);
  const { addToast } = useToast();
  const { user } = useUser();
  const listEndRef = useRef(null);
  const processedEventsRef = useRef(new Set());

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchComments = useCallback(async () => {
    if (!workspaceId || !campaignId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listComments(workspaceId, campaignId, {
        section,
        pieceIndex: contentPieceIndex,
      });
      setComments(data);
    } catch (err) {
      setError(err.message || "Failed to load comments.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId, section, contentPieceIndex]);

  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  // ---------------------------------------------------------------------------
  // WebSocket real-time updates
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const commentEvents = events.filter((e) => {
      const kind = e.event ?? e.type;
      return (
        ["comment_added", "comment_updated", "comment_resolved", "comment_deleted"].includes(kind)
      );
    });

    const newCommentEvents = commentEvents.filter((e) => {
      const key = e.id ?? `${e.event ?? e.type}-${e.comment?.id ?? ""}-${e.timestamp ?? ""}`;
      if (processedEventsRef.current.has(key)) return false;
      processedEventsRef.current.add(key);
      return true;
    });

    if (newCommentEvents.length === 0) return;

    // Re-fetch to stay in sync rather than doing complex merging
    fetchComments();
  }, [events, fetchComments]);

  // ---------------------------------------------------------------------------
  // Create top-level comment
  // ---------------------------------------------------------------------------

  const handleCreate = async (e) => {
    e.preventDefault();
    const trimmed = newBody.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      const payload = { body: trimmed };
      if (section) payload.section = section;
      if (contentPieceIndex != null) payload.content_piece_index = contentPieceIndex;
      await createComment(workspaceId, campaignId, payload);
      setNewBody("");
      await fetchComments();
      listEndRef.current?.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      addToast({ stage: "Error", message: "Failed to post comment: " + err.message });
    } finally {
      setSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Reply
  // ---------------------------------------------------------------------------

  const handleReply = async (body) => {
    setReplySubmitting(true);
    try {
      const parentComment = comments.find((c) => c.id === replyingToId);
      const payload = {
        body,
        parent_id: replyingToId,
        section: parentComment?.section ?? section,
      };
      await createComment(workspaceId, campaignId, payload);
      setReplyingToId(null);
      await fetchComments();
    } catch (err) {
      addToast({ stage: "Error", message: "Failed to post reply: " + err.message });
    } finally {
      setReplySubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Resolve / Unresolve
  // ---------------------------------------------------------------------------

  const handleResolve = async (commentId, resolved) => {
    try {
      await resolveComment(workspaceId, campaignId, commentId, resolved);
      setComments((prev) =>
        prev.map((c) => (c.id === commentId ? { ...c, is_resolved: resolved } : c))
      );
    } catch (err) {
      addToast({ stage: "Error", message: "Failed to update comment: " + err.message });
    }
  };

  // ---------------------------------------------------------------------------
  // Edit
  // ---------------------------------------------------------------------------

  const handleEditSave = async (body) => {
    if (!editingComment) return;
    setEditSaving(true);
    try {
      await updateComment(workspaceId, campaignId, editingComment.id, { body });
      setComments((prev) =>
        prev.map((c) => (c.id === editingComment.id ? { ...c, body } : c))
      );
      setEditingComment(null);
    } catch (err) {
      addToast({ stage: "Error", message: "Failed to edit comment: " + err.message });
    } finally {
      setEditSaving(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Delete
  // ---------------------------------------------------------------------------

  const handleDelete = async (commentId) => {
    try {
      await deleteComment(workspaceId, campaignId, commentId);
      // Re-fetch to stay in sync; backend does not cascade-delete replies automatically.
      await fetchComments();
    } catch (err) {
      addToast({ stage: "Error", message: "Failed to delete comment: " + err.message });
    }
  };

  // ---------------------------------------------------------------------------
  // Group comments: top-level + replies
  // ---------------------------------------------------------------------------

  const topLevel = comments.filter((c) => !c.parent_id);
  const repliesMap = {};
  comments
    .filter((c) => c.parent_id)
    .forEach((c) => {
      repliesMap[c.parent_id] = repliesMap[c.parent_id] ?? [];
      repliesMap[c.parent_id].push(c);
    });

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <aside className={`comment-panel${isOpen ? " comment-panel--open" : ""}`} aria-label="Comments panel">
      {/* Header */}
      <div className="comment-panel-header">
        <span className="comment-panel-title">💬 Comments</span>
        {onClose && (
          <button
            className="comment-panel-close"
            onClick={onClose}
            aria-label="Close comments panel"
          >
            ✕
          </button>
        )}
      </div>

      {/* Body */}
      <div className="comment-panel-body">
        {loading && (
          <div className="comment-panel-loading">
            <span className="spinner" /> Loading comments…
          </div>
        )}

        {!loading && error && (
          <div className="comment-panel-error">⚠ {error}</div>
        )}

        {!loading && !error && topLevel.length === 0 && (
          <div className="comment-panel-empty">
            No comments yet.{isReadOnly ? "" : " Be the first!"}
          </div>
        )}

        {!loading &&
          !error &&
          topLevel.map((comment) => {
            const isEditing = editingComment?.id === comment.id;
            const replies = repliesMap[comment.id] ?? [];

            return (
              <div key={comment.id} className="comment-thread">
                {isEditing ? (
                  <EditCommentForm
                    initialBody={comment.body}
                    saving={editSaving}
                    onSave={handleEditSave}
                    onCancel={() => setEditingComment(null)}
                  />
                ) : (
                  <CommentItem
                    comment={comment}
                    currentUserId={user?.id}
                    isReadOnly={isReadOnly}
                    onReply={(id) => {
                      setReplyingToId((prev) => (prev === id ? null : id));
                    }}
                    onResolve={handleResolve}
                    onEdit={(c) => setEditingComment(c)}
                    onDelete={handleDelete}
                    isTopLevel
                  />
                )}

                {/* Replies */}
                {replies.length > 0 && (
                  <div className="comment-replies">
                    {replies.map((reply) => {
                      const isEditingReply = editingComment?.id === reply.id;
                      return isEditingReply ? (
                        <EditCommentForm
                          key={reply.id}
                          initialBody={reply.body}
                          saving={editSaving}
                          onSave={handleEditSave}
                          onCancel={() => setEditingComment(null)}
                        />
                      ) : (
                        <CommentItem
                          key={reply.id}
                          comment={reply}
                          currentUserId={user?.id}
                          isReadOnly={isReadOnly}
                          onReply={() => {}}
                          onResolve={() => {}}
                          onEdit={(c) => setEditingComment(c)}
                          onDelete={handleDelete}
                          isTopLevel={false}
                        />
                      );
                    })}
                  </div>
                )}

                {/* Inline reply form */}
                {replyingToId === comment.id && (
                  <div className="comment-replies">
                    <ReplyForm
                      onSubmit={handleReply}
                      onCancel={() => setReplyingToId(null)}
                      submitting={replySubmitting}
                    />
                  </div>
                )}
              </div>
            );
          })}

        <div ref={listEndRef} />
      </div>

      {/* New comment form */}
      {!isReadOnly && (
        <form className="comment-panel-compose" onSubmit={handleCreate}>
          <textarea
            className="comment-textarea"
            placeholder="Add a comment…"
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            rows={3}
          />
          <div className="comment-form-actions">
            <button
              type="submit"
              className="btn btn-primary comment-submit-btn"
              disabled={!newBody.trim() || submitting}
            >
              {submitting ? (
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              ) : (
                "Post"
              )}
            </button>
          </div>
        </form>
      )}
    </aside>
  );
}
