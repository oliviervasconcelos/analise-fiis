# -*- coding: utf-8 -*-
"""
dados.py - CAPTURA DE DADOS do site de FIIs
===========================================

Todas as funções que buscam informação na internet ficam aqui. Cada uma usa
o cache do Streamlit (st.cache_data) com um tempo de validade (ttl), para que
o site não baixe tudo de novo a cada clique:

  Fonte                          | O que fornece                         | Cache
  -------------------------------|---------------------------------------|-------
  Fundamentus (fii_resultado)    | lista de TODOS os FIIs, segmento,     | 1 h
                                 | DY, P/VP, liquidez, vacância etc.     |
  Fundamentus (detalhes.php)     | nome, mandato, gestão, VP/cota,       | 1 h
                                 | dividendo/cota 12m de um FII          |
  Yahoo Finance (yfinance)       | cotação atual (~15 min de atraso),    | 5 min
                                 | histórico de preços e dividendos      |
  CVM - Informe Mensal de FII    | composição dos ativos (papel/tijolo/  | 24 h
                                 | FoF), cotistas, PL, taxa de adm.      |
  Banco Central - Focus (Olinda) | expectativa de IPCA para 12 meses     | 6 h
  Banco Central - SGS            | IPCA 12m realizado, CDI diário        | 6 h
  Tesouro Transparente           | taxas do Tesouro IPCA+ (diárias)      | 6 h
"""
import io
import logging
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# Silencia mensagens técnicas do yfinance (códigos sem negociação, etc.)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Alguns sites recusam requisições sem um "navegador" identificado
CABECALHO = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

BENCHMARK = "XFIX11"   # ETF que replica o IFIX (índice de FIIs da B3)


# -----------------------------------------------------------------------------
# Funções auxiliares
# -----------------------------------------------------------------------------
def _pct(valor):
    """Converte textos como '13,49%' em número decimal (0.1349)."""
    if pd.isna(valor):
        return np.nan
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(texto) / 100
    except ValueError:
        return np.nan


def _baixar_html(url):
    """Baixa uma página do Fundamentus (que usa codificação ISO-8859-1)."""
    resposta = requests.get(url, headers=CABECALHO, timeout=30)
    resposta.raise_for_status()
    return resposta.content.decode("iso-8859-1")


# -----------------------------------------------------------------------------
# PLANO B: cópia local dos dados
# -----------------------------------------------------------------------------
# Toda captura bem-sucedida grava uma cópia em dados_salvos/. Se a fonte estiver
# fora do ar (ou sem internet), o site usa a última cópia e avisa a data dela.
PASTA_COPIAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_salvos")


def _com_copia_local(nome, baixar):
    """Executa 'baixar()'. Se der certo, salva a cópia e devolve (dados, "online").
    Se falhar ou vier vazio, devolve (cópia salva, "cópia de dd/mm hh:mm")."""
    caminho = os.path.join(PASTA_COPIAS, f"{nome}.csv")
    try:
        tabela = baixar()
        if tabela is None or tabela.empty:
            raise ValueError("fonte devolveu dados vazios")
        try:
            os.makedirs(PASTA_COPIAS, exist_ok=True)
            tabela.to_csv(caminho)
        except OSError:
            pass
        return tabela, "online"
    except Exception:
        if not os.path.exists(caminho):
            raise
        quando = datetime.fromtimestamp(os.path.getmtime(caminho))
        return pd.read_csv(caminho, index_col=0), f"cópia de {quando:%d/%m/%Y %H:%M}"


@st.cache_data(ttl=3600, show_spinner="Baixando a lista de FIIs no Fundamentus...")
def carregar_lista_fiis():
    """Lista de todos os FIIs (Fundamentus). Retorna (tabela, origem)."""
    return _com_copia_local("fundamentus", _baixar_lista_fiis)


@st.cache_data(ttl=24 * 3600, show_spinner="Baixando o Informe Mensal dos FIIs na CVM...")
def carregar_cvm():
    """Composição e cadastro dos FIIs (CVM). Retorna (tabela, origem)."""
    return _com_copia_local("cvm", _baixar_cvm)


@st.cache_data(ttl=300, show_spinner="Atualizando cotações e dividendos no Yahoo Finance (~20 s)...")
def carregar_mercado(tickers):
    """Cotações e métricas de 1 ano (Yahoo). Retorna (tabela, horário, origem)."""
    momento = {}

    def baixar():
        tabela, momento["hora"] = _baixar_mercado(tickers)
        return tabela

    tabela, origem = _com_copia_local("mercado", baixar)
    if origem != "online":
        momento["hora"] = datetime.fromtimestamp(os.path.getmtime(os.path.join(PASTA_COPIAS, "mercado.csv")))
    return tabela, momento["hora"], origem


# -----------------------------------------------------------------------------
# 1. Lista de todos os FIIs (Fundamentus)
# -----------------------------------------------------------------------------
def _baixar_lista_fiis():
    """Tabela com todos os FIIs negociados na B3 e seus indicadores.

    O Fundamentus não informa diretamente o dividendo em R$ nem o valor
    patrimonial por cota, mas eles podem ser deduzidos:
        Dividendo 12m (R$) = Dividend Yield x Cotação
        VP por cota (R$)   = Cotação / (P/VP)
    Assim, quando a cotação mudar ao longo do dia, recalculamos DY e P/VP
    com o preço atualizado.
    """
    tabela = pd.read_html(io.StringIO(_baixar_html("https://www.fundamentus.com.br/fii_resultado.php")),
                          decimal=",", thousands=".")[0]
    tabela.columns = ["fii", "segmento", "preco_ref", "ffo_yield", "dy", "pvp", "valor_mercado",
                      "liquidez", "qtd_imoveis", "preco_m2", "aluguel_m2", "cap_rate", "vacancia"]
    for col in ["ffo_yield", "dy", "cap_rate", "vacancia"]:
        tabela[col] = tabela[col].map(_pct)
    tabela["div_12m"] = tabela["dy"] * tabela["preco_ref"]
    tabela["vp_cota"] = np.where(tabela["pvp"] > 0, tabela["preco_ref"] / tabela["pvp"], np.nan)
    tabela["fonte"] = "Fundamentus"
    return tabela


# -----------------------------------------------------------------------------
# 2. Cotações em tempo (quase) real (Yahoo Finance)
# -----------------------------------------------------------------------------
def _baixar_mercado(tickers):
    """Baixa, de uma só vez, 1 ano de cotações e dividendos de vários FIIs e
    resume o que o site precisa de cada um:

      preco, var_dia, data_preco -> cotação atual (~15 min de atraso)
      div_12m_y   -> soma dos dividendos com data-ex nos últimos 12 meses
      vol_1a      -> volatilidade anual dos retornos totais (risco de preço)
      dd_1a       -> máxima queda desde um pico no último ano (drawdown)
      cv_div      -> coeficiente de variação dos pagamentos de dividendos
                     (desvio-padrão / média): mede a ESTABILIDADE da renda
      tend_div    -> média dos 6 últimos pagamentos / média dos anteriores - 1:
                     mostra se os dividendos estão caindo ou subindo
      meses_pagos -> quantos pagamentos houve nos últimos 12 meses

    As medidas de dividendos usam os PAGAMENTOS individuais (e não somas por
    mês do calendário), pois a data-ex às vezes cai no fim de um mês e às
    vezes no início do seguinte, o que criaria meses "vazios" artificiais.

    Retorna (DataFrame indexado pelo código, horário da consulta).
    """
    colunas = ["preco", "var_dia", "data_preco", "div_12m_y", "vol_1a", "dd_1a", "cv_div",
               "tend_div", "meses_pagos"]
    vazio = pd.DataFrame(columns=colunas)
    if not tickers:
        return vazio, datetime.now()
    bruto = yf.download([t + ".SA" for t in tickers], period="1y", interval="1d", actions=True,
                        auto_adjust=False, progress=False, threads=True)
    if bruto is None or bruto.empty:
        return vazio, datetime.now()
    precos = bruto["Close"].rename(columns=lambda c: c.replace(".SA", ""))
    precos.index = pd.to_datetime(precos.index).tz_localize(None)
    if "Dividends" in bruto.columns.get_level_values(0):
        divs = bruto["Dividends"].rename(columns=lambda c: c.replace(".SA", "")).fillna(0.0)
        divs.index = precos.index
    else:
        divs = pd.DataFrame(0.0, index=precos.index, columns=precos.columns)
    precos_limpos = _limpar_precos(precos)

    linhas = {}
    for fii in precos.columns:
        serie = precos[fii].dropna()
        if serie.empty:
            continue
        p = precos_limpos[fii].dropna()
        d = divs[fii].reindex(p.index).fillna(0.0)
        r = ((p + d) / p.shift(1) - 1).iloc[1:]
        pagamentos = divs[fii][divs[fii] > 0]
        media = pagamentos.mean() if len(pagamentos) >= 3 else np.nan
        ult6 = pagamentos.tail(6).mean()
        ant6 = pagamentos.iloc[:-6].mean() if len(pagamentos) >= 9 else np.nan
        patrimonio = (1 + r.fillna(0)).cumprod()
        linhas[fii] = {
            "preco": float(serie.iloc[-1]),
            "var_dia": float(serie.iloc[-1] / serie.iloc[-2] - 1) if len(serie) > 1 else np.nan,
            "data_preco": serie.index[-1].date(),
            "div_12m_y": float(divs[fii][divs.index > divs.index[-1] - pd.DateOffset(years=1)].sum()),
            "vol_1a": float(r.std() * np.sqrt(252)) if len(r) > 60 else np.nan,
            "dd_1a": float((patrimonio / patrimonio.cummax() - 1).min()) if len(r) > 60 else np.nan,
            "cv_div": float(pagamentos.std() / media) if media > 0 else np.nan,
            "tend_div": float(ult6 / ant6 - 1) if ant6 > 0 else np.nan,
            "meses_pagos": int(len(pagamentos)),
        }
    return pd.DataFrame(linhas).T.reindex(columns=colunas), datetime.now()


# -----------------------------------------------------------------------------
# 2b. Composição da carteira e dados cadastrais (CVM - Informe Mensal de FII)
# -----------------------------------------------------------------------------
# Grupos de ativos do Informe Mensal usados para classificar o fundo:
ATIVOS_PAPEL = ["CRI", "CRI_CRA", "LCI", "LCI_LCA", "Letras_Hipotecarias", "LIG", "Debentures",
                "Certificados_Deposito_Valores_Mobiliarios", "Notas_Promissorias"]
ATIVOS_TIJOLO = ["Direitos_Bens_Imoveis", "Acoes_Sociedades_Atividades_FII",
                 "Cotas_Sociedades_Atividades_FII"]
ATIVOS_FOF = ["FII"]   # cotas de outros FIIs (fundo de fundos)


def _baixar_cvm_ano(ano):
    import zipfile
    url = f"https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
    resp = requests.get(url, headers=CABECALHO, timeout=120)
    resp.raise_for_status()
    pacote = zipfile.ZipFile(io.BytesIO(resp.content))
    ler = lambda parte: pd.read_csv(pacote.open(f"inf_mensal_fii_{parte}_{ano}.csv"), sep=";",
                                    encoding="latin-1", low_memory=False)
    return ler("geral"), ler("ativo_passivo"), ler("complemento")


def _baixar_cvm():
    """Informe Mensal que todo FII entrega à CVM (dados abertos, dados.cvm.gov.br).

    Com ele calculamos, para o último mês entregue de cada fundo, quanto do
    patrimônio investido está em:
        papel  (CRI, LCI, debêntures...)     -> rendimento corrigido pela inflação/CDI
        tijolo (imóveis e SPEs imobiliárias) -> rendimento vem de aluguéis
        FoF    (cotas de outros FIIs)
    Também traz número de cotistas, patrimônio líquido e taxa de administração.

    O código de negociação vem do ISIN (ex.: BRHGLGCTF004 -> HGLG11).
    Retorna DataFrame indexado pelo código.
    """
    partes = []
    for ano in (date.today().year, date.today().year - 1):
        try:
            partes.append(_baixar_cvm_ano(ano))
        except Exception:
            continue
        if ano == date.today().year and date.today().month > 3:
            break   # o ano corrente já tem meses suficientes
    if not partes:
        return pd.DataFrame()
    geral = pd.concat([p[0] for p in partes])
    ativos = pd.concat([p[1] for p in partes])
    compl = pd.concat([p[2] for p in partes])

    ultimo = lambda df: df.sort_values("Data_Referencia").groupby("CNPJ_Fundo_Classe").tail(1)
    base = (ultimo(geral)[["CNPJ_Fundo_Classe", "Data_Referencia", "Nome_Fundo_Classe", "Codigo_ISIN",
                           "Segmento_Atuacao", "Tipo_Gestao", "Nome_Administrador"]]
            .merge(ultimo(ativos), on="CNPJ_Fundo_Classe", suffixes=("", "_a"))
            .merge(ultimo(compl)[["CNPJ_Fundo_Classe", "Total_Numero_Cotistas", "Patrimonio_Liquido",
                                  "Percentual_Despesas_Taxa_Administracao"]], on="CNPJ_Fundo_Classe"))
    base = base[base["Codigo_ISIN"].astype(str).str.match(r"^BR[A-Z]{4}CTF")]
    base["fii"] = base["Codigo_ISIN"].str[2:6] + "11"

    soma = lambda cols: base[[c for c in cols if c in base]].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    papel, tijolo, fof = soma(ATIVOS_PAPEL), soma(ATIVOS_TIJOLO), soma(ATIVOS_FOF)
    total = (papel + tijolo + fof).replace(0, np.nan)
    resultado = pd.DataFrame({
        "fii": base["fii"], "cnpj": base["CNPJ_Fundo_Classe"], "nome_cvm": base["Nome_Fundo_Classe"],
        "data_cvm": base["Data_Referencia"], "gestao_cvm": base["Tipo_Gestao"],
        "administrador": base["Nome_Administrador"],
        "pct_papel": papel / total, "pct_tijolo": tijolo / total, "pct_fof": fof / total,
        "cotistas": pd.to_numeric(base["Total_Numero_Cotistas"], errors="coerce"),
        "pl": pd.to_numeric(base["Patrimonio_Liquido"], errors="coerce"),
        "taxa_adm_mes": pd.to_numeric(base["Percentual_Despesas_Taxa_Administracao"], errors="coerce"),
    })
    # Se o mesmo código aparecer em mais de um CNPJ (classes/feeders), fica o maior PL
    resultado = resultado.sort_values("pl", ascending=False).drop_duplicates("fii")
    return resultado.set_index("fii")


@st.cache_data(ttl=3600, show_spinner=False)
def dados_yahoo_avulso(ticker):
    """Para fundos que não aparecem no Fundamentus (ex.: Fiagros como VGIA11),
    busca preço e soma dos dividendos dos últimos 12 meses direto no Yahoo."""
    try:
        ativo = yf.Ticker(ticker + ".SA")
        hist = ativo.history(period="1y", auto_adjust=False)
        if hist.empty:
            return None
        hist.index = hist.index.tz_localize(None)
        preco = float(hist["Close"].dropna().iloc[-1])
        div_12m = float(hist["Dividends"].sum())
        return {"fii": ticker, "segmento": "Outros (fora do Fundamentus)", "preco_ref": preco,
                "dy": div_12m / preco, "div_12m": div_12m, "fonte": "Yahoo"}
    except Exception:
        return None


# -----------------------------------------------------------------------------
# 3. Detalhes de um FII (Fundamentus)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def carregar_detalhes(ticker):
    """Lê a página de detalhes do FII e devolve um dicionário 'rótulo -> valor'.

    A página tem várias tabelas com pares (rótulo, valor) lado a lado; os
    rótulos começam com '?' (ícone de ajuda do site), que removemos.
    """
    try:
        tabelas = pd.read_html(io.StringIO(_baixar_html(
            f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}")), decimal=",", thousands=".")
    except Exception:
        return {}
    info = {}
    for tabela in tabelas:
        for _, linha in tabela.iterrows():
            valores = list(linha.values)
            for i in range(0, len(valores) - 1, 2):
                rotulo, valor = valores[i], valores[i + 1]
                if pd.isna(rotulo) or pd.isna(valor):
                    continue
                rotulo = str(rotulo).lstrip("?").strip()
                if rotulo and rotulo != str(valor) and rotulo not in info:
                    info[rotulo] = valor
    return info


# -----------------------------------------------------------------------------
# 4. Histórico de preços e dividendos (Yahoo Finance)
# -----------------------------------------------------------------------------
def _limpar_precos(precos):
    """Remove cotações espúrias (ex.: preço dividido por 100 por alguns dias,
    erro que ocorre no Yahoo): preços mais de 50% distantes da mediana dos 21
    pregões vizinhos são descartados e substituídos pelo último preço válido."""
    mediana = precos.rolling(21, center=True, min_periods=5).median()
    razao = precos / mediana
    return precos.mask((razao > 1.5) | (razao < 1 / 1.5)).ffill()


@st.cache_data(ttl=900, show_spinner="Baixando histórico de preços e dividendos...")
def carregar_historico(tickers, inicio):
    """Preço de fechamento e dividendos diários de uma lista de FIIs, desde
    'inicio'. Retorna (precos, dividendos), DataFrames com uma coluna por FII."""
    dados = yf.download([t + ".SA" for t in tickers], start=inicio, auto_adjust=False,
                        actions=True, progress=False, threads=True)
    if dados is None or dados.empty:
        return pd.DataFrame(), pd.DataFrame()
    precos = dados["Close"].copy()
    if "Dividends" in dados.columns.get_level_values(0):
        dividendos = dados["Dividends"].copy().fillna(0.0)
    else:
        dividendos = pd.DataFrame(0.0, index=precos.index, columns=precos.columns)
    renomear = lambda c: c.replace(".SA", "")
    precos = precos.rename(columns=renomear)
    dividendos = dividendos.rename(columns=renomear).reindex(columns=precos.columns, fill_value=0.0)
    precos.index = pd.to_datetime(precos.index).tz_localize(None)
    dividendos.index = precos.index
    precos = _limpar_precos(precos.dropna(how="all", axis=1))
    return precos, dividendos[precos.columns]


# -----------------------------------------------------------------------------
# 5. Indicadores macroeconômicos (Banco Central e Tesouro)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def ipca_focus_12m():
    """Expectativa de IPCA para os próximos 12 meses (mediana do Boletim Focus)."""
    url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
           "ExpectativasMercadoInflacao12Meses?$top=1&$filter=Indicador%20eq%20'IPCA'%20and%20"
           "Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200&$orderby=Data%20desc&$format=json")
    try:
        item = requests.get(url, timeout=20).json()["value"][0]
        return item["Mediana"] / 100, item["Data"]
    except Exception:
        return None, None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def serie_sgs_ultimo(codigo):
    """Último valor de uma série do SGS/Banco Central (em %, convertido para decimal).
    Ex.: 13522 = IPCA acumulado em 12 meses; 432 = meta Selic; 4389 = CDI anualizado."""
    try:
        item = requests.get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/1"
                            "?formato=json", timeout=20).json()[0]
        return float(item["valor"]) / 100, item["data"]
    except Exception:
        return None, None


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando taxas do Tesouro IPCA+...")
def taxas_tesouro_ipca():
    """Taxas de compra do Tesouro IPCA+ (sem cupom) no último dia disponível,
    a partir do arquivo público do Tesouro Transparente (atualizado diariamente)."""
    url = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
           "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv")
    try:
        bruto = pd.read_csv(io.BytesIO(requests.get(url, headers=CABECALHO, timeout=90).content),
                            sep=";", decimal=",")
        bruto["Data Base"] = pd.to_datetime(bruto["Data Base"], dayfirst=True)
        ipca = bruto[bruto["Tipo Titulo"] == "Tesouro IPCA+"]
        ultimo = ipca[ipca["Data Base"] == ipca["Data Base"].max()].copy()
        ultimo["Vencimento"] = pd.to_datetime(ultimo["Data Vencimento"], dayfirst=True)
        ultimo = ultimo.sort_values("Vencimento")
        return pd.DataFrame({"Vencimento": ultimo["Vencimento"].dt.year,
                             "Taxa": ultimo["Taxa Compra Manha"] / 100,
                             "Data": ultimo["Data Base"].dt.date}).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["Vencimento", "Taxa", "Data"])


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cdi_diario(inicio):
    """CDI diário (decimal) desde 'inicio' - SGS série 12. Usado como taxa
    livre de risco nos cálculos de Sharpe e CAPM."""
    fim = date.today()
    partes = []
    # A API limita consultas diárias a 10 anos; dividimos em blocos por segurança
    atual = inicio
    while atual <= fim:
        bloco_fim = min(atual + timedelta(days=365 * 9), fim)
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
               f"&dataInicial={atual:%d/%m/%Y}&dataFinal={bloco_fim:%d/%m/%Y}")
        try:
            bruto = pd.read_json(url)
            bruto["data"] = pd.to_datetime(bruto["data"], dayfirst=True)
            partes.append(bruto.set_index("data")["valor"] / 100)
        except Exception:
            return None
        atual = bloco_fim + timedelta(days=1)
    return pd.concat(partes) if partes else None
