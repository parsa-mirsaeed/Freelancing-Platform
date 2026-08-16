from app import create_app
from app.celery import create_celery_app

flask_app = create_app()
celery_app = create_celery_app(flask_app)
