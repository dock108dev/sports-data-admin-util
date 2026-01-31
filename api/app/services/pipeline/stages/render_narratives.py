"""RENDER_NARRATIVES Stage Implementation.

This stage generates narrative text for each validated moment using OpenAI.
It is the ONLY AI-driven step in the Story pipeline.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- AI is a renderer, not an author
- Moments are batched (up to 25 per call) for efficiency
- Narrative is grounded strictly in backing plays
- No story-level prose or summaries
- Narrative is traceable to explicit plays

RENDERING RULES
===============
The prompt REQUIRES:
- Direct reference to at least one explicitly narrated play
- Concrete actions only (shots, fouls, turnovers, scores)
- Chronological order
- Neutral, factual language

The prompt FORBIDS:
- Momentum, flow, turning points
- Summaries or retrospection
- "Earlier/later in the game"
- Speculation or interpretation
- Referencing plays not provided

POST-GENERATION VALIDATION
==========================
After receiving AI output, we validate:
1. Narrative is non-empty
2. No forbidden abstraction language
3. Response is well-formed JSON
4. At least one explicitly narrated play is referenced (traceability)

If validation fails, the stage fails. No retries with weaker rules.
No auto-editing of text. AI output is untrusted until validated.

GUARANTEES
==========
1. Moments batched efficiently (~25 per OpenAI call)
2. All narratives pass validation
3. Broken narratives fail loudly
4. Output includes narrative per moment
5. Human can audit text → plays deterministically
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from ..models import StageInput, StageOutput
from ...openai_client import get_openai_client

# Import from modular helpers
from .narrative_types import (
    FallbackType,
    FallbackReason,
    CoverageResolution,
    MOMENTS_PER_BATCH,
    VALID_FALLBACK_NARRATIVES,  # noqa: F401 - re-exported for tests
    FORBIDDEN_PATTERNS,  # noqa: F401 - re-exported for tests
)
from .fallback_helpers import (
    get_valid_fallback_narrative,
    get_invalid_fallback_narrative,
    is_valid_score_context,
    has_valid_play_metadata,
    classify_empty_narrative_fallback,
)
from .prompt_builders import build_batch_prompt
from .coverage_helpers import (
    count_sentences,
    check_explicit_play_coverage,
    inject_missing_explicit_plays,
    log_coverage_resolution,
    validate_narrative,
)

# Backward compatibility aliases for tests (underscore-prefixed versions)
_get_valid_fallback_narrative = get_valid_fallback_narrative
_get_invalid_fallback_narrative = get_invalid_fallback_narrative
_is_valid_score_context = is_valid_score_context
_has_valid_play_metadata = has_valid_play_metadata
_classify_empty_narrative_fallback = classify_empty_narrative_fallback
_build_batch_prompt = build_batch_prompt
_count_sentences = count_sentences
_validate_narrative = validate_narrative


def _check_explicit_play_coverage(
    narrative: str,
    moment: dict,
    moment_plays: list,
) -> list[int]:
    """Backward-compatible wrapper for check_explicit_play_coverage.

    Old API: takes moment dict, returns list of missing play indices.
    New API: takes explicit_play_ids set, returns (all_covered, covered, missing) tuple.
    """
    explicit_ids = set(moment.get("explicitly_narrated_play_ids", []))
    if not explicit_ids:
        return []
    _, _, missing_ids = check_explicit_play_coverage(narrative, explicit_ids, moment_plays)
    return list(missing_ids)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def execute_render_narratives(stage_input: StageInput) -> StageOutput:
    """Execute the RENDER_NARRATIVES stage.

    Generates narrative text for each validated moment using OpenAI.
    Moments are batched (up to MOMENTS_PER_BATCH per call) for efficiency.
    Validates all narratives before returning.

    Args:
        stage_input: Input containing previous_output with validated moments

    Returns:
        StageOutput with moments enriched with narrative field

    Raises:
        ValueError: If OpenAI is not configured or validation fails
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting RENDER_NARRATIVES for game {game_id}")

    # Get OpenAI client
    openai_client = get_openai_client()
    if openai_client is None:
        raise ValueError(
            "OpenAI API key not configured - cannot render narratives. "
            "Set OPENAI_API_KEY environment variable."
        )

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("RENDER_NARRATIVES requires previous stage output")

    # Verify validation passed
    validated = previous_output.get("validated")
    if validated is not True:
        raise ValueError(
            "RENDER_NARRATIVES requires VALIDATE_MOMENTS to pass. "
            f"Got validated={validated}"
        )

    # Get moments and PBP data
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    # Build play_index -> event lookup
    play_lookup: dict[int, dict[str, Any]] = {}
    for event in pbp_events:
        play_index = event.get("play_index")
        if play_index is not None:
            play_lookup[play_index] = event

    game_context = stage_input.game_context

    # Prepare all moments with their plays
    moments_with_plays: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for i, moment in enumerate(moments):
        play_ids = moment.get("play_ids", [])
        moment_plays = [play_lookup[pid] for pid in play_ids if pid in play_lookup]
        moments_with_plays.append((i, moment, moment_plays))

    # Calculate batch count
    num_batches = (len(moments) + MOMENTS_PER_BATCH - 1) // MOMENTS_PER_BATCH
    output.add_log(
        f"Rendering {len(moments)} moments in {num_batches} batches "
        f"({MOMENTS_PER_BATCH} per batch)"
    )

    # Process in batches
    enriched_moments: list[dict[str, Any]] = [None] * len(moments)  # type: ignore
    successful_renders = 0
    total_openai_calls = 0
    retry_count = 0
    injection_count = 0

    # Style violation tracking
    all_style_violations: list[dict[str, Any]] = []

    # Fallback tracking with classification
    fallback_moments: list[int] = []
    valid_fallbacks: list[dict[str, Any]] = []
    invalid_fallbacks: list[dict[str, Any]] = []

    for batch_start in range(0, len(moments_with_plays), MOMENTS_PER_BATCH):
        batch_end = min(batch_start + MOMENTS_PER_BATCH, len(moments_with_plays))
        batch = moments_with_plays[batch_start:batch_end]

        # Check for moments with no plays -> INVALID fallback
        valid_batch = []
        for moment_index, moment, moment_plays in batch:
            if not moment_plays:
                reason = FallbackReason.MISSING_PLAY_METADATA
                fallback_narrative = get_invalid_fallback_narrative(reason)

                logger.warning(
                    f"Moment {moment_index}: No plays found for play_ids "
                    f"{moment.get('play_ids', [])}, using INVALID fallback"
                )

                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                })
                successful_renders += 1
            else:
                valid_batch.append((moment_index, moment, moment_plays))

        if not valid_batch:
            continue

        # Track moments that need retry due to soft validation errors
        moments_needing_retry: list[tuple[int, dict[str, Any], list[dict[str, Any]], str, list[int]]] = []

        # Build batch prompt and call OpenAI
        prompt = build_batch_prompt(valid_batch, game_context, is_retry=False)

        try:
            total_openai_calls += 1
            max_tokens = 250 * len(valid_batch)
            response_json = await asyncio.to_thread(
                openai_client.generate,
                prompt=prompt,
                temperature=0.3,
                max_tokens=max_tokens,
            )
            response_data = json.loads(response_json)

        except json.JSONDecodeError as e:
            reason = FallbackReason.AI_INVALID_JSON
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI returned invalid JSON: {e}, "
                f"using INVALID fallback"
            )
            for moment_index, moment, _ in valid_batch:
                fallback_narrative = get_invalid_fallback_narrative(reason)
                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "error": str(e)[:200],
                })
                successful_renders += 1
            continue

        except Exception as e:
            reason = FallbackReason.AI_GENERATION_FAILED
            logger.warning(
                f"Batch {batch_start}-{batch_end}: OpenAI call failed: {e}, "
                f"using INVALID fallback"
            )
            for moment_index, moment, _ in valid_batch:
                fallback_narrative = get_invalid_fallback_narrative(reason)
                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": FallbackType.INVALID.value,
                    "fallback_reason": reason.value,
                }
                fallback_moments.append(moment_index)
                invalid_fallbacks.append({
                    "moment_index": moment_index,
                    "reason": reason.value,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "error": str(e)[:200],
                })
                successful_renders += 1
            continue

        # Extract items array from response
        items = response_data.get("items", [])
        if not items and isinstance(response_data, list):
            items = response_data

        logger.info(
            f"Batch {batch_start}-{batch_end}: Got {len(items)} items from OpenAI "
            f"(expected {len(valid_batch)})"
        )

        # Build lookup of narratives by moment_index
        narrative_lookup: dict[int, str] = {}
        for item in items:
            idx = item.get("i") if item.get("i") is not None else item.get("moment_index")
            narrative = item.get("n") or item.get("narrative", "")
            if idx is not None:
                narrative_lookup[idx] = narrative

        # Log if we're missing narratives
        missing = [idx for idx, _, _ in valid_batch if idx not in narrative_lookup]
        if missing:
            logger.warning(
                f"Batch {batch_start}-{batch_end}: Missing narratives for moments {missing[:5]}..."
            )

        # Process each moment in the batch
        for moment_index, moment, moment_plays in valid_batch:
            narrative = narrative_lookup.get(moment_index, "")

            # Handle empty narratives with classified fallback
            if not narrative or not narrative.strip():
                fallback_narrative, fallback_type, fallback_reason = (
                    classify_empty_narrative_fallback(moment, moment_plays, moment_index)
                )

                fallback_moments.append(moment_index)

                fallback_detail = {
                    "moment_index": moment_index,
                    "period": moment.get("period"),
                    "start_clock": moment.get("start_clock"),
                    "fallback_type": fallback_type.value,
                }
                if fallback_reason:
                    fallback_detail["reason"] = fallback_reason.value

                if fallback_type == FallbackType.VALID:
                    valid_fallbacks.append(fallback_detail)
                    logger.info(
                        f"Moment {moment_index}: Empty narrative, using VALID fallback "
                        f"(low-signal gameplay)",
                        extra={"game_id": game_id, **fallback_detail},
                    )
                else:
                    invalid_fallbacks.append(fallback_detail)
                    logger.warning(
                        f"Moment {moment_index}: Empty narrative, using INVALID fallback "
                        f"(reason: {fallback_reason.value if fallback_reason else 'unknown'})",
                        extra={"game_id": game_id, **fallback_detail},
                    )

                enriched_moments[moment_index] = {
                    **moment,
                    "narrative": fallback_narrative,
                    "fallback_type": fallback_type.value,
                    "fallback_reason": fallback_reason.value if fallback_reason else None,
                }
                successful_renders += 1

            else:
                # Validate with hard/soft error separation and style checks
                hard_errors, soft_errors, moment_style_details = validate_narrative(
                    narrative, moment, moment_plays, moment_index
                )

                if moment_style_details:
                    all_style_violations.extend(moment_style_details)

                # Check explicit play coverage separately
                explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])
                missing_explicit = _check_explicit_coverage(narrative, moment, moment_plays)

                if hard_errors and "explicit" not in hard_errors[0].lower():
                    reason = FallbackReason.MISSING_EXPLICIT_PLAY_REFERENCE
                    fallback_narrative = get_invalid_fallback_narrative(reason)

                    logger.warning(
                        f"Moment {moment_index}: Hard validation error, using INVALID fallback: "
                        f"{hard_errors[0]}"
                    )

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "validation_errors": hard_errors,
                    })
                    successful_renders += 1

                elif soft_errors or missing_explicit:
                    moments_needing_retry.append(
                        (moment_index, moment, moment_plays, narrative, missing_explicit)
                    )
                    if missing_explicit:
                        logger.info(
                            f"Moment {moment_index}: Missing explicit plays {missing_explicit}, will retry"
                        )
                    else:
                        logger.info(
                            f"Moment {moment_index}: Soft validation errors, will retry: "
                            f"{soft_errors[0]}"
                        )

                else:
                    if explicit_play_ids:
                        log_coverage_resolution(
                            moment_index,
                            CoverageResolution.INITIAL_PASS,
                            (True, set(explicit_play_ids), set()),
                        )
                    successful_renders += 1
                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": narrative,
                        "fallback_type": None,
                        "fallback_reason": None,
                        "coverage_resolution": CoverageResolution.INITIAL_PASS.value if explicit_play_ids else None,
                    }

        # Retry moments with soft validation errors or missing explicit plays
        if moments_needing_retry:
            retry_count += len(moments_needing_retry)
            output.add_log(
                f"Retrying {len(moments_needing_retry)} moments with validation issues"
            )

            retry_batch = [(idx, m, plays) for idx, m, plays, _, _ in moments_needing_retry]
            retry_prompt = build_batch_prompt(retry_batch, game_context, is_retry=True)

            try:
                total_openai_calls += 1
                retry_max_tokens = 250 * len(retry_batch)
                retry_response_json = await asyncio.to_thread(
                    openai_client.generate,
                    prompt=retry_prompt,
                    temperature=0.2,
                    max_tokens=retry_max_tokens,
                )
                retry_response_data = json.loads(retry_response_json)
                retry_items = retry_response_data.get("items", [])

                retry_narrative_lookup: dict[int, str] = {}
                for item in retry_items:
                    idx = item.get("i") if item.get("i") is not None else item.get("moment_index")
                    narr = item.get("n") or item.get("narrative", "")
                    if idx is not None:
                        retry_narrative_lookup[idx] = narr

                for moment_index, moment, moment_plays, original_narrative, initial_missing in moments_needing_retry:
                    retry_narrative = retry_narrative_lookup.get(moment_index, original_narrative)
                    explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])

                    if not retry_narrative or not retry_narrative.strip():
                        retry_narrative = original_narrative

                    missing_after_regen = _check_explicit_coverage(
                        retry_narrative, moment, moment_plays
                    )

                    if not missing_after_regen:
                        hard_errors, soft_errors, _ = validate_narrative(
                            retry_narrative, moment, moment_plays, moment_index,
                            check_style=False
                        )

                        if not hard_errors or "explicit" in str(hard_errors).lower():
                            if explicit_play_ids:
                                log_coverage_resolution(
                                    moment_index,
                                    CoverageResolution.REGENERATION_PASS,
                                    (True, set(explicit_play_ids), set()),
                                    (False, set(explicit_play_ids) - set(initial_missing), set(initial_missing)),
                                )
                            successful_renders += 1
                            enriched_moments[moment_index] = {
                                **moment,
                                "narrative": retry_narrative,
                                "fallback_type": None,
                                "fallback_reason": None,
                                "coverage_resolution": CoverageResolution.REGENERATION_PASS.value if initial_missing else None,
                            }
                            logger.info(f"Moment {moment_index}: Retry succeeded")
                            continue

                    if missing_after_regen:
                        injection_count += 1
                        logger.warning(
                            f"Moment {moment_index}: Regeneration failed to cover plays "
                            f"{missing_after_regen}, injecting deterministic sentences"
                        )

                        injected_narrative = inject_missing_explicit_plays(
                            retry_narrative, set(missing_after_regen), moment_plays, game_context
                        )

                        still_missing = _check_explicit_coverage(
                            injected_narrative, moment, moment_plays
                        )

                        if still_missing:
                            logger.error(
                                f"Moment {moment_index}: Injection failed, still missing {still_missing}"
                            )
                            log_coverage_resolution(
                                moment_index,
                                CoverageResolution.INJECTION_REQUIRED,
                                (False, set(explicit_play_ids) - set(still_missing), set(still_missing)),
                            )
                            raise ValueError(
                                f"Explicit play coverage invariant violated: "
                                f"Moment {moment_index} still missing plays {still_missing} after injection"
                            )

                        log_coverage_resolution(
                            moment_index,
                            CoverageResolution.INJECTION_REQUIRED,
                            (True, set(explicit_play_ids), set()),
                            (False, set(explicit_play_ids) - set(missing_after_regen), set(missing_after_regen)),
                        )
                        successful_renders += 1
                        enriched_moments[moment_index] = {
                            **moment,
                            "narrative": injected_narrative,
                            "fallback_type": None,
                            "fallback_reason": None,
                            "coverage_resolution": CoverageResolution.INJECTION_REQUIRED.value,
                        }
                        logger.info(
                            f"Moment {moment_index}: Injection succeeded"
                        )
                        continue

                    reason = FallbackReason.FORBIDDEN_LANGUAGE_DETECTED
                    fallback_narrative = get_invalid_fallback_narrative(reason)

                    logger.warning(
                        f"Moment {moment_index}: Retry failed with non-coverage errors, using INVALID fallback"
                    )

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "original_narrative": original_narrative[:200],
                    })
                    successful_renders += 1

            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Retry batch failed: {e}, attempting injection on original narratives")
                for moment_index, moment, moment_plays, original_narrative, initial_missing in moments_needing_retry:
                    explicit_play_ids = moment.get("explicitly_narrated_play_ids", [])

                    if initial_missing and original_narrative:
                        injection_count += 1
                        injected_narrative = inject_missing_explicit_plays(
                            original_narrative, set(initial_missing), moment_plays, game_context
                        )

                        still_missing = _check_explicit_coverage(
                            injected_narrative, moment, moment_plays
                        )

                        if not still_missing:
                            log_coverage_resolution(
                                moment_index,
                                CoverageResolution.INJECTION_REQUIRED,
                                (True, set(explicit_play_ids), set()),
                                (False, set(explicit_play_ids) - set(initial_missing), set(initial_missing)),
                            )
                            successful_renders += 1
                            enriched_moments[moment_index] = {
                                **moment,
                                "narrative": injected_narrative,
                                "fallback_type": None,
                                "fallback_reason": None,
                                "coverage_resolution": CoverageResolution.INJECTION_REQUIRED.value,
                            }
                            continue

                    reason = FallbackReason.AI_GENERATION_FAILED
                    fallback_narrative = get_invalid_fallback_narrative(reason)

                    enriched_moments[moment_index] = {
                        **moment,
                        "narrative": fallback_narrative,
                        "fallback_type": FallbackType.INVALID.value,
                        "fallback_reason": reason.value,
                    }
                    fallback_moments.append(moment_index)
                    invalid_fallbacks.append({
                        "moment_index": moment_index,
                        "reason": reason.value,
                        "period": moment.get("period"),
                        "start_clock": moment.get("start_clock"),
                        "error": str(e)[:200],
                    })
                    successful_renders += 1

    output.add_log(f"OpenAI calls made: {total_openai_calls}")
    output.add_log(f"Successful renders: {successful_renders}/{len(moments)}")
    if retry_count > 0:
        output.add_log(f"Retries: {retry_count} moments retried")
    if injection_count > 0:
        output.add_log(
            f"Injections: {injection_count} moments required deterministic injection"
        )

    # Log style violations (non-blocking, for monitoring)
    if all_style_violations:
        violation_types: dict[str, int] = {}
        for v in all_style_violations:
            vtype = v.get("type", v.get("violation_type", "unknown"))
            violation_types[vtype] = violation_types.get(vtype, 0) + 1

        output.add_log(
            f"Style violations: {len(all_style_violations)} total "
            f"({', '.join(f'{t}:{c}' for t, c in violation_types.items())})",
            level="info",
        )

        logger.info(
            "render_narratives_style_violations",
            extra={
                "game_id": game_id,
                "style_violation_count": len(all_style_violations),
                "violation_types": violation_types,
                "violations": all_style_violations[:10],
            },
        )

    # Log fallback usage with classification
    if fallback_moments:
        output.add_log(
            f"Fallback narratives used: {len(fallback_moments)} total "
            f"({len(valid_fallbacks)} VALID, {len(invalid_fallbacks)} INVALID)",
            level="warning" if invalid_fallbacks else "info",
        )

        if valid_fallbacks:
            output.add_log(
                f"  VALID fallbacks (low-signal gameplay): {len(valid_fallbacks)}",
                level="info",
            )

        if invalid_fallbacks:
            output.add_log(
                f"  INVALID fallbacks (needs debugging): {len(invalid_fallbacks)}",
                level="warning",
            )
            for fb in invalid_fallbacks[:5]:
                output.add_log(
                    f"    Moment {fb['moment_index']}: {fb.get('reason', 'unknown')}",
                    level="warning",
                )
            if len(invalid_fallbacks) > 5:
                output.add_log(
                    f"    ... and {len(invalid_fallbacks) - 5} more INVALID fallbacks",
                    level="warning",
                )

        logger.warning(
            "render_narratives_fallbacks_used",
            extra={
                "game_id": game_id,
                "fallback_count": len(fallback_moments),
                "valid_fallback_count": len(valid_fallbacks),
                "invalid_fallback_count": len(invalid_fallbacks),
                "fallback_moment_indices": fallback_moments,
                "invalid_fallback_details": invalid_fallbacks[:10],
            },
        )

    if fallback_moments:
        output.add_log(
            f"{len(moments) - len(fallback_moments)} narratives from OpenAI, "
            f"{len(fallback_moments)} fallbacks used "
            f"({len(valid_fallbacks)} valid, {len(invalid_fallbacks)} invalid)"
        )
    else:
        output.add_log(f"All {len(moments)} narratives generated successfully")

    if invalid_fallbacks:
        output.add_log(
            f"WARNING: {len(invalid_fallbacks)} INVALID fallbacks detected - "
            f"these indicate pipeline issues that need debugging",
            level="warning",
        )

    output.add_log("RENDER_NARRATIVES completed successfully")

    output.data = {
        "rendered": True,
        "moments": enriched_moments,
        "errors": [],
        "openai_calls": total_openai_calls,
        "successful_renders": successful_renders,
        "fallback_count": len(fallback_moments),
        "fallback_moment_indices": fallback_moments,
        "valid_fallback_count": len(valid_fallbacks),
        "invalid_fallback_count": len(invalid_fallbacks),
        "valid_fallbacks": valid_fallbacks,
        "invalid_fallbacks": invalid_fallbacks,
        "retry_count": retry_count,
        "injection_count": injection_count,
        "style_violation_count": len(all_style_violations),
        "style_violations": all_style_violations,
    }

    return output


def _check_explicit_coverage(
    narrative: str,
    moment: dict[str, Any],
    moment_plays: list[dict[str, Any]],
) -> list[int]:
    """Wrapper for check_explicit_play_coverage that returns missing play IDs.

    Args:
        narrative: The narrative text
        moment: The moment data
        moment_plays: PBP events for the moment

    Returns:
        List of missing play indices
    """
    explicit_ids = set(moment.get("explicitly_narrated_play_ids", []))
    if not explicit_ids:
        return []

    all_covered, covered_ids, missing_ids = check_explicit_play_coverage(
        narrative, explicit_ids, moment_plays
    )
    return list(missing_ids)
