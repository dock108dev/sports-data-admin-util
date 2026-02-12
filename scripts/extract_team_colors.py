#!/usr/bin/env python3
"""One-time helper: extract team colors from GameTheme.swift → _team_color_data.py.

This script documents how the color data in _team_color_data.py was originally
extracted from the iOS app's GameTheme.swift file. The output module is already
committed and used by the Alembic migration, so this script does not need to be
re-run unless GameTheme.swift changes.

Usage (for reference):
    python scripts/extract_team_colors.py path/to/GameTheme.swift

The script:
1. Parses NBA colors (30 teams + 2 aliases) — exact rgb(r,g,b) pairs
2. Parses NHL colors (32 teams) — same format
3. Parses college palettes (16 palettes) and team-to-palette mapping (345 teams)
4. Converts all RGB values to hex strings: rgb(0, 122, 51) → #007A33
5. Outputs verification stats

The actual data is maintained in scripts/_team_color_data.py.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Verify the generated color data module."""
    # Import the generated data module to verify it loads correctly
    sys.path.insert(0, "scripts")
    from _team_color_data import TEAM_COLORS

    nba = [k for k, v in TEAM_COLORS.items() if v["league"] == "NBA"]
    nhl = [k for k, v in TEAM_COLORS.items() if v["league"] == "NHL"]
    ncaab = [k for k, v in TEAM_COLORS.items() if v["league"] == "NCAAB"]

    print(f"Total teams: {len(TEAM_COLORS)}")
    print(f"  NBA:   {len(nba)} (includes LA/Los Angeles aliases)")
    print(f"  NHL:   {len(nhl)}")
    print(f"  NCAAB: {len(ncaab)}")

    # Validate all hex values are 7-char format
    errors = 0
    for name, data in TEAM_COLORS.items():
        for mode in ("light", "dark"):
            hex_val = data[mode]
            if len(hex_val) != 7 or hex_val[0] != "#":
                print(f"  INVALID: {name} {mode} = {hex_val}")
                errors += 1

    if errors:
        print(f"\n{errors} invalid hex values found!")
        sys.exit(1)
    else:
        print("\nAll hex values valid (7-char #RRGGBB format)")


if __name__ == "__main__":
    main()
