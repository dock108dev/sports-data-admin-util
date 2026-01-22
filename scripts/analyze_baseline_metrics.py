#!/usr/bin/env python3
"""
Baseline Metrics Analyzer for Timeline Generation Pipeline

This script analyzes game data to produce baseline metrics for the timeline
generation pipeline. It identifies problem patterns and generates a comprehensive
metrics report.

Usage:
    python scripts/analyze_baseline_metrics.py --game-id 109953 --data-dir ./data/game_109953

Required files in data directory:
    - game_{id}_full.json       # Full game data
    - game_{id}_moments.json    # Generated moments
    - game_{id}_pbp.json        # Play-by-play data

Optional files:
    - generation_trace.json     # Moment generation trace
    - moment_selection_trace.json  # Selection trace
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BaselineMetrics:
    """Container for all baseline metrics."""

    game_id: int
    total_moments: int = 0
    notable_moments: int = 0
    total_plays: int = 0

    # Moment type distribution
    moments_by_type: dict[str, int] = field(default_factory=dict)
    notable_by_type: dict[str, int] = field(default_factory=dict)

    # Trigger distribution
    trigger_distribution: dict[str, int] = field(default_factory=dict)

    # Per-quarter distribution
    quarters: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Problem patterns
    consecutive_same_type: list[dict[str, Any]] = field(default_factory=list)
    flip_tie_chains: list[dict[str, Any]] = field(default_factory=list)
    redundant_neutrals: list[dict[str, Any]] = field(default_factory=list)
    short_moments: list[dict[str, Any]] = field(default_factory=list)

    # Moment length stats
    play_counts: list[int] = field(default_factory=list)
    avg_play_count: float = 0.0
    min_play_count: int = 0
    max_play_count: int = 0

    # Boundary detection (if trace available)
    total_boundaries: int = 0
    boundaries_by_type: dict[str, int] = field(default_factory=dict)
    density_gated_count: int = 0
    late_false_drama_suppressed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "game_id": self.game_id,
            "summary": {
                "total_moments": self.total_moments,
                "notable_moments": self.notable_moments,
                "notable_percentage": (
                    round(self.notable_moments / self.total_moments * 100, 1)
                    if self.total_moments > 0
                    else 0.0
                ),
                "total_plays": self.total_plays,
                "avg_plays_per_moment": (
                    round(self.total_plays / self.total_moments, 1)
                    if self.total_moments > 0
                    else 0.0
                ),
            },
            "moment_distribution": {
                "by_type": self.moments_by_type,
                "notable_by_type": self.notable_by_type,
            },
            "trigger_distribution": self.trigger_distribution,
            "per_quarter_distribution": self.quarters,
            "moment_length_stats": {
                "avg_play_count": self.avg_play_count,
                "min_play_count": self.min_play_count,
                "max_play_count": self.max_play_count,
                "play_count_distribution": dict(Counter(self.play_counts)),
                "moments_under_3_plays": len([p for p in self.play_counts if p < 3]),
            },
            "problem_patterns": {
                "consecutive_same_type": {
                    "count": len(self.consecutive_same_type),
                    "instances": self.consecutive_same_type,
                },
                "flip_tie_chains": {
                    "count": len(self.flip_tie_chains),
                    "instances": self.flip_tie_chains,
                },
                "redundant_neutrals": {
                    "count": len(self.redundant_neutrals),
                    "instances": self.redundant_neutrals,
                },
                "short_moments": {
                    "count": len(self.short_moments),
                    "instances": self.short_moments,
                },
            },
            "boundary_detection": {
                "total_boundaries": self.total_boundaries,
                "boundaries_by_type": self.boundaries_by_type,
                "gating_decisions": {
                    "density_gated_count": self.density_gated_count,
                    "late_false_drama_suppressed": self.late_false_drama_suppressed,
                },
            },
        }


def load_json_file(filepath: Path) -> dict[str, Any] | None:
    """Load JSON file, return None if not found."""
    if not filepath.exists():
        return None
    with open(filepath) as f:
        return json.load(f)


def analyze_moments(moments: list[dict[str, Any]], metrics: BaselineMetrics) -> None:
    """Analyze moment data and populate metrics."""
    metrics.total_moments = len(moments)

    # Initialize quarter tracking
    quarters = defaultdict(
        lambda: {
            "moment_count": 0,
            "notable_count": 0,
            "flip_tie_count": 0,
            "neutral_count": 0,
            "total_plays": 0,
        }
    )

    prev_moment = None
    flip_tie_chain = []

    for i, moment in enumerate(moments):
        moment_type = moment.get("type", "UNKNOWN")
        is_notable = moment.get("is_notable", False)
        play_count = moment.get("play_count", 0)
        clock = moment.get("clock", "")
        reason = moment.get("reason", {})
        trigger = reason.get("trigger", "unknown") if isinstance(reason, dict) else "unknown"

        # Basic counts
        metrics.moments_by_type[moment_type] = (
            metrics.moments_by_type.get(moment_type, 0) + 1
        )
        if is_notable:
            metrics.notable_moments += 1
            metrics.notable_by_type[moment_type] = (
                metrics.notable_by_type.get(moment_type, 0) + 1
            )

        metrics.trigger_distribution[trigger] = (
            metrics.trigger_distribution.get(trigger, 0) + 1
        )
        metrics.play_counts.append(play_count)

        # Extract quarter from clock (e.g., "Q1 9:12-7:48" -> "Q1")
        quarter = clock.split()[0] if clock else "UNKNOWN"
        quarters[quarter]["moment_count"] += 1
        quarters[quarter]["total_plays"] += play_count
        if is_notable:
            quarters[quarter]["notable_count"] += 1
        if moment_type in ("FLIP", "TIE"):
            quarters[quarter]["flip_tie_count"] += 1
        if moment_type == "NEUTRAL":
            quarters[quarter]["neutral_count"] += 1

        # Problem pattern detection

        # 1. Consecutive same type (excluding protected types)
        protected_types = {"FLIP", "CLOSING_CONTROL", "HIGH_IMPACT", "MOMENTUM_SHIFT"}
        if (
            prev_moment
            and prev_moment.get("type") == moment_type
            and moment_type not in protected_types
        ):
            metrics.consecutive_same_type.append(
                {
                    "moment_ids": [prev_moment.get("id"), moment.get("id")],
                    "type": moment_type,
                    "clock": [prev_moment.get("clock"), clock],
                }
            )

        # 2. FLIP/TIE chains (3+ consecutive FLIP/TIE moments)
        if moment_type in ("FLIP", "TIE"):
            flip_tie_chain.append(
                {"id": moment.get("id"), "type": moment_type, "clock": clock}
            )
        else:
            if len(flip_tie_chain) >= 3:
                metrics.flip_tie_chains.append(
                    {
                        "chain_length": len(flip_tie_chain),
                        "moments": flip_tie_chain.copy(),
                    }
                )
            flip_tie_chain = []

        # 3. Redundant neutrals (NEUTRAL moments between non-protected moments)
        if (
            moment_type == "NEUTRAL"
            and prev_moment
            and prev_moment.get("type") not in protected_types
        ):
            # Check if next moment is also non-protected
            if i + 1 < len(moments):
                next_moment = moments[i + 1]
                if next_moment.get("type") not in protected_types:
                    metrics.redundant_neutrals.append(
                        {
                            "moment_id": moment.get("id"),
                            "clock": clock,
                            "between": [
                                prev_moment.get("type"),
                                next_moment.get("type"),
                            ],
                        }
                    )

        # 4. Short moments (< 3 plays, excluding recaps)
        if play_count < 3 and not moment.get("is_recap", False):
            metrics.short_moments.append(
                {
                    "moment_id": moment.get("id"),
                    "type": moment_type,
                    "play_count": play_count,
                    "clock": clock,
                }
            )

        prev_moment = moment

    # Finalize FLIP/TIE chain detection
    if len(flip_tie_chain) >= 3:
        metrics.flip_tie_chains.append(
            {"chain_length": len(flip_tie_chain), "moments": flip_tie_chain.copy()}
        )

    # Calculate moment length stats
    if metrics.play_counts:
        metrics.avg_play_count = round(sum(metrics.play_counts) / len(metrics.play_counts), 1)
        metrics.min_play_count = min(metrics.play_counts)
        metrics.max_play_count = max(metrics.play_counts)

    # Store quarter data
    metrics.quarters = dict(quarters)
    metrics.total_plays = sum(q["total_plays"] for q in quarters.values())


def analyze_trace(trace: dict[str, Any], metrics: BaselineMetrics) -> None:
    """Analyze generation trace if available."""
    if not trace:
        return

    # Extract boundary detection metrics
    boundaries = trace.get("boundaries", [])
    metrics.total_boundaries = len(boundaries)

    for boundary in boundaries:
        boundary_type = boundary.get("type", "unknown")
        metrics.boundaries_by_type[boundary_type] = (
            metrics.boundaries_by_type.get(boundary_type, 0) + 1
        )

    # Extract gating decisions
    gating = trace.get("gating_decisions", {})
    metrics.density_gated_count = gating.get("density_gated", 0)
    metrics.late_false_drama_suppressed = gating.get("late_false_drama_suppressed", 0)


def generate_report(metrics: BaselineMetrics, output_path: Path) -> None:
    """Generate human-readable report."""
    report = f"""# Baseline Metrics Report - Game {metrics.game_id}

## Summary

- **Total Moments:** {metrics.total_moments}
- **Notable Moments:** {metrics.notable_moments} ({round(metrics.notable_moments / metrics.total_moments * 100, 1) if metrics.total_moments > 0 else 0}%)
- **Total Plays:** {metrics.total_plays}
- **Avg Plays/Moment:** {round(metrics.total_plays / metrics.total_moments, 1) if metrics.total_moments > 0 else 0}

## Moment Type Distribution

"""
    for moment_type, count in sorted(
        metrics.moments_by_type.items(), key=lambda x: x[1], reverse=True
    ):
        notable_count = metrics.notable_by_type.get(moment_type, 0)
        report += f"- **{moment_type}:** {count} ({notable_count} notable)\n"

    report += f"""
## Trigger Distribution

"""
    for trigger, count in sorted(
        metrics.trigger_distribution.items(), key=lambda x: x[1], reverse=True
    ):
        report += f"- **{trigger}:** {count}\n"

    report += f"""
## Per-Quarter Distribution

"""
    for quarter in sorted(metrics.quarters.keys()):
        q_data = metrics.quarters[quarter]
        report += f"""### {quarter}
- Moments: {q_data['moment_count']} ({q_data['notable_count']} notable)
- FLIP/TIE: {q_data['flip_tie_count']}
- NEUTRAL: {q_data['neutral_count']}
- Total Plays: {q_data['total_plays']}

"""

    report += f"""## Moment Length Stats

- **Average:** {metrics.avg_play_count} plays
- **Min:** {metrics.min_play_count} plays
- **Max:** {metrics.max_play_count} plays
- **Moments < 3 plays:** {len([p for p in metrics.play_counts if p < 3])}

## Problem Patterns Detected

### 1. Consecutive Same Type
**Count:** {len(metrics.consecutive_same_type)}

"""
    if metrics.consecutive_same_type:
        for pattern in metrics.consecutive_same_type[:5]:  # Show first 5
            report += f"- {pattern['type']}: {pattern['moment_ids']} at {pattern['clock']}\n"
        if len(metrics.consecutive_same_type) > 5:
            report += f"- ... and {len(metrics.consecutive_same_type) - 5} more\n"
    else:
        report += "✅ No issues detected\n"

    report += f"""
### 2. FLIP/TIE Chains (3+ consecutive)
**Count:** {len(metrics.flip_tie_chains)}

"""
    if metrics.flip_tie_chains:
        for chain in metrics.flip_tie_chains[:3]:  # Show first 3
            report += f"- Chain of {chain['chain_length']} moments: "
            report += " → ".join([m["type"] for m in chain["moments"]])
            report += "\n"
        if len(metrics.flip_tie_chains) > 3:
            report += f"- ... and {len(metrics.flip_tie_chains) - 3} more\n"
    else:
        report += "✅ No issues detected\n"

    report += f"""
### 3. Redundant Neutral Moments
**Count:** {len(metrics.redundant_neutrals)}

"""
    if metrics.redundant_neutrals:
        for neutral in metrics.redundant_neutrals[:5]:  # Show first 5
            report += f"- {neutral['moment_id']} between {neutral['between'][0]} and {neutral['between'][1]} at {neutral['clock']}\n"
        if len(metrics.redundant_neutrals) > 5:
            report += f"- ... and {len(metrics.redundant_neutrals) - 5} more\n"
    else:
        report += "✅ No issues detected\n"

    report += f"""
### 4. Short Moments (< 3 plays)
**Count:** {len(metrics.short_moments)}

"""
    if metrics.short_moments:
        for short in metrics.short_moments[:5]:  # Show first 5
            report += f"- {short['moment_id']} ({short['type']}): {short['play_count']} plays at {short['clock']}\n"
        if len(metrics.short_moments) > 5:
            report += f"- ... and {len(metrics.short_moments) - 5} more\n"
    else:
        report += "✅ No issues detected\n"

    report += f"""
## Boundary Detection Metrics

- **Total Boundaries:** {metrics.total_boundaries}
- **Density Gated:** {metrics.density_gated_count}
- **Late False Drama Suppressed:** {metrics.late_false_drama_suppressed}

### Boundaries by Type
"""
    for boundary_type, count in sorted(
        metrics.boundaries_by_type.items(), key=lambda x: x[1], reverse=True
    ):
        report += f"- **{boundary_type}:** {count}\n"

    report += """
---

**Report Generated:** 2026-01-21
"""

    with open(output_path, "w") as f:
        f.write(report)

    print(f"✅ Report written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze baseline metrics for timeline generation"
    )
    parser.add_argument("--game-id", type=int, required=True, help="Game ID to analyze")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing game data files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/analysis"),
        help="Output directory for reports (default: ./data/analysis)",
    )

    args = parser.parse_args()

    # Validate data directory
    if not args.data_dir.exists():
        print(f"❌ Error: Data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    # Load data files
    print(f"📂 Loading data files from {args.data_dir}...")

    moments_file = args.data_dir / f"game_{args.game_id}_moments.json"
    pbp_file = args.data_dir / f"game_{args.game_id}_pbp.json"
    full_file = args.data_dir / f"game_{args.game_id}_full.json"
    trace_file = args.data_dir / "generation_trace.json"

    moments_data = load_json_file(moments_file)
    pbp_data = load_json_file(pbp_file)
    full_data = load_json_file(full_file)
    trace_data = load_json_file(trace_file)

    if not moments_data:
        print(f"❌ Error: Moments file not found: {moments_file}", file=sys.stderr)
        sys.exit(1)

    # Initialize metrics
    metrics = BaselineMetrics(game_id=args.game_id)

    # Extract moments array (handle different formats)
    moments = moments_data.get("moments", [])
    if not moments and isinstance(moments_data, list):
        moments = moments_data

    if not moments:
        print("❌ Error: No moments found in moments file", file=sys.stderr)
        sys.exit(1)

    print(f"📊 Analyzing {len(moments)} moments...")

    # Analyze moments
    analyze_moments(moments, metrics)

    # Analyze trace if available
    if trace_data:
        print("📊 Analyzing generation trace...")
        analyze_trace(trace_data, metrics)
    else:
        print("⚠️  No generation trace found, skipping boundary analysis")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate outputs
    json_output = args.output_dir / f"game_{args.game_id}_baseline_metrics.json"
    report_output = args.output_dir / f"game_{args.game_id}_baseline_report.md"

    print(f"💾 Writing metrics to {json_output}...")
    with open(json_output, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2)

    print(f"📝 Generating report...")
    generate_report(metrics, report_output)

    # Print summary
    print("\n" + "=" * 60)
    print(f"✅ Analysis complete for game {args.game_id}")
    print("=" * 60)
    print(f"Total Moments: {metrics.total_moments}")
    print(f"Notable Moments: {metrics.notable_moments}")
    print(f"Problem Patterns Found:")
    print(f"  - Consecutive Same Type: {len(metrics.consecutive_same_type)}")
    print(f"  - FLIP/TIE Chains: {len(metrics.flip_tie_chains)}")
    print(f"  - Redundant Neutrals: {len(metrics.redundant_neutrals)}")
    print(f"  - Short Moments: {len(metrics.short_moments)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
