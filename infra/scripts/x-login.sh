#!/bin/bash
# One-time X/Twitter login for social scraper
#
# This script opens a VISIBLE browser window inside the Docker container
# for manual X login. The browser profile (cookies, local storage) is saved
# to the bind-mounted volume so the social-scraper worker can reuse it.
#
# Requirements:
#   - Linux server with a display (e.g., Hetzner with desktop or VNC)
#   - Docker Compose services defined
#
# For Mac (local dev), you don't need this script:
#   1. Log in to x.com in any browser
#   2. Copy auth_token and ct0 from DevTools > Cookies
#   3. Set X_AUTH_TOKEN and X_CT0 in infra/.env
#   4. Restart social-scraper — tokens are seeded automatically on boot
#
# Usage:
#   ./infra/scripts/x-login.sh
#
# After running:
#   1. Log in to X in the browser that opens
#   2. Close the browser window
#   3. The profile is saved — start containers normally

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== X/Twitter Login Setup (Docker) ==="
echo ""
echo "This runs a visible browser INSIDE the social-scraper container."
echo "Make sure you have a display available (X11, VNC, etc)."
echo ""

cd "$INFRA_DIR"

docker compose run --rm \
  -e DISPLAY="${DISPLAY}" \
  social-scraper \
  python -c "
from playwright.sync_api import sync_playwright
import os

profile_dir = os.environ.get('PLAYWRIGHT_PROFILE_DIR', '/app/browser-profile')
os.makedirs(profile_dir, exist_ok=True)
print(f'Browser profile will be saved to: {profile_dir}')
print()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        viewport={'width': 1280, 'height': 800},
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://x.com/login')

    print('Waiting for browser to close...')
    print('(Log in to X, then close the browser window)')
    print()

    # Wait for all pages to close (user closes browser)
    try:
        while context.pages:
            context.pages[0].wait_for_event('close', timeout=0)
    except Exception:
        pass

    context.close()

print()
print('Profile saved!')
"

echo ""
echo "Done! Profile saved inside the container volume."
echo "Start containers: docker compose --profile dev up -d"
echo ""
echo "The social-scraper container will use the saved browser session."
echo "Tokens auto-refresh on each use — no need to log in again unless"
echo "the profile directory is deleted."
