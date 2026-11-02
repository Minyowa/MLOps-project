# LinkGuard 서빙 이미지
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements-serve.txt .
RUN pip install -r requirements-serve.txt

COPY linkguard/ linkguard/
COPY app/ app/
COPY models/ models/

# 루트가 아닌 사용자로 실행, 로컬 로그 폴더만 쓰기 허용
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/logs && chown appuser /app/logs
USER appuser

# 어떤 커밋이 배포됐는지 /health와 화면에서 확인 (CI가 --build-arg로 넣음)
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} LOG_SINKS=local BRAND_REGION=jp

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
