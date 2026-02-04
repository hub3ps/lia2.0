"""
Configurações centralizadas da aplicação.
Usa Pydantic Settings para validação e tipagem.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do ambiente."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ==========================================
    # Ambiente
    # ==========================================
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    
    # ==========================================
    # Supabase
    # ==========================================
    supabase_url: str = Field(..., description="URL do projeto Supabase")
    supabase_key: str = Field(..., description="Service role key do Supabase")
    
    # ==========================================
    # OpenAI
    # ==========================================
    openai_api_key: str = Field(..., description="API key da OpenAI")
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.3
    
    # ==========================================
    # Evolution API (WhatsApp)
    # ==========================================
    evolution_base_url: str = Field(..., description="URL base da Evolution API")
    evolution_api_key: str = Field(..., description="API key da Evolution")
    evolution_instance: str = "Lia"
    
    # ==========================================
    # Saipos (PDV) - Opcional em desenvolvimento
    # ==========================================
    saipos_base_url: str = "https://api.saipos.com"
    saipos_partner_id: str | None = None
    saipos_partner_secret: str | None = None
    saipos_cod_store: str | None = None
    saipos_display_id: str | None = None
    
    # ==========================================
    # Google Maps
    # ==========================================
    google_maps_api_key: str | None = None
    
    # ==========================================
    # Configurações do Agente
    # ==========================================
    message_debounce_seconds: int = 3
    max_correction_attempts: int = 3
    followup_timeout_minutes: int = 10
    default_tenant: str = "marcio-lanches"
    
    # ==========================================
    # Propriedades computadas
    # ==========================================
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    @property
    def saipos_enabled(self) -> bool:
        """Verifica se integração Saipos está configurada."""
        return bool(self.saipos_partner_id and self.saipos_partner_secret)
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level deve ser um de: {valid}")
        return upper


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    return Settings()


# Alias para importação mais fácil
settings = get_settings()
