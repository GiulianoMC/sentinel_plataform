import uuid
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser
from typing import Optional, List, Tuple, Dict, Any

from .celery_app import celery
from .tasks import processar_novo_comentario

from app.database import SessionLocal
from app.models.VideoModel import Video
from app.models.UserModel import User

# Importacoes da API do Google
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Lemos a Chave de API que passamos no docker-compose
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
if not YOUTUBE_API_KEY:
    print("[COLETOR] AVISO: YOUTUBE_API_KEY nao definida. O coletor real nao pode funcionar.")

youtube_service = None
if YOUTUBE_API_KEY:
    youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY, cache_discovery=False)


def fetch_novos_comentarios_youtube(video_id: str, published_after: Optional[datetime]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Funcao REAL que busca comentarios na API do YouTube
    para um video_id especifico, com paginacao.

    Retorna uma tupla: (lista_de_comentarios_com_metadados, timestamp_do_comentario_mais_recente)
    Cada comentario e um dict com: text, author, published_at
    """
    if not youtube_service:
        print("[COLETOR] Servico do YouTube nao inicializado. A saltar a busca.")
        return [], None

    print(f"--- [COLETOR] Buscando comentarios REAIS para o video: {video_id}... ---")

    comentarios_encontrados = []
    next_page_token = None

    newest_timestamp_str: Optional[str] = None

    params = {
        'part': 'snippet',
        'videoId': video_id,
        'textFormat': 'plainText',
        'maxResults': 100,
        'order': 'time'
    }

    if published_after:
        print(f"--- [COLETOR] A verificar comentarios mais recentes que: {published_after.isoformat()} ---")

    try:
        while True:
            if next_page_token:
                params['pageToken'] = next_page_token

            response = youtube_service.commentThreads().list(**params).execute()

            stop_processing = False

            for item in response.get('items', []):
                comment_snippet = item['snippet']['topLevelComment']['snippet']

                comment_published_at_str = comment_snippet['publishedAt']

                if newest_timestamp_str is None:
                    newest_timestamp_str = comment_published_at_str

                if published_after:
                    comment_published_at_dt = parser.isoparse(comment_published_at_str)

                    # Normaliza para UTC se nao tiver timezone
                    if comment_published_at_dt.tzinfo is None:
                        comment_published_at_dt = comment_published_at_dt.replace(tzinfo=timezone.utc)

                    # Garante que published_after tambem tem timezone
                    ultimo_visto_dt = published_after
                    if ultimo_visto_dt.tzinfo is None:
                        ultimo_visto_dt = ultimo_visto_dt.replace(tzinfo=timezone.utc)

                    if comment_published_at_dt <= ultimo_visto_dt:
                        stop_processing = True
                        break

                # Extrai todos os metadados necessarios
                comentario = {
                    'text': comment_snippet['textOriginal'],
                    'author': comment_snippet.get('authorDisplayName', 'Desconhecido'),
                    'published_at': comment_published_at_str
                }
                comentarios_encontrados.append(comentario)

            if stop_processing:
                print(f"--- [COLETOR] Encontrado comentario ja processado. A parar a busca para {video_id}. ---")
                break

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

            print(f"--- [COLETOR] A buscar proxima pagina de comentarios para {video_id}... ---")

    except HttpError as e:
        if e.resp.status == 403:
            print(f"--- [COLETOR] ERRO: Comentarios estao desativados para o video {video_id}. (Erro: {e}) ---")
        else:
            print(f"--- [COLETOR] ERRO na API do YouTube: {e} ---")
        return [], None

    return comentarios_encontrados, newest_timestamp_str


@celery.task(name='app.celery.collector_tasks.coletar_comentarios_youtube')
def coletar_comentarios_youtube():
    """
    Esta e a tarefa agendada pelo Celery Beat.
    Le o PostgreSQL e chama a API real para cada usuario ativo.
    """
    print(f"--- [COLETOR] Tarefa agendada iniciada: A buscar utilizadores ativos... ---")

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()

        if not users:
            print(f"--- [COLETOR] Nenhum utilizador ativo encontrado. A saltar... ---")
            return "Nenhum utilizador ativo."

        total_comentarios_enviados = 0

        for user in users:
            print(f"--- [COLETOR] Processando utilizador: {user.email} (ID: {user.id}) ---")
            
            videos_para_verificar = db.query(Video).filter(Video.user_id == user.id).all()

            if not videos_para_verificar:
                print(f"--- [COLETOR] Nenhum video registado para o utilizador {user.email}. ---")
                continue

            print(f"--- [COLETOR] Encontrados {len(videos_para_verificar)} videos para o utilizador {user.email} ---")

            for video in videos_para_verificar:
                print(f"--- [COLETOR] User {user.email} - A verificar o video: {video.youtube_id} (Titulo: {video.titulo}) ---")

                ultimo_visto = video.ultimo_comentario_verificado_em

                try:
                    comentarios, newest_timestamp_str = fetch_novos_comentarios_youtube(video.youtube_id, ultimo_visto)
                except Exception as e:
                    print(f"[COLETOR] ERRO ao buscar comentarios para video {video.youtube_id}: {e}")
                    continue

                if not comentarios:
                    print(f"--- [COLETOR] Nenhum comentario novo para o video {video.youtube_id}. ---")
                    continue

                print(f"--- [COLETOR] Encontrados {len(comentarios)} novos comentarios para {video.youtube_id}. A envia-los para a fila... ---")

                for comentario in comentarios:
                    comment_id = str(uuid.uuid4())
                    # Agora passamos todos os metadados necessarios
                    processar_novo_comentario.delay(
                        comment_id=comment_id,
                        comment_text=comentario['text'],
                        video_id=video.youtube_id,
                        author=comentario['author'],
                        published_at=comentario['published_at']
                    )
                    total_comentarios_enviados += 1

                if newest_timestamp_str:
                    video.ultimo_comentario_verificado_em = parser.isoparse(newest_timestamp_str)

            # Commit once per user after all their videos processed
            db.commit()

        return f"Foram enviadas {total_comentarios_enviados} tarefas para a fila."

    except Exception as e:
        print(f"[COLETOR] ERRO ao coletar comentarios: {e}")
        db.rollback()
        return "Falha na coleta."
    finally:
        db.close()


@celery.task(name='app.celery.collector_tasks.coletar_comentarios_video_especifico')
def coletar_comentarios_video_especifico(video_id: str, user_id: int):
    """
    Coleta comentarios para um video especifico (usado apos registro de novo video).
    """
    print(f"--- [COLETOR] Coleta imediata para video especifico: {video_id} ---")

    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.youtube_id == video_id, Video.user_id == user_id).first()
        if not video:
            print(f"[COLETOR] Video {video_id} nao encontrado para user {user_id}")
            return "Video nao encontrado"

        ultimo_visto = video.ultimo_comentario_verificado_em

        try:
            comentarios, newest_timestamp_str = fetch_novos_comentarios_youtube(video.youtube_id, ultimo_visto)
        except Exception as e:
            print(f"[COLETOR] ERRO ao buscar comentarios para video {video.youtube_id}: {e}")
            return "Falha na coleta"

        if not comentarios:
            print(f"--- [COLETOR] Nenhum comentario novo para o video {video.youtube_id}. ---")
            return "Nenhum comentario novo"

        print(f"--- [COLETOR] Encontrados {len(comentarios)} novos comentarios para {video.youtube_id}. A envia-los para a fila... ---")

        for comentario in comentarios:
            comment_id = str(uuid.uuid4())
            processar_novo_comentario.delay(
                comment_id=comment_id,
                comment_text=comentario['text'],
                video_id=video.youtube_id,
                author=comentario['author'],
                published_at=comentario['published_at']
            )

        if newest_timestamp_str:
            video.ultimo_comentario_verificado_em = parser.isoparse(newest_timestamp_str)
            db.commit()

        return f"Enviadas {len(comentarios)} tarefas para a fila."

    except Exception as e:
        print(f"[COLETOR] ERRO ao coletar comentarios: {e}")
        db.rollback()
        return "Falha na coleta."
    finally:
        db.close()
