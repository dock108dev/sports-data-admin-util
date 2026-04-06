"""Tests for FairBet runtime cache/snapshot/limiter helpers."""

from __future__ import annotations

from app.services import fairbet_runtime as fr


class _Pipe:
    def __init__(self, redis_obj):
        self.r = redis_obj
        self.ops = []

    def zremrangebyscore(self, key, low, high):
        self.ops.append(("zrem", key, low, high))
        return self

    def zcard(self, key):
        self.ops.append(("zcard", key))
        return self

    def zadd(self, key, payload):
        self.ops.append(("zadd", key, payload))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "zrem":
                _, key, _, high = op
                members = self.r.zsets.setdefault(key, {})
                stale = [m for m, score in members.items() if score <= high]
                for m in stale:
                    del members[m]
                out.append(len(stale))
            elif op[0] == "zcard":
                _, key = op
                out.append(len(self.r.zsets.get(key, {})))
            elif op[0] == "zadd":
                _, key, payload = op
                members = self.r.zsets.setdefault(key, {})
                for member, score in payload.items():
                    members[member] = score
                out.append(1)
            elif op[0] == "expire":
                out.append(True)
        self.ops = []
        return out


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.zsets: dict[str, dict[str, int]] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True

    def pipeline(self):
        return _Pipe(self)


def test_cursor_roundtrip():
    payload = {"sort": "game_time", "v": ["2026-01-01T00:00:00+00:00", 1, "spreads", "team:a", -3.5]}
    encoded = fr.encode_cursor(payload)
    decoded = fr.decode_cursor(encoded)
    assert decoded == payload


def test_cache_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(fr, "get_redis_client", lambda: fake)
    monkeypatch.setattr(fr.settings, "fairbet_odds_cache_enabled", True)

    fr.set_cached_response("q1", "v1", {"ok": True}, ttl_seconds=10)
    cached = fr.get_cached_response("q1", "v1")
    assert cached == {"ok": True}


def test_snapshot_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(fr, "get_redis_client", lambda: fake)

    sid, _ = fr.create_snapshot("qhash", [{"game_id": 1}], total=1)
    snap = fr.get_snapshot(sid)
    assert snap is not None
    assert snap["query_hash"] == "qhash"
    assert snap["total"] == 1


def test_redis_allow_request_blocks_after_limit(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(fr, "get_redis_client", lambda: fake)

    # Simulate multi-instance calls by invoking function repeatedly.
    assert fr.redis_allow_request("ip-1", limit=2, window_seconds=60)[0] is True
    assert fr.redis_allow_request("ip-1", limit=2, window_seconds=60)[0] is True
    allowed, retry = fr.redis_allow_request("ip-1", limit=2, window_seconds=60)
    assert allowed is False
    assert retry >= 1
