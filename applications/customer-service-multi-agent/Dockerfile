FROM ghcr.io/astral-sh/uv:0.9.30 AS uv
FROM python:3.11.14-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --python /usr/local/bin/python3 --system --no-cache -r requirements.txt
COPY app.py auth.py chat.py native.py provision_agents.py scenarios.py settings.py simulation.py simulation_schema.py evaluation.py telemetry.py ./
COPY hosted/validation.py ./hosted/validation.py
COPY static ./static
USER 10001:10001
EXPOSE 8080
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["/usr/local/bin/python3", "-m", "uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--log-level", "critical"]
