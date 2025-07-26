FROM python:3.12-slim

ENV DATADOG_SITE=datadoghq.eu

WORKDIR /app

COPY src/ ./
COPY requirements.txt ./
COPY entrypoint.sh ./

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["./entrypoint.sh"]
