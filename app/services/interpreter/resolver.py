"""
Order Interpreter - Resolver.

Resolve girias e normalizacoes antes do matcher.
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.services.interpreter.parser import ParsedItem
from app.utils.text import normalize_text

_SIZE_HINT_PATTERNS = [
    (re.compile(r"\b(1/4|um\s+quarto|porcao\s+pequena|porcao\s+pequena)\b", re.IGNORECASE), "1/4"),
    (re.compile(r"\b(1/2|meia\s+porcao|meia\s+porcao|meia)\b", re.IGNORECASE), "1/2"),
]


def resolve_parsed_items(items: List[ParsedItem]) -> List[ParsedItem]:
    """
    Aplica regras de normalizacao nos ParsedItem.

    Regras cobertas nos testes iniciais:
    - "careca" => sem salada geral
    - "burger" => "burguer"
    - "porcao pequena" => size_hint 1/4
    - "guarana 2 l" => "guarana 2 litros"
    """
    resolved: List[ParsedItem] = []
    for item in items:
        resolved.append(_resolve_item(item))
    return resolved


def _resolve_item(item: ParsedItem) -> ParsedItem:
    base = normalize_text(item.name)

    # normaliza "xegg" -> "x egg"
    base = re.sub(r"^x(?=[a-z])", "x ", base, flags=re.IGNORECASE)

    # "careca" => sem salada geral
    if "careca" in base:
        base = base.replace("careca", " ").strip()
        item.removals.append("salada geral")

    # remove "completo(s)" para melhorar match
    base = re.sub(r"\bcomplet[oa]s?\b", "", base, flags=re.IGNORECASE).strip()

    # "burger" => "burguer"
    base = re.sub(r"\bburger\b", "burguer", base, flags=re.IGNORECASE)

    # "burg" => "burguer"
    base = re.sub(r"\bx\s+burg\b", "x burguer", base, flags=re.IGNORECASE)

    # correcoes comuns de typo
    base = re.sub(r"\bmigon\b", "mignon", base, flags=re.IGNORECASE)
    base = re.sub(r"\bevilha\b", "ervilha", base, flags=re.IGNORECASE)
    base = re.sub(r"\btbm\b", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\btambem\b", "", base, flags=re.IGNORECASE)

    # normaliza coca
    if "coca cola" not in base:
        base = re.sub(r"\bcoca\b", "coca cola", base, flags=re.IGNORECASE)

    # correcao simples de typo
    base = re.sub(r"\bbata\s+frita\b", "batata frita", base, flags=re.IGNORECASE)

    # size hints
    size_hint = _extract_size_hint(base)
    item.size_hint = size_hint or item.size_hint

    # batata frita size normalization
    if "batata frita" in base:
        if "tradicional" in base:
            base = "batata frita tradicional"
        else:
            base = "batata frita"

    # 2 l / 2 lt => 2 litros
    base = re.sub(r"\b(\d+)\s*l(t|itros)?\b", r"\1 litros", base, flags=re.IGNORECASE)

    # normalize additions/removals to improve matching
    item.additions = [normalize_text(a) for a in item.additions if a]
    normalized_removals: List[str] = []
    for removal in item.removals:
        if not removal:
            continue
        cleaned = normalize_text(removal)
        cleaned = re.sub(r"\bevilha\b", "ervilha", cleaned, flags=re.IGNORECASE)
        normalized_removals.append(cleaned)
    item.removals = _dedupe(normalized_removals)

    # batata frita com bacon/queijo costuma ser item do cardapio, nao adicional
    if "batata frita" in base and item.additions:
        base = f"{base} {' '.join(item.additions)}".strip()
        item.additions = []

    item.match_text = _compact_spaces(base)
    return item


def _extract_size_hint(text: str) -> Optional[str]:
    for pattern, hint in _SIZE_HINT_PATTERNS:
        if pattern.search(text):
            return hint
    return None


def _compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


__all__ = [
    "resolve_parsed_items",
]
