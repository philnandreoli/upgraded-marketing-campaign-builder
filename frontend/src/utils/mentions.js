/**
 * Mention token utilities.
 *
 * Token format: @[user_id:display_name]
 * Example:     @[abc-123:Alice Smith]
 */

/** Regex that matches a single mention token in a comment body. */
export const MENTION_REGEX = /@\[([^:]+):([^\]]+)\]/g;

/**
 * Parse all mention tokens from a comment body string.
 * Returns an array of { userId, displayName, index, length }.
 */
export function parseMentions(text) {
  const mentions = [];
  if (!text) return mentions;
  let match;
  const re = new RegExp(MENTION_REGEX.source, "g");
  while ((match = re.exec(text)) !== null) {
    mentions.push({
      userId: match[1],
      displayName: match[2],
      index: match.index,
      length: match[0].length,
    });
  }
  return mentions;
}

/**
 * Build an encoded mention token to embed in comment text.
 */
export function buildMentionToken(userId, displayName) {
  return `@[${userId}:${displayName}]`;
}

/**
 * Split a comment body into an array of segments:
 *  - { type: "text", value: "..." }
 *  - { type: "mention", userId: "...", displayName: "..." }
 *
 * This is useful for rendering the body with highlighted mentions.
 */
export function segmentBody(text) {
  if (!text) return [{ type: "text", value: "" }];
  const segments = [];
  const re = new RegExp(MENTION_REGEX.source, "g");
  let lastIndex = 0;
  let match;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    segments.push({ type: "mention", userId: match[1], displayName: match[2] });
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  if (segments.length === 0) {
    segments.push({ type: "text", value: text });
  }
  return segments;
}
