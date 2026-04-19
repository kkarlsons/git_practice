# Backend image: Java 21 (r5py) + Python 3.12 + FastAPI.
FROM eclipse-temurin:21-jdk-noble

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    RIGA_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

COPY backend backend

EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
