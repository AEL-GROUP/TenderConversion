# syntax=docker/dockerfile:1
FROM python:3.12-slim

# --- System dependencies -----------------------------------------------------
# libreoffice-writer + libreoffice-core: headless .doc/.docx -> .pdf conversion
# fonts-dejavu-core / fonts-liberation: common substitute fonts so converted
#   PDFs render consistently even without the original Word fonts installed
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libreoffice-core \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python dependencies ------------------------------------------------------
# Installed as a separate layer so code changes below don't bust the pip cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ----------------------------------------------------------
COPY pdf_tender_pipeline.py .

# --- Runtime ---------------------------------------------------------------
# Default working folder inside the container; mounted from the host via
# docker-compose.yml. -i can be overridden at `docker compose run` time.
ENTRYPOINT ["python3", "pdf_tender_pipeline.py"]
CMD ["-i", "/data/my_tender_docs", "--dpi", "200", "-q", "80", "--max-mb", "50.0"]
