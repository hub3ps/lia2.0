"""
Utilitários do sistema.
"""
from __future__ import annotations

from app.utils.phone import (
    extract_ddd,
    format_phone_display,
    get_session_id_from_phone,
    is_valid_brazilian_phone,
    normalize_phone,
)
from app.utils.text import (
    clean_whatsapp_formatting,
    find_best_match,
    find_matches,
    make_fingerprint,
    normalize_text,
    parse_quantity,
    similarity_ratio,
    truncate,
)

__all__ = [
    # Phone
    "normalize_phone",
    "format_phone_display",
    "extract_ddd",
    "is_valid_brazilian_phone",
    "get_session_id_from_phone",
    # Text
    "make_fingerprint",
    "normalize_text",
    "truncate",
    "parse_quantity",
    "similarity_ratio",
    "find_best_match",
    "find_matches",
    "clean_whatsapp_formatting",
]
