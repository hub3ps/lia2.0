"""
Order Interpreter - Matcher.

Faz match (fuzzy) entre os itens interpretados e o cardapio.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, DefaultDict, Dict, Iterable, List, Optional

from app.core.schemas import (
    CartItem,
    CartItemAddition,
    CartPendency,
    InterpretedOrder,
    PendencyReason,
)
from app.services.interpreter.parser import ParsedItem
from app.utils.text import find_best_match, find_matches, make_fingerprint, normalize_text


def match_items(
    items: List[ParsedItem],
    menu_index: List[Dict[str, Any]],
    raw_text: str = "",
) -> InterpretedOrder:
    """
    Recebe ParsedItem + menu_index e retorna InterpretedOrder.

    menu_index esperado (view v_menu_search_index):
    - pdv, parent_pdv, nome_original, price, item_type, fingerprint
    """
    products, additions_by_parent = _build_menu_index(menu_index)

    interpreted_items: List[CartItem] = []
    pendencies: List[CartPendency] = []

    for item in items:
        if item.is_additional_only:
            pendencies.append(_pendency_for_additional_only(item, products))
            continue

        product = _match_product(item, products)
        if not product:
            pendencies.append(_pendency_for_missing_product(item, products))
            continue

        additions = _match_additions(item, additions_by_parent.get(product["pdv"], []), pendencies, product)
        observacoes = _build_observacoes(item)

        cart_item = CartItem(
            pdv=product["pdv"],
            nome=product["nome_original"],
            quantidade=item.quantity,
            preco_unitario=_to_decimal(product.get("price")),
            adicionais=additions,
            observacoes=observacoes,
        )
        interpreted_items.append(cart_item)

    confidence = _compute_confidence(pendencies)
    return InterpretedOrder(
        items=interpreted_items,
        pendencies=pendencies,
        raw_text=raw_text,
        confidence=confidence,
    )


def _build_menu_index(
    menu_index: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], DefaultDict[Optional[str], List[Dict[str, Any]]]]:
    products: List[Dict[str, Any]] = []
    additions_by_parent: DefaultDict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)

    for entry in menu_index:
        item_type = entry.get("item_type")
        if item_type == "product":
            products.append(entry)
        elif item_type == "addition":
            additions_by_parent[entry.get("parent_pdv")].append(entry)

    return products, additions_by_parent


def _match_product(item: ParsedItem, products: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    query = item.match_text or item.name
    query_fp = make_fingerprint(query)

    # Exact fingerprint match
    exact = [p for p in products if p.get("fingerprint") == query_fp]
    if len(exact) == 1:
        return exact[0]

    query_norm = normalize_text(query)

    # Batata frita com bacon/queijo: filtra por tokens para evitar escolher "batata frita" simples
    if "batata frita" in query_norm and ("bacon" in query_norm or "queijo" in query_norm):
        required_tokens = []
        if "bacon" in query_norm:
            required_tokens.append("bacon")
        if "queijo" in query_norm:
            required_tokens.append("queijo")

        filtered: List[Dict[str, Any]] = []
        for p in products:
            name_norm = normalize_text(p.get("nome_original", ""))
            if "batata frita" in name_norm and all(token in name_norm for token in required_tokens):
                filtered.append(p)
        if filtered:
            if item.size_hint:
                filtered = _filter_by_size_hint(filtered, item.size_hint)
            candidate = _best_match(query, filtered)
            if candidate:
                return candidate

    # Suco de morango: filtra por sabor para evitar match errado
    if "suco" in query_norm and "morango" in query_norm:
        filtered = [
            p
            for p in products
            if "suco" in normalize_text(p.get("nome_original", ""))
            and "morango" in normalize_text(p.get("nome_original", ""))
        ]
        if filtered:
            candidate = _best_match(query, filtered)
            if candidate:
                return candidate

    # Prefer plain "batata frita" when query says tradicional
    if "batata frita" in query_norm and "tradicional" in query_norm:
        filtered = _filter_plain_batata(products)
        if item.size_hint:
            filtered = _filter_by_size_hint(filtered, item.size_hint)
        candidate = _best_match(query, filtered)
        if candidate:
            return candidate

    # Size hint for batata frita
    if item.size_hint and "batata frita" in query_norm:
        filtered = _filter_by_size_hint(products, item.size_hint)
        candidate = _best_match(query, filtered)
        if candidate:
            return candidate

    return _best_match(query, products)


def _best_match(query: str, products: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not products:
        return None
    names = [p.get("nome_original", "") for p in products]
    match_name, _score = find_best_match(query, names, threshold=0.6)
    if not match_name:
        return None
    for p in products:
        if p.get("nome_original") == match_name:
            return p
    return None


def _filter_by_size_hint(products: List[Dict[str, Any]], size_hint: str) -> List[Dict[str, Any]]:
    tokens = []
    if size_hint == "1/4":
        tokens = ["1/4", "1/4 por", "1/4 porcao"]
    elif size_hint == "1/2":
        tokens = ["meia", "1/2"]

    filtered: List[Dict[str, Any]] = []
    for p in products:
        name_norm = normalize_text(p.get("nome_original", ""))
        if any(token in name_norm for token in tokens):
            filtered.append(p)
    return filtered or products


def _filter_plain_batata(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    forbidden = ["bacon", "queijo", "calabresa", "frango", "cheddar", "coracao", "catupiry", "mussarela", "tres"]
    filtered: List[Dict[str, Any]] = []
    for p in products:
        name_norm = normalize_text(p.get("nome_original", ""))
        if "batata frita" in name_norm and not any(word in name_norm for word in forbidden):
            filtered.append(p)
    return filtered or products


def _match_additions(
    item: ParsedItem,
    additions: List[Dict[str, Any]],
    pendencies: List[CartPendency],
    product: Dict[str, Any],
) -> List[CartItemAddition]:
    results: List[CartItemAddition] = []
    if not item.additions:
        return results

    for addition_text in item.additions:
        matched = _match_addition(addition_text, additions)
        if not matched:
            pendencies.append(
                CartPendency(
                    motivo=PendencyReason.ADICIONAL_NAO_ENCONTRADO,
                    texto_original=addition_text,
                    sugestoes=_suggest_additions(addition_text, additions),
                    dados_extras={"produto_base": product.get("nome_original")},
                )
            )
            continue

        results.append(
            CartItemAddition(
                pdv=matched["pdv"],
                nome=_clean_addition_name(matched.get("nome_original", "")),
                quantidade=1,
                preco_unitario=_to_decimal(matched.get("price")),
            )
        )
    return results


def _match_addition(text: str, additions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not additions:
        return None

    query_fp = make_fingerprint(text)
    for entry in additions:
        label_fp = make_fingerprint(_addition_label(entry))
        if label_fp == query_fp:
            return entry

    # fallback fuzzy
    labels = [_addition_label(a) for a in additions]
    match_name, _score = find_best_match(text, labels, threshold=0.6)
    if not match_name:
        return None
    for entry in additions:
        if _addition_label(entry) == match_name:
            return entry
    return None


def _addition_label(entry: Dict[str, Any]) -> str:
    name = normalize_text(entry.get("nome_original", ""))
    name = name.replace("adicionais no prato", "").replace("adicionais", "")
    return name.strip()


def _clean_addition_name(name: str) -> str:
    cleaned = name.replace("Adicionais ", "").replace("Adicionais no Prato ", "")
    return cleaned.strip()


def _pendency_for_additional_only(item: ParsedItem, products: List[Dict[str, Any]]) -> CartPendency:
    suggestions = _suggest_products(item.name, products)
    return CartPendency(
        motivo=PendencyReason.ADICIONAL_NAO_ENCONTRADO,
        texto_original=item.raw,
        sugestoes=suggestions,
        dados_extras={"quantidade": item.quantity, "adicional": item.name},
    )


def _pendency_for_missing_product(item: ParsedItem, products: List[Dict[str, Any]]) -> CartPendency:
    suggestions = _suggest_products(item.match_text or item.name, products)
    return CartPendency(
        motivo=PendencyReason.PRODUTO_NAO_ENCONTRADO,
        texto_original=item.raw,
        sugestoes=suggestions,
        dados_extras={"quantidade": item.quantity},
    )


def _suggest_products(query: str, products: List[Dict[str, Any]]) -> List[str]:
    names = [p.get("nome_original", "") for p in products]
    matches = find_matches(query, names, threshold=0.6, limit=5)
    return [m[0] for m in matches]


def _suggest_additions(query: str, additions: List[Dict[str, Any]]) -> List[str]:
    labels = [_addition_label(a) for a in additions]
    matches = find_matches(query, labels, threshold=0.6, limit=5)
    return [m[0] for m in matches]


def _build_observacoes(item: ParsedItem) -> str:
    parts: List[str] = []
    if item.removals:
        parts.append("Sem: " + ", ".join(item.removals))
    if item.notes:
        parts.append("Obs: " + ", ".join(item.notes))
    return " | ".join(parts)


def _compute_confidence(pendencies: Iterable[CartPendency]) -> float:
    count = len(list(pendencies))
    return max(0.1, 1.0 - (0.2 * count))


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


__all__ = [
    "match_items",
]
