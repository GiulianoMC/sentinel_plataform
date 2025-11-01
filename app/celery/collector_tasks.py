import uuid
from .celery_app import celery
from .tasks import processar_novo_comentario

def fetch_novos_comentarios_youtube() -> list[str]:
    """
    Função mockada que simula uma busca na API do YouTube
    e retorna uma lista de novos comentários.
    """
    print("--- [COLETOR] A simular busca na API do YouTube... ---")
    novos_comentarios = [
        "Este comentário acabou de chegar da API do YouTube!",
        "Que vídeo incrível, parabéns pelo conteúdo!"
    ]
    return novos_comentarios


@celery.task(name='app.celery.collector_tasks.coletar_comentarios_youtube')
def coletar_comentarios_youtube():
    """
    Esta é a tarefa agendada pelo Celery Beat.
    Sua única função é buscar dados (do YouTube) e 
    disparar tarefas de processamento.
    """
    print(f"--- [COLETOR] Tarefa agendada iniciada: A buscar novos comentários... ---")
    
    try:
        comentarios = fetch_novos_comentarios_youtube()
        
        if not comentarios:
            print(f"--- [COLETOR] Nenhum comentário novo encontrado. ---")
            return "Nenhum comentário novo."

        print(f"--- [COLETOR] Encontrados {len(comentarios)} novos comentários. A enviá-los para a fila... ---")

        for texto in comentarios:
            comment_id = str(uuid.uuid4())
            processar_novo_comentario.delay(comment_id, texto)
            
        return f"Foram enviadas {len(comentarios)} tarefas para a fila."

    except Exception as e:
        print(f"[COLETOR] ERRO ao coletar comentários: {e}")
        return "Falha na coleta."