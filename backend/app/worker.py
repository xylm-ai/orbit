from celery import Celery
from app.config import settings

celery_app = Celery(
    "orbit",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.classify",
        "app.tasks.preprocess",
        "app.tasks.extract",
        "app.tasks.normalize",
        "app.tasks.stage",
        "app.tasks.price_feed",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    beat_schedule={
        "fetch-prices-every-15-min": {
            "task": "app.tasks.price_feed.fetch_prices",
            "schedule": 900.0,  # 15 minutes in seconds
        },
    },
    timezone="UTC",
)
