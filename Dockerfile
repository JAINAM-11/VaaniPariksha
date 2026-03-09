# VaaniPariksha - Dockerfile for AWS Deployment (App Runner / ECS / Elastic Beanstalk)

# Use Python 3.10 slim image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=run.py

# Install system dependencies
# - tesseract-ocr: For PDF parsing/OCR
# - libgl1: For OpenCV (if needed)
# - espeak, libespeak-dev: For pyttsx3 (TTS)
# - libportaudio2: For sounddevice (STT)
# - ffmpeg: For audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    espeak \
    libespeak-dev \
    libportaudio2 \
    ffmpeg \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy project files
COPY . .

# Ensure upload/generated folders exist
RUN mkdir -p uploads generated_pdfs

# Expose port (App Runner defaults to 8080, but Flask normally uses 5000)
EXPOSE 5000

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "--workers", "2", "run:app"]
