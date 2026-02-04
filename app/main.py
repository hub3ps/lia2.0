"""
Lia Agent v2.0 - Aplicação FastAPI Principal

Este é o ponto de entrada da aplicação.
"""
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.exceptions import LiaError

# Configura logging estruturado
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    logger.info(
        "app_starting",
        environment=settings.environment,
        debug=settings.debug,
        tenant=settings.default_tenant,
    )
    
    # Testa conexão com Supabase
    try:
        from app.db import db
        tenant = await db.get_tenant_by_slug(settings.default_tenant)
        if tenant:
            logger.info("tenant_loaded", tenant=tenant["name"])
        else:
            logger.warning("tenant_not_found", slug=settings.default_tenant)
    except Exception as e:
        logger.error("supabase_connection_error", error=str(e))
    
    yield
    
    # Shutdown
    logger.info("app_shutting_down")


# Cria aplicação
app = FastAPI(
    title="Lia Agent",
    description="AI Delivery Agent for WhatsApp",
    version="2.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Exception Handlers
# ==========================================

@app.exception_handler(LiaError)
async def lia_error_handler(request: Request, exc: LiaError) -> JSONResponse:
    """Handler para exceções do sistema."""
    logger.warning(
        "lia_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler para exceções não tratadas."""
    logger.exception(
        "unhandled_error",
        error=str(exc),
        path=request.url.path,
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "Erro interno do servidor",
        },
    )


# ==========================================
# Rotas Básicas
# ==========================================

@app.get("/")
async def root() -> dict[str, str]:
    """Rota raiz."""
    return {
        "app": "Lia Agent",
        "version": "2.0.0",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check básico."""
    return {
        "status": "healthy",
        "environment": settings.environment,
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness check - verifica dependências.
    
    Usado pelo Kubernetes/Docker para saber se a aplicação
    está pronta para receber requisições.
    """
    checks: dict[str, Any] = {
        "status": "ready",
        "checks": {},
    }
    
    # Check Supabase
    try:
        from app.db import db
        await db.get_tenant_by_slug(settings.default_tenant)
        checks["checks"]["database"] = "ok"
    except Exception as e:
        checks["status"] = "not_ready"
        checks["checks"]["database"] = f"error: {str(e)[:100]}"
    
    # Check OpenAI (só verifica se a key existe)
    checks["checks"]["openai"] = "ok" if settings.openai_api_key else "missing_key"
    
    # Check Evolution (só verifica configuração)
    checks["checks"]["evolution"] = "ok" if settings.evolution_base_url else "not_configured"
    
    status_code = 200 if checks["status"] == "ready" else 503
    return JSONResponse(content=checks, status_code=status_code)


# ==========================================
# Importa rotas dos módulos
# ==========================================

# TODO: Descomentar quando implementados
# from app.api.webhooks import router as webhooks_router
# from app.api.admin import router as admin_router
# 
# app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
# app.include_router(admin_router, prefix="/admin", tags=["admin"])


# ==========================================
# Rota temporária para teste de FSM
# ==========================================

@app.get("/debug/fsm")
async def debug_fsm() -> dict[str, Any]:
    """Debug: mostra estrutura da FSM."""
    if not settings.debug:
        return {"error": "Debug disabled"}
    
    from app.core.fsm import STATE_MACHINE, ConversationState
    
    states = {}
    for state, req in STATE_MACHINE.items():
        states[state.value] = {
            "allowed_transitions": [s.value for s in req.allowed_transitions],
            "required_fields": req.required_fields,
            "can_receive_items": req.can_receive_items,
            "is_terminal": req.is_terminal,
            "hint": req.agent_hint[:50] + "..." if len(req.agent_hint) > 50 else req.agent_hint,
        }
    
    return {"states": states}


@app.get("/debug/guardrails")
async def debug_guardrails(text: str = "sim") -> dict[str, Any]:
    """Debug: testa classificação de input."""
    if not settings.debug:
        return {"error": "Debug disabled"}
    
    from app.core.guardrails import guardrails
    
    intent, data = guardrails.classify(text)
    
    return {
        "input": text,
        "intent": intent.value,
        "extracted_data": data,
        "needs_llm": intent.value == "needs_llm",
    }


# ==========================================
# Entry point para desenvolvimento
# ==========================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
