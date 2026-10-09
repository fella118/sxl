FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config.toml .
COPY sogixel ./sogixel
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "sogixel", "serve"]
