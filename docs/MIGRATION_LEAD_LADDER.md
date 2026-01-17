# Migration Guide: Lead Ladder Moment Types

> **Date:** 2026-01-17  
> **Affects:** `scroll-down-app` (iOS), `scroll-down-sports-ui` (Web)

---

## Summary

The Moments system has been refactored to use **Lead Ladder**-based detection. This changes the `type` field values in moment responses but preserves backward compatibility for highlight filtering.

---

## What Changed

### MomentType Values

| Old Type | Status | New Equivalent |
|----------|--------|----------------|
| `RUN` | ❌ **Removed** | Runs are now `run_info` metadata |
| `BATTLE` | ❌ **Removed** | Replaced by `FLIP`, `TIE`, `CUT` |
| `CLOSING` | ❌ **Removed** | Renamed to `CLOSING_CONTROL` |
| `NEUTRAL` | ✅ Unchanged | Still means "normal flow" |

### New MomentType Values

| Type | Description | Always Notable? |
|------|-------------|-----------------|
| `LEAD_BUILD` | Lead tier increased | No (only if tier change ≥ 2) |
| `CUT` | Lead tier decreased (comeback) | No (only if tier change ≥ 2) |
| `TIE` | Game returned to even | **Yes** |
| `FLIP` | Leader changed | **Yes** |
| `CLOSING_CONTROL` | Late-game lock-in | **Yes** |
| `HIGH_IMPACT` | Ejection, injury, flagrant | **Yes** |
| `OPENER` | First plays of a period | No (only if strong lead) |
| `NEUTRAL` | Normal flow | No |

### New Optional Fields

These fields may appear on moments but are not required:

```typescript
interface MomentEntry {
  // ... existing fields unchanged ...
  
  // NEW (optional)
  run_info?: {
    team: "home" | "away";
    points: number;
    unanswered: boolean;
    play_ids: number[];
  };
  ladder_tier_before?: number;
  ladder_tier_after?: number;
  team_in_control?: "home" | "away" | null;
  key_play_ids?: number[];
}
```

---

## Consumer Impact Assessment

### ✅ No Changes Needed If...

1. **You filter highlights by `is_notable`**
   ```typescript
   // This still works exactly the same
   const highlights = moments.filter(m => m.is_notable);
   ```

2. **You display moments without filtering by type**
   ```typescript
   // This still works - just renders all moments
   moments.map(m => <MomentCard moment={m} />)
   ```

3. **You only use `id`, `start_play`, `end_play`, `note`, `clock`, `score_*` fields**
   - All existing fields are preserved

### ⚠️ Changes Needed If...

1. **You filter by `type === "RUN"`**
   ```typescript
   // OLD (no longer works)
   const runs = moments.filter(m => m.type === "RUN");
   
   // NEW: Check for run_info instead
   const runsWithMetadata = moments.filter(m => m.run_info);
   
   // Or check for tier-crossing types that might have runs
   const leadChanges = moments.filter(m => 
     ["LEAD_BUILD", "CUT", "FLIP"].includes(m.type)
   );
   ```

2. **You filter by `type === "BATTLE"`**
   ```typescript
   // OLD (no longer works)
   const battles = moments.filter(m => m.type === "BATTLE");
   
   // NEW: Use specific crossing types
   const leadBattles = moments.filter(m => 
     ["FLIP", "TIE", "CUT"].includes(m.type)
   );
   ```

3. **You filter by `type === "CLOSING"`**
   ```typescript
   // OLD (no longer works)
   const closing = moments.filter(m => m.type === "CLOSING");
   
   // NEW: Renamed type
   const closing = moments.filter(m => m.type === "CLOSING_CONTROL");
   ```

4. **You display type as a label**
   ```typescript
   // Update label map
   const typeLabels: Record<string, string> = {
     // NEW types
     LEAD_BUILD: "Lead Extended",
     CUT: "Comeback",
     TIE: "Game Tied",
     FLIP: "Lead Change",
     CLOSING_CONTROL: "Late Control",
     HIGH_IMPACT: "Key Moment",
     OPENER: "Period Start",
     NEUTRAL: "Game Flow",
     
     // OLD types (for cached data)
     RUN: "Scoring Run",
     BATTLE: "Back and Forth",
     CLOSING: "Closing Stretch",
   };
   ```

---

## Recommended Migration Steps

### Step 1: Handle Unknown Types Gracefully

Add a fallback for any type you don't recognize:

```typescript
function getMomentLabel(type: string): string {
  const labels: Record<string, string> = {
    LEAD_BUILD: "Lead Extended",
    CUT: "Comeback",
    TIE: "Game Tied",
    FLIP: "Lead Change",
    CLOSING_CONTROL: "Late Control",
    HIGH_IMPACT: "Key Moment",
    OPENER: "Period Start",
    NEUTRAL: "Game Flow",
  };
  return labels[type] ?? type.replace(/_/g, " ");
}
```

### Step 2: Update Type Filters (if used)

```typescript
// Backward-compatible type checking
function isExcitingMoment(type: string): boolean {
  const exciting = new Set([
    "FLIP", "TIE", "CLOSING_CONTROL", "HIGH_IMPACT",  // New
    "RUN", "BATTLE", "CLOSING",  // Old (for cached data)
  ]);
  return exciting.has(type);
}
```

### Step 3: Use `is_notable` as Primary Filter

The safest approach is to rely on `is_notable`:

```typescript
// RECOMMENDED: Works for old and new data
const highlights = moments.filter(m => m.is_notable);
```

### Step 4: Optionally Use New Fields

Take advantage of new metadata:

```typescript
// Show run details if available
if (moment.run_info) {
  return `${moment.run_info.points}-0 ${moment.run_info.team} run`;
}

// Show control status
if (moment.team_in_control) {
  return `${moment.team_in_control} in control`;
}
```

---

## Timeline Regeneration

Existing timeline artifacts will have old type values until regenerated.

**Regeneration options:**
1. Timelines are automatically regenerated on next scrape
2. Use admin UI: `/admin/timelines` → "Regenerate"
3. API: `POST /api/admin/sports/timelines/regenerate-batch`

**Mixed data handling:**
- During transition, consumers should handle both old and new types
- Use the fallback pattern in Step 1 above

---

## Testing

Test your app with these moment types:

```json
[
  { "type": "OPENER", "is_notable": false, "note": "Period 1 start" },
  { "type": "LEAD_BUILD", "is_notable": true, "note": "Lead extended", 
    "run_info": { "team": "home", "points": 12, "unanswered": true, "play_ids": [3,5,8] } },
  { "type": "TIE", "is_notable": true, "note": "Game tied" },
  { "type": "FLIP", "is_notable": true, "note": "Lead changes hands" },
  { "type": "NEUTRAL", "is_notable": false },
  { "type": "CLOSING_CONTROL", "is_notable": true, "note": "Game control locked" }
]
```

---

## Questions?

Contact the backend team if you encounter issues during migration.
