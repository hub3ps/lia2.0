"""
Conexão com o banco de dados Supabase.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

import structlog
from supabase import Client, create_client

from app.config import settings

logger = structlog.get_logger()


@lru_cache
def get_supabase_client() -> Client:
    """
    Retorna cliente Supabase singleton.
    
    Usa lru_cache para manter uma única instância.
    """
    logger.info(
        "supabase_connecting",
        url=settings.supabase_url[:50] + "...",
    )
    
    client = create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key,
    )
    
    logger.info("supabase_connected")
    return client


def get_db() -> Client:
    """Alias para get_supabase_client()."""
    return get_supabase_client()


class Database:
    """
    Wrapper para operações de banco de dados.
    
    Provê métodos de conveniência e tratamento de erros.
    """
    
    def __init__(self):
        self._client: Optional[Client] = None
    
    @property
    def client(self) -> Client:
        """Retorna cliente Supabase (lazy loading)."""
        if self._client is None:
            self._client = get_supabase_client()
        return self._client
    
    def table(self, name: str):
        """Acessa uma tabela."""
        return self.client.table(name)
    
    # ==========================================
    # Métodos de conveniência
    # ==========================================
    
    async def get_tenant_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Busca tenant pelo slug."""
        result = (
            self.table("tenants")
            .select("*")
            .eq("slug", slug)
            .eq("is_active", True)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def get_tenant_by_evolution_instance(
        self,
        instance: str,
    ) -> Optional[Dict[str, Any]]:
        """Busca tenant pela instância Evolution."""
        result = (
            self.table("tenants")
            .select("*")
            .eq("evolution_instance", instance)
            .eq("is_active", True)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def get_session(
        self,
        tenant_id: str,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Busca sessão ativa."""
        result = (
            self.table("sessions")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("session_id", session_id)
            .eq("status", "active")
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def upsert_session(
        self,
        tenant_id: str,
        session_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Cria ou atualiza sessão."""
        # Prepara dados
        session_data = {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "status": "active",
            **data,
        }
        
        result = (
            self.table("sessions")
            .upsert(session_data, on_conflict="tenant_id,session_id,status")
            .execute()
        )
        
        return result.data[0] if result.data else session_data
    
    async def get_client_by_phone(
        self,
        tenant_id: str,
        phone: str,
    ) -> Optional[Dict[str, Any]]:
        """Busca cliente pelo telefone."""
        # Normaliza telefone
        from app.utils.phone import normalize_phone
        phone_normalized = normalize_phone(phone)
        
        result = (
            self.table("clients")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("phone_normalized", phone_normalized)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def get_client_snapshot(
        self,
        tenant_id: str,
        phone: str,
    ) -> Optional[Dict[str, Any]]:
        """Busca snapshot completo do cliente via view."""
        from app.utils.phone import normalize_phone
        phone_normalized = normalize_phone(phone)
        
        result = (
            self.table("v_client_snapshot")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("phone_normalized", phone_normalized)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def search_menu(
        self,
        tenant_id: str,
        query: Optional[str] = None,
        category: Optional[str] = None,
        item_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Busca itens no cardápio."""
        q = (
            self.table("menu_items")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("is_available", True)
        )
        
        if category:
            q = q.eq("category", category)
        
        if item_type:
            q = q.eq("item_type", item_type)
        
        if query:
            # Busca por fingerprint ou nome
            from app.utils.text import make_fingerprint
            fingerprint = make_fingerprint(query)
            q = q.or_(f"fingerprint.ilike.%{fingerprint}%,name.ilike.%{query}%")
        
        q = q.limit(limit)
        
        result = q.execute()
        return result.data or []
    
    async def get_menu_item_by_pdv(
        self,
        tenant_id: str,
        pdv_code: str,
    ) -> Optional[Dict[str, Any]]:
        """Busca item do cardápio pelo código PDV."""
        result = (
            self.table("menu_items")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("pdv_code", pdv_code)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def get_delivery_fee(
        self,
        tenant_id: str,
        district: str,
        city: str = "Itajaí",
    ) -> Optional[Dict[str, Any]]:
        """Busca taxa de entrega por bairro."""
        result = (
            self.table("delivery_areas")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("city", city)
            .ilike("district", f"%{district}%")
            .eq("is_active", True)
            .single()
            .execute()
        )
        return result.data if result.data else None
    
    async def add_message_to_history(
        self,
        session_uuid: str,
        role: str,
        content: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Adiciona mensagem ao histórico."""
        message_data = {
            "session_id": session_uuid,
            "role": role,
            "content": content,
            **kwargs,
        }
        
        result = self.table("messages").insert(message_data).execute()
        return result.data[0] if result.data else message_data
    
    async def get_message_history(
        self,
        session_uuid: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Busca histórico de mensagens da sessão."""
        result = (
            self.table("messages")
            .select("*")
            .eq("session_id", session_uuid)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []


# Instância global
db = Database()
