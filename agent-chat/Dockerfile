FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r server/requirements.txt \
    && adduser --disabled-password --no-create-home appuser

USER appuser

ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD exec gunicorn --bind :$PORT --workers 2 --timeout 30 server.app:app
