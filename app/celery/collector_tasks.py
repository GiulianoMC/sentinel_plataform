import uuid
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser 
from typing import Optional 

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

def fetch_novos_comentarios_youtube(video_id: str, published_after: Optional[datetime]) -> list[str]:
    """
    Função REAL que busca comentários na API do YouTube
    para um video_id específico, com paginação.
    """
    if not youtube_service:
        print("[COLETOR] Serviço do YouTube não inicializado. A saltar a busca.")
        return []

    print(f"--- [COLETOR] Buscando comentários REAIS para o vídeo: {video_id}... ---")
    
    comentarios_encontrados = []
    next_page_token = None
    
    # Parâmetros da API
    params = {
        'part': 'snippet',
        'videoId': video_id,
        'textFormat': 'plainText',
        'maxResults': 100 
    }

    if published_after:
        published_after_safe = published_after + timedelta(seconds=1)
        params['publishedAfter'] = published_after_safe.isoformat()
        print(f"--- [COLETOR] A buscar comentários apenas após: {published_after_safe.isoformat()} ---")

    try:
        while True:
            if next_page_token:
                params['pageToken'] = next_page_token
            
            response = youtube_service.commentThreads().list(**params).execute()

            for item in response.get('items', []):
                comment = item['snippet']['topLevelComment']['snippet']
                texto_original = comment['textOriginal']
                comentarios_encontrados.append(texto_original)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break 
                
            print(f"--- [COLETOR] A buscar próxima página de comentários para {video_id}... ---")

    except HttpError as e:
        if e.resp.status == 403:
            print(f"--- [COLETOR] ERRO: Comentários estão desativados para o vídeo {video_id}. (Erro: {e}) ---")
        else:
            print(f"--- [COLETOR] ERRO na API do YouTube: {e} ---")
        return [] 

    return comentarios_encontrados


@celery.task(name='app.celery.collector_tasks.coletar_comentarios_youtube')
def coletar_comentarios_youtube():
    """
    Esta é a tarefa agendada pelo Celery Beat.
    Agora, ela lê a tabela 'videos' do PostgreSQL e chama a API real.
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
            
            comentarios = fetch_novos_comentarios_youtube(video.youtube_id, ultimo_visto)
            
            if not comentarios:
                print(f"--- [COLETOR] Nenhum comentário novo para o vídeo {video.youtube_id}. ---")
                continue

            print(f"--- [COLETOR] Encontrados {len(comentarios)} novos comentários para {video.youtube_id}. A enviá-los para a fila... ---")

            for texto in comentarios:
                comment_id = str(uuid.uuid4())
                processar_novo_comentario.delay(comment_id, texto)
                total_comentarios_enviados += 1
                
            video.ultimo_comentario_verificado_em = datetime.now(timezone.utc)
            db.commit()
            
        return f"Foram enviadas {total_comentarios_enviados} tarefas para a fila."

    except Exception as e:
        print(f"[COLETOR] ERRO ao coletar comentários: {e}")
        db.rollback() 
        return "Falha na coleta."
    finally:
        db.close()