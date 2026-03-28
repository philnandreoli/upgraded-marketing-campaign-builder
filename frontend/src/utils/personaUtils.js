/**
 * Parse a persona description string (possibly structured) back into the
 * individual fields used by PersonaEditor.
 *
 * If the description contains "Field: value" sections, each section is
 * extracted into its own field.  If the description is plain text (legacy
 * format), it is placed into the demographics field.
 */
export function parseDescriptionToFields(description) {
  if (!description) {
    return { demographics: "", psychographics: "", pain_points: "", behaviors: "", channels: "" };
  }

  const result = { demographics: "", psychographics: "", pain_points: "", behaviors: "", channels: "" };
  const blocks = description.split(/\n\n+/);

  for (const block of blocks) {
    const trimmed = block.trim();
    if (trimmed.startsWith("Demographics:")) {
      result.demographics = trimmed.replace(/^Demographics:\s*/i, "").trim();
    } else if (trimmed.startsWith("Psychographics:")) {
      result.psychographics = trimmed.replace(/^Psychographics:\s*/i, "").trim();
    } else if (trimmed.startsWith("Pain Points:")) {
      result.pain_points = trimmed.replace(/^Pain Points:\s*/i, "").trim();
    } else if (trimmed.startsWith("Behaviors:")) {
      result.behaviors = trimmed.replace(/^Behaviors:\s*/i, "").trim();
    } else if (trimmed.startsWith("Channels:")) {
      result.channels = trimmed.replace(/^Channels:\s*/i, "").trim();
    }
  }

  // If no structured fields were found, treat the whole text as demographics
  const hasStructured = Object.values(result).some((v) => v.length > 0);
  if (!hasStructured) {
    result.demographics = description.trim();
  }

  return result;
}
