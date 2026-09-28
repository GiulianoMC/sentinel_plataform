from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.dependencies import require_admin, get_search_service
from app.models.UserModel import User, RevokedToken
from app.models.VideoModel import Video, Comment
from app.schemas.AuthSchema import UserResponse
from app.services.SemanticSearchService import SemanticSearchService

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    size: int

class UserRoleUpdate(BaseModel):
    role: str

class UserStatusUpdate(BaseModel):
    is_active: bool


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(20, ge=1, le=100, description="Itens por página"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    """
    Lista todos os usuários (paginado).
    """
    query = db.query(User)
    total = query.count()
    users = query.offset((page - 1) * size).limit(size).all()
    
    return UserListResponse(
        users=users,
        total=total,
        page=page,
        size=size
    )


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    """
    Altera a role do usuário (user ↔ admin).
    """
    if role_update.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Role deve ser 'user' ou 'admin'")
    
    # Admin não pode alterar a própria role
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Não é possível alterar a própria role")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Prevent demoting the last admin
    if user.role == "admin" and role_update.role == "user":
        admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Não é possível remover o último administrador ativo")
    
    user.role = role_update.role
    db.commit()
    db.refresh(user)
    
    return user


@router.patch("/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    status_update: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    """
    Ativa ou desativa um usuário.
    """
    # Admin não pode desativar a si mesmo
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Não é possível alterar o próprio status")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Prevent deactivating the last admin
    if user.role == "admin" and not status_update.is_active:
        active_admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Não é possível desativar o último administrador ativo")
    
    user.is_active = status_update.is_active
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
    search_service: SemanticSearchService = Depends(get_search_service)
):
    """
    Deleta um usuário (cascade → videos + comments + ChromaDB embeddings).
    """
    # Admin não pode deletar a si mesmo
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Não é possível deletar a si mesmo")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Prevent deleting the last admin
    if user.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Não é possível deletar o último administrador ativo")
    
    # Get user's video IDs before cascade delete
    video_ids = db.query(Video.youtube_id).filter(Video.user_id == user_id).all()
    video_ids = [v[0] for v in video_ids]

    # Delete comments explicitly before videos: the FK comments.youtube_id ->
    # videos.youtube_id has no ON DELETE CASCADE, so the ORM cascade
    # (User.videos) alone would fail with an IntegrityError.
    if video_ids:
        db.query(Comment).filter(Comment.youtube_id.in_(video_ids)).delete(synchronize_session=False)

    # Delete user (cascade deletes videos in PostgreSQL)
    db.delete(user)
    db.commit()
    
    # Clean up ChromaDB embeddings for user's videos
    if video_ids:
        try:
            collection = search_service.get_collection("comentarios_produtos")
            for vid in video_ids:
                collection.delete(where={"video_id": vid})
            print(f"[ADMIN] Cleaned up ChromaDB embeddings for {len(video_ids)} videos of deleted user {user_id}")
        except Exception as e:
            print(f"[ADMIN] Warning: Failed to clean ChromaDB for user {user_id}: {e}")
    
    return None