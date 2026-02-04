# Lia Agent v2.0 - Dockerfile
# Multi-stage build para imagem otimizada

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.11-slim as builder

WORKDIR /app

# Instala dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia arquivos de dependências
COPY pyproject.toml ./

# Cria venv e instala dependências
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.11-slim as runtime

WORKDIR /app

# Cria usuário não-root
RUN useradd --create-home --shell /bin/bash appuser

# Copia venv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia código da aplicação
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser prompts/ ./prompts/
COPY --chown=appuser:appuser migrations/ ./migrations/

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    DEBUG=false \
    LOG_LEVEL=INFO

# Muda para usuário não-root
USER appuser

# Expõe porta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Comando de inicialização
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
