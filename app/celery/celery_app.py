from celery import Celery
from kombu import Queue

BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'

celery = Celery(
    'app',
    broker=BROKER_URL,
    backend='rpc://',
    include=['app.celery.tasks', 'app.celery.collector_tasks', 'app.celery.ai_tasks']
)

# Duas filas: ingestion (embedding + postgres) e ai (chamadas Groq)
celery.conf.task_queues = (
    Queue('ingestion'),
    Queue('ai'),
)
celery.conf.task_default_queue = 'ingestion'

celery.conf.task_routes = {
    'app.celery.tasks.processar_novo_comentario':              {'queue': 'ingestion'},
    'app.celery.collector_tasks.coletar_comentarios_youtube':  {'queue': 'ingestion'},
    'app.celery.ai_tasks.process_comments_with_ai':            {'queue': 'ai'},
}

celery.conf.beat_schedule = {
    'coletar-comentarios-a-cada-5-minutos': {
        'task': 'app.celery.collector_tasks.coletar_comentarios_youtube',
        'schedule': 60.0,
    },
}
