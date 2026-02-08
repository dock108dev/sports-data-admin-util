/**
 * League segment and label constants for timeline display.
 *
 * Mirrors the canonical LEAGUE_SEGMENTS and phase labels defined in
 * api/app/services/timeline_types.py — keep in sync.
 */

export const LEAGUE_SEGMENTS: Record<string, string[]> = {
  NBA: ["q1", "q2", "halftime", "q3", "q4"],
  NCAAB: ["first_half", "halftime", "second_half"],
  NHL: ["p1", "p2", "p3"],
};

export const SEGMENT_LABELS: Record<string, string> = {
  q1: "Q1",
  q2: "Q2",
  q3: "Q3",
  q4: "Q4",
  first_half: "1st Half",
  second_half: "2nd Half",
  p1: "1st Period",
  p2: "2nd Period",
  p3: "3rd Period",
  halftime: "Halftime",
  ot: "Overtime",
  ot1: "Overtime",
};
