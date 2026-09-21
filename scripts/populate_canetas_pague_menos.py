"""Povoa a tabela caneta_insulina com canetas de insulina vendidas na Pague Menos.

Busca os produtos na API pública da Pague Menos (VTEX), filtra apenas
apresentações em caneta/refil e grava nome, fabricante, preco e descricao no
banco. Se a API estiver indisponivel, usa o snapshot em
data/canetas_pague_menos.json como fallback.

Uso:
    python -m scripts.populate_canetas_pague_menos [--fonte api|arquivo]
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import requests
from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.models import CanetaInsulina

BASE_URL = "https://www.paguemenos.com.br/api/catalog_system/pub/products/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; reposicao-bd-insulina/1.0)"}
PAGE_SIZE = 50

CATEGORY_PATH = "medicamentos-e-saude/diabetes/insulina"

PEN_KEYWORDS = [
    "caneta", "flexpen", "flex pen", "kwikpen", "kwik pen", "solostar",
    "refil", "innolet", "penfill", "pen fill",
]

BRAND_KEYWORDS = [
    "lantus", "basaglar", "humalog", "humulin", "novolin", "novorapid",
    "levemir", "apidra", "toujeo", "fiasp", "tresiba", "novomix",
    "xultophy", "soliqua", "afrezza", "glargilin", "ryzodeg",
]

BRAND_MANUFACTURER_FALLBACK = {
    "novomix": "Novo Nordisk",
}

TAG_RE = re.compile(r"<[^>]+>")
MANUFACTURER_RE = re.compile(r"Fabricado por:</strong>\s*(?:<a[^>]*>)?([^<]+)", re.I)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "canetas_pague_menos.json"


def _normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower()


def _clean_html(html):
    if not html:
        return ""
    text = TAG_RE.sub(" ", html)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _fetch_all(url, params):
    products = {}
    from_idx = 0
    while True:
        params.update({"_from": from_idx, "_to": from_idx + PAGE_SIZE - 1})
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if response.status_code not in (200, 206):
            response.raise_for_status()
        page = response.json()
        if not page:
            break
        for product in page:
            products[product["productId"]] = product
        if len(page) < PAGE_SIZE:
            break
        from_idx += PAGE_SIZE
    return products


def _is_medicamento(product):
    valor = product.get("Medicamento")
    return bool(valor) and valor[0] == "True"


def _is_insulina(product):
    nome = _normalize(product.get("productName", ""))
    substancia = _normalize((product.get("NomeSubstanciaPrincipioAtivo") or [""])[0])
    if "insulin" in substancia:
        return True
    return any(marca in nome for marca in BRAND_KEYWORDS)


def _is_caneta(product):
    nome = _normalize(product.get("productName", ""))
    return any(palavra in nome for palavra in PEN_KEYWORDS)


def _extrai_fabricante(descricao_html, marca):
    match = MANUFACTURER_RE.search(descricao_html or "")
    if match:
        return _clean_html(match.group(1)).rstrip(". ")
    return BRAND_MANUFACTURER_FALLBACK.get((marca or "").lower(), marca)


def _extrai_preco(product):
    try:
        return product["items"][0]["sellers"][0]["commertialOffer"]["Price"]
    except (KeyError, IndexError):
        return None


def buscar_canetas_na_api():
    produtos = {}
    produtos.update(_fetch_all(f"{BASE_URL}/{CATEGORY_PATH}", {"map": "c,c,c"}))
    produtos.update(_fetch_all(f"{BASE_URL}/insulina", {}))

    canetas = []
    for product in produtos.values():
        if not (_is_medicamento(product) and _is_insulina(product) and _is_caneta(product)):
            continue
        preco = _extrai_preco(product)
        if preco is None:
            continue
        descricao_html = product.get("description") or ""
        descricao_limpa = _clean_html(descricao_html)
        canetas.append({
            "nome": product["productName"],
            "fabricante": _extrai_fabricante(descricao_html, product.get("brand")),
            "preco": preco,
            "descricao": descricao_limpa[:400] or product["productName"],
            "fonte_url": product.get("link"),
        })
    return canetas


def carregar_canetas_do_arquivo():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def povoar(canetas):
    if not canetas:
        print("Nenhuma caneta de insulina encontrada, nada foi gravado.")
        return

    with SessionLocal() as session:
        for caneta in canetas:
            stmt = insert(CanetaInsulina).values(**caneta)
            stmt = stmt.on_conflict_do_update(
                index_elements=[CanetaInsulina.fonte_url],
                set_={
                    "nome": stmt.excluded.nome,
                    "fabricante": stmt.excluded.fabricante,
                    "preco": stmt.excluded.preco,
                    "descricao": stmt.excluded.descricao,
                },
            )
            session.execute(stmt)
        session.commit()

    print(f"{len(canetas)} canetas de insulina gravadas/atualizadas no banco.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fonte",
        choices=["api", "arquivo"],
        default="api",
        help="de onde ler os produtos: 'api' (Pague Menos, ao vivo) ou 'arquivo' (snapshot em data/)",
    )
    args = parser.parse_args()

    if args.fonte == "arquivo":
        canetas = carregar_canetas_do_arquivo()
    else:
        try:
            canetas = buscar_canetas_na_api()
        except requests.RequestException as erro:
            print(f"Falha ao consultar a API da Pague Menos ({erro}); usando snapshot local.", file=sys.stderr)
            canetas = carregar_canetas_do_arquivo()

    povoar(canetas)


if __name__ == "__main__":
    main()
