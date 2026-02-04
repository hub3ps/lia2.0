"""
Finite State Machine (FSM) para controle do fluxo de conversa.

A FSM garante que:
- O agente sempre sabe em qual etapa está
- Transições são explícitas e validadas
- Não há "saltos" inválidos entre estados
- O contexto necessário para cada estado está disponível
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class ConversationState(str, Enum):
    """Estados possíveis da conversa.
    
    Fluxo típico:
    GREETING → COLLECTING_ITEMS → CONFIRMING_ITEMS → COLLECTING_DELIVERY_TYPE
    → COLLECTING_ADDRESS → CONFIRMING_ADDRESS → COLLECTING_PAYMENT
    → COLLECTING_PAYMENT_DETAILS → [AWAITING_PIX_PROOF] → CONFIRMING_ORDER
    → ORDER_SENT
    
    Estados de desvio:
    - RESOLVING_PENDING: quando há itens não encontrados
    - CANCELLED: conversa cancelada
    """
    
    # Início
    GREETING = "GREETING"
    
    # Coleta do pedido
    COLLECTING_ITEMS = "COLLECTING_ITEMS"
    CONFIRMING_ITEMS = "CONFIRMING_ITEMS"
    RESOLVING_PENDING = "RESOLVING_PENDING"
    
    # Tipo de entrega
    COLLECTING_DELIVERY_TYPE = "COLLECTING_DELIVERY_TYPE"
    
    # Endereço (se delivery)
    COLLECTING_ADDRESS = "COLLECTING_ADDRESS"
    CONFIRMING_ADDRESS = "CONFIRMING_ADDRESS"
    
    # Pagamento
    COLLECTING_PAYMENT = "COLLECTING_PAYMENT"
    COLLECTING_PAYMENT_DETAILS = "COLLECTING_PAYMENT_DETAILS"
    AWAITING_PIX_PROOF = "AWAITING_PIX_PROOF"
    
    # Finalização
    CONFIRMING_ORDER = "CONFIRMING_ORDER"
    ORDER_SENT = "ORDER_SENT"
    
    # Cancelamento
    CANCELLED = "CANCELLED"


@dataclass
class StateRequirements:
    """Requisitos e metadados de um estado."""
    
    # Campos obrigatórios no collected_data para entrar neste estado
    required_fields: List[str] = field(default_factory=list)
    
    # Estados para os quais pode transicionar
    allowed_transitions: List[ConversationState] = field(default_factory=list)
    
    # Prompt hint para o agente
    agent_hint: str = ""
    
    # Se este estado pode receber itens do pedido
    can_receive_items: bool = False
    
    # Se este estado finaliza a conversa
    is_terminal: bool = False
    
    # Timeout específico (minutos, None = usa padrão)
    timeout_minutes: Optional[int] = None


# Definição completa da máquina de estados
STATE_MACHINE: Dict[ConversationState, StateRequirements] = {
    
    ConversationState.GREETING: StateRequirements(
        required_fields=[],
        allowed_transitions=[
            ConversationState.COLLECTING_ITEMS,
            ConversationState.CANCELLED,
        ],
        agent_hint="Cumprimente o cliente e pergunte o que ele gostaria de pedir.",
        can_receive_items=True,  # Cliente pode já pedir no greeting
    ),
    
    ConversationState.COLLECTING_ITEMS: StateRequirements(
        required_fields=[],
        allowed_transitions=[
            ConversationState.CONFIRMING_ITEMS,
            ConversationState.RESOLVING_PENDING,
            ConversationState.CANCELLED,
        ],
        agent_hint="Colete os itens do pedido. Quando o cliente terminar, confirme o pedido.",
        can_receive_items=True,
    ),
    
    ConversationState.CONFIRMING_ITEMS: StateRequirements(
        required_fields=["cart_has_items"],
        allowed_transitions=[
            ConversationState.COLLECTING_ITEMS,      # Cliente quer alterar
            ConversationState.COLLECTING_DELIVERY_TYPE,  # Confirmado
            ConversationState.CANCELLED,
        ],
        agent_hint="Mostre o resumo do pedido e peça confirmação.",
        can_receive_items=True,  # Cliente pode adicionar mais
    ),
    
    ConversationState.RESOLVING_PENDING: StateRequirements(
        required_fields=["cart_has_pendencies"],
        allowed_transitions=[
            ConversationState.COLLECTING_ITEMS,
            ConversationState.CONFIRMING_ITEMS,
            ConversationState.CANCELLED,
        ],
        agent_hint="Há itens não encontrados. Apresente as sugestões e peça esclarecimento.",
        can_receive_items=True,
    ),
    
    ConversationState.COLLECTING_DELIVERY_TYPE: StateRequirements(
        required_fields=["items_confirmed"],
        allowed_transitions=[
            ConversationState.COLLECTING_ADDRESS,    # Delivery
            ConversationState.COLLECTING_PAYMENT,    # Retirada
            ConversationState.COLLECTING_ITEMS,      # Voltar a editar
            ConversationState.CANCELLED,
        ],
        agent_hint="Pergunte se será entrega ou retirada no balcão.",
    ),
    
    ConversationState.COLLECTING_ADDRESS: StateRequirements(
        required_fields=["delivery_type"],
        allowed_transitions=[
            ConversationState.CONFIRMING_ADDRESS,
            ConversationState.CANCELLED,
        ],
        agent_hint="Colete o endereço de entrega completo.",
    ),
    
    ConversationState.CONFIRMING_ADDRESS: StateRequirements(
        required_fields=["delivery_address"],
        allowed_transitions=[
            ConversationState.COLLECTING_ADDRESS,    # Corrigir
            ConversationState.COLLECTING_PAYMENT,    # Confirmado
            ConversationState.CANCELLED,
        ],
        agent_hint="Confirme o endereço e informe a taxa de entrega.",
    ),
    
    ConversationState.COLLECTING_PAYMENT: StateRequirements(
        required_fields=["delivery_type"],  # E address se for delivery
        allowed_transitions=[
            ConversationState.COLLECTING_PAYMENT_DETAILS,
            ConversationState.CONFIRMING_ORDER,      # Se não precisa detalhes
            ConversationState.CANCELLED,
        ],
        agent_hint="Pergunte a forma de pagamento.",
    ),
    
    ConversationState.COLLECTING_PAYMENT_DETAILS: StateRequirements(
        required_fields=["payment_method"],
        allowed_transitions=[
            ConversationState.AWAITING_PIX_PROOF,    # Se PIX
            ConversationState.CONFIRMING_ORDER,      # Outros
            ConversationState.COLLECTING_PAYMENT,    # Trocar forma
            ConversationState.CANCELLED,
        ],
        agent_hint="Colete detalhes do pagamento (troco, etc).",
    ),
    
    ConversationState.AWAITING_PIX_PROOF: StateRequirements(
        required_fields=["payment_method"],
        allowed_transitions=[
            ConversationState.CONFIRMING_ORDER,
            ConversationState.COLLECTING_PAYMENT,    # Trocar forma
            ConversationState.CANCELLED,
        ],
        agent_hint="Aguardando comprovante PIX. Valide quando recebido.",
        timeout_minutes=15,  # PIX tem timeout maior
    ),
    
    ConversationState.CONFIRMING_ORDER: StateRequirements(
        required_fields=["items_confirmed", "delivery_type", "payment_method"],
        allowed_transitions=[
            ConversationState.ORDER_SENT,
            ConversationState.COLLECTING_ITEMS,      # Alterar pedido
            ConversationState.COLLECTING_PAYMENT,    # Alterar pagamento
            ConversationState.CANCELLED,
        ],
        agent_hint="Mostre resumo final e peça confirmação para enviar.",
    ),
    
    ConversationState.ORDER_SENT: StateRequirements(
        required_fields=["order_confirmed"],
        allowed_transitions=[],  # Terminal
        agent_hint="Pedido enviado! Agradeça e informe tempo estimado.",
        is_terminal=True,
    ),
    
    ConversationState.CANCELLED: StateRequirements(
        required_fields=[],
        allowed_transitions=[],  # Terminal
        agent_hint="Conversa cancelada. Agradeça e se despeça.",
        is_terminal=True,
    ),
}


@dataclass
class StateTransition:
    """Representa uma transição de estado."""
    from_state: ConversationState
    to_state: ConversationState
    reason: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class FSM:
    """Gerenciador da máquina de estados da conversa."""
    
    def __init__(
        self,
        initial_state: ConversationState = ConversationState.GREETING,
        state_data: Optional[Dict[str, Any]] = None,
    ):
        self.current_state = initial_state
        self.state_data = state_data or {}
        self.transition_history: List[StateTransition] = []
    
    @property
    def requirements(self) -> StateRequirements:
        """Retorna os requisitos do estado atual."""
        return STATE_MACHINE[self.current_state]
    
    @property
    def allowed_transitions(self) -> List[ConversationState]:
        """Estados para os quais pode transicionar."""
        return self.requirements.allowed_transitions
    
    @property
    def is_terminal(self) -> bool:
        """Verifica se está em estado terminal."""
        return self.requirements.is_terminal
    
    @property
    def can_receive_items(self) -> bool:
        """Verifica se o estado atual aceita itens do pedido."""
        return self.requirements.can_receive_items
    
    @property
    def agent_hint(self) -> str:
        """Dica para o agente sobre o que fazer."""
        return self.requirements.agent_hint
    
    def can_transition_to(self, target: ConversationState) -> bool:
        """Verifica se a transição é permitida."""
        return target in self.allowed_transitions
    
    def transition(
        self,
        to_state: ConversationState,
        reason: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Tenta fazer a transição para outro estado.
        
        Args:
            to_state: Estado de destino
            reason: Motivo da transição
            data: Dados adicionais para o novo estado
            
        Returns:
            True se a transição foi bem-sucedida
        """
        if not self.can_transition_to(to_state):
            logger.warning(
                "fsm_invalid_transition",
                from_state=self.current_state.value,
                to_state=to_state.value,
                allowed=self.allowed_transitions,
            )
            return False
        
        # Registra transição
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            reason=reason,
            data=data or {},
        )
        self.transition_history.append(transition)
        
        # Atualiza estado
        old_state = self.current_state
        self.current_state = to_state
        
        # Merge state_data
        if data:
            self.state_data.update(data)
        
        logger.info(
            "fsm_transition",
            from_state=old_state.value,
            to_state=to_state.value,
            reason=reason,
        )
        
        return True
    
    def force_transition(
        self,
        to_state: ConversationState,
        reason: str = "forced",
    ) -> None:
        """Força transição (ignora validações). Usar com cuidado."""
        logger.warning(
            "fsm_forced_transition",
            from_state=self.current_state.value,
            to_state=to_state.value,
            reason=reason,
        )
        self.current_state = to_state
    
    def get_context_for_prompt(self) -> Dict[str, Any]:
        """Retorna contexto do FSM para incluir no prompt."""
        return {
            "estado_atual": self.current_state.value,
            "estados_permitidos": [s.value for s in self.allowed_transitions],
            "hint": self.agent_hint,
            "pode_receber_itens": self.can_receive_items,
            "eh_terminal": self.is_terminal,
            "dados_estado": self.state_data,
        }
    
    def suggest_next_state(
        self,
        cart_has_items: bool = False,
        cart_has_pendencies: bool = False,
        items_confirmed: bool = False,
        delivery_type: Optional[str] = None,
        address_provided: bool = False,
        address_confirmed: bool = False,
        payment_method: Optional[str] = None,
        payment_details_complete: bool = False,
        pix_proof_validated: bool = False,
        order_confirmed: bool = False,
    ) -> Optional[ConversationState]:
        """
        Sugere o próximo estado baseado no contexto.
        
        Útil para auto-transição quando o agente não especifica.
        """
        current = self.current_state
        
        # GREETING → COLLECTING_ITEMS (quando começou a pedir)
        if current == ConversationState.GREETING and cart_has_items:
            return ConversationState.COLLECTING_ITEMS
        
        # COLLECTING_ITEMS → próximo estado
        if current == ConversationState.COLLECTING_ITEMS:
            if cart_has_pendencies:
                return ConversationState.RESOLVING_PENDING
            if items_confirmed:
                return ConversationState.COLLECTING_DELIVERY_TYPE
        
        # CONFIRMING_ITEMS → próximo
        if current == ConversationState.CONFIRMING_ITEMS:
            if items_confirmed:
                return ConversationState.COLLECTING_DELIVERY_TYPE
        
        # RESOLVING_PENDING → volta para items
        if current == ConversationState.RESOLVING_PENDING:
            if not cart_has_pendencies:
                if cart_has_items:
                    return ConversationState.CONFIRMING_ITEMS
                return ConversationState.COLLECTING_ITEMS
        
        # COLLECTING_DELIVERY_TYPE → próximo
        if current == ConversationState.COLLECTING_DELIVERY_TYPE:
            if delivery_type == "pickup":
                return ConversationState.COLLECTING_PAYMENT
            if delivery_type == "delivery":
                return ConversationState.COLLECTING_ADDRESS
        
        # COLLECTING_ADDRESS → confirmar
        if current == ConversationState.COLLECTING_ADDRESS and address_provided:
            return ConversationState.CONFIRMING_ADDRESS
        
        # CONFIRMING_ADDRESS → pagamento
        if current == ConversationState.CONFIRMING_ADDRESS and address_confirmed:
            return ConversationState.COLLECTING_PAYMENT
        
        # COLLECTING_PAYMENT → detalhes ou confirmar
        if current == ConversationState.COLLECTING_PAYMENT and payment_method:
            # PIX sempre precisa de comprovante
            if payment_method == "pix":
                return ConversationState.COLLECTING_PAYMENT_DETAILS
            # Dinheiro precisa perguntar troco
            if payment_method == "dinheiro":
                return ConversationState.COLLECTING_PAYMENT_DETAILS
            # Cartão vai direto para confirmar
            return ConversationState.CONFIRMING_ORDER
        
        # COLLECTING_PAYMENT_DETAILS → próximo
        if current == ConversationState.COLLECTING_PAYMENT_DETAILS:
            if payment_method == "pix":
                return ConversationState.AWAITING_PIX_PROOF
            if payment_details_complete:
                return ConversationState.CONFIRMING_ORDER
        
        # AWAITING_PIX_PROOF → confirmar
        if current == ConversationState.AWAITING_PIX_PROOF and pix_proof_validated:
            return ConversationState.CONFIRMING_ORDER
        
        # CONFIRMING_ORDER → enviado
        if current == ConversationState.CONFIRMING_ORDER and order_confirmed:
            return ConversationState.ORDER_SENT
        
        return None


def get_state_display_name(state: ConversationState) -> str:
    """Retorna nome amigável do estado para logs/debug."""
    names = {
        ConversationState.GREETING: "Saudação",
        ConversationState.COLLECTING_ITEMS: "Coletando Itens",
        ConversationState.CONFIRMING_ITEMS: "Confirmando Itens",
        ConversationState.RESOLVING_PENDING: "Resolvendo Pendências",
        ConversationState.COLLECTING_DELIVERY_TYPE: "Tipo de Entrega",
        ConversationState.COLLECTING_ADDRESS: "Coletando Endereço",
        ConversationState.CONFIRMING_ADDRESS: "Confirmando Endereço",
        ConversationState.COLLECTING_PAYMENT: "Forma de Pagamento",
        ConversationState.COLLECTING_PAYMENT_DETAILS: "Detalhes Pagamento",
        ConversationState.AWAITING_PIX_PROOF: "Aguardando PIX",
        ConversationState.CONFIRMING_ORDER: "Confirmação Final",
        ConversationState.ORDER_SENT: "Pedido Enviado",
        ConversationState.CANCELLED: "Cancelado",
    }
    return names.get(state, state.value)
