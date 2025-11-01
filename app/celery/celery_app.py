from celery import Celery

BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'

# Inicializa a aplicação Celery
celery = Celery(
    'app.celery',
    broker=BROKER_URL,
    backend='rpc://',
    include=['app.celery.tasks'] 
)
