# Build context: applications/customer-service-multi-agent, not repository root.
FROM ghcr.io/astral-sh/uv:0.9.30 AS uv
FROM python:3.11-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY hosted/requirements.txt /app/hosted/requirements.txt
RUN uv pip install --python /usr/local/bin/python --system --no-cache -r /app/hosted/requirements.txt
COPY scenarios.py telemetry.py /app/
COPY hosted/runtime.py hosted/main.py hosted/validation.py /app/hosted/
ENV PYTHONUNBUFFERED=1
EXPOSE 8088
USER 10001
CMD ["python", "-m", "hosted.main"]
