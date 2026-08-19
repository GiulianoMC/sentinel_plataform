"""make video user_id not null

Revision ID: 002
Revises: 001
Create Date: 2026-08-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Garante que existe pelo menos um admin para o backfill
    admin = bind.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
    ).fetchone()
    if admin is None:
        import os
        from app.core.security import hash_password
        email = os.environ.get("ADMIN_EMAIL", "admin@sentinela.local")
        password = os.environ.get("ADMIN_PASSWORD", "changeme123")
        result = bind.execute(
            sa.text(
                "INSERT INTO users (email, hashed_password, role, is_active) "
                "VALUES (:email, :password, 'admin', true) RETURNING id"
            ).bindparams(email=email, password=hash_password(password))
        )
        admin = result.fetchone()
        print(f"Admin criado para backfill de videos: {email}")

    # Atribui videos sem dono ao primeiro admin
    op.execute(
        sa.text(
            "UPDATE videos SET user_id = :admin_id WHERE user_id IS NULL"
        ).bindparams(admin_id=admin[0])
    )

    # Agora torna user_id NOT NULL
    op.alter_column('videos', 'user_id', nullable=False)

    # NOTA: nao se adiciona unique composto (user_id, youtube_id) porque o ORM
    # define youtube_id como globalmente unico (unique=True) e a FK
    # comments.youtube_id -> videos.youtube_id depende dessa unicidade.


def downgrade() -> None:
    # Tornar user_id nullable novamente
    op.alter_column('videos', 'user_id', nullable=True)