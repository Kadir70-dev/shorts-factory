FROM python:3.12-slim

# system deps: ffmpeg (render/post), build tools + whisper.cpp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git build-essential cmake curl \
 && rm -rf /var/lib/apt/lists/*

# whisper.cpp + base.en model (captions)
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp /opt/whisper.cpp \
 && cd /opt/whisper.cpp && make -j \
 && bash ./models/download-ggml-model.sh base.en

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
# default cmd runs the API; the worker service overrides command in compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
