/**
 * Tests for mention token utilities (parseMentions, buildMentionToken, segmentBody).
 */

import { describe, it, expect } from "vitest";
import { parseMentions, buildMentionToken, segmentBody } from "../utils/mentions.js";

describe("buildMentionToken", () => {
  it("builds the expected token format", () => {
    expect(buildMentionToken("u-123", "Alice Smith")).toBe("@[u-123:Alice Smith]");
  });
});

describe("parseMentions", () => {
  it("returns empty array for plain text", () => {
    expect(parseMentions("Hello world")).toEqual([]);
  });

  it("returns empty array for null/undefined", () => {
    expect(parseMentions(null)).toEqual([]);
    expect(parseMentions(undefined)).toEqual([]);
    expect(parseMentions("")).toEqual([]);
  });

  it("parses a single mention token", () => {
    const text = "Hey @[u-1:Alice] check this";
    const result = parseMentions(text);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      userId: "u-1",
      displayName: "Alice",
      index: 4,
      length: 12,
    });
  });

  it("parses multiple mention tokens", () => {
    const text = "@[u-1:Alice] and @[u-2:Bob Jones] should review";
    const result = parseMentions(text);
    expect(result).toHaveLength(2);
    expect(result[0].userId).toBe("u-1");
    expect(result[1].userId).toBe("u-2");
    expect(result[1].displayName).toBe("Bob Jones");
  });
});

describe("segmentBody", () => {
  it("returns a single text segment for plain text", () => {
    expect(segmentBody("Hello world")).toEqual([
      { type: "text", value: "Hello world" },
    ]);
  });

  it("returns empty text segment for null", () => {
    expect(segmentBody(null)).toEqual([{ type: "text", value: "" }]);
  });

  it("segments a string with a mention in the middle", () => {
    const text = "Hey @[u-1:Alice] check this";
    const result = segmentBody(text);
    expect(result).toEqual([
      { type: "text", value: "Hey " },
      { type: "mention", userId: "u-1", displayName: "Alice" },
      { type: "text", value: " check this" },
    ]);
  });

  it("segments a string starting with a mention", () => {
    const text = "@[u-1:Alice] is great";
    const result = segmentBody(text);
    expect(result).toEqual([
      { type: "mention", userId: "u-1", displayName: "Alice" },
      { type: "text", value: " is great" },
    ]);
  });

  it("segments a string ending with a mention", () => {
    const text = "Thanks @[u-2:Bob]";
    const result = segmentBody(text);
    expect(result).toEqual([
      { type: "text", value: "Thanks " },
      { type: "mention", userId: "u-2", displayName: "Bob" },
    ]);
  });

  it("segments multiple consecutive mentions", () => {
    const text = "@[u-1:Alice] @[u-2:Bob]";
    const result = segmentBody(text);
    expect(result).toEqual([
      { type: "mention", userId: "u-1", displayName: "Alice" },
      { type: "text", value: " " },
      { type: "mention", userId: "u-2", displayName: "Bob" },
    ]);
  });
});
