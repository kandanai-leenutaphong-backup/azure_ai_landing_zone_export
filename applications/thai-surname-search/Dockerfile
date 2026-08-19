FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8501

CMD ["sh", "-c", "python azure_setup.py --target all && streamlit run app.py --server.address=0.0.0.0 --server.port=8501"]
