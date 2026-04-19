"""Tests for the Bluesky AT Protocol social collector prototype.

Uses importlib to load bluesky_collector.py and models.py directly,
bypassing the social package __init__.py which pulls in structlog/db
dependencies not present in the minimal test venv.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import httpx

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

# ---------------------------------------------------------------------------
# Load models.py and bluesky_collector.py directly to avoid __init__.py
# chain that requires structlog (not installed in minimal test venv).
# ---------------------------------------------------------------------------

def _load_module(name: str, path: Path, package: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the social package so relative imports inside the loaded modules resolve.
_social_pkg = types.ModuleType("sports_scraper.social")
_social_pkg.__path__ = []
_social_pkg.__package__ = "sports_scraper.social"
sys.modules.setdefault("sports_scraper.social", _social_pkg)

_models_mod = _load_module(
    "sports_scraper.social.models",
    SCRAPER_ROOT / "sports_scraper/social/models.py",
    "sports_scraper.social",
)
_social_pkg.models = _models_mod  # type: ignore[attr-defined]

_bc_mod = _load_module(
    "sports_scraper.social.bluesky_collector",
    SCRAPER_ROOT / "sports_scraper/social/bluesky_collector.py",
    "sports_scraper.social",
)

CollectedPost = _models_mod.CollectedPost
BlueSkyCollector = _bc_mod.BlueSkyCollector
_build_post_url = _bc_mod._build_post_url
_extract_media = _bc_mod._extract_media
_parse_at_uri = _bc_mod._parse_at_uri
_to_utc = _bc_mod._to_utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feed_item(
    rkey: str = "abc123",
    handle: str = "patriots.bsky.social",
    did: str = "did:plc:testdid",
    created_at: str = "2024-01-15T14:00:00Z",
    text: str = "Game day!",
    embed: dict | None = None,
    is_repost: bool = False,
) -> dict:
    item: dict = {
        "post": {
            "uri": f"at://{did}/app.bsky.feed.post/{rkey}",
            "author": {"did": did, "handle": handle},
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": created_at,
            },
            "indexedAt": created_at,
        }
    }
    if embed is not None:
        item["post"]["record"]["embed"] = embed
    if is_repost:
        item["reason"] = {"$type": "app.bsky.feed.defs#reasonRepost"}
    return item


def _mock_client(pages: list[dict]) -> httpx.Client:
    client = MagicMock(spec=httpx.Client)
    responses = []
    for page in pages:
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = page
        resp.raise_for_status = MagicMock()
        responses.append(resp)
    client.get.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestParseAtUri:
    def test_valid_uri(self):
        did, rkey = _parse_at_uri("at://did:plc:abc/app.bsky.feed.post/xyz789")
        assert did == "did:plc:abc"
        assert rkey == "xyz789"

    def test_not_at_uri(self):
        assert _parse_at_uri("https://bsky.app/foo") == (None, None)

    def test_too_short(self):
        assert _parse_at_uri("at://did:plc:abc") == (None, None)


class TestBuildPostUrl:
    def test_basic(self):
        url = _build_post_url("patriots.bsky.social", "rkey123")
        assert url == "https://bsky.app/profile/patriots.bsky.social/post/rkey123"


class TestExtractMedia:
    def test_no_embed(self):
        image_url, video_url, media_type = _extract_media({})
        assert image_url is None
        assert video_url is None
        assert media_type == "none"

    def test_images_embed(self):
        record = {
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [
                    {"image": {"ref": {"$link": "abc123"}, "mimeType": "image/jpeg"}, "alt": ""}
                ],
            }
        }
        image_url, video_url, media_type = _extract_media(record)
        assert media_type == "image"
        assert "abc123" in (image_url or "")
        assert video_url is None

    def test_images_embed_empty_list(self):
        record = {"embed": {"$type": "app.bsky.embed.images", "images": []}}
        _, _, media_type = _extract_media(record)
        assert media_type == "none"

    def test_video_embed(self):
        record = {
            "embed": {
                "$type": "app.bsky.embed.video",
                "video": {"ref": {"$link": "vid456"}, "mimeType": "video/mp4"},
            }
        }
        image_url, video_url, media_type = _extract_media(record)
        assert media_type == "video"
        assert "vid456" in (video_url or "")
        assert image_url is None

    def test_external_with_thumb(self):
        record = {
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {"uri": "https://example.com", "thumb": "thumbdata"},
            }
        }
        _, _, media_type = _extract_media(record)
        assert media_type == "image"

    def test_external_without_thumb(self):
        record = {
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {"uri": "https://example.com"},
            }
        }
        _, _, media_type = _extract_media(record)
        assert media_type == "none"


class TestToUtc:
    def test_naive_datetime_gets_utc(self):
        dt = datetime(2024, 1, 1, 12, 0)
        result = _to_utc(dt)
        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0

    def test_aware_datetime_converted(self):
        from datetime import timedelta, timezone
        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2024, 1, 1, 7, 0, tzinfo=eastern)
        result = _to_utc(dt)
        assert result.hour == 12  # 7 AM ET == 12 PM UTC


# ---------------------------------------------------------------------------
# BlueSkyCollector integration-style tests
# ---------------------------------------------------------------------------

class TestBlueSkyCollectorCollectPosts:
    def _collector(self, pages: list[dict]) -> BlueSkyCollector:
        return BlueSkyCollector(client=_mock_client(pages))

    def test_returns_collected_posts_within_window(self):
        page = {
            "feed": [_make_feed_item(rkey="r1", created_at="2024-01-15T14:00:00Z")],
            "cursor": None,
        }
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 1
        post = results[0]
        assert isinstance(post, CollectedPost)
        assert post.platform == "bluesky"
        assert post.external_post_id == "r1"
        assert "bsky.app/profile" in post.post_url
        assert post.text == "Game day!"

    def test_skips_reposts(self):
        page = {
            "feed": [
                _make_feed_item(rkey="r1", created_at="2024-01-15T14:00:00Z"),
                _make_feed_item(rkey="r2", created_at="2024-01-15T14:05:00Z", is_repost=True),
            ],
            "cursor": None,
        }
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 1
        assert results[0].external_post_id == "r1"

    def test_skips_posts_after_window_end(self):
        page = {
            "feed": [
                _make_feed_item(rkey="future", created_at="2024-01-15T20:00:00Z"),
                _make_feed_item(rkey="in_window", created_at="2024-01-15T14:00:00Z"),
            ],
            "cursor": None,
        }
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 1
        assert results[0].external_post_id == "in_window"

    def test_stops_early_when_post_before_window_start(self):
        page = {
            "feed": [_make_feed_item(rkey="old", created_at="2024-01-15T10:00:00Z")],
            "cursor": "some_cursor",
        }
        collector = self._collector([page])
        results = collector.collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert results == []
        # Stops early — only one page fetched even though cursor was present
        assert collector._client.get.call_count == 1

    def test_paginates_until_no_cursor(self):
        page1 = {
            "feed": [_make_feed_item(rkey="r1", created_at="2024-01-15T14:30:00Z")],
            "cursor": "next_cursor",
        }
        page2 = {
            "feed": [_make_feed_item(rkey="r2", created_at="2024-01-15T14:00:00Z")],
            "cursor": None,
        }
        collector = self._collector([page1, page2])
        results = collector.collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 2
        assert collector._client.get.call_count == 2

    def test_returns_empty_on_api_error(self):
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.ConnectError("connection refused")
        collector = BlueSkyCollector(client=client)
        results = collector.collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert results == []

    def test_empty_feed_returns_empty_list(self):
        page = {"feed": [], "cursor": None}
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert results == []

    def test_post_with_image_embed(self):
        item = _make_feed_item(
            rkey="img1",
            created_at="2024-01-15T14:00:00Z",
            embed={
                "$type": "app.bsky.embed.images",
                "images": [{"image": {"ref": {"$link": "linkref"}, "mimeType": "image/jpeg"}, "alt": ""}],
            },
        )
        page = {"feed": [item], "cursor": None}
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 1
        assert results[0].media_type == "image"
        assert results[0].has_video is False
        assert "linkref" in (results[0].image_url or "")

    def test_post_with_video_embed(self):
        item = _make_feed_item(
            rkey="vid1",
            created_at="2024-01-15T14:00:00Z",
            embed={
                "$type": "app.bsky.embed.video",
                "video": {"ref": {"$link": "vidlink"}, "mimeType": "video/mp4"},
            },
        )
        page = {"feed": [item], "cursor": None}
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert len(results) == 1
        assert results[0].media_type == "video"
        assert results[0].has_video is True

    def test_skips_item_with_unparseable_uri(self):
        item = _make_feed_item(rkey="r1", created_at="2024-01-15T14:00:00Z")
        item["post"]["uri"] = "at://did:plc:x"  # too short — no rkey segment
        page = {"feed": [item], "cursor": None}
        results = self._collector([page]).collect_posts(
            "patriots.bsky.social",
            window_start=datetime(2024, 1, 15, 13, 0, tzinfo=UTC),
            window_end=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert results == []

    def test_fetch_page_passes_cursor(self):
        client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = {"feed": [], "cursor": None}
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        collector = BlueSkyCollector(client=client)
        collector._fetch_page("handle.bsky.social", cursor="tok123")

        call_kwargs = client.get.call_args
        assert call_kwargs[1]["params"]["cursor"] == "tok123"
        assert call_kwargs[1]["params"]["actor"] == "handle.bsky.social"
        assert call_kwargs[1]["params"]["filter"] == "posts_no_replies"


# ---------------------------------------------------------------------------
# Feature flag — load Settings via importlib to avoid lru_cache from prior
# settings singleton if one exists in sys.modules.
# ---------------------------------------------------------------------------

class TestFeatureFlag:
    def _fresh_settings(self, overrides: dict) -> object:
        """Load a fresh Settings instance without triggering validate_env."""
        import importlib
        # Clear cached module so we get a fresh class without lru_cache singleton
        for key in list(sys.modules):
            if key in ("sports_scraper.config", "sports_scraper.validate_env"):
                del sys.modules[key]

        # Stub validate_env so Settings() doesn't try to read the real env
        ve_mod = types.ModuleType("sports_scraper.validate_env")
        ve_mod.validate_env = lambda: None  # type: ignore[attr-defined]
        sys.modules["sports_scraper.validate_env"] = ve_mod

        config_mod = _load_module(
            "sports_scraper.config",
            SCRAPER_ROOT / "sports_scraper/config.py",
            "sports_scraper",
        )
        return config_mod.Settings.model_validate(overrides)

    def test_bluesky_disabled_by_default(self):
        s = self._fresh_settings({
            "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379/0",
        })
        assert s.bluesky_enabled is False

    def test_bluesky_enabled_via_env(self):
        s = self._fresh_settings({
            "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379/0",
            "ENABLE_BLUESKY_SOCIAL": "true",
        })
        assert s.bluesky_enabled is True
