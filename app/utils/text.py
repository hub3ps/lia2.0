"""
Utilitários para manipulação de texto.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from unidecode import unidecode


def make_fingerprint(text: str) -> str:
    """
    Cria fingerprint para busca de produtos.
    
    Remove acentos, espaços, pontuação e converte para lowercase.
    
    Exemplos:
        "X-Burguer" → "xburguer"
        "Coca-Cola 2L" → "cocacola2l"
        "Açaí com Banana" → "acaicombanana"
    
    Args:
        text: Texto original
        
    Returns:
        Fingerprint normalizado
    """
    if not text:
        return ""
    
    # Remove acentos
    text = unidecode(text)
    # Lowercase
    text = text.lower()
    # Remove tudo que não é alfanumérico
    text = re.sub(r"[^a-z0-9]", "", text)
    
    return text


def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparação.
    
    Diferente do fingerprint, mantém espaços.
    
    Args:
        text: Texto original
        
    Returns:
        Texto normalizado
    """
    if not text:
        return ""
    
    # Remove acentos
    text = unidecode(text)
    # Lowercase
    text = text.lower()
    # Normaliza espaços
    text = " ".join(text.split())
    # Remove pontuação no início/fim
    text = text.strip(".,!?;:\"'")
    
    return text


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Trunca texto para tamanho máximo.
    
    Args:
        text: Texto original
        max_length: Tamanho máximo
        suffix: Sufixo a adicionar se truncado
        
    Returns:
        Texto truncado
    """
    if len(text) <= max_length:
        return text
    
    return text[: max_length - len(suffix)] + suffix


def extract_numbers(text: str) -> List[int]:
    """
    Extrai números de um texto.
    
    Args:
        text: Texto contendo números
        
    Returns:
        Lista de números encontrados
    """
    return [int(n) for n in re.findall(r"\d+", text)]


def parse_quantity(text: str) -> int:
    """
    Interpreta quantidade de texto.
    
    Exemplos:
        "2" → 2
        "dois" → 2
        "uma" → 1
        "meia dúzia" → 6
    
    Args:
        text: Texto representando quantidade
        
    Returns:
        Quantidade numérica (default: 1)
    """
    text = normalize_text(text)
    
    # Mapeamento de palavras para números
    word_map = {
        "um": 1, "uma": 1,
        "dois": 2, "duas": 2,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6, "meia duzia": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
        "onze": 11,
        "doze": 12, "uma duzia": 12,
    }
    
    # Tenta mapeamento de palavra
    if text in word_map:
        return word_map[text]
    
    # Tenta converter para número
    try:
        return int(float(text))
    except ValueError:
        pass
    
    # Extrai primeiro número encontrado
    numbers = extract_numbers(text)
    if numbers:
        return numbers[0]
    
    # Default
    return 1


def similarity_ratio(s1: str, s2: str) -> float:
    """
    Calcula similaridade entre duas strings (0.0 a 1.0).
    
    Usa algoritmo de Levenshtein normalizado.
    
    Args:
        s1: Primeira string
        s2: Segunda string
        
    Returns:
        Ratio de similaridade (0.0 = diferentes, 1.0 = iguais)
    """
    from rapidfuzz import fuzz
    
    return fuzz.ratio(s1, s2) / 100.0


def find_best_match(
    query: str,
    candidates: Sequence[str],
    threshold: float = 0.6,
) -> Tuple[Optional[str], float]:
    """
    Encontra melhor match para uma query em uma lista de candidatos.
    
    Args:
        query: Texto a buscar
        candidates: Lista de candidatos
        threshold: Threshold mínimo de similaridade
        
    Returns:
        Tuple de (melhor match, score) ou (None, 0.0)
    """
    from rapidfuzz import process, fuzz
    
    if not candidates:
        return None, 0.0
    
    # Normaliza query
    query_normalized = normalize_text(query)
    candidates_normalized = [normalize_text(c) for c in candidates]
    
    # Busca melhor match
    result = process.extractOne(
        query_normalized,
        candidates_normalized,
        scorer=fuzz.WRatio,
    )
    
    if result is None:
        return None, 0.0
    
    match, score, index = result
    score = score / 100.0  # Normaliza para 0-1
    
    if score < threshold:
        return None, score
    
    # Retorna o candidato original (não normalizado)
    return candidates[index], score


def find_matches(
    query: str,
    candidates: Sequence[str],
    threshold: float = 0.6,
    limit: int = 5,
) -> List[Tuple[str, float]]:
    """
    Encontra múltiplos matches para uma query.
    
    Args:
        query: Texto a buscar
        candidates: Lista de candidatos
        threshold: Threshold mínimo de similaridade
        limit: Máximo de resultados
        
    Returns:
        Lista de tuples (match, score) ordenada por score
    """
    from rapidfuzz import process, fuzz
    
    if not candidates:
        return []
    
    # Normaliza query
    query_normalized = normalize_text(query)
    candidates_normalized = [normalize_text(c) for c in candidates]
    
    # Busca matches
    results = process.extract(
        query_normalized,
        candidates_normalized,
        scorer=fuzz.WRatio,
        limit=limit,
    )
    
    # Filtra por threshold e retorna candidatos originais
    matches = []
    for match, score, index in results:
        score = score / 100.0
        if score >= threshold:
            matches.append((candidates[index], score))
    
    return matches


def clean_whatsapp_formatting(text: str) -> str:
    """
    Remove formatação do WhatsApp.
    
    Remove marcadores de negrito (*), itálico (_), etc.
    
    Args:
        text: Texto com formatação WhatsApp
        
    Returns:
        Texto limpo
    """
    # Remove negrito
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    # Remove itálico
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Remove tachado
    text = re.sub(r"~([^~]+)~", r"\1", text)
    # Remove monospace
    text = re.sub(r"```([^`]+)```", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    
    return text
