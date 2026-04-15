from celery import Celery
from celery.schedules import crontab

BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'

celery = Celery(
    'app',
    broker=BROKER_URL,
    backend='rpc://',
    # Incluimos todos os modulos de tasks
    include=['app.celery.tasks', 'app.celery.collector_tasks', 'app.celery.ai_tasks']
)

celery.conf.beat_schedule = {
    'coletar-comentarios-a-cada-5-minutos': {
        'task': 'app.celery.collector_tasks.coletar_comentarios_youtube',
        'schedule': 60.0,
    },
}
