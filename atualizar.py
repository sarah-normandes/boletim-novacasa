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
    ("Valor",         "https://pox.globo.com/rss/valor/brasil/"),
    ("Forbes",        "https://forbes.com.br/feed/"),
    ("InfoMoney",     "https://www.infomoney.com.br/feed/"),
    ("PlásticoNews",  "https://plasticonews.org/feed/"),
    # fontes do setor de construcao (WordPress, padrao /feed/). O robo
    # ignora automaticamente qualquer feed que nao responder ou vier vazio,
    # entao candidatos que sairem do ar nao quebram a coleta.
    ("CBIC",          "https://cbic.org.br/feed/"),
    ("O Empreiteiro", "https://revistaoe.com.br/feed/"),
    ("Cimento",       "https://www.cimento.org/feed/"),
    ("MoneyTimes",    "https://www.moneytimes.com.br/feed/"),
    ("ABRAMAT",       "https://abramat.org.br/feed/"),
    # Investing.com: mercado/bolsa. Costuma bloquear robos; se falhar, o robo
    # ignora e segue. So entram materias relacionadas ao setor (passa pelo FILTRO).
    ("Investing",     "https://br.investing.com/rss/news_25.rss"),
]

# Filtro de palavras-chave do setor
FILTRO = re.compile(
    r"\b(constru\w*|cimento\w*|aço\w*|siderurg\w*|tinta\w*|"
    r"material(is)? de constru\w*|habitaç\w*|imobiliári\w*|reforma da casa|"
    r"MCMV|Minha Casa Minha Vida|INCC|argamassa\w*|revestiment\w*|"
    r"hidráulic\w*|\bPVC\b|\bobra\b|obras de|canteiro de obras|"
    r"engenharia civil|incorporador\w*|construtora\w*|vergalhão|"
    r"vergalhões|alvenaria|cerâmic\w* (de piso|de revestimento)|"
    r"resina\w*|petroquímic\w*|termoplástic\w*|polímero\w*|tubo\w*|conexõe\w*|"
    r"polietileno|polipropileno|\bPP\b|\bPE\b|\bPEAD\b|\bPEBD\b)",
    re.I)

# Filtro de exclusao para remover temas irrelevantes
EXCLUI = re.compile(
    r"\b(médico|hospitalar|odontol|embalagem|automot|autopeca|cosmético|brinquedo)\b"
    r"|tintas? de impress|flexografia|rotogravura|nitrocelulose|ABITIM|"
    r"coninflex|r[oó]tulo|label|artes? gráfica",
    re.I)

# ----------------------------------------------------------------------
# B2. CLASSIFICACAO POR ABA TEMATICA
# ----------------------------------------------------------------------
# cada noticia recebe uma etiqueta 'aba' conforme o assunto, para o painel
# distribuir as noticias entre as telas (insumos, custos, demanda) em vez de
# jogar tudo so na aba de manchetes.
TEMA_INSUMOS = re.compile(
    r"(aço|aco\b|siderurg|cimento|tinta|pvc|resina|polietileno|polipropileno|"
    r"petroquímic|petroquimic|alumíni|alumini|cobre|argamassa|revestiment|"
    r"cerâmic|ceramic|hidráulic|hidraulic|\btubo|conexõe|conexoe|vergalhã|vergalho|"
    r"insumo|material de constru|matéria-prima|materia-prima)", re.I)
TEMA_CUSTOS = re.compile(
    r"(selic|juro|câmbio|cambio|dólar|dolar|frete|diesel|combustív|combustiv|"
    r"antidumping|importaç|importac|exportaç|exportac|tarifa|imposto|"
    r"tributár|tributar|inflaç|inflac|ipca|igp|incc|custo|energia|petróleo|petroleo)", re.I)
TEMA_DEMANDA = re.compile(
    r"(venda|consumo|demanda|mcmv|minha casa|habitaç|habitac|financiament|"
    r"crédito|credito|\bobra|lançament|lancament|imobiliári|imobiliari|construtora|"
    r"incorporador|\bpib\b|emprego|vaga|caged|varejo|confianç|confianc|expectativa|"
    r"faturar|faturament|índice abramat|indice abramat|termômetro|termometro|"
    r"indústria de materiais|industria de materiais|atividade do setor|"
    r"desempenho do setor|conjuntura|nível de atividade|nivel de atividade)", re.I)

def classificar_aba(titulo, resumo=""):
    """Devolve a aba tematica ('insumos'|'custos'|'demanda'|'geral') da noticia."""
    t = (titulo or "") + " " + (resumo or "")
    # ordem de prioridade: insumos e custos sao mais especificos que demanda
    if TEMA_INSUMOS.search(t):
        return "insumos"
    if TEMA_CUSTOS.search(t):
        return "custos"
    if TEMA_DEMANDA.search(t):
        return "demanda"
    return "geral"


# ----------------------------------------------------------------------
# FILTRO DE CONTEUDO EXCLUSIVO PARA ASSINANTES (paywall)
# ----------------------------------------------------------------------
# Alguns feeds (Valor, InfoMoney, etc.) marcam materias pagas com selos no
# titulo/resumo ou em categorias do RSS. O painel e para exibicao publica na
# loja, entao materia que o cliente nao consegue abrir nao deve aparecer.
PAYWALL = re.compile(
    r"(para\s+assinantes|conte[úu]do\s+exclusivo|exclusivo\s+para\s+assinantes|"
    r"assine\s+o|assine\s+j[áa]|seja\s+assinante|continue\s+lendo|"
    r"leia\s+na\s+[íi]ntegra|acesso\s+exclusivo|somente\s+para\s+assinantes|"
    r"conte[úu]do\s+pago|conte[úu]do\s+premium|vers[ãa]o\s+premium|assinante[s]?\s+premium|"
    r"paywall|subscriber\s+only|🔒|🔓)", re.I)

# termo isolado que, se aparecer numa CATEGORIA do RSS, ja indica paywall
PAYWALL_CAT = re.compile(r"\b(assinante[s]?|exclusivo|premium|pago)\b", re.I)

def eh_assinante(it, titulo, desc):
    """True se a materia parece ser conteudo pago/exclusivo de assinante."""
    # 1) selo no titulo ou no resumo
    if PAYWALL.search(titulo) or PAYWALL.search(desc):
        return True
    # 2) categorias do RSS que indicam paywall
    try:
        cats = " ".join(c.get_text(" ", strip=True) for c in it.find_all("category"))
        if PAYWALL_CAT.search(cats):
            return True
    except Exception:
        pass
    # 3) resumo vazio ou minusculo costuma ser materia cortada por paywall
    if desc and len(desc.strip()) < 15:
        return True
    return False


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
            # descarta conteudo exclusivo para assinantes (paywall)
            if eh_assinante(it, titulo, desc):
                continue
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
    "selic":   432,    # meta Selic % a.a.
    "ipca12": 13522,  # IPCA acumulado 12 meses
    "igpm12": 190,    # IGP-M acumulado 12 meses
}

def buscar_dolar_awesome():
    """Cotacao do dolar via AwesomeAPI (mesma fonte do painel de cobre, para
    os valores baterem lado a lado). Retorna (valor_venda, data)."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        d = r.json().get("USDBRL", {})
        valor = float(d.get("bid") or d.get("ask"))  # bid = compra, referencia
        # timestamp vem em epoch; converte para data BR
        ts = d.get("timestamp")
        from datetime import datetime as _dt
        data = _dt.fromtimestamp(int(ts), ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y") if ts else HOJE.strftime("%d/%m/%Y")
        return valor, data
    except Exception as e:
        print("  [!] Dolar (AwesomeAPI) indisponivel:", e)
        return None, None

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


def historico_selic(n=60):
    """Le os ultimos n valores da Selic meta (serie 432) direto da API do BC
    e devolve (atual, anterior_diferente, data_da_mudanca).

    A serie 432 e diaria e repete o mesmo valor ate o Copom mudar. Para
    detectar 'o corte' de verdade, pegamos o valor mais recente e recuamos
    ate achar o primeiro valor DIFERENTE dele: essa e a taxa antiga, e a
    data em que o valor atual comecou e a data da decisao.

    Nao depende de comparar entre execucoes do robo, entao pega a variacao
    real mesmo que o robo so tenha rodado depois da reuniao.
    """
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/"
           f"ultimos/{n}?formato=json")

    # tudo dentro de um try amplo: se qualquer coisa falhar (rede, formato
    # inesperado, valor invalido), a funcao devolve None e o robo segue sem
    # o insight, em vez de quebrar a coleta inteira.
    try:
        r = requests.get(url, headers=UA, timeout=25)
        dados = r.json()

        # a API as vezes devolve um dict em vez de lista; normaliza para lista
        if isinstance(dados, dict):
            dados = list(dados.values())
        if not isinstance(dados, list) or not dados:
            return None, None, None

        def num(d):
            v = d.get("valor") if isinstance(d, dict) else None
            if v is None:
                return None
            return float(str(v).replace(",", "."))

        def dia(d):
            return d.get("data") if isinstance(d, dict) else None

        atual = num(dados[-1])
        if atual is None:
            return None, None, None
        data_mudanca = dia(dados[-1])
        anterior = None
        # recua achando o primeiro valor diferente do atual; a data em que o
        # valor atual aparece pela primeira vez e a data da mudanca
        for d in reversed(dados[:-1]):
            v = num(d)
            if v is None:
                continue
            if abs(v - atual) < 1e-9:
                data_mudanca = dia(d)  # atual ja valia aqui: recua a data de inicio
            else:
                anterior = v
                break
        return atual, anterior, data_mudanca
    except Exception as e:
        print("  [!] Historico Selic indisponivel:", e)
        return None, None, None


def buscar_indicadores_bc():
    out = {}
    # dolar pela AwesomeAPI (alinhado ao painel de cobre)
    dv, dd = buscar_dolar_awesome()
    if dv is not None:
        out["dolar"] = {"valor": dv, "data": dd}
        print(f"  [ok] dolar (AwesomeAPI): {dv} ({dd})")
    else:
        print("  [--] dolar: mantido o valor anterior")
    # demais series (selic, ipca, igpm) seguem no Banco Central
    for nome, cod in SERIES_BC.items():
        valor, data = buscar_serie_bc(cod)
        if valor is not None:
            out[nome] = {"valor": valor, "data": data}
            print(f"  [ok] {nome}: {valor} ({data})")
        else:
            print(f"  [--] {nome}: mantido o valor anterior")
    return out


def insight_selic(bc_atual=None):
    """Gera uma manchete sobre a Selic ja traduzida para o nosso setor.

    Usa a variacao REAL da serie 432 da API do BC (via historico_selic):
    compara o valor vigente com o ultimo valor diferente antes dele. Assim
    detecta o corte/alta de verdade, sem depender de quando o robo rodou.
    Se a API do historico falhar, cai para o valor ja coletado em bc_atual
    e trata como 'patamar mantido' (fallback seguro).
    """
    atual, anterior, data_mud = historico_selic()

    # fallback: se o historico falhou mas ja temos a Selic da coleta normal
    if atual is None:
        atual = (bc_atual or {}).get("selic", {}).get("valor")
        anterior = None
    if atual is None:
        return None

    # formata no padrao brasileiro (14 ou 14,25 em vez de 14.0 / 14.25)
    fmt = lambda v: (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")
    taxa = fmt(atual)

    if anterior is not None and atual < anterior:
        variacao = fmt(anterior - atual)
        titulo = f"Copom corta Selic para {taxa}% ao ano"
        resumo = (f"Reducao de {variacao} ponto leva a taxa basica a {taxa}%. "
                  f"Queda de juros tende a destravar credito imobiliario e "
                  f"financiamento de obra, aquecendo a demanda por material de "
                  f"construcao. Momento favoravel para girar estoque e negociar "
                  f"prazo com fornecedor.")
    elif anterior is not None and atual > anterior:
        variacao = fmt(atual - anterior)
        titulo = f"Copom eleva Selic para {taxa}% ao ano"
        resumo = (f"Alta de {variacao} ponto leva a taxa basica a {taxa}%. "
                  f"Juro mais caro pesa sobre a decisao de reforma e construcao "
                  f"e encarece o credito. Tende a esfriar a demanda no varejo de "
                  f"material; atencao ao custo de estoque parado.")
    else:
        titulo = f"Selic mantida em {taxa}% ao ano"
        resumo = (f"Taxa basica segue em {taxa}%, sem mudanca na ultima decisao "
                  f"do Copom. Custo do credito estavel: sem novo estimulo nem "
                  f"freio para reforma e construcao no curto prazo; planejamento "
                  f"de compra segue o cenario atual.")

    return {
        "titulo": titulo,
        "data": HOJE.strftime("%d/%m/%Y"),
        "fonte": "Banco Central",
        "aba": "custos",
        "resumo": resumo,
        "link": "https://www.bcb.gov.br/controleinflacao/historicotaxasjuros",
    }


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

    # etiqueta cada manchete com sua aba tematica (insumos/custos/demanda/geral)
    for m in manchetes:
        m["aba"] = classificar_aba(m.get("titulo", ""), m.get("resumo", ""))

    if not manchetes:
        manchetes = anterior.get("manchetes", [])

    print("\n> Indicadores do Banco Central")
    bc = buscar_indicadores_bc()

    # insight estrategico da Selic, ligado ao nosso setor, entra como
    # manchete de fonte "Banco Central" no topo do giro de noticias
    insight = insight_selic(bc)
    if insight:
        manchetes = [insight] + [m for m in manchetes
                                 if m.get("fonte") != "Banco Central"]
        manchetes = manchetes[:16]
        print(f"  [ok] insight Selic: {insight['titulo']}")

    # indicadores mensais preenchidos na mao (preserva o que ja existia)
    mensais = anterior.get("mensais", {
        "incc":     {"valor": "6,40", "unidade": "% em 12 meses", "ref": "jul/26", "fonte": "FGV Ibre"},
        "cimento": {"valor": "38,2M", "unidade": "ton no ano", "ref": "jan-jul/26", "fonte": "SNIC"},
        "termometro": {"alta": 40.3, "estavel": 41.3, "queda": 18.4, "ref": "1o sem/26", "fonte": "Anamaco"},
        "expectativa": {"valor": "68,7", "unidade": "% esperam crescer", "ref": "1o sem/26", "fonte": "Anamaco"},
        # ABRAMAT: preenchimento manual mensal (indice sai em PDF, sem API).
        # Dados de junho/2026, ultima divulgacao publica.
        "abramat_indice": {"valor": "1,9", "unidade": "% no mes (jun vs mai)", "acumulado": "-3,4% no 1o sem", "ref": "jun/26", "fonte": "ABRAMAT"},
        "abramat_termometro": {"valor": "62", "unidade": "% pretendem investir", "ref": "jan/26", "fonte": "ABRAMAT"},
        "abramat_projecao": {"valor": "0,5", "unidade": "% projecao 2026", "ref": "revisado jul/26", "fonte": "ABRAMAT"},
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
