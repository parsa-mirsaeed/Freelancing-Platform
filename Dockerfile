FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app

COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--threads=4", "--access-logfile=-", "--error-logfile=-", "app:create_app()"]
