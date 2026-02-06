#!/bin/bash
# One-time X/Twitter login for social scraper
#
# This script opens a browser window for manual X login. The browser profile
# (cookies, local storage) is saved to a Docker volume so the social-scraper
# container can reuse the session without manual token extraction.
#
# Usage:
#   ./infra/scripts/x-login.sh
#
# After running:
#   1. Log in to X in the browser that opens
#   2. Close the browser window
#   3. Press Enter in the terminal
#   4. The profile is saved - start containers normally

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== X/Twitter Login Setup ==="
echo ""
echo "This will open a browser window for you to log in to X."
echo "After logging in, close the browser and press Enter."
echo ""
echo "Starting browser..."

# Run a one-off container with the social-scraper profile volume mounted
docker compose -f "$INFRA_DIR/docker-compose.yml" --profile dev run --rm \
  -e PLAYWRIGHT_PROFILE_DIR=/app/.playwright-profile \
  social-scraper \
  python -c "
from playwright.sync_api import sync_playwright
import os

profile_dir = os.environ.get('PLAYWRIGHT_PROFILE_DIR', '/app/.playwright-profile')
print(f'Browser profile will be saved to: {profile_dir}')
print()
print('Instructions:')
print('  1. Log in to X/Twitter in the browser window')
print('  2. Close the browser window when done')
print('  3. Press Enter in this terminal')
print()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        profile_dir,
        headless=False,  # Show browser for manual login
        viewport={'width': 1280, 'height': 800},
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://x.com/login')
    input('Press Enter after logging in and closing the browser...')
    context.close()

print()
print('Profile saved! The social-scraper container will now use this session.')
print('Start containers with: docker compose --profile dev up -d')
"

echo ""
echo "Done! Start your containers normally - social scraper will use the saved session."
