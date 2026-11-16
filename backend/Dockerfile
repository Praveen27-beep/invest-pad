FROM python:3.13-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir .
# --no-access-log: uvicorn's access log prints full URLs including query strings.
# The app writes its own one-line request log without them.
CMD ["sh", "-c", "python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
