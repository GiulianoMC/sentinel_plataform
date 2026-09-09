"""add video_insights (cache dos cards de insights)

Revision ID: 003
Revises: 002
Create Date: 2026-09-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'video_insights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('youtube_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('evidence_ids', sa.JSON(), nullable=True),
        sa.Column('analyzed_at_generation', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['youtube_id'], ['videos.youtube_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('youtube_id', 'kind', name='uq_video_insights_video_kind'),
    )
    op.create_index(op.f('ix_video_insights_id'), 'video_insights', ['id'], unique=False)
    op.create_index(op.f('ix_video_insights_youtube_id'), 'video_insights', ['youtube_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_video_insights_youtube_id'), table_name='video_insights')
    op.drop_index(op.f('ix_video_insights_id'), table_name='video_insights')
    op.drop_table('video_insights')
