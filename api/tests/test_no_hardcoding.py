"""
Tests for no hardcoded sport-specific values.

These tests scan the source code to ensure no sport-specific
constants (like NBA thresholds) are embedded in the core modules.

This prevents silent regressions where someone adds a "convenient"
default that breaks multi-sport support.
"""

from __future__ import annotations

import inspect
import re
import unittest


class TestNoHardcodedNBAInMoments(unittest.TestCase):
    """
    GUARDRAIL: moments.py has no hardcoded NBA values.
    """

    def test_no_nba_string_literals(self) -> None:
        """No 'NBA' string literals in moments.py."""
        from app.services import moments
        source = inspect.getsource(moments)
        
        # Should not have NBA as a default or constant
        # Allow NBA in comments/docstrings but not in code
        lines = source.split("\n")
        for i, line in enumerate(lines):
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if '= "NBA"' in line or "= 'NBA'" in line:
                self.fail(f"Line {i+1}: Hardcoded 'NBA' string found: {line}")

    def test_no_hardcoded_point_thresholds(self) -> None:
        """No hardcoded point thresholds like 8, 10 for runs."""
        from app.services import moments
        source = inspect.getsource(moments)
        
        # Old hardcoded values that should NOT exist
        forbidden_patterns = [
            r"RUN_POINTS_THRESHOLD\s*=\s*\d+",
            r"RUN_NOTABLE_THRESHOLD\s*=\s*\d+",
            r"CLOSING_MINUTES\s*=\s*\d+",
            r"CLOSING_MARGIN\s*=\s*\d+",
            r"BATTLE_LEAD_CHANGES\s*=\s*\d+",
        ]
        
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, source)
            self.assertEqual(
                len(matches), 0,
                f"Hardcoded constant found: {matches}"
            )

    def test_no_old_moment_types(self) -> None:
        """Verify old moment types (RUN, BATTLE, CLOSING) don't exist in enum."""
        from app.services.moments import MomentType
        
        # Guardrail: These types were removed in Lead Ladder refactor
        # If they reappear, it's a regression
        self.assertFalse(hasattr(MomentType, "RUN"), "RUN type should not exist")
        self.assertFalse(hasattr(MomentType, "BATTLE"), "BATTLE type should not exist")
        self.assertFalse(hasattr(MomentType, "CLOSING"), "CLOSING type should not exist (use CLOSING_CONTROL)")


class TestNoHardcodedNBAInLeadLadder(unittest.TestCase):
    """
    GUARDRAIL: lead_ladder.py has no hardcoded NBA values.
    """

    def test_no_nba_thresholds_as_defaults(self) -> None:
        """No hardcoded [3, 6, 10, 16] thresholds as function defaults."""
        from app.services import lead_ladder
        source = inspect.getsource(lead_ladder)
        
        # Check for NBA threshold array as DEFAULT PARAMETER
        # Examples in docstrings are acceptable
        # Pattern: "thresholds = [3, 6, 10, 16]" in function signature
        pattern = r"def.*thresholds\s*=\s*\[3,?\s*6,?\s*10,?\s*16\]"
        matches = re.findall(pattern, source)
        self.assertEqual(
            len(matches), 0,
            f"Hardcoded NBA thresholds as function defaults: {matches}"
        )

    def test_no_default_threshold_parameters(self) -> None:
        """Functions don't have default threshold parameters."""
        from app.services import lead_ladder
        source = inspect.getsource(lead_ladder)
        
        # Pattern for default threshold in function signature
        # e.g., "thresholds = [3, 6, 10, 16]" or "thresholds=[1,2,3]"
        pattern = r"thresholds\s*=\s*\[\d"
        matches = re.findall(pattern, source)
        self.assertEqual(
            len(matches), 0,
            f"Default thresholds in function signature: {matches}"
        )


class TestNoHardcodedNBAInCompactMode(unittest.TestCase):
    """
    GUARDRAIL: compact_mode.py has no hardcoded NBA values.
    """

    def test_no_nba_string_literals(self) -> None:
        """No 'NBA' string literals in compact_mode.py."""
        from app.services import compact_mode
        source = inspect.getsource(compact_mode)
        
        # Check for NBA defaults
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '= "NBA"' in line or "= 'NBA'" in line:
                self.fail(f"Line {i+1}: Hardcoded 'NBA' string found: {line}")


class TestNoHardcodedNBAInThresholds(unittest.TestCase):
    """
    GUARDRAIL: compact_mode_thresholds.py has no inline defaults.
    """

    def test_thresholds_come_from_database(self) -> None:
        """Thresholds are loaded from database, not hardcoded."""
        from app.services import compact_mode_thresholds
        source = inspect.getsource(compact_mode_thresholds)
        
        # Should NOT have a default threshold array in get functions
        # (except for test helpers or fallback documentation)
        
        # Check that get_lead_tier doesn't have defaults
        self.assertNotIn("def get_lead_tier(margin, thresholds=[", source)


class TestNoHardcodedNBAInAI(unittest.TestCase):
    """
    GUARDRAIL: AI client has no hardcoded sport assumptions.
    """

    def test_no_sport_specific_prompts(self) -> None:
        """AI prompts don't assume NBA-specific language."""
        from app.services import ai_client
        source = inspect.getsource(ai_client)
        
        # Check for hardcoded NBA assumptions in prompts
        # Prompts should use {sport} placeholder, not hardcoded NBA
        
        # Find PROMPT constants
        prompt_pattern = r'(PROMPT\s*=\s*"""[\s\S]*?""")'
        prompts = re.findall(prompt_pattern, source)
        
        for prompt in prompts:
            # Prompts may mention NBA as context, but shouldn't assume it
            # Check they use {sport} placeholder
            if "basketball" in prompt.lower() and "{sport}" not in prompt:
                self.fail("Prompt has hardcoded basketball reference without {sport} placeholder")


class TestSourceCodeInvariants(unittest.TestCase):
    """
    GUARDRAIL: General source code invariants.
    """

    def test_all_moment_types_in_compression_behavior(self) -> None:
        """All MomentTypes have compression behavior defined."""
        from app.services.moments import MomentType
        from app.services.compact_mode import COMPRESSION_BEHAVIOR
        
        for mt in MomentType:
            self.assertIn(
                mt, COMPRESSION_BEHAVIOR,
                f"MomentType.{mt.name} missing from COMPRESSION_BEHAVIOR"
            )

    def test_validate_moments_exists(self) -> None:
        """validate_moments() function exists and is exported."""
        from app.services.moments import validate_moments
        self.assertTrue(callable(validate_moments))

    def test_partition_game_signature(self) -> None:
        """partition_game() requires thresholds parameter."""
        from app.services.moments import partition_game
        
        sig = inspect.signature(partition_game)
        params = list(sig.parameters.keys())
        
        self.assertIn("timeline", params)
        self.assertIn("thresholds", params)
        
        # thresholds should NOT have a hardcoded default list
        thresholds_param = sig.parameters["thresholds"]
        default = thresholds_param.default
        if default != inspect.Parameter.empty:
            self.assertIsNone(
                default,
                f"partition_game has default thresholds: {default}"
            )


if __name__ == "__main__":
    unittest.main()
