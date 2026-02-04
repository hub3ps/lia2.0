from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    import psycopg
except ImportError:
    print("Erro: psycopg não está instalado. Instale com: pip install psycopg")
    sys.exit(1)

from app.services.interpreter.parser import parse_order_text
from app.services.interpreter.resolver import resolve_parsed_items
from app.services.interpreter.matcher import match_items
from app.utils.text import normalize_text

DATABASE_URL = os.getenv("DATABASE_URL", "")

TEST_1 = """1 X galinha com bacon
1 X galinha careca com batata palha cortado ao meio
2 maionese adicional
2 X galinha careca com bacon e milho
1 X Burger com coração 
1 X galinha sem ervilha e sem pepino
1 porção pequena de bata frita tradicional
1 guaraná 2 l"""

TEST_2 = """Ola boa noite, eu gostaria de 2 X salada e 1 X coracao para a rua lico amaral 110, pagamento no cartao na entrega, tudo bem?"""

TEST_3 = """Rua Tiradentes 
Número 125
Bairro Murta 
Próx. A praça do coreto...

2 x saladas completos"""

TEST_4 = """Boa Noite
1 X salada sem milho e sem  alface  
1 torrada de migon
1 coca cola de 2 litros"""

TEST_5 = """[22:17, 21/01/2026] +55 47 9630-5032: Boa Noite 
1  torrada de mignon
1 coca cola
[22:17, 21/01/2026] +55 47 9630-5032: Para entregar na rua Antônio peirao 171 bairro São Vicente
[22:17, 21/01/2026] +55 47 9630-5032: Quantos que deu"""

TEST_6 = """[21:51, 09/01/2026] +55 47 9630-5032: 1 X salada sem milho e sem alface 
1 X burg  
1 coca 2 lt
[21:51, 09/01/2026] +55 47 9630-5032: Troco para 100"""

TEST_7 = """Bia noite 
1 X salada sem milho  e sem alface 
1 X burg 
1 coca cola  de 2lt 
Troco para 100,00 
Entregar na rua Antônio peirao 171 bairro São Vicente"""

TEST_8 = """[19:02, 08/01/2026] +55 47 9671-6161: Oiii, gostaria de fazer um pedido
X galinha completo 
Xegg sem milho sem evilha e sem pepino 
Coca lata
Guaraná lata
[19:02, 08/01/2026] +55 47 9671-6161: Será que entrega até as 20?
[19:02, 08/01/2026] +55 47 9671-6161: Rua Nivaldo detoie, 143 Ressacada"""

TEST_9 = """olá boa noite
quero uma batata frita com queijo e bacon grande
e um suco de morango
pra entregar na rua urubici 58 são Vicente Itajaí
ok?"""

TEST_10 = """olá
vê  2 X frango ,1 X mignon grande e uma coca 2 litros
rua sergipe 20 paga na entrega blz no debito"""

TEST_11 = """[21:46, 05/12/2025] +55 47 9764-1694: Opa
[21:47, 05/12/2025] +55 47 9764-1694: Vê 1 X galinha e 1 X bacon
[21:48, 05/12/2025] +55 47 9764-1694: Rua Ismael Orlando Evaristo 169
[21:48, 05/12/2025] +55 47 9764-1694: Coca 600 tbm"""

TEST_12 = """Boa noite, gostaria  de um x galinha (bem passado) sem ervilha e pepino.
Rua Rio Araguaia 118 casa 2
Pix"""


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    return url


def _fetch_menu_subset(conn, terms: List[str]) -> List[Dict[str, Any]]:
    where_clause = " OR ".join(["nome_original ILIKE %s OR fingerprint ILIKE %s"] * len(terms))
    params: List[Any] = []
    for term in terms:
        like = f"%{term}%"
        params.extend([like, like])

    query_products = f"""
        select pdv, parent_pdv, nome_original, price, item_type, fingerprint
        from v_menu_search_index
        where item_type = 'product' and ({where_clause})
    """

    with conn.cursor() as cur:
        cur.execute(query_products, params)
        products = _rows_to_dicts(cur.fetchall())

    parent_pdvs = [p["pdv"] for p in products]
    additions: List[Dict[str, Any]] = []
    if parent_pdvs:
        with conn.cursor() as cur:
            cur.execute(
                """
                select pdv, parent_pdv, nome_original, price, item_type, fingerprint
                from v_menu_search_index
                where item_type = 'addition' and parent_pdv = ANY(%s)
                """,
                (parent_pdvs,),
            )
            additions = _rows_to_dicts(cur.fetchall())

    return products + additions


def _rows_to_dicts(rows):
    return [
        {
            "pdv": row[0],
            "parent_pdv": row[1],
            "nome_original": row[2],
            "price": row[3],
            "item_type": row[4],
            "fingerprint": row[5],
        }
        for row in rows
    ]


def _has_addition(item, name_substr: str) -> bool:
    needle = normalize_text(name_substr)
    return any(needle in normalize_text(add.nome) for add in item.adicionais)


def _obs_contains(item, text: str) -> bool:
    return text.lower() in (item.observacoes or "").lower()


def _has_item_pdv(items, pdv: str, qty: Optional[int] = None) -> bool:
    for item in items:
        if item.pdv == pdv and (qty is None or item.quantidade == qty):
            return True
    return False


def _has_item_name(items, needle: str, qty: Optional[int] = None) -> bool:
    needle = normalize_text(needle)
    for item in items:
        if needle in normalize_text(item.nome) and (qty is None or item.quantidade == qty):
            return True
    return False


def run_test(label: str, text: str, menu_index: List[Dict[str, Any]]) -> List[str]:
    failures: List[str] = []

    parsed = parse_order_text(text)
    resolved = resolve_parsed_items(parsed)
    result = match_items(resolved, menu_index, raw_text=text)

    print(f"\n=== {label} ===")
    print("RAW:")
    print(text)
    print("\nPARSED:")
    for p in parsed:
        print(
            f"- qty={p.quantity} name='{p.name}' additions={p.additions} removals={p.removals} notes={p.notes} "
            f"is_additional_only={p.is_additional_only} size_hint={p.size_hint}"
        )
    print("\nRESOLVED:")
    for r in resolved:
        print(
            f"- qty={r.quantity} match_text='{r.match_text}' additions={r.additions} removals={r.removals} notes={r.notes} "
            f"is_additional_only={r.is_additional_only} size_hint={r.size_hint}"
        )
    print("\nMATCHED ITEMS:")
    for item in result.items:
        adds = [(a.nome, a.pdv) for a in item.adicionais]
        print(
            f"- pdv={item.pdv} nome='{item.nome}' qty={item.quantidade} adds={adds} obs='{item.observacoes}'"
        )
    print("\nPENDENCIES:")
    for pend in result.pendencies:
        print(
            f"- motivo={pend.motivo.value} texto='{pend.texto_original}' sugestoes={pend.sugestoes}"
        )

    # --- Expectativas do Teste 1
    if label == "TEST_1":
        if len(result.items) != 7:
            failures.append(f"Esperado 7 itens, obtido {len(result.items)}.")

        # X Galinha + Bacon
        if not any(i.pdv == "23137416" and _has_addition(i, "bacon") for i in result.items):
            failures.append("Faltando X Galinha com Bacon.")

        # X Galinha careca + batata palha + cortado ao meio
        if not any(
            i.pdv == "23137416"
            and _has_addition(i, "batata palha")
            and _obs_contains(i, "sem: salada geral")
            and _obs_contains(i, "cortado ao meio")
            for i in result.items
        ):
            failures.append("Faltando X Galinha careca com batata palha + obs cortado ao meio.")

        # X Galinha careca + bacon + milho (qty 2)
        if not any(
            i.pdv == "23137416"
            and i.quantidade == 2
            and _has_addition(i, "bacon")
            and _has_addition(i, "milho")
            and _obs_contains(i, "sem: salada geral")
            for i in result.items
        ):
            failures.append("Faltando X Galinha careca com bacon e milho (qtd 2).")

        # X Galinha sem ervilha e pepino
        if not any(
            i.pdv == "23137416"
            and _obs_contains(i, "sem: ervilha")
            and _obs_contains(i, "pepino")
            for i in result.items
        ):
            failures.append("Faltando X Galinha sem ervilha e pepino.")

        # X Burguer + Coração
        if not any(i.pdv == "23137502" and _has_addition(i, "coração") for i in result.items):
            failures.append("Faltando X Burguer com Coração.")

        # Batata frita 1/4
        if not any(i.pdv == "23137573" for i in result.items):
            failures.append("Faltando Batata Frita (1/4 Porção).")

        # Guarana 2L
        if not any(i.pdv == "23172036" for i in result.items):
            failures.append("Faltando Guaraná 2 Litros.")

        # Pendência de maionese adicional
        if len(result.pendencies) != 1:
            failures.append(f"Esperado 1 pendência, obtido {len(result.pendencies)}.")
        else:
            pend = result.pendencies[0]
            if pend.motivo.value != "adicional_nao_encontrado":
                failures.append("Pendência não é ADICIONAL_NAO_ENCONTRADO.")
            if "maionese" not in pend.texto_original.lower():
                failures.append("Pendência não corresponde à maionese.")

        if not (result.confidence < 1.0):
            failures.append("Confiança deveria ser < 1.0.")

    # --- Expectativas do Teste 2
    if label == "TEST_2":
        if len(result.items) != 2:
            failures.append(f"Esperado 2 itens, obtido {len(result.items)}.")

        if not any(i.pdv == "23137463" and i.quantidade == 2 for i in result.items):
            failures.append("Faltando X Salada (qtd 2).")

        if not any(i.pdv == "23137438" and i.quantidade == 1 for i in result.items):
            failures.append("Faltando X Coração (qtd 1).")

        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

        if result.confidence < 0.9:
            failures.append("Confiança deveria ser alta (>= 0.9).")

    if label == "TEST_3":
        if not _has_item_pdv(result.items, "23137463", qty=2):
            failures.append("Faltando X Salada (qtd 2).")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_4":
        if not _has_item_pdv(result.items, "23137463", qty=1):
            failures.append("Faltando X Salada.")
        if not any(
            i.pdv == "23137463"
            and _obs_contains(i, "sem: milho")
            and _obs_contains(i, "alface")
            for i in result.items
        ):
            failures.append("X Salada sem milho e alface não identificado.")
        if not _has_item_pdv(result.items, "23137577", qty=1):
            failures.append("Faltando Torrada de Mignon.")
        if not _has_item_pdv(result.items, "23137491", qty=1):
            failures.append("Faltando Coca Cola 2 Litros.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_5":
        if not _has_item_pdv(result.items, "23137577", qty=1):
            failures.append("Faltando Torrada de Mignon.")
        if not _has_item_name(result.items, "coca cola", qty=1):
            failures.append("Faltando Coca Cola.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_6":
        if not _has_item_pdv(result.items, "23137463", qty=1):
            failures.append("Faltando X Salada.")
        if not _has_item_pdv(result.items, "23137502", qty=1):
            failures.append("Faltando X Burguer.")
        if not _has_item_pdv(result.items, "23137491", qty=1):
            failures.append("Faltando Coca Cola 2 Litros.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_7":
        if not _has_item_pdv(result.items, "23137463", qty=1):
            failures.append("Faltando X Salada.")
        if not _has_item_pdv(result.items, "23137502", qty=1):
            failures.append("Faltando X Burguer.")
        if not _has_item_pdv(result.items, "23137491", qty=1):
            failures.append("Faltando Coca Cola 2 Litros.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_8":
        if not _has_item_pdv(result.items, "23137416", qty=1):
            failures.append("Faltando X Galinha.")
        if not _has_item_pdv(result.items, "23137559", qty=1):
            failures.append("Faltando X Egg.")
        if not any(
            i.pdv == "23137559"
            and _obs_contains(i, "sem: milho")
            and _obs_contains(i, "ervilha")
            and _obs_contains(i, "pepino")
            for i in result.items
        ):
            failures.append("X Egg sem milho/ervilha/pepino não identificado.")
        if not _has_item_name(result.items, "coca cola lata", qty=1):
            failures.append("Faltando Coca Cola Lata.")
        if not _has_item_name(result.items, "guarana", qty=1):
            failures.append("Faltando Guaraná Lata.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_9":
        if not _has_item_name(result.items, "batata frita", qty=1):
            failures.append("Faltando Batata Frita.")
        if not _has_item_name(result.items, "bacon e queijo", qty=1):
            failures.append("Faltando Batata Frita com Bacon e Queijo.")
        if not _has_item_name(result.items, "suco morango", qty=1):
            failures.append("Faltando Suco de Morango.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_10":
        if not _has_item_name(result.items, "x frango", qty=2):
            failures.append("Faltando X Frango (qtd 2).")
        if not _has_item_name(result.items, "x mignon", qty=1):
            failures.append("Faltando X Mignon.")
        if not _has_item_pdv(result.items, "23137491", qty=1):
            failures.append("Faltando Coca Cola 2 Litros.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_11":
        if not _has_item_pdv(result.items, "23137416", qty=1):
            failures.append("Faltando X Galinha.")
        if not _has_item_pdv(result.items, "23137467", qty=1):
            failures.append("Faltando X Bacon.")
        if not _has_item_name(result.items, "coca cola 600", qty=1):
            failures.append("Faltando Coca Cola 600ml.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    if label == "TEST_12":
        if not _has_item_pdv(result.items, "23137416", qty=1):
            failures.append("Faltando X Galinha.")
        if not any(
            i.pdv == "23137416"
            and _obs_contains(i, "sem: ervilha")
            and _obs_contains(i, "pepino")
            and _obs_contains(i, "bem passado")
            for i in result.items
        ):
            failures.append("X Galinha sem ervilha/pepino e bem passado não identificado.")
        if len(result.pendencies) != 0:
            failures.append(f"Esperado 0 pendências, obtido {len(result.pendencies)}.")

    return failures

def main() -> int:
    db_url = _normalize_db_url(DATABASE_URL)

    terms = [
        "galinha",
        "salada",
        "bacon",
        "mignon",
        "torrada",
        "coracao",
        "burguer",
        "frango",
        "x egg",
        "batata frita",
        "guarana",
        "maionese",
        "coca",
        "suco",
        "morango",
    ]

    with psycopg.connect(db_url) as conn:
        menu_index = _fetch_menu_subset(conn, terms)

    failures = []
    failures.extend(run_test("TEST_1", TEST_1, menu_index))
    failures.extend(run_test("TEST_2", TEST_2, menu_index))
    failures.extend(run_test("TEST_3", TEST_3, menu_index))
    failures.extend(run_test("TEST_4", TEST_4, menu_index))
    failures.extend(run_test("TEST_5", TEST_5, menu_index))
    failures.extend(run_test("TEST_6", TEST_6, menu_index))
    failures.extend(run_test("TEST_7", TEST_7, menu_index))
    failures.extend(run_test("TEST_8", TEST_8, menu_index))
    failures.extend(run_test("TEST_9", TEST_9, menu_index))
    failures.extend(run_test("TEST_10", TEST_10, menu_index))
    failures.extend(run_test("TEST_11", TEST_11, menu_index))
    failures.extend(run_test("TEST_12", TEST_12, menu_index))

    if failures:
        print("FAIL")
        for fail in failures:
            print("-", fail)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
