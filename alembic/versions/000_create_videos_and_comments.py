"""create videos and comments tables (baseline)

Revision ID: 000
Revises: 
Create Date: 2026-08-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create videos table
    op.create_table(
        'videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('youtube_id', sa.String(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('channel_id', sa.String(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('ultimo_comentario_verificado_em', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_videos_id'), 'videos', ['id'], unique=False)
    op.create_index(op.f('ix_videos_youtube_id'), 'videos', ['youtube_id'], unique=True)

    # Create comments table
    op.create_table(
        'comments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('youtube_id', sa.String(), nullable=False),
        sa.Column('author', sa.String(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('sentiment', sa.Integer(), nullable=True),
        sa.Column('intent', sa.String(), nullable=True),
        sa.Column('product_mentioned', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comments_id'), 'comments', ['id'], unique=False)
    op.create_index(op.f('ix_comments_youtube_id'), 'comments', ['youtube_id'], unique=False)

    # Add foreign key comments.youtube_id -> videos.youtube_id (batch mode for SQLite compat)
    with op.batch_alter_table('comments') as batch_op:
        batch_op.create_foreign_key(
            'fk_comments_youtube_id_videos', 'videos',
            ['youtube_id'], ['youtube_id']
        )


def downgrade() -> None:
    with op.batch_alter_table('comments') as batch_op:
        batch_op.drop_constraint('fk_comments_youtube_id_videos', type_='foreignkey')
    op.drop_index(op.f('ix_comments_youtube_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_id'), table_name='comments')
    op.drop_table('comments')

    op.drop_index(op.f('ix_videos_youtube_id'), table_name='videos')
    op.drop_index(op.f('ix_videos_id'), table_name='videos')
    op.drop_table('videos')