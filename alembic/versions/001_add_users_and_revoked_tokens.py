"""add users and revoked_tokens tables, video user_id fk

Revision ID: 001
Revises: 
Create Date: 2026-08-13 23:22:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = '000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='user'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # Create revoked_tokens table
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(length=36), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('jti')
    )
    op.create_index(op.f('ix_revoked_tokens_expires_at'), 'revoked_tokens', ['expires_at'], unique=False)

    # user_id já existe na tabela videos (criada na migração 000); aqui
    # apenas adicionamos o índice e a FK para a tabela users.
    op.create_index(op.f('ix_videos_user_id'), 'videos', ['user_id'], unique=False)
    op.create_foreign_key('fk_videos_user_id_users', 'videos', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Drop FK and index from videos (a coluna user_id pertence à migração 000)
    op.drop_constraint('fk_videos_user_id_users', 'videos', type_='foreignkey')
    op.drop_index(op.f('ix_videos_user_id'), table_name='videos')

    # Drop revoked_tokens
    op.drop_index(op.f('ix_revoked_tokens_expires_at'), table_name='revoked_tokens')
    op.drop_table('revoked_tokens')

    # Drop users
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')