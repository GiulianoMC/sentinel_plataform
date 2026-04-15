import uuid
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser 
from typing import Optional, List, Tuple # Precisamos de Tipos mais complexos

from .celery_app import celery
from .tasks import processar_novo_comentario

from app.database import SessionLocal
from app.models.VideoModel import Video

# Importações da API do Google
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Lemos a Chave de API que passámos no docker-compose
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
if not YOUTUBE_API_KEY:
    print("[COLETOR] AVISO: YOUTUBE_API_KEY não definida. O coletor real não pode funcionar.")

youtube_service = None
if YOUTUBE_API_KEY:
    youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY, cache_discovery=False)

def fetch_novos_comentarios_youtube(video_id: str, published_after: Optional[datetime]) -> Tuple[List[str], Optional[str]]:
    """
    Função REAL que busca comentários na API do YouTube
    para um video_id específico, com paginação.
    
    Retorna uma tupla: (lista_de_textos_dos_comentários, timestamp_do_comentário_mais_recente)
    """
    if not youtube_service:
        print("[COLETOR] Serviço do YouTube não inicializado. A saltar a busca.")
        return [], None

    print(f"--- [COLETOR] Buscando comentários REAIS para o vídeo: {video_id}... ---")
    
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
        print(f"--- [COLETOR] A verificar comentários mais recentes que: {published_after.isoformat()} ---")

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
                    
                    if comment_published_at_dt <= published_after:
                        stop_processing = True 
                        break 
                
                texto_original = comment_snippet['textOriginal']
                comentarios_encontrados.append(texto_original)

            if stop_processing:
                print(f"--- [COLETOR] Encontrado comentário já processado. A parar a busca para {video_id}. ---")
                break
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break 
                
            print(f"--- [COLETOR] A buscar próxima página de comentários para {video_id}... ---")

    except HttpError as e:
        if e.resp.status == 403:
            print(f"--- [COLETOR] ERRO: Comentários estão desativados para o vídeo {video_id}. (Erro: {e}) ---")
        else:
            print(f"--- [COLETOR] ERRO na API do YouTube: {e} ---")
        return [], None

    return comentarios_encontrados, newest_timestamp_str


@celery.task(name='app.celery.collector_tasks.coletar_comentarios_youtube')
def coletar_comentarios_youtube():
    """
    Esta é a tarefa agendada pelo Celery Beat.
    Lê o PostgreSQL e chama a API real.
    """
    print(f"--- [COLETOR] Tarefa agendada iniciada: A buscar vídeos no PostgreSQL... ---")
    
    db = SessionLocal()
    try:
        videos_para_verificar = db.query(Video).all()
        
        if not videos_para_verificar:
            print(f"--- [COLETOR] Nenhum vídeo registado no banco de dados. A saltar... ---")
            return "Nenhum vídeo registado."

        print(f"--- [COLETOR] Encontrados {len(videos_para_verificar)} vídeos para verificar... ---")

        total_comentarios_enviados = 0
        
        for video in videos_para_verificar:
            print(f"--- [COLETOR] A verificar o vídeo: {video.youtube_id} (Título: {video.titulo}) ---")
            
            ultimo_visto = video.ultimo_comentario_verificado_em
            
            comentarios, newest_timestamp_str = fetch_novos_comentarios_youtube(video.youtube_id, ultimo_visto)
            
            if not comentarios:
                print(f"--- [COLETOR] Nenhum comentário novo para o vídeo {video.youtube_id}. ---")
                continue

            print(f"--- [COLETOR] Encontrados {len(comentarios)} novos comentários para {video.youtube_id}. A enviá-los para a fila... ---")

            for texto in comentarios:
                comment_id = str(uuid.uuid4())
                processar_novo_comentario.delay(comment_id, texto, video.youtube_id)
                total_comentarios_enviados += 1
                
            if newest_timestamp_str:
                video.ultimo_comentario_verificado_em = parser.isoparse(newest_timestamp_str)
                db.commit()
            
        return f"Foram enviadas {total_comentarios_enviados} tarefas para a fila."

    except Exception as e:
        print(f"[COLETOR] ERRO ao coletar comentários: {e}")
        db.rollback() 
        return "Falha na coleta."
    finally:
        db.close()

