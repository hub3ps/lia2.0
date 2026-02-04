"""
Schemas Pydantic para validação de dados.

Este módulo define os modelos de dados tipados que eliminam alucinação estrutural:
- O LLM retorna JSON que é validado contra estes schemas
- Se inválido, o sistema tenta self-correction
- Garante que dados malformados nunca chegam ao processamento
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================
# ENUMS
# ============================================

class DeliveryType(str, Enum):
    """Tipo de entrega."""
    DELIVERY = "delivery"
    PICKUP = "pickup"


class PaymentMethod(str, Enum):
    """Métodos de pagamento aceitos."""
    DINHEIRO = "dinheiro"
    CARTAO_CREDITO = "cartao_credito"
    CARTAO_DEBITO = "cartao_debito"
    PIX = "pix"


class PendencyReason(str, Enum):
    """Motivos de pendência no carrinho."""
    PRODUTO_NAO_ENCONTRADO = "produto_nao_encontrado"
    ADICIONAL_NAO_ENCONTRADO = "adicional_nao_encontrado"
    QUANTIDADE_INVALIDA = "quantidade_invalida"
    MODIFICACAO_NAO_PERMITIDA = "modificacao_nao_permitida"
    AMBIGUIDADE = "ambiguidade"


class ModificationAction(str, Enum):
    """Ações de modificação em itens."""
    ADD = "add"       # Adicionar ingrediente
    REMOVE = "remove" # Remover ingrediente (ex: "sem cebola")
    EXTRA = "extra"   # Quantidade extra (ex: "bastante queijo")


# ============================================
# SCHEMAS DO CARRINHO
# ============================================

class CartItemAddition(BaseModel):
    """Um adicional vinculado a um item do carrinho."""
    
    pdv: str = Field(..., description="Código PDV do adicional")
    nome: str = Field(..., description="Nome do adicional")
    quantidade: int = Field(default=1, ge=1, le=10)
    preco_unitario: Decimal = Field(..., ge=0)
    
    @property
    def preco_total(self) -> Decimal:
        return self.preco_unitario * self.quantidade


class CartItem(BaseModel):
    """Um item no carrinho de compras."""
    
    pdv: str = Field(..., description="Código PDV do produto")
    nome: str = Field(..., description="Nome do produto")
    quantidade: int = Field(default=1, ge=1, le=50)
    preco_unitario: Decimal = Field(..., ge=0, description="Preço base do produto")
    
    adicionais: list[CartItemAddition] = Field(default_factory=list)
    observacoes: str = Field(default="", max_length=500)
    
    # Campos calculados (preenchidos automaticamente)
    preco_total_unitario: Decimal | None = None  # Preço com adicionais (1 unidade)
    preco_total: Decimal | None = None           # Preço total (quantidade * unitário)
    
    @model_validator(mode="after")
    def calculate_totals(self) -> "CartItem":
        """Calcula os preços totais automaticamente."""
        # Soma dos adicionais
        adicionais_total = sum(
            a.preco_unitario * a.quantidade 
            for a in self.adicionais
        )
        
        # Preço unitário com adicionais
        self.preco_total_unitario = self.preco_unitario + adicionais_total
        
        # Preço total considerando quantidade
        self.preco_total = self.preco_total_unitario * self.quantidade
        
        return self
    
    @field_validator("quantidade", mode="before")
    @classmethod
    def parse_quantidade(cls, v: Any) -> int:
        """Converte quantidade de string/float para int."""
        if isinstance(v, str):
            # Remove espaços e tenta converter
            v = v.strip().lower()
            # Mapeamento de palavras para números
            word_map = {
                "um": 1, "uma": 1, "dois": 2, "duas": 2,
                "três": 3, "tres": 3, "quatro": 4, "cinco": 5,
                "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
            }
            if v in word_map:
                return word_map[v]
            try:
                return int(float(v))
            except ValueError:
                return 1
        if isinstance(v, float):
            return int(v)
        return v


class CartPendency(BaseModel):
    """Uma pendência que precisa ser resolvida antes de continuar."""
    
    motivo: PendencyReason
    texto_original: str = Field(..., description="O que o cliente pediu")
    sugestoes: list[str] = Field(default_factory=list, max_length=5)
    dados_extras: dict[str, Any] = Field(default_factory=dict)


class CartState(BaseModel):
    """Estado completo do carrinho de compras."""
    
    itens: list[CartItem] = Field(default_factory=list)
    pendencias: list[CartPendency] = Field(default_factory=list)
    
    @property
    def subtotal(self) -> Decimal:
        """Soma dos preços de todos os itens."""
        return sum(item.preco_total or Decimal(0) for item in self.itens)
    
    @property
    def total_itens(self) -> int:
        """Quantidade total de itens no carrinho."""
        return sum(item.quantidade for item in self.itens)
    
    @property
    def tem_pendencias(self) -> bool:
        """Verifica se há pendências não resolvidas."""
        return len(self.pendencias) > 0
    
    @property
    def is_empty(self) -> bool:
        """Verifica se o carrinho está vazio."""
        return len(self.itens) == 0
    
    def add_item(self, item: CartItem) -> None:
        """Adiciona item ao carrinho (agrupa se já existir)."""
        # Procura item existente com mesmo PDV e observações
        for existing in self.itens:
            if existing.pdv == item.pdv and existing.observacoes == item.observacoes:
                # Verifica se adicionais são iguais
                existing_adds = {(a.pdv, a.quantidade) for a in existing.adicionais}
                new_adds = {(a.pdv, a.quantidade) for a in item.adicionais}
                
                if existing_adds == new_adds:
                    existing.quantidade += item.quantidade
                    # Recalcula totais
                    existing.preco_total = existing.preco_total_unitario * existing.quantidade
                    return
        
        # Item novo, adiciona à lista
        self.itens.append(item)
    
    def remove_item(self, pdv: str, quantidade: int = 1) -> bool:
        """Remove item do carrinho. Retorna True se removido."""
        for i, item in enumerate(self.itens):
            if item.pdv == pdv:
                if item.quantidade <= quantidade:
                    self.itens.pop(i)
                else:
                    item.quantidade -= quantidade
                    item.preco_total = item.preco_total_unitario * item.quantidade
                return True
        return False
    
    def clear(self) -> None:
        """Limpa o carrinho."""
        self.itens = []
        self.pendencias = []
    
    def add_pendency(self, pendency: CartPendency) -> None:
        """Adiciona pendência à lista."""
        self.pendencias.append(pendency)
    
    def resolve_pendency(self, index: int) -> CartPendency | None:
        """Remove e retorna pendência pelo índice."""
        if 0 <= index < len(self.pendencias):
            return self.pendencias.pop(index)
        return None
    
    def to_summary(self) -> str:
        """Gera resumo textual do carrinho para o cliente."""
        if self.is_empty:
            return "Seu carrinho está vazio."
        
        lines = ["📦 *Seu Pedido:*", ""]
        
        for item in self.itens:
            line = f"• {item.quantidade}x {item.nome}"
            if item.adicionais:
                adds = ", ".join(f"+{a.nome}" for a in item.adicionais)
                line += f" ({adds})"
            line += f" — R$ {item.preco_total:.2f}"
            lines.append(line)
            
            if item.observacoes:
                lines.append(f"  _Obs: {item.observacoes}_")
        
        lines.append("")
        lines.append(f"*Subtotal: R$ {self.subtotal:.2f}*")
        
        return "\n".join(lines)


# ============================================
# SCHEMAS DE PEDIDO
# ============================================

class OrderItem(BaseModel):
    """Item formatado para envio ao Saipos."""
    
    pdv_code: str
    name: str
    quantity: int = Field(ge=1)
    unit_price: Decimal
    total_price: Decimal
    notes: str = ""
    additions: list[dict[str, Any]] = Field(default_factory=list)


class PaymentDetails(BaseModel):
    """Detalhes do pagamento."""
    
    method: PaymentMethod
    
    # Para dinheiro
    needs_change: bool = False
    change_for: Decimal | None = None
    
    # Para PIX
    pix_proof_validated: bool = False
    pix_proof_url: str | None = None
    
    # Para cartão
    card_brand: str | None = None
    
    @model_validator(mode="after")
    def validate_change(self) -> "PaymentDetails":
        """Valida dados de troco."""
        if self.method == PaymentMethod.DINHEIRO and self.needs_change:
            if self.change_for is None or self.change_for <= 0:
                raise ValueError("change_for é obrigatório quando needs_change=True")
        return self


class DeliveryAddress(BaseModel):
    """Endereço de entrega validado."""
    
    street: str
    number: str
    complement: str = ""
    district: str
    city: str
    state: str = "SC"
    postal_code: str = ""
    
    # Geocoding
    latitude: float | None = None
    longitude: float | None = None
    formatted_address: str | None = None
    
    def to_display(self) -> str:
        """Formata endereço para exibição."""
        parts = [f"{self.street}, {self.number}"]
        if self.complement:
            parts.append(self.complement)
        parts.append(f"{self.district} - {self.city}/{self.state}")
        return ", ".join(parts)


# ============================================
# SCHEMAS DE TOOL CALLS
# ============================================

class ToolCallResult(BaseModel):
    """Resultado de uma chamada de tool."""
    
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    should_retry: bool = False


class InterpretedOrder(BaseModel):
    """Resultado do order interpreter."""
    
    items: list[CartItem] = Field(default_factory=list)
    pendencies: list[CartPendency] = Field(default_factory=list)
    raw_text: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)


# ============================================
# SCHEMAS DE SESSÃO
# ============================================

class CollectedData(BaseModel):
    """Dados coletados durante a conversa."""
    
    # Cliente
    client_name: str | None = None
    client_phone: str | None = None
    
    # Entrega
    delivery_type: DeliveryType | None = None
    delivery_address: DeliveryAddress | None = None
    delivery_fee: Decimal | None = None
    
    # Pagamento
    payment: PaymentDetails | None = None
    
    # Totais
    subtotal: Decimal | None = None
    total: Decimal | None = None
    
    # Confirmações
    items_confirmed: bool = False
    address_confirmed: bool = False
    order_confirmed: bool = False


class SessionContext(BaseModel):
    """Contexto completo da sessão para o agente."""
    
    session_id: str
    tenant_id: str
    
    # Estado
    fsm_state: str
    fsm_state_data: dict[str, Any] = Field(default_factory=dict)
    
    # Carrinho
    cart: CartState = Field(default_factory=CartState)
    
    # Dados coletados
    collected: CollectedData = Field(default_factory=CollectedData)
    
    # Cliente (se identificado)
    client_id: str | None = None
    client_name: str | None = None
    client_is_returning: bool = False
    
    # Histórico resumido
    last_messages: list[dict[str, str]] = Field(default_factory=list)
    
    # Métricas
    message_count: int = 0
    created_at: datetime | None = None
