"""
Order Interpreter - Parser.

Extrai itens e quantidades do texto do cliente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.utils.text import normalize_text, parse_quantity

_WORD_NUMBERS = r"um|uma|dois|duas|tres|três|quatro|cinco|seis|sete|oito|nove|dez"
_ITEM_START_RE = re.compile(
    rf"(?:^|\n+|\s+e\s+|\s*,\s*|\s*;\s*)({_WORD_NUMBERS}|\d+)\b\s*(?:x\s*)?",
    re.IGNORECASE,
)
_SEGMENT_RE = re.compile(r"^(\d+)\s*(?:x\s*)?(.*)$", re.IGNORECASE)
_WORD_QTY_RE = re.compile(rf"^({_WORD_NUMBERS})\b", re.IGNORECASE)
_CUTOFF_RE = re.compile(r"\b(para\s+a|para\s+o|pagamento|entrega)\b", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(r"^\[\d{1,2}:\d{2},\s*\d{2}/\d{2}/\d{4}\]\s+[^:]+:\s*")
_GREETING_RE = re.compile(
    r"^\s*(oi|ola|olá|boa\s+noite|bom\s+dia|boa\s+tarde|opa|oiii+|bia\s+noite)"
    r"(\s+(boa\s+noite|bom\s+dia|boa\s+tarde))?\s*$",
    re.IGNORECASE,
)
_LEADING_VERBS_RE = re.compile(
    r"^\s*(gostaria\s+de\s+fazer\s+um\s+pedido|gostaria\s+de\s+fazer|"
    r"gostaria\s+de|gostaria|queria|quero|ve|vê|ver|manda|pode|vou|vai)\b",
    re.IGNORECASE,
)
_CONTEXT_RE = re.compile(
    r"\b(rua|bairro|numero|número|prox|próx|praça|entrega|entregar|pagamento|pix|"
    r"debito|débito|credito|crédito|cartao|cartão|troco|casa|apto|apartamento|"
    r"blz|ok|tudo\s+bem|quantos|deu)\b",
    re.IGNORECASE,
)

_NOTE_KEYWORDS = [
    "cortado ao meio",
    "bem passado",
]


@dataclass
class ParsedItem:
    raw: str
    quantity: int
    name: str
    additions: List[str] = field(default_factory=list)
    removals: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    is_additional_only: bool = False
    size_hint: Optional[str] = None
    match_text: str = ""


def parse_order_text(text: str) -> List[ParsedItem]:
    """
    Parseia texto bruto e retorna lista de ParsedItem.

    Regras de escopo para testes iniciais:
    - Endereco/pagamento sao ignorados (corta a frase a partir de marcadores).
    - Cada linha/segmento vira item ou pendencia posteriormente.
    """
    if not text:
        return []

    # Remove trechos de endereco/pagamento para focar no pedido
    cut_text = _cut_context(text)

    segments = _split_segments(cut_text)
    items: List[ParsedItem] = []
    for seg in segments:
        parsed = _parse_segment(seg)
        if parsed:
            items.append(parsed)
    return items


def _cut_context(text: str) -> str:
    if "\n" in text:
        return text
    match = _CUTOFF_RE.search(text)
    if not match:
        return text
    return text[: match.start()].strip()


def _split_segments(text: str) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    segments: List[str] = []

    for raw_line in lines:
        line = _strip_metadata(raw_line)
        if not line or _is_context_line(line):
            continue

        matches = list(_ITEM_START_RE.finditer(line))
        if not matches:
            segments.append(line.strip(" ,;"))
            continue

        for idx, match in enumerate(matches):
            start = match.start(1)
            end = matches[idx + 1].start(1) if idx + 1 < len(matches) else len(line)
            segment = line[start:end].strip(" ,;")
            if segment:
                segments.append(segment)
    return segments


def _parse_segment(segment: str) -> Optional[ParsedItem]:
    segment = segment.strip()
    match = _SEGMENT_RE.match(segment)
    if match:
        quantity = int(match.group(1))
        desc = match.group(2).strip()
    else:
        word_match = _WORD_QTY_RE.match(segment)
        if word_match:
            quantity = parse_quantity(word_match.group(1))
            desc = segment[word_match.end():].strip()
        else:
            quantity = 1
            desc = segment.strip()
    raw = segment.strip()
    has_x = bool(re.match(rf"^({_WORD_NUMBERS}|\d+)?\s*x\b", segment, re.IGNORECASE))

    notes, desc = _extract_notes(desc)
    is_additional_only = bool(re.search(r"\badicional\b", normalize_text(desc))) and not re.search(
        r"\bx\b", raw, re.IGNORECASE
    )
    desc = re.sub(r"\badicional\b", "", desc, flags=re.IGNORECASE).strip()

    desc, removals = _extract_removals(desc)

    base_name = desc
    additions: List[str] = []
    if re.search(r"\bcom\b", desc, re.IGNORECASE):
        base_name, add_part = re.split(r"\bcom\b", desc, maxsplit=1, flags=re.IGNORECASE)
        additions = _split_list(add_part)

    base_name = _clean_text(base_name)
    if has_x and not re.match(r"^x\s+", base_name, re.IGNORECASE):
        base_name = f"x {base_name}".strip()

    item = ParsedItem(
        raw=raw,
        quantity=quantity,
        name=base_name,
        additions=additions,
        removals=removals,
        notes=notes,
        is_additional_only=is_additional_only,
        match_text=base_name,
    )
    return item


def _extract_notes(text: str) -> tuple[List[str], str]:
    notes: List[str] = []
    cleaned = text
    for keyword in _NOTE_KEYWORDS:
        if keyword in normalize_text(cleaned):
            notes.append(keyword)
            cleaned = re.sub(keyword, "", cleaned, flags=re.IGNORECASE).strip()
    return notes, cleaned


def _extract_removals(text: str) -> tuple[str, List[str]]:
    removals: List[str] = []
    pattern = re.compile(r"\bsem\s+([^,]+?)(?=(\bsem\b|\bcom\b|$))", re.IGNORECASE)
    for match in pattern.finditer(text):
        part = match.group(1).strip()
        removals.extend(_split_list(part))

    cleaned = pattern.sub("", text)
    if removals:
        cleaned = re.sub(r"\s+e\s+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = _clean_text(cleaned)
    return cleaned, removals


def _strip_metadata(text: str) -> str:
    cleaned = _TIMESTAMP_RE.sub("", text).strip()
    cleaned = re.sub(
        r"^\s*(oiii+|oi|ola|olá|boa\s+noite|bom\s+dia|boa\s+tarde|opa)\s*,?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*(boa\s+noite|bom\s+dia|boa\s+tarde)\s*,?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*eu\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = _LEADING_VERBS_RE.sub("", cleaned).strip(" ,.-")
    cleaned = re.sub(r"^\s*e\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _is_context_line(text: str) -> bool:
    if _GREETING_RE.match(text):
        return True
    return bool(_CONTEXT_RE.search(text))


def _split_list(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"\s+e\s+|,", text, flags=re.IGNORECASE)
    return [_clean_text(p) for p in parts if _clean_text(p)]


def _clean_text(text: str) -> str:
    cleaned = text.strip().strip(",;")
    cleaned = re.sub(r"[()]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\b(e|de)\b$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.strip()


__all__ = [
    "ParsedItem",
    "parse_order_text",
]
