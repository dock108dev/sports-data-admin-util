"""Add model_home_wp and blend_alpha to mlb_daily_forecasts.

Revision ID: forecast_blend_cols_001
Revises: team_colors_full_seed_001
Create Date: 2026-04-08

Stores the raw model win-probability and the blending alpha used
when combining model output with market lines.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "forecast_blend_cols_001"
down_revision = "team_colors_full_seed_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mlb_daily_forecasts",
        sa.Column("model_home_wp", sa.Float(), nullable=True),
    )
    op.add_column(
        "mlb_daily_forecasts",
        sa.Column("blend_alpha", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mlb_daily_forecasts", "blend_alpha")
    op.drop_column("mlb_daily_forecasts", "model_home_wp")
