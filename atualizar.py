#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Boletim Nova Casa - coletor diario
Le as manchetes da Revista Anamaco, feeds RSS e cotacoes do Banco Central,
e grava tudo em dados.js, que o painel HTML consome.

Uso:  python3 atualizar.py
Requisitos:  pip install requests beautifulsoup4
"""

import json, re, sys
from datetime import datetime, timedelta

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Faltam bibliotecas. Rode:  pip install requests beautifulsoup4")
    sys.exit(1)

from zoneinfo import ZoneInfo
HOJE = datetime.now(ZoneInfo("America/Sao_Paulo"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ----------------------------------------------------------------------
# 1. MANCHETES DA ANAMACO
# ----------------------------------------------------------------------
def buscar_manchetes(qtd=12):
    """Raspa a pagina de Noticias do Mercado da Revista Anamaco."""
    url = "https://www.revistaanamaco.com.br/noticias-online"
    try:
        r = requests.get(url, headers=UA, timeout=25)
        r.encoding = "utf-8"
        sopa = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print("  [!] Falha ao acessar a Anamaco:", e)
        return []

    noticias = []
    for h in sopa.find_all(["h2", "h3"]):
        a = h.find("a", href=True)
        if not a:
            continue
        titulo = a.get_text(strip=True)
        link = a["href"]
        if not titulo or len(titulo) < 15:
            continue

        candidatos = []
        if h.parent:
            candidatos.append(h.parent.get_text(" ", strip=True))
            if h.parent.parent:
                candidatos.append(h.parent.parent.get_text(" ", strip=True))
        vizinho = h.find_previous(string=re.compile(r"\d{2}/\d{2}/\d{4}"))
        if vizinho:
            candidatos.append(str(vizinho))

        data = ""
        for texto_busca in candidatos:
            m = re.search(r"(\d{2}/\d{2}/\d{4})", texto_busca)
            if m:
                data = m.group(1)
                break

        if not data:
            data = HOJE.strftime("%d/%m/%Y")

        resumo = ""
        prox = h.find_next("p")
        if prox:
            resumo = prox.get_text(" ", strip=True)
            resumo = re.sub(r"\s*Veja mais\s*$", "", resumo)
            if len(resumo) > 220:
                resumo = resumo[:217].rsplit(" ", 1)[0] + "..."

        if titulo not in [n["titulo"] for n in noticias]:
            noticias.append({
                "titulo": titulo,
                "data": data,
                "fonte": "Anamaco",
                "resumo": resumo,
                "link": link if link.startswith("http") else "https://www.revistaanamaco.com.br/" + link.lstrip("/"),
            })
        if len(noticias) >= qtd:
            break

    print(f"  [ok] {len(noticias)} manchetes capturadas")
    return noticias


# ----------------------------------------------------------------------
# 1b. OUTRAS FONTES VIA RSS (Valor, Forbes, InfoMoney, PlásticoNews)
# ----------------------------------------------------------------------
FONTES_RSS = [
    ("Valor",        "https://pox.globo.com/rss/valor/brasil/"),
    ("Forbes",       "https://forbes.com.br/feed/"),
    ("InfoMoney",    "https://www.infomoney.com.br/feed/"),
    ("PlásticoNews", "https://plasticonews.org/feed/"),
]

# Filtro de palavras-chave do setor
FILTRO = re.compile(
    r"\b(constru\w*|cimento\w*|aço\w*|siderurg\w*|tinta\w*|"
    r"material(is)? de constru\w*|habitaç\w*|imobiliári\w*|reforma da casa|"
    r"MCMV|Minha Casa Minha Vida|INCC|argamassa\w*|revestiment\w*|"
    r"hidráulic\w*|\bPVC\b|\bobra\b|obras de|canteiro de obras|"
    r"engenharia civil|incorporador\w*|construtora\w*|vergalhão|"
    r"vergalhões|alvenaria|cerâmic\w* (de piso|de revestimento)|"
    r"resina\w*|petroquímic\w*|termoplástic\w*|polímero\w*|tubo\w*|conexõe\w*)",
    re.I)

# Filtro de exclusao para remover temas irrelevantes
EXCLUI = re.compile(
    r"\b(médico|hospitalar|odontol|embalagem|automot|autopeca|cosmético|brinquedo)\b",
    re.I)

def buscar_rss(qtd_por_fonte=4):
    """Le os feeds RSS e devolve so o que interessa ao setor."""
    achados = []
    for nome, url in FONTES_RSS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            sopa = BeautifulSoup(r.content, "xml")
            itens = sopa.find_all("item")[:40]
        except Exception as e:
            print(f"  [!] RSS {nome} indisponivel:", e)
            continue

        n = 0
        for it in itens:
            titulo = it.title.get_text(strip=True) if it.title else ""
            if not titulo or not FILTRO.search(titulo) or EXCLUI.search(titulo):
                continue
            desc = ""
            if it.description:
                desc = BeautifulSoup(it.description.get_text(), "html.parser").get_text(" ", strip=True)
                if len(desc) > 220:
                    desc = desc[:217].rsplit(" ", 1)[0] + "..."
            data = ""
            if it.pubDate:
                try:
                    from email.utils import parsedate_to_datetime
                    data = parsedate_to_datetime(it.pubDate.get_text()).strftime("%d/%m/%Y")
                except Exception:
                    pass
            achados.append({
                "titulo": titulo, "data": data, "fonte": nome,
                "resumo": desc,
                "link": it.link.get_text(strip=True) if it.link else "",
            })
            n += 1
            if n >= qtd_por_fonte:
                break
        print(f"  [ok] {nome}: {n} materias do setor")
    return achados


# ----------------------------------------------------------------------
# 2. INDICADORES DO BANCO CENTRAL
# ----------------------------------------------------------------------
SERIES_BC = {
    "dolar":   1,      # dolar comercial venda
    "selic":   432,    # meta Selic % a.a.
    "ipca12": 13522,  # IPCA acumulado 12 meses
    "igpm12": 190,    # IGP-M acumulado 12 meses
}

def buscar_serie_bc(codigo, dias=20):
    """Busca o ultimo valor disponivel de uma serie do Banco Central."""
    ini = (HOJE - timedelta(days=dias)).strftime("%d/%m/%Y")
    fim = HOJE.strftime("%d/%m/%Y")
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={ini}&dataFinal={fim}")
    try:
        r = requests.get(url, headers=UA, timeout=20)
        dados = r.json()
        if not dados:
            return None, None
        ultimo = dados[-1]
        return float(ultimo["valor"].replace(",", ".")), ultimo["data"]
    except Exception as e:
        print(f"  [!] Serie {codigo} indisponivel:", e)
        return None, None


def buscar_indicadores_bc():
    out = {}
    for nome, cod in SERIES_BC.items():
        valor, data = buscar_serie_bc(cod)
        if valor is not None:
            out[nome] = {"valor": valor, "data": data}
            print(f"  [ok] {nome}: {valor} ({data})")
        else:
            print(f"  [--] {nome}: mantido o valor anterior")
    return out


# ----------------------------------------------------------------------
# 3. MONTA O ARQUIVO DE DADOS
# ----------------------------------------------------------------------
def carregar_anterior(caminho="dados.js"):
    """Le o dados.js atual para preservar o que e preenchido na mao."""
    try:
        txt = open(caminho, encoding="utf-8").read()
        bruto = txt.split("=", 1)[1].strip().rstrip(";")
        return json.loads(bruto)
    except Exception:
        return {}


def main():
    print("Boletim Nova Casa - coleta iniciada")
    anterior = carregar_anterior()

    print("\n> Manchetes da Anamaco")
    manchetes = buscar_manchetes()

    print("\n> Valor, Forbes, InfoMoney e PlásticoNews (RSS)")
    manchetes += buscar_rss()

    # remove duplicadas por titulo e ordena da mais recente para a mais antiga
    vistos, unicas = set(), []
    for m in manchetes:
        chave = m["titulo"].lower()[:60]
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(m)
    def ordem(m):
        try:
            return datetime.strptime(m.get("data", ""), "%d/%m/%Y")
        except Exception:
            return datetime(2000, 1, 1)
    manchetes = sorted(unicas, key=ordem, reverse=True)[:16]

    if not manchetes:
        manchetes = anterior.get("manchetes", [])

    print("\n> Indicadores do Banco Central")
    bc = buscar_indicadores_bc()

    # indicadores mensais preenchidos na mao (preserva o que ja existia)
    mensais = anterior.get("mensais", {
        "incc":     {"valor": "6,40", "unidade": "% em 12 meses", "ref": "jul/26", "fonte": "FGV Ibre"},
        "cimento": {"valor": "38,2M", "unidade": "ton no ano", "ref": "jan-jul/26", "fonte": "SNIC"},
        "termometro": {"alta": 40.3, "estavel": 41.3, "queda": 18.4, "ref": "1o sem/26", "fonte": "Anamaco"},
        "expectativa": {"valor": "68,7", "unidade": "% esperam crescer", "ref": "1o sem/26", "fonte": "Anamaco"},
    })

    dados = {
        "atualizado_em": HOJE.strftime("%d/%m/%Y %H:%M"),
        "manchetes": manchetes,
        "diarios": bc if bc else anterior.get("diarios", {}),
        "mensais": mensais,
    }

    with open("dados.js", "w", encoding="utf-8") as f:
        f.write("// Gerado automaticamente por atualizar.py - nao edite a mao\n")
        f.write("window.DADOS = ")
        json.dump(dados, f, ensure_ascii=False, indent=1)
        f.write(";\n")

    print(f"\nPronto. dados.js atualizado em {dados['atualizado_em']}")
    print(f"Manchetes: {len(manchetes)} | Indicadores diarios: {len(dados['diarios'])}")


if __name__ == "__main__":
    main()
