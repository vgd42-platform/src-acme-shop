# The vendor owns this file. The platform build runs it unchanged.
FROM python:3.12-slim

# --- Version and commit come from the platform build (shown on the page) ---
ARG VERSION=0.0.0
ARG COMMIT=local
ENV APP_VERSION=$VERSION APP_COMMIT=$COMMIT PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# --- Dependencies first (cached layer), then the app ---
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .

# --- Run as a non-root user (platform policy) ---
USER 10001
EXPOSE 8080
CMD ["python", "main.py"]
