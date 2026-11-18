# Image de Yilgré (API et interfaces web) (même démarrage que scripts/run.sh, sans venv).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHON_BIN=python HTTPS_PORT=8443
EXPOSE 8443 8000
CMD ["./scripts/start.sh"]
