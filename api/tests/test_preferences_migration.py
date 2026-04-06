"""Tests for user preference score-hide migration statements."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_migration_upgrade_executes_safe_backfill(monkeypatch):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260406_000027_add_score_hide_lists_preferences.py"
    )
    spec = importlib.util.spec_from_file_location("prefs_migration", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    executed: list[str] = []

    def fake_execute(sql):
        executed.append(str(sql))

    monkeypatch.setattr(module.op, "execute", fake_execute)
    module.upgrade()

    joined = "\n".join(executed)
    assert "ADD COLUMN IF NOT EXISTS score_reveal_mode" in joined
    assert "ADD COLUMN IF NOT EXISTS score_hide_leagues" in joined
    assert "ADD COLUMN IF NOT EXISTS score_hide_teams" in joined
    assert "UPDATE user_preferences" in joined


def test_migration_downgrade_drops_columns(monkeypatch):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260406_000027_add_score_hide_lists_preferences.py"
    )
    spec = importlib.util.spec_from_file_location("prefs_migration", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dropped: list[str] = []

    def fake_drop_column(table, col):
        dropped.append(f"{table}.{col}")

    monkeypatch.setattr(module.op, "drop_column", fake_drop_column)
    module.downgrade()

    assert "user_preferences.score_hide_teams" in dropped
    assert "user_preferences.score_hide_leagues" in dropped
    assert "user_preferences.score_reveal_mode" in dropped
