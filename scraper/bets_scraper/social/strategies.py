"""
X post collection strategies.

Includes mock implementations for tests and a direct X API collector.
"""

from __future__ import annotations

from datetime import datetime

from ..logging import logger
from .collector_base import XCollectorStrategy
from .exceptions import SocialRateLimitError
from .models import CollectedPost


class MockXCollector(XCollectorStrategy):
    """
    Mock collector for testing without X API access.

    Returns empty results - real data should come from actual X integration.
    """

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        logger.info(
            "mock_x_collector_called",
            x_handle=x_handle,
            window_start=str(window_start),
            window_end=str(window_end),
        )
        return []


class XApiCollector(XCollectorStrategy):
    """
    Collector using X API v2.

    Requires X_BEARER_TOKEN environment variable.
    Rate limited to 450 requests per 15 minutes (user timeline).
    """

    def __init__(self, bearer_token: str | None = None):
        import os

        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN")
        if not self.bearer_token:
            logger.warning("x_api_collector_no_token", msg="X_BEARER_TOKEN not set")

    def collect_posts(
        self,
        x_handle: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CollectedPost]:
        if not self.bearer_token:
            logger.warning("x_api_skipped_no_token", x_handle=x_handle)
            return []

        import httpx

        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        base_url = "https://api.x.com/2"
        handle_clean = x_handle.lstrip("@")

        with httpx.Client(timeout=15) as client:
            user_resp = client.get(
                f"{base_url}/users/by/username/{handle_clean}",
                headers=headers,
                params={"user.fields": "id"},
            )
            if user_resp.status_code == 429:
                retry_after = int(user_resp.headers.get("retry-after", "60"))
                raise SocialRateLimitError("X API rate limit hit", retry_after_seconds=retry_after)
            user_resp.raise_for_status()
            user_data = user_resp.json().get("data")
            if not user_data or "id" not in user_data:
                logger.warning("x_api_user_not_found", handle=handle_clean)
                return []

            user_id = user_data["id"]
            posts: list[CollectedPost] = []
            next_token: str | None = None

            while True:
                params = {
                    "start_time": window_start.isoformat(),
                    "end_time": window_end.isoformat(),
                    "max_results": 100,
                    "exclude": "retweets",
                    "tweet.fields": "created_at",
                    "expansions": "attachments.media_keys",
                    "media.fields": "type,url,preview_image_url",
                }
                if next_token:
                    params["pagination_token"] = next_token

                resp = client.get(
                    f"{base_url}/users/{user_id}/tweets",
                    headers=headers,
                    params=params,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", "60"))
                    raise SocialRateLimitError("X API rate limit hit", retry_after_seconds=retry_after)
                resp.raise_for_status()
                payload = resp.json()
                tweets = payload.get("data", [])
                media_map = {
                    item["media_key"]: item
                    for item in payload.get("includes", {}).get("media", [])
                    if "media_key" in item
                }

                for tweet in tweets:
                    tweet_id = str(tweet.get("id"))
                    created_at = tweet.get("created_at")
                    if not tweet_id or not created_at:
                        continue
                    posted_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    post_url = f"https://x.com/{handle_clean}/status/{tweet_id}"

                    media_type = "none"
                    has_video = False
                    video_url = None
                    image_url = None
                    media_keys = tweet.get("attachments", {}).get("media_keys", [])
                    for key in media_keys:
                        media = media_map.get(key, {})
                        media_kind = media.get("type")
                        if media_kind == "video":
                            has_video = True
                            media_type = "video"
                            video_url = media.get("url") or video_url
                            image_url = media.get("preview_image_url") or image_url
                        elif media_kind == "photo":
                            media_type = "image"
                            image_url = media.get("url") or image_url

                    posts.append(
                        CollectedPost(
                            post_url=post_url,
                            external_post_id=tweet_id,
                            posted_at=posted_at,
                            has_video=has_video,
                            text=tweet.get("text"),
                            author_handle=handle_clean,
                            video_url=video_url,
                            image_url=image_url,
                            media_type=media_type,
                        )
                    )

                next_token = payload.get("meta", {}).get("next_token")
                if not next_token:
                    break

        return posts
