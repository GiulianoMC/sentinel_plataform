"""add channel_title aos vídeos e índice em channel_id (filtro por canal)

Revision ID: 004
Revises: 003
Create Date: 2026-09-09 00:00:00.000000

`channel_id` já existia desde a revisão 000 mas nunca era preenchido. Esta
revisão adiciona o nome legível do canal (para a UI) e indexa `channel_id`,
que passa a ser usado nos filtros de /video/list e nas agregações por canal
do Analytics.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('channel_title', sa.String(), nullable=True))
    op.create_index(op.f('ix_videos_channel_id'), 'videos', ['channel_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_videos_channel_id'), table_name='videos')
    op.drop_column('videos', 'channel_title')
