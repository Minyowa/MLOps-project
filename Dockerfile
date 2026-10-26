FROM python:3.13-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" scikit-learn==1.9.1 joblib boto3

COPY linkguard/ linkguard/
COPY app/ app/
COPY models/ models/

ENV LOG_SINKS=local
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
