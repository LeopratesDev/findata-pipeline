# Imagem unica para API e dashboard: o comando muda por servico no compose.
# Mantem uma so cadeia de build/dependencias (brief: Dockerfile separado so se
# simplificar - aqui uma imagem comum simplifica).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

# Usuario nao-root
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Dependencias primeiro (cache de camada)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Codigo e tema do dashboard
COPY src ./src
COPY .streamlit ./.streamlit

# Diretorios persistentes (montados como volumes no compose)
RUN mkdir -p /data /reports && chown -R appuser:appuser /app /data /reports

USER appuser

EXPOSE 8000 8501

# Padrao = API. O servico 'dashboard' sobrescreve o comando no compose.
# Uvicorn trata SIGTERM corretamente (encerramento gracioso).
CMD ["uvicorn", "findata_pipeline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
