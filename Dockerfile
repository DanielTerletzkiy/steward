# Steward server image. Build the web UI first (cd frontend && npm run build); it lands in
# server/steward_server/static and is copied in with the package.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 STEWARD_DATA_DIR=/data
WORKDIR /app
COPY server/pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.32" "sqlalchemy[asyncio]>=2.0" "aiosqlite>=0.20" \
        "pydantic>=2.9" "python-multipart>=0.0.12" "pdfplumber>=0.11" "rapidfuzz>=3.10" pytz tqdm \
    # The eBon parser's own metadata pulls in dev tools; its runtime needs only the packages above.
    && pip install --no-cache-dir --no-deps rewe-ebon-parser
COPY server/steward_server ./steward_server
EXPOSE 8095
VOLUME /data
CMD ["python", "-m", "steward_server.main"]
