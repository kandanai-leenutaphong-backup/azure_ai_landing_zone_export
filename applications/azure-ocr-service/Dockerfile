FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ocr_functions.py .
COPY app.py .

EXPOSE 8501

# Streamlit config: disable telemetry, bind to all interfaces
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

ENTRYPOINT ["streamlit", "run", "app.py", "--server.headless=true"]
