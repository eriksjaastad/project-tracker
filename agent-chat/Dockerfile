FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r server/requirements.txt

ENV PORT=8080

CMD exec gunicorn --bind :$PORT --workers 2 --timeout 30 server.app:app
