# NBA PBP Patterns to Mirror

This document distills the NBA play-by-play (PBP) integration behaviors that NHL PBP must mirror, plus areas where NHL can diverge without breaking expectations.

## Must Mirror (Behavioral Guarantees)
- **Deterministic ordering:** PBP events are stored in chronological order with a stable `play_index`. Sports Reference HTML order is used to assign monotonic indices, while live feed uses `period * 10000 + sequence`.
- **Period handling:** The PBP parser relies on explicit period headers (e.g., `q1`, `q2`) and skips rows until a period is identified.
- **Clock parsing:** The PBP `game_clock` value is preserved as raw text from the source.
- **Raw text preservation:** When the event row does not fit a structured format, the full description is stored in `raw_data` and `description` without additional inference.
- **Append-only storage:** Plays are written via `upsert_plays` with `ON CONFLICT DO NOTHING`, so ordering is stable and no prior events are overwritten.

## Acceptable NHL Divergences
- **Period semantics:** NHL uses three regulation periods, overtime, and shootouts. The `quarter` field is reused for NHL period numbering.
- **Event taxonomy:** NHL event types differ (goals, penalties, faceoffs, stoppages). `play_type` can be NHL-specific strings without mapping to NBA enums.
- **Score availability:** Not all rows include a score column; NHL parsing can leave `home_score`/`away_score` unset when not present.
- **Player attribution:** NHL Sports Reference rows do not reliably expose player IDs; `player_id`/`player_name` can remain unset.

## NBA PBP Non-Goals (Parity Notes)
- No possession modeling or derived possessions.
- No normalization of event text into a shared cross-sport taxonomy.
- No attempt to infer missing data (teams, players, or timestamps) beyond what the source provides.
