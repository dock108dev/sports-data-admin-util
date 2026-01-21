#!/usr/bin/env python3
"""
Command-line interface for chapter building.

This is a minimal executable entry point that demonstrates the chapter
building pipeline without AI involvement.

Usage:
    python -m app.services.chapters.cli <input.json>
    
Input format:
    JSON file containing a timeline array:
    {
        "game_id": 123,
        "timeline": [
            {"event_type": "pbp", "quarter": 1, ...},
            {"event_type": "pbp", "quarter": 1, ...},
            ...
        ],
        "metadata": {
            "home_team": "Lakers",
            "away_team": "Celtics",
            ...
        }
    }

Output:
    JSON to stdout containing the GameStory with chapters
"""

import json
import sys
import logging
from pathlib import Path

from .builder import build_chapters

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.services.chapters.cli <input.json>", file=sys.stderr)
        print("\nInput JSON format:", file=sys.stderr)
        print("  {", file=sys.stderr)
        print('    "game_id": 123,', file=sys.stderr)
        print('    "timeline": [...],', file=sys.stderr)
        print('    "metadata": {...}', file=sys.stderr)
        print("  }", file=sys.stderr)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load input
    logger.info(f"Loading input from {input_path}")
    with open(input_path) as f:
        data = json.load(f)
    
    game_id = data.get("game_id", 1)
    timeline = data.get("timeline", [])
    metadata = data.get("metadata", {})
    
    if not timeline:
        print("Error: No timeline found in input", file=sys.stderr)
        sys.exit(1)
    
    logger.info(f"Building chapters for game {game_id}")
    logger.info(f"Timeline has {len(timeline)} events")
    
    # Build chapters
    try:
        story = build_chapters(timeline, game_id, metadata)
    except Exception as e:
        print(f"Error building chapters: {e}", file=sys.stderr)
        logger.exception("Chapter building failed")
        sys.exit(1)
    
    # Output result
    logger.info(f"Successfully created {story.chapter_count} chapters")
    logger.info(f"Total plays: {story.total_plays}")
    
    output = story.to_dict()
    print(json.dumps(output, indent=2))
    
    logger.info("Done")


if __name__ == "__main__":
    main()
