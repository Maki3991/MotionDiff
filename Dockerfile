# PocketBay / container runtime entry
# stdlib HTTP server (app.py) + MediaPipe; health endpoint: /healthz
FROM python:3.11-slim

# opencv + mediapipe need system GL/EGL/GLES at runtime even on CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libegl1 libgles2 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MOTIONDIFF_HOST=0.0.0.0
EXPOSE 8765
CMD ["sh", "-c", "python app.py --host 0.0.0.0 --port ${PORT:-8765}"]
