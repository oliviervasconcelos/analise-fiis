# -*- coding: utf-8 -*-
"""
calculos.py - FÓRMULAS FINANCEIRAS do site de FIIs
==================================================

RELAÇÃO COM A DISCIPLINA (Administração Financeira, 1ª metade do curso)
-----------------------------------------------------------------------
  VALOR DO DINHEIRO NO TEMPO
    - Custo de oportunidade: o dinheiro aplicado no FII deixa de render no
      Tesouro IPCA+; essa taxa é a TAXA DE DESCONTO da análise.
    - Composição de taxas e equação de Fisher: (1 + nominal) = (1 + real) x (1 + inflação).
    - Taxa bruta x taxa líquida de impostos.
    - Valor presente de uma PERPETUIDADE: VP = PMT / i. Um FII paga dividendos
      sem prazo para acabar; descontá-los à taxa exigida dá o preço teto.
  RISCO E RETORNO
    - Prêmio de risco: quanto mais arriscado o ativo, maior o retorno exigido
      (taxa exigida = taxa livre de risco + prêmio, mesma lógica do CAPM).
    - Medidas de risco: volatilidade (desvio-padrão), Beta, Sharpe, drawdown, VaR.

PREÇO TETO (mesma lógica da planilha)
-------------------------------------
A ideia é comparar o FII com um investimento de referência "seguro": um
título atrelado à inflação (IPCA + taxa fixa). O FII só vale a pena se o seu
rendimento superar o desse título, acrescido de um PRÊMIO pelo risco.

  1) Taxa bruta do título       = (1 + IPCA) x (1 + taxa IPCA+) - 1
       -> composição de taxas: inflação e juro real se multiplicam.
  2) Taxa líquida (após IR)     = Taxa bruta x (1 - alíquota de IR)
       -> o título paga IR (15% no prazo longo); o rendimento do FII é isento
          para pessoa física, por isso comparamos com a taxa LÍQUIDA.
  3) Equivalente a IPCA+        = (1 + Taxa líquida) / (1 + IPCA) - 1
       -> equação de Fisher: ganho REAL líquido do título (acima da inflação).
  4) Taxa exigida do FII        = Equivalente IPCA+ + Prêmio + Ajuste IPCA
       -> Prêmio: compensação pelo risco do fundo (risco e retorno).
       -> Ajuste IPCA: FIIs de papel (CRI) distribuem a correção monetária
          como rendimento; parte do dividendo é só inflação, então exigimos
          que o yield cubra também o IPCA.
  5) Preço teto                 = Dividendo 12m / Taxa exigida
       -> valor presente de uma perpetuidade (VP = PMT / i): é o preço máximo
          que ainda entrega ao investidor a taxa exigida.
  6) Margem de segurança        = Preço teto / Preço atual - 1

RISCO E RETORNO
---------------
Retorno total (cota + dividendos), volatilidade, Sharpe, Beta, drawdown e
VaR, usados na página de cada fundo e no score do prêmio automático.
"""
import numpy as np
import pandas as pd

DIAS_UTEIS_ANO = 252


# -----------------------------------------------------------------------------
# Preço teto
# -----------------------------------------------------------------------------
def taxas_referencia(ipca, ipca_mais, aliquota_ir):
    """Calcula as taxas do título de referência (passos 1 a 3 acima)."""
    bruta = (1 + ipca) * (1 + ipca_mais) - 1
    liquida = bruta * (1 - aliquota_ir)
    equivalente = (1 + liquida) / (1 + ipca) - 1
    return {"bruta": bruta, "liquida": liquida, "equivalente": equivalente}


def preco_teto(div_12m, equivalente, premio, ajuste_ipca):
    """Preço teto e taxa exigida (passos 4 e 5). Funciona com números ou
    colunas inteiras (pandas), devolvendo NaN quando a taxa não é positiva."""
    taxa = equivalente + premio + ajuste_ipca
    teto = div_12m / taxa
    if isinstance(teto, pd.Series):
        teto = teto.where(taxa > 0)
    elif taxa <= 0:
        teto = np.nan
    return teto, taxa


def premio_implicito(div_12m, preco, equivalente, ajuste_ipca):
    """Prêmio que o preço atual 'paga': o prêmio que faria Preço teto = Preço.
    Prêmio implícito = DY atual - Equivalente IPCA+ - Ajuste IPCA."""
    return div_12m / preco - equivalente - ajuste_ipca


# -----------------------------------------------------------------------------
# Tipo do fundo (papel / tijolo / híbrido / FoF) e ajuste de IPCA
# -----------------------------------------------------------------------------
# Fração do IPCA somada à taxa exigida, conforme o tipo. Em fundos de papel,
# o rendimento inclui a correção monetária dos CRIs (parte do dividendo é só
# inflação); em tijolo, o aluguel é reajustado mas o rendimento distribuído é
# "real". Híbridos e FoFs ficam no meio.
FATOR_IPCA_PADRAO = {"Papel": 1.0, "Híbrido": 0.5, "FoF": 0.5, "Tijolo": 0.0, "Indefinido": 0.5}
LIMITE_PREDOMINANTE = 0.67    # >= 67% de um tipo de ativo define a classificação


def classificar_tipo(pct_papel, pct_tijolo, pct_fof, qtd_imoveis, segmento):
    """Classifica o fundo pela composição dos ativos (CVM). Se o fundo não
    estiver na base da CVM, usa uma regra aproximada com dados do Fundamentus.
    Retorna (tipo, origem da classificação)."""
    if pd.notna(pct_papel):
        if pct_papel >= LIMITE_PREDOMINANTE:
            return "Papel", "CVM"
        if pct_tijolo >= LIMITE_PREDOMINANTE:
            return "Tijolo", "CVM"
        if pct_fof >= 0.5:
            return "FoF", "CVM"
        return "Híbrido", "CVM"
    if segmento == "Títulos e Val. Mob.":
        return "Papel", "estimado"
    if pd.notna(qtd_imoveis) and qtd_imoveis > 0:
        return "Tijolo", "estimado"
    return "Indefinido", "estimado"


# -----------------------------------------------------------------------------
# Prêmio automático (score de risco)
# -----------------------------------------------------------------------------
# O prêmio é a remuneração extra exigida, além do título IPCA+, pelos riscos
# do FII. Partimos de um prêmio-base e somamos pontos (em % a.a.) para cada
# fator de risco observado. Cada regra divide o indicador em faixas e atribui
# pontos a cada faixa (ex.: liquidez abaixo de R$ 500 mil/dia soma +1,0%).
PREMIO_BASE = 1.0 / 100
PREMIO_MIN, PREMIO_MAX = 0.5 / 100, 8.0 / 100

REGRAS_PREMIO = {
    # fator: (coluna, limites, pontos em % por faixa, só para estes tipos)
    "Baixa liquidez":         ("liquidez", [0.5e6, 2e6, 5e6], [1.0, 0.5, 0.25, 0.0], None),
    "Fundo pequeno":          ("valor_mercado", [0.5e9, 1e9, 3e9], [1.0, 0.5, 0.25, 0.0], None),
    "Poucos imóveis":         ("qtd_imoveis", [2, 5, 10], [1.0, 0.5, 0.25, 0.0], ("Tijolo", "Híbrido")),
    "Vacância":               ("vacancia", [0.05, 0.10, 0.20], [0.0, 0.25, 0.5, 1.0], ("Tijolo", "Híbrido")),
    "Volatilidade da cota":   ("vol_1a", [0.10, 0.15, 0.20], [0.0, 0.25, 0.5, 1.0], None),
    "Dividendos instáveis":   ("cv_div", [0.10, 0.25, 0.50], [0.0, 0.25, 0.5, 1.0], None),
    "Dividendos em queda":    ("queda_div", [0.05, 0.15, 0.30], [0.0, 0.25, 0.5, 1.0], None),
    "Yield acima dos pares":  ("excesso_dy", [0.02, 0.04], [0.0, 0.5, 1.0], None),
}

DESCRICAO_REGRAS = {
    "Baixa liquidez": "Volume médio diário < R$ 5 mi: +0,25 · < R$ 2 mi: +0,5 · < R$ 500 mil: +1,0",
    "Fundo pequeno": "Valor de mercado < R$ 3 bi: +0,25 · < R$ 1 bi: +0,5 · < R$ 500 mi: +1,0",
    "Poucos imóveis": "(tijolo/híbrido) < 10 imóveis: +0,25 · < 5: +0,5 · monoativo: +1,0",
    "Vacância": "(tijolo/híbrido) > 5%: +0,25 · > 10%: +0,5 · > 20%: +1,0",
    "Volatilidade da cota": "Volatilidade anual (12m) > 10%: +0,25 · > 15%: +0,5 · > 20%: +1,0",
    "Dividendos instáveis": "Coef. de variação dos pagamentos (12m) > 10%: +0,25 · > 25%: +0,5 · > 50%: +1,0",
    "Dividendos em queda": "Média dos 6 últimos pagamentos vs anteriores: queda > 5%: +0,25 · > 15%: +0,5 · > 30%: +1,0",
    "Yield acima dos pares": "DY 12m acima da mediana dos FIIs do mesmo tipo (papel, tijolo...): "
                             "> 2 p.p.: +0,5 · > 4 p.p.: +1,0. Yield muito alto costuma indicar risco "
                             "percebido pelo mercado (crédito, vacância futura, dividendo insustentável)",
}


def _pontuar(valores, limites, pontos):
    """Converte uma coluna de valores em pontos de prêmio, por faixas:
    faixa 0 = abaixo do 1º limite, faixa 1 = entre o 1º e o 2º, etc.
    Os pontos de cada faixa já refletem se 'maior' ou 'menor' é pior."""
    faixa = np.searchsorted(limites, valores.to_numpy(dtype=float), side="right")
    resultado = np.asarray(pontos, dtype=float)[np.clip(faixa, 0, len(pontos) - 1)]
    return pd.Series(np.where(valores.isna(), 0.0, resultado), index=valores.index)


def mediana_dy_pares(tab):
    """Para cada FII, a mediana do DY 12m dos FIIs do mesmo tipo (pares) com
    liquidez de pelo menos R$ 500 mil/dia."""
    pares = tab[(tab["dy_atual"] > 0) & (tab["liquidez"].fillna(0) >= 0.5e6)]
    mediana_tipo = pares.groupby("tipo")["dy_atual"].median()
    return tab["tipo"].map(mediana_tipo).fillna(pares["dy_atual"].median())


def premio_automatico(tab, base=PREMIO_BASE, multiplicador=1.0):
    """Calcula o prêmio de risco de cada FII da tabela.

    Retorna (prêmio total em decimal, DataFrame com os pontos de cada fator),
    permitindo mostrar ao usuário a composição do prêmio ("de onde veio").
    Dados ausentes não somam pontos (o fator é ignorado).
    """
    t = tab.copy()
    t["queda_div"] = -pd.to_numeric(t["tend_div"], errors="coerce")
    t["qtd_imoveis"] = t["qtd_imoveis"].replace(0, np.nan)   # 0 = sem informação
    t["excesso_dy"] = t["dy_atual"] - mediana_dy_pares(t)
    componentes = pd.DataFrame(index=t.index)
    for fator, (coluna, limites, pontos, tipos) in REGRAS_PREMIO.items():
        pts = _pontuar(pd.to_numeric(t[coluna], errors="coerce"), limites, pontos) / 100
        if tipos:
            pts = pts.where(t["tipo"].isin(tipos), 0.0)
        componentes[fator] = pts
    total = (base + componentes.sum(axis=1) * multiplicador).clip(PREMIO_MIN, PREMIO_MAX)
    return total, componentes


# -----------------------------------------------------------------------------
# Risco e retorno
# -----------------------------------------------------------------------------
def retornos_totais(precos, dividendos):
    """R_t = (P_t + D_t) / P_{t-1} - 1  (valorização + dividendo do dia)."""
    return ((precos + dividendos) / precos.shift(1) - 1).iloc[1:]


def anualizar(retornos):
    """Retorno anual composto: (prod(1+R))^(252/n) - 1."""
    retornos = retornos.dropna()
    if len(retornos) < 2:
        return np.nan
    return (1 + retornos).prod() ** (DIAS_UTEIS_ANO / len(retornos)) - 1


def drawdown(retornos):
    """Queda percentual do patrimônio em relação ao pico anterior."""
    patrimonio = (1 + retornos.fillna(0)).cumprod()
    return patrimonio / patrimonio.cummax() - 1


def metricas_risco_retorno(r, r_preco, r_mercado, rf_diario):
    """Métricas de risco e retorno de um FII (série de retornos diários 'r').

    r_preco   : retornos só da cota (sem dividendos)
    r_mercado : retornos do IFIX (XFIX11), para o Beta
    rf_diario : CDI diário alinhado às datas (taxa livre de risco)
    """
    r = r.dropna()
    if len(r) < 20:
        return {}
    rf_anual = anualizar(rf_diario.reindex(r.index).ffill().bfill()) if rf_diario is not None else np.nan
    ret_anual = anualizar(r)
    vol = r.std() * np.sqrt(DIAS_UTEIS_ANO)
    alinhado = pd.concat([r, r_mercado], axis=1).dropna()
    beta = (alinhado.iloc[:, 0].cov(alinhado.iloc[:, 1]) / alinhado.iloc[:, 1].var()
            if len(alinhado) > 20 else np.nan)
    corte = r.quantile(0.05)
    return {
        "Retorno acumulado": (1 + r).prod() - 1,
        "Retorno anual (total)": ret_anual,
        "Retorno anual (só cota)": anualizar(r_preco),
        "Volatilidade anual": vol,
        "Índice de Sharpe": (ret_anual - rf_anual) / vol if vol > 0 else np.nan,
        "Beta (vs IFIX)": beta,
        "Máximo drawdown": drawdown(r).min(),
        "VaR 95% diário": -corte,
        "CDI no período (a.a.)": rf_anual,
    }
