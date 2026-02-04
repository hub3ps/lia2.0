"""
Input Guardrails - Filtros de entrada para economia de LLM.

Baseado no Princípio de Pareto: ~80% das mensagens são simples
("sim", "ok", "não", números) e não precisam de LLM completo.

Este módulo implementa:
1. Classificação rápida por regex
2. Extração de dados estruturados (telefone, endereço)
3. Detecção de intenção sem LLM
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from unidecode import unidecode


class QuickIntent(str, Enum):
    """Intenções que podem ser detectadas sem LLM."""
    
    # Confirmações
    CONFIRM = "confirm"           # sim, ok, pode, isso
    DENY = "deny"                 # não, nao, n, cancela
    
    # Pedido
    ADD_ITEM = "add_item"         # "quero X", "mais um Y"
    REMOVE_ITEM = "remove_item"   # "tira", "remove"
    
    # Navegação
    CANCEL = "cancel"             # cancelar, desistir
    HELP = "help"                 # ajuda, cardápio
    REPEAT = "repeat"             # repete, de novo
    
    # Dados estruturados
    PHONE_NUMBER = "phone"        # Número de telefone
    ADDRESS = "address"           # Possível endereço
    QUANTITY = "quantity"         # Apenas número
    
    # Pagamento
    PAYMENT_METHOD = "payment"    # dinheiro, pix, cartão
    
    # Precisa LLM
    NEEDS_LLM = "needs_llm"       # Não conseguiu classificar


class InputGuardrails:
    """Classificador rápido de mensagens."""
    
    # ==========================================
    # Patterns de Confirmação
    # ==========================================
    CONFIRM_PATTERNS = [
        r"^(sim|ss?|s|siiim*|yes|yeah|yep)$",
        r"^(ok|okay|oks?|okk+|blz|beleza)$",
        r"^(pode|podee*|isso|iss+o|exato)$",
        r"^(confirm[ao]?|certo|certinho)$",
        r"^(tá|ta|taa+|tudo bem|fechado)$",
        r"^(bora|vamos|manda|dale|partiu)$",
        r"^(perfeito|ótimo|otimo|show)$",
        r"^(positivo|afirmativo|correto)$",
        r"^👍+$",  # Emoji de joinha
        r"^✅+$",  # Emoji de check
    ]
    
    # ==========================================
    # Patterns de Negação
    # ==========================================
    DENY_PATTERNS = [
        r"^(não|nao|n|nn+|naoo*|nope)$",
        r"^(nunca|jamais|negativo)$",
        r"^(errado|incorreto)$",
        r"^(para|pare|espera)$",
        r"^👎+$",  # Emoji negativo
        r"^❌+$",  # Emoji de X
    ]
    
    # ==========================================
    # Patterns de Cancelamento
    # ==========================================
    CANCEL_PATTERNS = [
        r"^(cancel[ao]?r?|cancela isso)$",
        r"^(desist[io]r?|desisto)$",
        r"^(esquece|deixa|para|pare)$",
        r"^(não quero mais|nao quero mais)$",
        r"^(sair|sai|exit|quit)$",
    ]
    
    # ==========================================
    # Patterns de Ajuda
    # ==========================================
    HELP_PATTERNS = [
        r"^(ajuda|help|socorro)$",
        r"^(cardápio|cardapio|menu)$",
        r"^(o que (tem|voc[eê]s t[eê]m))$",
        r"^(quais? (são|sao) (os|as)? (opç[oõ]es|opcoes))$",
    ]
    
    # ==========================================
    # Patterns de Repetição
    # ==========================================
    REPEAT_PATTERNS = [
        r"^(repet[ei]r?|repete)$",
        r"^(de novo|denovo)$",
        r"^(novamente|outra vez)$",
        r"^(como|oi|hã|hum)\??$",
        r"^(\?+)$",
    ]
    
    # ==========================================
    # Patterns de Pagamento
    # ==========================================
    PAYMENT_PATTERNS = {
        "dinheiro": [
            r"^(dinheiro|din|grana|cash)$",
            r"^(em espécie|especie)$",
        ],
        "pix": [
            r"^(pix|piks?)$",
        ],
        "cartao_credito": [
            r"^(cart[aã]o\s*(de\s*)?cr[eé]dito|credito)$",
            r"^(cr[eé]dito)$",
        ],
        "cartao_debito": [
            r"^(cart[aã]o\s*(de\s*)?d[eé]bito|debito)$",
            r"^(d[eé]bito)$",
        ],
        "cartao": [
            r"^(cart[aã]o|cartao)$",  # Genérico, precisa perguntar qual
        ],
    }
    
    # ==========================================
    # Patterns de Quantidade (só números)
    # ==========================================
    QUANTITY_PATTERN = r"^(\d{1,2})$"  # 1-99
    
    # ==========================================
    # Patterns de Telefone BR
    # ==========================================
    PHONE_PATTERNS = [
        r"^\+?55?\s*\(?(\d{2})\)?\s*9?\s*(\d{4})[-.\s]?(\d{4})$",  # +55 47 99999-9999
        r"^(\d{2})\s*9?(\d{4})[-.\s]?(\d{4})$",                     # 47 99999-9999
        r"^9?(\d{4})[-.\s]?(\d{4})$",                               # 99999-9999
    ]
    
    # ==========================================
    # Patterns de Endereço (heurísticas)
    # ==========================================
    ADDRESS_INDICATORS = [
        r"\brua\b",
        r"\bavenida\b",
        r"\bav\.?\b",
        r"\btravessa\b",
        r"\bservidão\b",
        r"\bn[úu]mero\b|\bn[ºo°]?\s*\d+",
        r"\bcep\b",
        r"\bbairro\b",
        r"\bcentro\b",
        r"\bprédio\b|\bpredio\b|\bapartamento\b|\bapto?\b",
        r"\bbloco\b|\bbl\.?\b",
    ]
    
    def __init__(self):
        # Compila patterns para performance
        self._confirm_re = self._compile_patterns(self.CONFIRM_PATTERNS)
        self._deny_re = self._compile_patterns(self.DENY_PATTERNS)
        self._cancel_re = self._compile_patterns(self.CANCEL_PATTERNS)
        self._help_re = self._compile_patterns(self.HELP_PATTERNS)
        self._repeat_re = self._compile_patterns(self.REPEAT_PATTERNS)
        self._quantity_re = re.compile(self.QUANTITY_PATTERN, re.IGNORECASE)
        self._phone_re = [re.compile(p, re.IGNORECASE) for p in self.PHONE_PATTERNS]
        self._address_re = [re.compile(p, re.IGNORECASE) for p in self.ADDRESS_INDICATORS]
        
        # Payment patterns
        self._payment_re = {
            method: self._compile_patterns(patterns)
            for method, patterns in self.PAYMENT_PATTERNS.items()
        }
    
    @staticmethod
    def _compile_patterns(patterns: List[str]) -> re.Pattern:
        """Compila lista de patterns em um único regex."""
        combined = "|".join(f"({p})" for p in patterns)
        return re.compile(combined, re.IGNORECASE | re.UNICODE)
    
    @staticmethod
    def normalize(text: str) -> str:
        """Normaliza texto para comparação."""
        # Remove acentos
        text = unidecode(text)
        # Lowercase
        text = text.lower()
        # Remove espaços extras
        text = " ".join(text.split())
        # Remove pontuação no início/fim
        text = text.strip(".,!?;:\"'")
        return text
    
    def classify(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[QuickIntent, Dict[str, Any]]:
        """
        Classifica uma mensagem.
        
        Args:
            text: Mensagem do usuário
            context: Contexto opcional (estado atual, etc)
            
        Returns:
            Tuple de (intenção detectada, dados extraídos)
        """
        # Normaliza
        normalized = self.normalize(text)
        original = text.strip()
        
        # Dict para dados extraídos
        extracted: Dict[str, Any] = {}
        
        # Mensagem vazia
        if not normalized:
            return QuickIntent.NEEDS_LLM, extracted
        
        # ==========================================
        # Confirmação
        # ==========================================
        if self._confirm_re.match(normalized):
            return QuickIntent.CONFIRM, extracted
        
        # ==========================================
        # Negação
        # ==========================================
        if self._deny_re.match(normalized):
            return QuickIntent.DENY, extracted
        
        # ==========================================
        # Cancelamento
        # ==========================================
        if self._cancel_re.match(normalized):
            return QuickIntent.CANCEL, extracted
        
        # ==========================================
        # Ajuda / Menu
        # ==========================================
        if self._help_re.match(normalized):
            return QuickIntent.HELP, extracted
        
        # ==========================================
        # Repetição
        # ==========================================
        if self._repeat_re.match(normalized):
            return QuickIntent.REPEAT, extracted
        
        # ==========================================
        # Forma de pagamento
        # ==========================================
        for method, pattern in self._payment_re.items():
            if pattern.match(normalized):
                extracted["payment_method"] = method
                return QuickIntent.PAYMENT_METHOD, extracted
        
        # ==========================================
        # Quantidade (apenas número)
        # ==========================================
        qty_match = self._quantity_re.match(normalized)
        if qty_match:
            extracted["quantity"] = int(qty_match.group(1))
            return QuickIntent.QUANTITY, extracted
        
        # ==========================================
        # Telefone
        # ==========================================
        for phone_re in self._phone_re:
            if phone_re.match(original):
                # Extrai apenas dígitos
                digits = re.sub(r"\D", "", original)
                extracted["phone"] = self._normalize_phone(digits)
                return QuickIntent.PHONE_NUMBER, extracted
        
        # ==========================================
        # Endereço (heurística - presença de indicadores)
        # ==========================================
        address_score = sum(
            1 for pattern in self._address_re
            if pattern.search(normalized)
        )
        if address_score >= 2:  # Pelo menos 2 indicadores
            extracted["possible_address"] = original
            return QuickIntent.ADDRESS, extracted
        
        # ==========================================
        # Não conseguiu classificar → LLM
        # ==========================================
        return QuickIntent.NEEDS_LLM, extracted
    
    @staticmethod
    def _normalize_phone(digits: str) -> str:
        """Normaliza telefone para formato padrão."""
        # Remove zeros à esquerda
        digits = digits.lstrip("0")
        
        # Adiciona código do país se necessário
        if len(digits) == 11:  # DDD + 9 dígitos
            digits = "55" + digits
        elif len(digits) == 10:  # DDD + 8 dígitos (fixo)
            digits = "55" + digits
        elif len(digits) == 9:  # Só o número móvel
            # Assumir DDD padrão? Por enquanto retorna como está
            pass
        
        return digits
    
    def is_simple_response(self, text: str) -> bool:
        """Verifica se é uma resposta simples (não precisa LLM)."""
        intent, _ = self.classify(text)
        return intent != QuickIntent.NEEDS_LLM
    
    def get_quick_response(
        self,
        intent: QuickIntent,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Retorna resposta rápida para intenções simples.
        
        Usado quando não precisa chamar o LLM.
        
        Args:
            intent: Intenção detectada
            context: Contexto (estado FSM, etc)
            
        Returns:
            Resposta pronta ou None se precisa LLM
        """
        # TODO: Implementar respostas baseadas no contexto
        # Por enquanto retorna None para delegar ao orquestrador
        return None


# Singleton para uso global
guardrails = InputGuardrails()


def classify_input(
    text: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[QuickIntent, Dict[str, Any]]:
    """Função de conveniência para classificar input."""
    return guardrails.classify(text, context)


def is_simple_input(text: str) -> bool:
    """Verifica se input é simples (não precisa LLM)."""
    return guardrails.is_simple_response(text)
