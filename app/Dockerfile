# Home Assistant app image. dev/scripts/build_app.sh stages the server (with the built web UI)
# next to this file; the Supervisor then builds it on the device.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 STEWARD_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    # The eBon parser's own metadata pulls in dev tools; its runtime needs only the packages above.
    && pip install --no-cache-dir --no-deps rewe-ebon-parser
COPY steward_server ./steward_server
LABEL io.hass.type="app" io.hass.name="Steward" io.hass.version="0.1.0"
CMD ["python", "-m", "steward_server.main"]
