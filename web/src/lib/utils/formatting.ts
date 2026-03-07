/**
 * Shared formatting helpers for analytics metric display.
 */

/** Convert snake_case key to Title Case (e.g. "contact_rate" → "Contact Rate"). */
export function formatMetricName(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Format a numeric metric value with appropriate precision. */
export function formatMetricValue(value: number): string {
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(4);
}
