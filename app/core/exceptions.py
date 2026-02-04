"""
Exceções customizadas do sistema Lia Agent.

Hierarquia:
- LiaError (base)
  - ValidationError (dados inválidos)
  - FSMError (erro de transição)
  - IntegrationError (erro de integração externa)
    - EvolutionError
    - SaiposError
    - OpenAIError
    - GoogleMapsError
  - CartError (erro no carrinho)
  - OrderError (erro no pedido)
"""
from typing import Any


class LiaError(Exception):
    """Exceção base do sistema."""
    
    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code or "LIA_ERROR"
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ==========================================
# Erros de Validação
# ==========================================

class ValidationError(LiaError):
    """Erro de validação de dados."""
    
    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Trunca valores longos
        
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details,
        )
        self.field = field
        self.value = value


class SchemaValidationError(ValidationError):
    """Erro de validação de schema Pydantic."""
    
    def __init__(self, message: str, errors: list[dict[str, Any]]):
        super().__init__(message=message)
        self.code = "SCHEMA_VALIDATION_ERROR"
        self.details["errors"] = errors


# ==========================================
# Erros de FSM
# ==========================================

class FSMError(LiaError):
    """Erro relacionado à máquina de estados."""
    
    def __init__(
        self,
        message: str,
        from_state: str | None = None,
        to_state: str | None = None,
    ):
        details = {}
        if from_state:
            details["from_state"] = from_state
        if to_state:
            details["to_state"] = to_state
        
        super().__init__(
            message=message,
            code="FSM_ERROR",
            details=details,
        )


class InvalidTransitionError(FSMError):
    """Transição de estado não permitida."""
    
    def __init__(
        self,
        from_state: str,
        to_state: str,
        allowed: list[str] | None = None,
    ):
        message = f"Transição inválida de {from_state} para {to_state}"
        super().__init__(
            message=message,
            from_state=from_state,
            to_state=to_state,
        )
        self.code = "INVALID_TRANSITION"
        if allowed:
            self.details["allowed_transitions"] = allowed


# ==========================================
# Erros de Integração
# ==========================================

class IntegrationError(LiaError):
    """Erro de integração com serviço externo."""
    
    def __init__(
        self,
        message: str,
        service: str,
        status_code: int | None = None,
        response: Any = None,
    ):
        details = {"service": service}
        if status_code:
            details["status_code"] = status_code
        if response:
            details["response"] = str(response)[:500]
        
        super().__init__(
            message=message,
            code="INTEGRATION_ERROR",
            details=details,
        )
        self.service = service
        self.status_code = status_code


class EvolutionError(IntegrationError):
    """Erro da Evolution API (WhatsApp)."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: Any = None,
    ):
        super().__init__(
            message=message,
            service="evolution",
            status_code=status_code,
            response=response,
        )
        self.code = "EVOLUTION_ERROR"


class SaiposError(IntegrationError):
    """Erro da API Saipos."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: Any = None,
    ):
        super().__init__(
            message=message,
            service="saipos",
            status_code=status_code,
            response=response,
        )
        self.code = "SAIPOS_ERROR"


class OpenAIError(IntegrationError):
    """Erro da API OpenAI."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: Any = None,
    ):
        super().__init__(
            message=message,
            service="openai",
            status_code=status_code,
            response=response,
        )
        self.code = "OPENAI_ERROR"


class GoogleMapsError(IntegrationError):
    """Erro da API Google Maps."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: Any = None,
    ):
        super().__init__(
            message=message,
            service="google_maps",
            status_code=status_code,
            response=response,
        )
        self.code = "GOOGLE_MAPS_ERROR"


# ==========================================
# Erros de Carrinho
# ==========================================

class CartError(LiaError):
    """Erro relacionado ao carrinho."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="CART_ERROR",
            details=details or {},
        )


class ItemNotFoundError(CartError):
    """Item não encontrado no cardápio."""
    
    def __init__(
        self,
        item_text: str,
        suggestions: list[str] | None = None,
    ):
        details = {"item_text": item_text}
        if suggestions:
            details["suggestions"] = suggestions
        
        super().__init__(
            message=f"Item não encontrado: {item_text}",
            details=details,
        )
        self.code = "ITEM_NOT_FOUND"
        self.suggestions = suggestions or []


class AdditionNotAllowedError(CartError):
    """Adicional não permitido para este produto."""
    
    def __init__(
        self,
        product_name: str,
        addition_name: str,
        allowed: list[str] | None = None,
    ):
        details = {
            "product": product_name,
            "addition": addition_name,
        }
        if allowed:
            details["allowed_additions"] = allowed
        
        super().__init__(
            message=f"'{addition_name}' não é permitido para '{product_name}'",
            details=details,
        )
        self.code = "ADDITION_NOT_ALLOWED"


# ==========================================
# Erros de Pedido
# ==========================================

class OrderError(LiaError):
    """Erro relacionado ao pedido."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="ORDER_ERROR",
            details=details or {},
        )


class OrderValidationError(OrderError):
    """Pedido inválido para envio."""
    
    def __init__(self, message: str, missing_fields: list[str] | None = None):
        details = {}
        if missing_fields:
            details["missing_fields"] = missing_fields
        
        super().__init__(message=message, details=details)
        self.code = "ORDER_VALIDATION_ERROR"


class OrderSubmissionError(OrderError):
    """Erro ao enviar pedido para o Saipos."""
    
    def __init__(
        self,
        message: str,
        saipos_error: str | None = None,
    ):
        details = {}
        if saipos_error:
            details["saipos_error"] = saipos_error
        
        super().__init__(message=message, details=details)
        self.code = "ORDER_SUBMISSION_ERROR"


# ==========================================
# Erros de Sessão
# ==========================================

class SessionError(LiaError):
    """Erro relacionado à sessão."""
    
    def __init__(self, message: str, session_id: str | None = None):
        details = {}
        if session_id:
            details["session_id"] = session_id
        
        super().__init__(
            message=message,
            code="SESSION_ERROR",
            details=details,
        )


class SessionNotFoundError(SessionError):
    """Sessão não encontrada."""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Sessão não encontrada: {session_id}",
            session_id=session_id,
        )
        self.code = "SESSION_NOT_FOUND"


class SessionExpiredError(SessionError):
    """Sessão expirada."""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Sessão expirada: {session_id}",
            session_id=session_id,
        )
        self.code = "SESSION_EXPIRED"
