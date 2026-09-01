import celery 
from celery.schedules import crontab
from src.config import settings

app = celery.Celery(
    "tasks_broker", 
    broker=settings.celery_tasks_broker_url, 
    backend=settings.celery_tasks_backend_url,
)

# ! run
# celery -A src.celery_tasks.broker worker --loglevel=info -P gevent
# ! run
# celery -A src.celery_tasks.broker beat --loglevel=info
# ! run


# set broker config
app.conf.beat_schedule = {
    'remove_inactive_users': {
        'task': 'src.celery_tasks.delete_inactive_users',
        'schedule': (settings.celery_tasks
                    .delete_inactive_users_periodic_task_interval
                    .total_seconds()),
    },
}
app.conf.timezone = 'UTC'
