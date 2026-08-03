FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir . \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
