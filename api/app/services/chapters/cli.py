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
from .ai_context import build_chapter_ai_input
from .story_state import derive_story_state_from_chapters

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.services.chapters.cli <input.json> [OPTIONS]", file=sys.stderr)
        print("\nModes:", file=sys.stderr)
        print("  Default: Build chapters and output GameStory", file=sys.stderr)
        print("  --chapter-index N: Show AI input payload for Chapter N (0-based)", file=sys.stderr)
        print("  --build-story-state: Show story state after each chapter", file=sys.stderr)
        print("  --debug-chapters: Show structured debug logs for chapter boundaries", file=sys.stderr)
        print("  --print-ai-signals --chapter-index N: Show AI-visible signals for Chapter N", file=sys.stderr)
        print("  --generate-chapter-summary --chapter-index N: Generate AI summary for Chapter N", file=sys.stderr)
        print("  --generate-chapter-title --chapter-index N: Generate AI title for Chapter N", file=sys.stderr)
        print("  --generate-compact-story: Generate full compact game story from chapters", file=sys.stderr)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    # Parse mode
    mode = "default"
    chapter_index = None
    debug_enabled = False
    
    if len(sys.argv) > 2:
        if sys.argv[2] == "--chapter-index" and len(sys.argv) > 3:
            mode = "chapter_ai_input"
            chapter_index = int(sys.argv[3])
        elif sys.argv[2] == "--build-story-state":
            mode = "story_state"
        elif sys.argv[2] == "--debug-chapters":
            mode = "debug_chapters"
            debug_enabled = True
        elif sys.argv[2] == "--print-ai-signals" and len(sys.argv) > 4 and sys.argv[3] == "--chapter-index":
            mode = "print_ai_signals"
            chapter_index = int(sys.argv[4])
        elif sys.argv[2] == "--generate-chapter-summary" and len(sys.argv) > 4 and sys.argv[3] == "--chapter-index":
            mode = "generate_chapter_summary"
            chapter_index = int(sys.argv[4])
        elif sys.argv[2] == "--generate-chapter-title" and len(sys.argv) > 4 and sys.argv[3] == "--chapter-index":
            mode = "generate_chapter_title"
            chapter_index = int(sys.argv[4])
        elif sys.argv[2] == "--generate-compact-story":
            mode = "generate_compact_story"
    
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
        if debug_enabled:
            # Use chapterizer directly with debug enabled
            from .chapterizer import ChapterizerV1
            chapterizer = ChapterizerV1(debug=True)
            story = chapterizer.chapterize(timeline, game_id, sport, metadata)
        else:
            story = build_chapters(timeline, game_id, sport, metadata)
            chapterizer = None
    except Exception as e:
        print(f"Error building chapters: {e}", file=sys.stderr)
        logger.exception("Chapter building failed")
        sys.exit(1)
    
    logger.info(f"Successfully created {story.chapter_count} chapters")
    logger.info(f"Total plays: {story.total_plays}")
    
    # Execute mode
    if mode == "default":
        # Show coverage validation
        from .coverage_validator import validate_game_story_coverage
        
        validation = validate_game_story_coverage(story, fail_fast=False)
        print(f"\n{validation}", file=sys.stderr)
        
        # Output GameStory
        output = story.to_dict()
        print(json.dumps(output, indent=2))
        logger.info("Done")
        
        # Exit with error if validation failed
        if not validation.passed:
            sys.exit(1)
    
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
    
    elif mode == "debug_chapters":
        # Show debug logs
        if chapterizer is None:
            print("Error: Debug mode requires chapterizer", file=sys.stderr)
            sys.exit(1)
        
        from .debug_logger import ChapterLogEventType
        
        logger.info("Chapter Debug Logs:")
        
        # Show chapter summary
        print("\n=== CHAPTER SUMMARY ===", file=sys.stderr)
        for chapter in story.chapters:
            print(
                f"{chapter.chapter_id}: plays {chapter.play_start_idx}-{chapter.play_end_idx} "
                f"({chapter.play_count} plays), "
                f"period={chapter.period}, "
                f"reasons={chapter.reason_codes}",
                file=sys.stderr
            )
        
        # Show debug events
        print("\n=== DEBUG EVENTS ===", file=sys.stderr)
        events = chapterizer.debug_logger.get_events()
        print(f"Total events: {len(events)}", file=sys.stderr)
        
        # Group by event type
        for event_type in ChapterLogEventType:
            type_events = chapterizer.debug_logger.get_events_by_type(event_type)
            if type_events:
                print(f"\n{event_type.value}: {len(type_events)} events", file=sys.stderr)
        
        # Output full JSON
        print(chapterizer.debug_logger.to_json())
        logger.info("Done")
    
    elif mode == "print_ai_signals":
        # Show AI-visible signals for specific chapter
        if chapter_index is None or chapter_index < 0 or chapter_index >= story.chapter_count:
            print(f"Error: Invalid chapter index {chapter_index}. Must be 0-{story.chapter_count-1}", file=sys.stderr)
            sys.exit(1)
        
        from .story_state import derive_story_state_from_chapters
        from .ai_signals import format_ai_signals_summary, validate_ai_signals
        
        logger.info(f"Building AI signals for Chapter {chapter_index}")
        
        # Build story state from prior chapters
        prior_chapters = story.chapters[:chapter_index] if chapter_index > 0 else []
        story_state = derive_story_state_from_chapters(prior_chapters, sport=sport)
        
        # Validate signals
        try:
            validate_ai_signals(story_state)
            validation_status = "✓ VALID"
        except Exception as e:
            validation_status = f"✗ INVALID: {e}"
        
        # Print summary
        print(f"\n=== AI SIGNALS FOR CHAPTER {chapter_index} ===", file=sys.stderr)
        print(f"Prior chapters processed: {story_state.chapter_index_last_processed + 1}", file=sys.stderr)
        print(f"Validation: {validation_status}\n", file=sys.stderr)
        
        # Print formatted summary
        summary = format_ai_signals_summary(story_state)
        print(summary, file=sys.stderr)
        
        # Output JSON
        output = {
            "chapter_index": chapter_index,
            "prior_chapters_count": story_state.chapter_index_last_processed + 1,
            "signals": story_state.to_dict(),
            "validation": validation_status,
        }
        print(json.dumps(output, indent=2))
        logger.info("Done")
    
    elif mode == "generate_chapter_summary":
        # Generate AI summary for specific chapter
        if chapter_index is None or chapter_index < 0 or chapter_index >= story.chapter_count:
            print(f"Error: Invalid chapter index {chapter_index}. Must be 0-{story.chapter_count-1}", file=sys.stderr)
            sys.exit(1)
        
        from .summary_generator import generate_chapter_summary
        
        logger.info(f"Generating summary for Chapter {chapter_index}")
        
        current_chapter = story.chapters[chapter_index]
        prior_chapters = story.chapters[:chapter_index]
        
        # Generate summary (no AI client = mock mode)
        result = generate_chapter_summary(
            current_chapter=current_chapter,
            prior_chapters=prior_chapters,
            sport=sport,
            ai_client=None,  # Mock mode for CLI
        )
        
        # Print summary
        print(f"\n=== CHAPTER {chapter_index} SUMMARY ===", file=sys.stderr)
        print(f"Chapter ID: {current_chapter.chapter_id}", file=sys.stderr)
        print(f"Play Range: {current_chapter.play_start_idx}-{current_chapter.play_end_idx}", file=sys.stderr)
        print(f"Plays: {len(current_chapter.plays)}", file=sys.stderr)
        print(f"Reason Codes: {', '.join(current_chapter.reason_codes)}", file=sys.stderr)
        
        if result.spoiler_warnings:
            print(f"\n⚠️  SPOILER WARNINGS: {', '.join(result.spoiler_warnings)}", file=sys.stderr)
        
        print(f"\nSummary: {result.chapter_summary}", file=sys.stderr)
        if result.chapter_title:
            print(f"Title: {result.chapter_title}", file=sys.stderr)
        
        # Output JSON
        output = {
            "chapter_index": result.chapter_index,
            "chapter_id": current_chapter.chapter_id,
            "chapter_summary": result.chapter_summary,
            "chapter_title": result.chapter_title,
            "spoiler_warnings": result.spoiler_warnings,
        }
        print(json.dumps(output, indent=2))
        logger.info("Done")
    
    elif mode == "generate_chapter_title":
        # Generate AI title for specific chapter
        if chapter_index is None or chapter_index < 0 or chapter_index >= story.chapter_count:
            print(f"Error: Invalid chapter index {chapter_index}. Must be 0-{story.chapter_count-1}", file=sys.stderr)
            sys.exit(1)
        
        from .summary_generator import generate_chapter_summary
        from .title_generator import generate_chapter_title
        
        logger.info(f"Generating title for Chapter {chapter_index}")
        
        current_chapter = story.chapters[chapter_index]
        prior_chapters = story.chapters[:chapter_index]
        
        # First generate summary (required for title)
        summary_result = generate_chapter_summary(
            current_chapter=current_chapter,
            prior_chapters=prior_chapters,
            sport=sport,
            ai_client=None,  # Mock mode
        )
        
        # Then generate title
        is_final = (chapter_index == story.chapter_count - 1)
        title_result = generate_chapter_title(
            chapter=current_chapter,
            chapter_summary=summary_result.chapter_summary,
            chapter_index=chapter_index,
            ai_client=None,  # Mock mode
            is_final_chapter=is_final,
        )
        
        # Print results
        print(f"\n=== CHAPTER {chapter_index} TITLE ===", file=sys.stderr)
        print(f"Chapter ID: {current_chapter.chapter_id}", file=sys.stderr)
        print(f"Summary: {summary_result.chapter_summary}", file=sys.stderr)
        print(f"Title: {title_result.chapter_title}", file=sys.stderr)
        
        if title_result.validation_result:
            if title_result.validation_result["valid"]:
                print("✓ Title validation: PASSED", file=sys.stderr)
            else:
                print(f"⚠️  Title validation issues: {', '.join(title_result.validation_result['issues'])}", file=sys.stderr)
        
        # Output JSON
        output = {
            "chapter_index": chapter_index,
            "chapter_id": current_chapter.chapter_id,
            "chapter_summary": summary_result.chapter_summary,
            "chapter_title": title_result.chapter_title,
            "validation": title_result.validation_result,
        }
        print(json.dumps(output, indent=2))
        logger.info("Done")
    
    elif mode == "generate_compact_story":
        # Generate full compact game story
        from .summary_generator import generate_summaries_sequentially
        from .compact_story_generator import generate_compact_story
        
        logger.info("Generating compact story for full game")
        
        # First generate all chapter summaries
        logger.info(f"Generating summaries for {story.chapter_count} chapters...")
        summary_results = generate_summaries_sequentially(
            chapters=story.chapters,
            sport=sport,
            ai_client=None,  # Mock mode
        )
        
        # Extract summaries
        summaries = [r.chapter_summary for r in summary_results]
        
        # Generate compact story
        logger.info("Generating compact story from summaries...")
        compact_result = generate_compact_story(
            chapter_summaries=summaries,
            sport=sport,
            ai_client=None,  # Mock mode
        )
        
        # Print results
        print(f"\n=== COMPACT GAME STORY ===", file=sys.stderr)
        print(f"Chapters: {len(summaries)}", file=sys.stderr)
        print(f"Word Count: {compact_result.word_count}", file=sys.stderr)
        print(f"Reading Time: {compact_result.reading_time_minutes:.1f} minutes", file=sys.stderr)
        
        if compact_result.validation_result:
            if compact_result.validation_result["valid"]:
                print("✓ Length validation: PASSED", file=sys.stderr)
            else:
                print(f"⚠️  Length validation issues: {', '.join(compact_result.validation_result['issues'])}", file=sys.stderr)
        
        if compact_result.new_nouns_detected:
            print(f"⚠️  Potentially new proper nouns: {', '.join(compact_result.new_nouns_detected)}", file=sys.stderr)
        
        print(f"\n{compact_result.compact_story}", file=sys.stderr)
        
        # Output JSON
        output = {
            "game_id": game_id,
            "chapter_count": len(summaries),
            "compact_story": compact_result.compact_story,
            "reading_time_minutes": compact_result.reading_time_minutes,
            "word_count": compact_result.word_count,
            "validation": compact_result.validation_result,
            "new_nouns_detected": compact_result.new_nouns_detected,
        }
        print(json.dumps(output, indent=2))
        logger.info("Done")


if __name__ == "__main__":
    main()
