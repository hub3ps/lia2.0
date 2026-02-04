"""
Utilitários para manipulação de números de telefone.
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_phone(phone: str) -> str:
    """
    Normaliza telefone brasileiro para formato padrão.
    
    Exemplos:
        "47 99999-9999" → "5547999999999"
        "+55 (47) 9 9999-9999" → "5547999999999"
        "999999999" → "55999999999" (assumindo DDD desconhecido)
    
    Args:
        phone: Número de telefone em qualquer formato
        
    Returns:
        Telefone normalizado (apenas dígitos, com código do país)
    """
    if not phone:
        return ""
    
    # Remove tudo exceto dígitos
    digits = re.sub(r"\D", "", phone)
    
    # Remove zeros à esquerda
    digits = digits.lstrip("0")
    
    # Adiciona código do país se necessário
    if len(digits) == 11:  # DDD + 9 dígitos (celular)
        digits = "55" + digits
    elif len(digits) == 10:  # DDD + 8 dígitos (fixo)
        digits = "55" + digits
    elif len(digits) == 9:  # Só celular sem DDD
        # Não conseguimos determinar o DDD, retorna como está
        pass
    elif len(digits) == 8:  # Só fixo sem DDD
        pass
    elif not digits.startswith("55") and len(digits) > 11:
        # Número internacional diferente do Brasil
        pass
    
    return digits


def format_phone_display(phone: str) -> str:
    """
    Formata telefone para exibição.
    
    Args:
        phone: Telefone normalizado
        
    Returns:
        Telefone formatado para exibição
    """
    digits = normalize_phone(phone)
    
    # Remove código do país para exibição
    if digits.startswith("55"):
        digits = digits[2:]
    
    if len(digits) == 11:  # Celular com DDD
        return f"({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}"
    elif len(digits) == 10:  # Fixo com DDD
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    elif len(digits) == 9:  # Celular sem DDD
        return f"{digits[0]} {digits[1:5]}-{digits[5:]}"
    elif len(digits) == 8:  # Fixo sem DDD
        return f"{digits[:4]}-{digits[4:]}"
    
    # Formato desconhecido, retorna como está
    return digits


def extract_ddd(phone: str) -> Optional[str]:
    """
    Extrai o DDD de um telefone.
    
    Args:
        phone: Telefone normalizado
        
    Returns:
        DDD ou None se não encontrado
    """
    digits = normalize_phone(phone)
    
    # Remove código do país
    if digits.startswith("55"):
        digits = digits[2:]
    
    if len(digits) >= 10:
        return digits[:2]
    
    return None


def is_valid_brazilian_phone(phone: str) -> bool:
    """
    Verifica se é um telefone brasileiro válido.
    
    Args:
        phone: Telefone normalizado
        
    Returns:
        True se for válido
    """
    digits = normalize_phone(phone)
    
    # Remove código do país
    if digits.startswith("55"):
        digits = digits[2:]
    
    # Celular: 11 dígitos (DDD + 9 + 8 dígitos)
    if len(digits) == 11 and digits[2] == "9":
        return True
    
    # Fixo: 10 dígitos (DDD + 8 dígitos)
    if len(digits) == 10:
        return True
    
    return False


def get_session_id_from_phone(phone: str) -> str:
    """
    Gera session_id a partir do telefone.
    
    O session_id é o telefone normalizado.
    
    Args:
        phone: Telefone em qualquer formato
        
    Returns:
        Session ID (telefone normalizado)
    """
    return normalize_phone(phone)
