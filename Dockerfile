# Serve the catalog importer web tool.
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY importer/ ./importer/
COPY web/ ./web/
COPY samples/ ./samples/

EXPOSE 8090
CMD ["gunicorn", "-b", "0.0.0.0:8090", "-w", "2", "web.app:app"]
