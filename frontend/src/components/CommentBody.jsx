import { segmentBody } from "../utils/mentions";

/**
 * CommentBody — renders comment text with @mentions highlighted.
 *
 * Parses `@[user_id:display_name]` tokens and renders them as styled spans.
 * Plain text segments are rendered preserving whitespace.
 */
export default function CommentBody({ text }) {
  const segments = segmentBody(text);

  return (
    <>
      {segments.map((seg, i) =>
        seg.type === "mention" ? (
          <span
            key={i}
            className="mention-highlight"
            title={seg.displayName}
            data-user-id={seg.userId}
          >
            {`@${seg.displayName}`}
          </span>
        ) : (
          <span key={i}>{seg.value}</span>
        )
      )}
    </>
  );
}
