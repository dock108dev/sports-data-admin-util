#!/usr/bin/env python3
"""
Command-line interface for chapter building and AI context demonstration.

This demonstrates the chapter building pipeline and AI context rules.

Usage:
    python -m app.services.chapters.cli <input.json>
    python -m app.services.chapters.cli <input.json> --chapter-index N
    python -m app.services.chapters.cli <input.json> --build-story-state
    
Modes:
    Default: Build chapters and output GameStory
    --chapter-index N: Show AI input payload for Chapter N (0-based)
    --build-story-state: Show story state after each chapter

Input format:
    JSON file containing a timeline array:
    {
        "game_id": 123,
        "sport": "NBA",
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
    JSON to stdout
"""

import json
import sys
import logging
from pathlib import Path

from .builder import build_chapters
from .ai_context import build_chapter_ai_input, ChapterSummary
from .story_state import derive_story_state_from_chapters

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.services.chapters.cli <input.json> [--chapter-index N | --build-story-state]", file=sys.stderr)
        print("\nModes:", file=sys.stderr)
        print("  Default: Build chapters and output GameStory", file=sys.stderr)
        print("  --chapter-index N: Show AI input payload for Chapter N (0-based)", file=sys.stderr)
        print("  --build-story-state: Show story state after each chapter", file=sys.stderr)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    # Parse mode
    mode = "default"
    chapter_index = None
    
    if len(sys.argv) > 2:
        if sys.argv[2] == "--chapter-index" and len(sys.argv) > 3:
            mode = "chapter_ai_input"
            chapter_index = int(sys.argv[3])
        elif sys.argv[2] == "--build-story-state":
            mode = "story_state"
    
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load input
    logger.info(f"Loading input from {input_path}")
    with open(input_path) as f:
        data = json.load(f)
    
    game_id = data.get("game_id", 1)
    timeline = data.get("timeline", [])
    sport = data.get("sport", "NBA")
    metadata = data.get("metadata", {})
    
    if not timeline:
        print("Error: No timeline found in input", file=sys.stderr)
        sys.exit(1)
    
    logger.info(f"Building chapters for game {game_id}")
    logger.info(f"Sport: {sport}")
    logger.info(f"Timeline has {len(timeline)} events")
    
    # Build chapters
    try:
        story = build_chapters(timeline, game_id, sport, metadata)
    except Exception as e:
        print(f"Error building chapters: {e}", file=sys.stderr)
        logger.exception("Chapter building failed")
        sys.exit(1)
    
    logger.info(f"Successfully created {story.chapter_count} chapters")
    logger.info(f"Total plays: {story.total_plays}")
    
    # Execute mode
    if mode == "default":
        # Output GameStory
        output = story.to_dict()
        print(json.dumps(output, indent=2))
        logger.info("Done")
    
    elif mode == "chapter_ai_input":
        # Show AI input for specific chapter
        if chapter_index is None or chapter_index < 0 or chapter_index >= story.chapter_count:
            print(f"Error: Invalid chapter index {chapter_index}. Must be 0-{story.chapter_count-1}", file=sys.stderr)
            sys.exit(1)
        
        logger.info(f"Building AI input for Chapter {chapter_index}")
        
        current_chapter = story.chapters[chapter_index]
        prior_chapters = story.chapters[:chapter_index]
        
        # Build AI input (no summaries yet, just structure)
        ai_input = build_chapter_ai_input(
            current_chapter=current_chapter,
            prior_chapters=prior_chapters,
            sport=sport
        )
        
        output = ai_input.to_dict()
        
        logger.info(f"AI Input for Chapter {chapter_index}:")
        logger.info(f"  - Current chapter: {current_chapter.chapter_id}")
        logger.info(f"  - Prior chapters: {len(prior_chapters)}")
        logger.info(f"  - Story state last processed: {output['story_state']['chapter_index_last_processed']}")
        logger.info(f"  - Players tracked: {len(output['story_state']['players'])}")
        
        print(json.dumps(output, indent=2))
        logger.info("Done")
    
    elif mode == "story_state":
        # Show story state after each chapter
        logger.info("Building story state incrementally")
        
        output = {
            "game_id": game_id,
            "sport": sport,
            "chapter_count": story.chapter_count,
            "story_states": []
        }
        
        for i in range(story.chapter_count):
            chapters_so_far = story.chapters[:i+1]
            state = derive_story_state_from_chapters(chapters_so_far, sport=sport)
            
            output["story_states"].append({
                "after_chapter": i,
                "chapter_id": story.chapters[i].chapter_id,
                "state": state.to_dict()
            })
            
            logger.info(f"After Chapter {i} ({story.chapters[i].chapter_id}):")
            logger.info(f"  - Players: {len(state.players)}")
            logger.info(f"  - Momentum: {state.momentum_hint.value}")
            logger.info(f"  - Theme tags: {len(state.theme_tags)}")
        
        print(json.dumps(output, indent=2))
        logger.info("Done")


if __name__ == "__main__":
    main()
