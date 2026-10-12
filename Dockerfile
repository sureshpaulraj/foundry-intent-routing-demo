FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py index.html synthetic_examples.json smoke.py ./
RUN useradd -r -u 10001 demo && chown -R demo:demo /app
USER demo
EXPOSE 8000
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=90", "app:app"]
