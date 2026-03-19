# Golf Country Club Pools

Live scoring pools for country club golf tournaments, primarily the Masters.

---

## Overview

Two club variants are supported:

### RVCC
- Pick any 7 golfers from the tournament field
- At least 5 must make the cut to qualify
- Best 5 scores count toward aggregate
- Lowest aggregate score wins

### Crestmont
- Pick 1 golfer from each of 6 buckets (admin-defined)
- At least 4 must make the cut to qualify
- Best 4 scores count toward aggregate
- Lowest aggregate score wins

---

## Data Flow

```
DataGolf API → golf_leaderboard (every 5 min)
                    ↓
           golf_score_pools task (every 5 min)
                    ↓
    golf_pool_entry_score_players (per-golfer materialized)
    golf_pool_entry_scores (per-entry materialized + rank)
                    ↓
           GET /api/golf/pools/{id}/leaderboard
```

The pool scoring task reads live leaderboard data and materializes scored results every 5 minutes during active tournaments. Leaderboard reads are fast because results are pre-computed.

---

## Setup

### 1. Run Migration

```bash
docker compose --profile prod run --rm migrate
```

### 2. Create a Pool

Via admin UI: `/admin/golf/pools/create`

Or via API:
```bash
POST /api/golf/pools
{
  "code": "masters-2026-rvcc",
  "name": "RVCC Masters Pool 2026",
  "club_code": "rvcc",
  "tournament_id": 42,
  "rules_json": {
    "variant": "rvcc",
    "pick_count": 7,
    "count_best": 5,
    "min_cuts_to_qualify": 5,
    "uses_buckets": false
  },
  "entry_deadline": "2026-04-10T12:00:00Z",
  "max_entries_per_email": 3,
  "allow_self_service_entry": true,
  "scoring_enabled": true
}
```

### 3. For Crestmont — Set Up Buckets

```bash
POST /api/golf/pools/{pool_id}/buckets
{
  "buckets": [
    {"bucket_number": 1, "label": "Tier 1", "players": [{"dg_id": 18417, "player_name": "Scottie Scheffler"}, ...]},
    {"bucket_number": 2, "label": "Tier 2", "players": [...]},
    ...
  ]
}
```

### 4. Open for Entries

Update pool status to "open":
```bash
PATCH /api/golf/pools/{pool_id}
{"status": "open"}
```

### 5. Lock Entries at Deadline

```bash
POST /api/golf/pools/{pool_id}/lock
```

### 6. Enable Live Scoring

Update status to "live" (or it transitions automatically when the tournament starts if scoring_enabled=true).

---

## Scoring Rules

### Status Semantics

From `golf_leaderboard.status`:
- **active**: Golfer is still in the tournament — eligible to count
- **cut**: Golfer missed the cut — NOT eligible
- **wd**: Golfer withdrew — NOT eligible
- **dq**: Golfer disqualified — NOT eligible

### Qualification

- **qualified**: Enough active golfers to meet the minimum (5 for RVCC, 4 for Crestmont)
- **pending**: Cut hasn't been settled yet (round 2 not complete) — some golfers may still be cut
- **not_qualified**: After the cut, too few active golfers to qualify

### Counted vs Dropped

Among eligible (active) golfers, the best N by `total_score` (lower = better) are marked as "counted". The rest are "dropped". Only counted golfers contribute to the aggregate score.

### Ties

Entries with the same aggregate score share the same rank. Both are marked `is_tied=true`.

---

## CSV Import

Admin can bulk-import entries via CSV upload:

```
POST /api/golf/pools/{pool_id}/entries/upload
Content-Type: multipart/form-data
```

CSV format:
```csv
email,entry_name,pick_1,pick_2,pick_3,pick_4,pick_5,pick_6,pick_7
mike@example.com,Mike Entry 1,Scottie Scheffler,Rory McIlroy,...
```

Player names are fuzzy-matched against the tournament field. The response includes row-level validation errors.

---

## Manual Rescoring

If data corrections are needed:
```bash
POST /api/golf/pools/{pool_id}/rescore
```

This triggers an immediate rescoring of the pool outside the normal 5-minute cycle.

---

## Troubleshooting

### Pool not scoring
1. Check `scoring_enabled` is true
2. Check pool status is "live"
3. Check tournament status is "in_progress"
4. Check `golf_sync_leaderboard` task is running (every 5 min)
5. Check `golf_score_pools` task is running (every 5 min)
6. Check training worker logs for errors

### Entry rejected
- Check entry deadline hasn't passed
- Check max entries per email
- Check all picked golfers are in the tournament field
- For Crestmont: check each pick is from the correct bucket

### Leaderboard shows stale data
- Check `last_scored_at` on the leaderboard response
- Manually trigger rescore via admin
- Check if the tournament's leaderboard data is being updated

### Golfer not found during CSV import
- Ensure player name matches exactly (case-insensitive)
- Use `dg_id` column instead of name for precise matching
- Check the player is in the tournament field, not just the global player catalog

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/golf/pools` | api_key | List pools |
| GET | `/api/golf/pools/{id}` | api_key | Pool detail |
| GET | `/api/golf/pools/{id}/field` | api_key | Pool field / buckets |
| POST | `/api/golf/pools/{id}/entries` | api_key | Submit entry |
| GET | `/api/golf/pools/{id}/entries/by-email` | api_key | Entries by email |
| GET | `/api/golf/pools/{id}/leaderboard` | api_key | Live standings |
| GET | `/api/golf/pools/{id}/entries/{eid}` | api_key | Entry detail |
| POST | `/api/golf/pools` | admin | Create pool |
| PATCH | `/api/golf/pools/{id}` | admin | Update pool |
| DELETE | `/api/golf/pools/{id}` | admin | Delete pool |
| POST | `/api/golf/pools/{id}/buckets` | admin | Set bucket assignments |
| GET | `/api/golf/pools/{id}/entries` | admin | List all entries |
| POST | `/api/golf/pools/{id}/rescore` | admin | Trigger rescoring |
| POST | `/api/golf/pools/{id}/lock` | admin | Lock entries |
| POST | `/api/golf/pools/{id}/entries/upload` | admin | CSV import |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `golf_pools` | Pool definitions |
| `golf_pool_buckets` | Bucket definitions (Crestmont) |
| `golf_pool_bucket_players` | Players per bucket |
| `golf_pool_entries` | Submitted entries |
| `golf_pool_entry_picks` | Individual golfer picks |
| `golf_pool_entry_score_players` | Materialized per-golfer scoring |
| `golf_pool_entry_scores` | Materialized entry totals + ranks |
| `golf_pool_score_runs` | Scoring run audit trail |

---

## Known Limitations

- No handicap support (gross scoring only)
- No points-based scoring (total score only)
- No automatic status transitions (admin must move pool to "live")
- Bucket assignments are snapshots — changing buckets after entries are submitted requires manual correction
- CSV import matches by player name, not DG ID — names must match the DataGolf catalog
