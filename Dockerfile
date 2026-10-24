FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py database.py simulation_engine.py launcher.py ./
COPY templates ./templates

EXPOSE 8090

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8090}"]
