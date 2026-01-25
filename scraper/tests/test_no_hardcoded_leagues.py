"""
Regression test to prevent hardcoded league defaults from being reintroduced.

This test scans key files for patterns that indicate hardcoded NBA defaults
or other sport-specific assumptions that should use SSOT instead.
"""

import re
from pathlib import Path

# Files to scan for hardcoded defaults
CRITICAL_FILES = [
    "sports_scraper/jobs/tasks.py",
    "sports_scraper/services/scheduler.py",
    "sports_scraper/services/ingestion.py",
    "sports_scraper/services/timeline_generator.py",
]

# Patterns that indicate hardcoded league defaults
FORBIDDEN_PATTERNS = [
    # get(..., "NBA") style defaults
    (r'\.get\([^,]+,\s*["\']NBA["\']', "Found get(..., 'NBA') default"),
    # Field(default="NBA")
    (r'Field\(default=["\']NBA["\']', "Found Field(default='NBA')"),
    # Query("NBA")
    (r'Query\(["\']NBA["\']', "Found Query('NBA') default"),
    # Hardcoded league tuple
    (r'LEAGUES\s*=\s*\(["\']NBA["\']', "Found hardcoded LEAGUES tuple"),
]

# Allowed patterns (exceptions)
ALLOWED_EXCEPTIONS = [
    # Display strings and error messages are OK
    r'print\(',
    r'logger\.',
    r'raise',
    r'#',  # Comments
    r'description=',  # API docs
]


def test_no_hardcoded_league_defaults():
    """Ensure no hardcoded league defaults exist in critical paths."""
    scraper_root = Path(__file__).parent.parent
    
    violations = []
    
    for file_path in CRITICAL_FILES:
        full_path = scraper_root / file_path
        if not full_path.exists():
            continue
        
        content = full_path.read_text()
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Skip allowed exceptions
            if any(re.search(pattern, line) for pattern in ALLOWED_EXCEPTIONS):
                continue
            
            # Check for forbidden patterns
            for pattern, message in FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    violations.append(f"{file_path}:{line_num}: {message}\n  {line.strip()}")
    
    if violations:
        raise AssertionError(
            f"Found {len(violations)} hardcoded league default(s):\n\n" + 
            "\n\n".join(violations) +
            "\n\nUse config_sports.py SSOT instead of hardcoded defaults."
        )


def test_config_sports_ssot_exists():
    """Ensure the SSOT configuration file exists."""
    scraper_root = Path(__file__).parent.parent
    ssot_path = scraper_root / "sports_scraper" / "config_sports.py"
    
    assert ssot_path.exists(), f"SSOT config file missing: {ssot_path}"
    
    content = ssot_path.read_text()
    assert "LEAGUE_CONFIG" in content, "SSOT must define LEAGUE_CONFIG"
    assert "get_scheduled_leagues" in content, "SSOT must define get_scheduled_leagues()"
    assert "validate_league_code" in content, "SSOT must define validate_league_code()"


def test_all_leagues_have_required_fields():
    """Validate that all league configs have required fields."""
    from sports_scraper.config_sports import LEAGUE_CONFIG
    
    required_fields = [
        "code",
        "display_name",
        "social_enabled",
        "timeline_enabled",
        "scheduled_ingestion",
    ]
    
    for code, config in LEAGUE_CONFIG.items():
        for field in required_fields:
            assert hasattr(config, field), f"League {code} missing field: {field}"


def test_validate_league_code_rejects_unknown():
    """Ensure validation rejects unknown leagues."""
    from sports_scraper.config_sports import validate_league_code
    import pytest
    
    # Valid codes should pass
    assert validate_league_code("NBA") == "NBA"
    
    # Unknown codes should raise
    with pytest.raises(ValueError, match="Invalid league_code"):
        validate_league_code("FAKE_LEAGUE")
    
    with pytest.raises(ValueError, match="Invalid league_code"):
        validate_league_code("")


if __name__ == "__main__":
    test_no_hardcoded_league_defaults()
    test_config_sports_ssot_exists()
    print("All hardcoded league tests passed!")
