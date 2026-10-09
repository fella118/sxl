FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --uid 1000 --create-home sogixel \
 && mkdir -p /app/data /app/out && chown sogixel /app/data /app/out
COPY config.toml .
COPY sogixel ./sogixel
USER sogixel
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)"
CMD ["python", "-m", "sogixel", "serve"]
