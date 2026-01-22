"""add game stories table

Revision ID: 20260122_000001
Revises: 20260218_000005
Create Date: 2026-01-22 01:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260122_000001'
down_revision = '20260218_000005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add sports_game_stories table for caching AI-generated stories."""
    op.create_table(
        'sports_game_stories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('sport', sa.String(length=20), nullable=False),
        sa.Column('story_version', sa.String(length=20), nullable=False),
        
        # Chapter structure (deterministic, can be regenerated)
        sa.Column('chapters_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('chapter_count', sa.Integer(), nullable=False, default=0),
        sa.Column('chapters_fingerprint', sa.String(length=64), nullable=True),
        
        # AI-generated content (expensive, should be cached)
        sa.Column('summaries_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('titles_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('compact_story', sa.Text(), nullable=True),
        sa.Column('reading_time_minutes', sa.Float(), nullable=True),
        
        # Generation metadata
        sa.Column('has_summaries', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column('has_titles', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column('has_compact_story', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ai_model_used', sa.String(length=50), nullable=True),
        sa.Column('total_ai_calls', sa.Integer(), nullable=False, default=0),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['game_id'], ['sports_games.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('game_id', 'story_version', name='uq_game_story_version'),
    )
    
    # Indexes for efficient lookups
    op.create_index('idx_game_stories_game_id', 'sports_game_stories', ['game_id'])
    op.create_index('idx_game_stories_sport', 'sports_game_stories', ['sport'])
    op.create_index('idx_game_stories_generated_at', 'sports_game_stories', ['generated_at'])


def downgrade() -> None:
    """Remove sports_game_stories table."""
    op.drop_index('idx_game_stories_generated_at', table_name='sports_game_stories')
    op.drop_index('idx_game_stories_sport', table_name='sports_game_stories')
    op.drop_index('idx_game_stories_game_id', table_name='sports_game_stories')
    op.drop_table('sports_game_stories')
