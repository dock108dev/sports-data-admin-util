# Game Flow Guide

> Integration guide for consuming apps (Scroll Down to Update, etc.)

This guide explains how to fetch and display the **Game Flow** — compact narrative blocks with mini box scores.

---

## Quick Start

```bash
# Get games with game flow for a date
curl -H "X-API-Key: YOUR_KEY" \
  "https://sports-data-admin.dock108.ai/api/admin/sports/games?startDate=2026-01-22&league=NBA"

# Get the game flow for a specific game
curl -H "X-API-Key: YOUR_KEY" \
  "https://sports-data-admin.dock108.ai/api/admin/sports/games/123/story"
```

---

## What You Get

Each game flow contains **4-7 narrative blocks** designed for a **20-60 second read**.

| Property | Value |
|----------|-------|
| Blocks per game | 4-7 |
| Words per block | 10-50 (~35 avg) |
| Total words | ≤ 350 |
| Read time | 20-60 seconds |

---

## API Endpoints

### 1. List Games

```http
GET /api/admin/sports/games
X-API-Key: YOUR_KEY
```

**Key Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league` | `string` | `NBA`, `NHL`, or `NCAAB` |
| `startDate` | `date` | Games on/after (Eastern Time) |
| `endDate` | `date` | Games on/before (Eastern Time) |
| `limit` | `int` | Max results (default 50, max 200) |

**Example:**
```bash
GET /api/admin/sports/games?league=NBA&startDate=2026-01-22&endDate=2026-01-22
```

**Response:**
```json
{
  "games": [
    {
      "id": 123,
      "leagueCode": "NBA",
      "gameDate": "2026-01-23T03:00:00Z",
      "homeTeam": "Lakers",
      "awayTeam": "Warriors",
      "homeScore": 112,
      "awayScore": 108,
      "hasStory": true
    }
  ],
  "total": 12,
  "withStoryCount": 10
}
```

Games with `hasStory: true` have game flow available.

---

### 2. Get Game Flow

```http
GET /api/admin/sports/games/{gameId}/story
X-API-Key: YOUR_KEY
```

**Response:**
```json
{
  "gameId": 123,
  "story": {
    "blocks": [...],
    "moments": [...]
  },
  "plays": [...],
  "validationPassed": true,
  "validationErrors": []
}
```

---

## Block Structure

Blocks are the consumer-facing output. Each block is a narrative segment:

```json
{
  "blockIndex": 0,
  "role": "SETUP",
  "momentIndices": [0, 1, 2],
  "periodStart": 1,
  "periodEnd": 1,
  "scoreBefore": [0, 0],
  "scoreAfter": [12, 15],
  "playIds": [1, 2, 3, 4, 5],
  "keyPlayIds": [2, 4],
  "narrative": "The Lakers jumped out early, with James orchestrating a 15-12 lead through balanced scoring in the opening minutes.",
  "miniBox": {
    "home": {
      "team": "Lakers",
      "players": [
        {"name": "James", "pts": 8, "reb": 2, "ast": 3, "delta_pts": 8, "delta_reb": 2, "delta_ast": 3},
        {"name": "Davis", "pts": 7, "reb": 3, "ast": 0, "delta_pts": 7, "delta_reb": 3, "delta_ast": 0}
      ]
    },
    "away": {
      "team": "Warriors",
      "players": [
        {"name": "Curry", "pts": 6, "reb": 0, "ast": 2, "delta_pts": 6, "delta_reb": 0, "delta_ast": 2}
      ]
    },
    "blockStars": ["James", "Davis"]
  },
  "embeddedTweet": null
}
```

### Block Fields

| Field | Type | Description |
|-------|------|-------------|
| `blockIndex` | `int` | Position (0 to N-1) |
| `role` | `string` | Semantic role (see below) |
| `scoreBefore` | `[away, home]` | Score at block start |
| `scoreAfter` | `[away, home]` | Score at block end |
| `narrative` | `string` | 1-2 sentences (~35 words) |
| `miniBox` | `object` | Player stats for this segment |
| `embeddedTweet` | `object?` | Optional social context (max 1 per block) |

### Semantic Roles

| Role | Position | Description |
|------|----------|-------------|
| `SETUP` | Always first | How the game started, early context |
| `MOMENTUM_SHIFT` | Middle | First meaningful swing in the game |
| `RESPONSE` | Middle | Counter-run or stabilization |
| `DECISION_POINT` | Late | The sequence that decided the outcome |
| `RESOLUTION` | Always last | How the game ended |

---

## Mini Box Score

The `miniBox` shows player stats **for that specific segment** of the game.

### Basketball (NBA/NCAAB)

```json
{
  "home": {
    "team": "Lakers",
    "players": [
      {
        "name": "James",
        "pts": 15,          // Cumulative through this block
        "reb": 4,
        "ast": 6,
        "3pm": 2,
        "delta_pts": 7,     // Scored during THIS block
        "delta_reb": 2,
        "delta_ast": 3
      }
    ]
  },
  "away": {...},
  "blockStars": ["James", "Curry"]  // Top performers in this segment
}
```

### Hockey (NHL)

```json
{
  "home": {
    "team": "Kings",
    "players": [
      {
        "name": "Kopitar",
        "goals": 1,
        "assists": 1,
        "sog": 3,
        "plusMinus": 1,
        "delta_goals": 1,
        "delta_assists": 0
      }
    ]
  },
  "away": {...},
  "blockStars": ["Kopitar"]
}
```

### Stat Fields

| Field | Basketball | Hockey |
|-------|------------|--------|
| Cumulative | `pts`, `reb`, `ast`, `3pm` | `goals`, `assists`, `sog`, `plusMinus` |
| Delta (this block) | `delta_pts`, `delta_reb`, `delta_ast` | `delta_goals`, `delta_assists` |

**Display tip:** Use `delta_*` fields to highlight who contributed most in each block. The `blockStars` array identifies top performers.

---

## Embedded Tweets

Blocks may include an optional embedded tweet for social context:

```json
{
  "embeddedTweet": {
    "tweetId": "1234567890",
    "authorHandle": "@Lakers",
    "text": "AD with the SLAM!",
    "mediaUrl": "https://..."
  }
}
```

**Constraints:**
- Max 5 tweets per game
- Max 1 tweet per block
- Tweets are additive context, not structural

---

## TypeScript Types

```typescript
interface GameFlowResponse {
  gameId: number;
  story: {
    blocks: GameFlowBlock[];
    moments: GameFlowMoment[];
  };
  plays: GameFlowPlay[];
  validationPassed: boolean;
  validationErrors: string[];
}

interface GameFlowBlock {
  blockIndex: number;
  role: "SETUP" | "MOMENTUM_SHIFT" | "RESPONSE" | "DECISION_POINT" | "RESOLUTION";
  momentIndices: number[];
  periodStart: number;
  periodEnd: number;
  scoreBefore: [number, number];  // [away, home]
  scoreAfter: [number, number];
  playIds: number[];
  keyPlayIds: number[];
  narrative: string;
  miniBox: BlockMiniBox | null;
  embeddedTweet: EmbeddedTweet | null;
}

interface BlockMiniBox {
  home: BlockTeamMiniBox;
  away: BlockTeamMiniBox;
  blockStars: string[];
}

interface BlockTeamMiniBox {
  team: string;
  players: BlockPlayerStat[];
}

interface BlockPlayerStat {
  name: string;
  // Basketball
  pts?: number;
  reb?: number;
  ast?: number;
  "3pm"?: number;
  delta_pts?: number;
  delta_reb?: number;
  delta_ast?: number;
  // Hockey
  goals?: number;
  assists?: number;
  sog?: number;
  plusMinus?: number;
  delta_goals?: number;
  delta_assists?: number;
}

interface EmbeddedTweet {
  tweetId: string;
  authorHandle: string;
  text: string;
  mediaUrl?: string;
}
```

---

## Swift Integration Example

```swift
struct GameFlowBlock: Codable {
    let blockIndex: Int
    let role: String
    let scoreBefore: [Int]
    let scoreAfter: [Int]
    let narrative: String
    let miniBox: BlockMiniBox?
    let embeddedTweet: EmbeddedTweet?
}

struct BlockMiniBox: Codable {
    let home: BlockTeamMiniBox
    let away: BlockTeamMiniBox
    let blockStars: [String]
}

struct BlockTeamMiniBox: Codable {
    let team: String
    let players: [BlockPlayerStat]
}

struct BlockPlayerStat: Codable {
    let name: String
    let pts: Int?
    let reb: Int?
    let ast: Int?
    let deltaPts: Int?
    let deltaReb: Int?
    let deltaAst: Int?

    enum CodingKeys: String, CodingKey {
        case name, pts, reb, ast
        case deltaPts = "delta_pts"
        case deltaReb = "delta_reb"
        case deltaAst = "delta_ast"
    }
}

// Fetch game flow
func fetchGameFlow(gameId: Int) async throws -> GameFlowResponse {
    var request = URLRequest(url: URL(string: "https://sports-data-admin.dock108.ai/api/admin/sports/games/\(gameId)/story")!)
    request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(GameFlowResponse.self, from: data)
}
```

---

## Display Layout

```
┌─────────────────────────────────────────┐
│ SETUP                        0-0 → 15-12│
│ The Lakers jumped out early...          │
│ ┌─────────────────────────────────────┐ │
│ │ LAL: James 8p/2r/3a  Davis 7p/3r   │ │
│ │ GSW: Curry 6p/2a                    │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ MOMENTUM_SHIFT              15-12 → 28-32│
│ The Warriors answered with a 20-13 run..│
│ ┌─────────────────────────────────────┐ │
│ │ GSW: Curry +12p  Thompson +8p       │ │
│ │ LAL: James +5p                      │ │
│ └─────────────────────────────────────┘ │
│ @warriors: Splash Brothers cooking!     │
└─────────────────────────────────────────┘
          │
          ▼
        [...]
```

### Design Tips

1. **Use semantic roles for visual hierarchy** — Style SETUP/RESOLUTION differently from middle blocks
2. **Highlight delta stats** — Show what happened in each segment, not just cumulative totals
3. **Score progression** — Display `scoreBefore → scoreAfter` to show the swing
4. **Block stars** — Bold or highlight players in `blockStars` array
5. **Tweets are optional** — Don't leave empty space if no tweet exists

---

## Error Handling

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `401` | Invalid or missing API key |
| `404` | Game not found or no game flow exists |
| `500` | Server error |

**No game flow response:**
```json
{
  "detail": "No Story found for game 123"
}
```

---

## Caching

- Game flows are immutable once generated — cache aggressively
- Recommended: Cache responses for 24 hours
- Games list can be cached for 5-15 minutes

---

## Questions?

Contact the Sports Data Admin team or check the full [API documentation](./API.md).
