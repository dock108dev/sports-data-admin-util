#!/usr/bin/env python3
"""
Update (or append) one Caddy site block inside an existing Caddyfile.

Usage:
  python3 update_caddy_site_block.py <source_caddyfile> <target_caddyfile> <site_header>
"""

from __future__ import annotations

import pathlib
import sys


def extract_site_block(content: str, header: str) -> str:
    start = content.find(header)
    if start == -1:
        raise RuntimeError(f"Could not find site header '{header}' in source Caddyfile")

    open_brace = content.find("{", start)
    if open_brace == -1:
        raise RuntimeError("Could not find opening brace for source site block")

    depth = 0
    for i in range(open_brace, len(content)):
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                block = content[start : i + 1]
                return block.strip() + "\n"
    raise RuntimeError("Could not find closing brace for source site block")


def replace_or_append_site_block(content: str, header: str, new_block: str) -> str:
    start = content.find(header)
    if start == -1:
        return content.rstrip() + "\n\n" + new_block

    open_brace = content.find("{", start)
    if open_brace == -1:
        raise RuntimeError("Malformed target Caddyfile: site header found without opening brace")

    depth = 0
    for i in range(open_brace, len(content)):
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return content[:start] + new_block + content[end:]
    raise RuntimeError("Malformed target Caddyfile: unmatched braces in site block")


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: python3 update_caddy_site_block.py <source_caddyfile> "
            "<target_caddyfile> <site_header>",
            file=sys.stderr,
        )
        return 2

    source_path = pathlib.Path(sys.argv[1])
    target_path = pathlib.Path(sys.argv[2])
    site_header = sys.argv[3]

    source_content = source_path.read_text()
    target_content = target_path.read_text()

    new_block = extract_site_block(source_content, site_header)
    updated = replace_or_append_site_block(target_content, site_header, new_block)

    target_path.write_text(updated)
    print(f"Updated site block '{site_header}' in {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
