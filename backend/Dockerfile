FROM python:3.11-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

USER app

ENV PORT=8080
EXPOSE 8080

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
