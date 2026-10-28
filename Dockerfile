# Steward server image for Docker setups (HA Container). Build the web UI first
# (cd frontend && npm run build); it lands in server/steward_server/static and is copied in with the package.
# The Home Assistant app uses app/Dockerfile instead.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 STEWARD_DATA_DIR=/data
WORKDIR /app
COPY server/pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    # The eBon parser's own metadata pulls in dev tools; its runtime needs only the packages above.
    && pip install --no-cache-dir --no-deps rewe-ebon-parser
COPY server/steward_server ./steward_server
EXPOSE 8095
VOLUME /data
CMD ["python", "-m", "steward_server.main"]
