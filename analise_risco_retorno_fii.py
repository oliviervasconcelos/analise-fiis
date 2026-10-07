# -*- coding: utf-8 -*-
"""
===============================================================================
 UNIVERSIDADE FEDERAL DE MINAS GERAIS - FACE / CAD
 Administração Financeira (CAD 167) - Trabalho 1
 Tema: RISCO E RETORNO aplicado a Fundos de Investimento Imobiliário (FIIs)
===============================================================================

OBJETIVO
--------
Esta aplicação é um exemplo prático do tema "Risco e Retorno". Ela:

  1. CAPTURA DADOS reais da internet:
       - Cotações diárias e dividendos (rendimentos) dos FIIs escolhidos
         pelo usuário, obtidos no Yahoo Finance (biblioteca yfinance);
       - Cotações de um benchmark de mercado (padrão: XFIX11, ETF que
         replica o IFIX, índice dos fundos imobiliários da B3);
       - Taxa CDI diária, obtida na API pública do Banco Central do Brasil
         (Sistema Gerenciador de Séries Temporais - SGS, série 12), usada
         como TAXA LIVRE DE RISCO.

  2. CALCULA as principais medidas de risco e retorno vistas em sala:
       - Retorno total (valorização da cota + dividendos), retorno anualizado;
       - Dividend Yield (DY) dos últimos 12 meses;
       - Desvio-padrão (volatilidade) anualizado e coeficiente de variação;
       - Índice de Sharpe (retorno em excesso ao CDI por unidade de risco);
       - Beta em relação ao mercado (IFIX) - risco sistemático;
       - CAPM: retorno exigido = Rf + Beta x (Rm - Rf), e o Alfa de Jensen;
       - Máximo drawdown, VaR e CVaR históricos (95%);
       - Matriz de correlação entre os FIIs (base da diversificação);
       - Teoria de carteiras de Markowitz: simulação de milhares de
         carteiras, fronteira eficiente, carteira de mínima variância e
         carteira de máximo Sharpe.

  3. GERA RELATÓRIOS na pasta "relatorios/<data_hora>/":
       - relatorio.html  -> relatório completo com tabelas, gráficos e
                            interpretação automática dos resultados;
       - *.png           -> gráficos individuais;
       - *.csv           -> tabelas de métricas e dados brutos capturados
                            (separador ";" e vírgula decimal, abre direto
                            no Excel em português).

COMO EXECUTAR
-------------
  pip install -r requirements.txt
  python analise_risco_retorno_fii.py

  O programa pergunta os FIIs e o período (basta apertar ENTER para usar os
  valores padrão). Também é possível passar tudo por linha de comando:

  python analise_risco_retorno_fii.py --fiis HGLG11 KNRI11 MXRF11 --inicio 2022-01-01
  python analise_risco_retorno_fii.py --padrao      (roda sem perguntas)

CONVENÇÕES
----------
  - Considera-se 252 dias úteis por ano (padrão do mercado brasileiro).
  - Retornos diários são "retornos totais": incluem o dividendo pago na
    data-ex, pois o investidor de FII recebe a maior parte do retorno via
    rendimentos mensais (isentos de IR para pessoa física).
"""

# =============================================================================
# 1. IMPORTAÇÃO DAS BIBLIOTECAS
# =============================================================================
import argparse          # leitura de parâmetros pela linha de comando
import base64            # embutir imagens dentro do HTML (arquivo único)
import os                # manipulação de pastas e arquivos
import sys               # configurações do terminal / encerramento
import time              # pausa entre novas tentativas de download
import webbrowser        # abrir o relatório ao final
from datetime import date, datetime, timedelta

import numpy as np       # cálculos numéricos (médias, desvios, matrizes)
import pandas as pd      # manipulação de séries temporais e tabelas

import matplotlib
matplotlib.use("Agg")    # gera gráficos em arquivo, sem abrir janelas
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

try:
    import yfinance as yf  # captura de cotações e dividendos (Yahoo Finance)
except ImportError:
    sys.exit("Biblioteca 'yfinance' não encontrada. Rode: pip install -r requirements.txt")

# Silencia mensagens técnicas (em inglês) do yfinance; o próprio programa
# avisa em português quando algum código não tiver dados.
import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Garante que acentos apareçam corretamente no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# =============================================================================
# 2. PARÂMETROS GERAIS
# =============================================================================
DIAS_UTEIS_ANO = 252                     # dias de pregão em um ano
NIVEL_CONFIANCA_VAR = 0.95               # nível de confiança do VaR/CVaR
N_CARTEIRAS_SIMULADAS = 20_000           # carteiras na simulação de Markowitz
SEMENTE_ALEATORIA = 42                   # torna a simulação reproduzível

# FIIs padrão: mistura de segmentos (logística, lajes/híbrido, papel/recebíveis,
# shoppings), para que a diversificação fique evidente na análise.
FIIS_PADRAO = ["HGLG11", "KNRI11", "MXRF11", "XPML11", "KNCR11", "VISC11"]
BENCHMARK_PADRAO = "XFIX11"             # ETF que replica o IFIX
ANOS_PADRAO = 3                         # janela padrão de análise

# Taxa livre de risco usada SOMENTE se a API do Banco Central estiver fora do ar
CDI_ANUAL_RESERVA = 0.1065

# Paleta de cores dos gráficos
CORES = ["#1f4e79", "#c0504d", "#4f9a3c", "#e08a1e", "#7b4fa0",
         "#2a9d9b", "#b5527d", "#6b6b6b", "#8c6d31", "#3b7dd8"]


# =============================================================================
# 3. FUNÇÕES DE CAPTURA DE DADOS
# =============================================================================
def normalizar_ticker(codigo: str) -> str:
    """Converte o código digitado (ex.: 'hglg11') para o formato do Yahoo
    Finance, que exige o sufixo '.SA' para ativos negociados na B3."""
    codigo = codigo.strip().upper()
    return codigo if codigo.endswith(".SA") else codigo + ".SA"


def capturar_cotacoes(tickers, inicio, fim):
    """Baixa do Yahoo Finance os preços de fechamento e os dividendos diários.

    Retorna dois DataFrames (linhas = datas, colunas = FIIs):
      - precos:     preço de fechamento NÃO ajustado (preço real negociado);
      - dividendos: valor do rendimento por cota na data-ex (0 nos demais dias).
    Usamos o preço não ajustado + dividendos explícitos para mostrar, de forma
    transparente, como o retorno total é composto.
    """
    print(f"  -> Baixando cotações e dividendos de {len(tickers)} ativos no Yahoo Finance...")
    dados = yf.download(
        tickers, start=inicio, end=fim + timedelta(days=1),
        auto_adjust=False,   # mantém o preço real (sem ajuste por proventos)
        actions=True,        # inclui a coluna de dividendos
        progress=False, threads=True,
    )
    if dados is None or dados.empty:
        sys.exit("ERRO: nenhum dado retornado pelo Yahoo Finance. Verifique a internet e os códigos.")

    precos = dados["Close"].copy()
    if "Dividends" in dados.columns.get_level_values(0):
        dividendos = dados["Dividends"].copy().fillna(0.0)
    else:
        dividendos = pd.DataFrame(0.0, index=precos.index, columns=precos.columns)

    # Remove fuso horário das datas (se houver) para alinhar com o CDI
    precos.index = pd.to_datetime(precos.index).tz_localize(None)
    dividendos.index = pd.to_datetime(dividendos.index).tz_localize(None)
    return precos, dividendos.reindex(columns=precos.columns, fill_value=0.0)


def limpar_precos(precos):
    """Tratamento de qualidade dos dados capturados.

    Fontes gratuitas às vezes trazem cotações erradas por alguns dias (ex.:
    preço dividido por 100). Um único valor errado distorce todo o cálculo de
    risco (a volatilidade 'explode'). Para detectar esses erros, comparamos
    cada preço com a MEDIANA dos 21 pregões ao redor dele: se o preço for mais
    de 50% maior ou menor que essa mediana, é considerado espúrio, apagado e
    substituído pelo último preço válido.

    Retorna os preços corrigidos e uma lista com as correções feitas.
    """
    mediana = precos.rolling(21, center=True, min_periods=5).median()
    razao = precos / mediana
    espurios = (razao > 1.5) | (razao < 1 / 1.5)
    correcoes = [(c.replace(".SA", ""), d.date(), precos.loc[d, c])
                 for c in precos.columns for d in precos.index[espurios[c]]]
    return precos.mask(espurios).ffill(), correcoes


def capturar_cdi(inicio, fim):
    """Captura a taxa CDI diária (% ao dia) na API do Banco Central (SGS, série 12).

    O CDI é a referência de "ativo livre de risco" no Brasil: é o retorno que o
    investidor obteria sem correr risco relevante (ex.: Tesouro Selic / CDB
    de grande banco). Retorna uma Series com a taxa diária em forma decimal.
    """
    print("  -> Baixando a taxa CDI diária na API do Banco Central (SGS 12)...")
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
           f"&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}")
    # A API do BC é instável às vezes: tentamos até 4 vezes antes de desistir
    for tentativa in range(1, 5):
        try:
            bruto = pd.read_json(url)
            bruto["data"] = pd.to_datetime(bruto["data"], dayfirst=True)
            cdi = bruto.set_index("data")["valor"].astype(float) / 100.0  # % -> decimal
            return cdi, "API do Banco Central (SGS série 12)"
        except Exception as erro:
            print(f"     AVISO: tentativa {tentativa} de acessar o Banco Central falhou ({erro}).")
            time.sleep(3 * tentativa)
    # Plano B: se a API falhar, usa uma taxa anual fixa convertida para diária
    print(f"     Usando CDI fixo de {CDI_ANUAL_RESERVA:.2%} a.a. como taxa livre de risco.")
    return None, f"Taxa fixa de reserva ({CDI_ANUAL_RESERVA:.2%} a.a.)"


# =============================================================================
# 4. FUNÇÕES DE CÁLCULO DE RISCO E RETORNO
# =============================================================================
def retornos_totais(precos, dividendos):
    """Retorno total diário de cada FII:

            R_t = (P_t + D_t - P_{t-1}) / P_{t-1}

    onde P é o preço da cota e D o dividendo recebido na data-ex. É a fórmula
    do "retorno de um período" vista em sala: ganho de capital + rendimento.
    """
    return ((precos + dividendos) / precos.shift(1) - 1).iloc[1:]


def anualizar_retorno_geometrico(retornos):
    """Retorno anual composto (CAGR): (produto de (1 + R_t))^(252/n) - 1.
    Representa a taxa anual que, capitalizada, gera o resultado acumulado."""
    acumulado = (1 + retornos).prod()
    n = retornos.count()
    return acumulado ** (DIAS_UTEIS_ANO / n) - 1


def drawdown(retornos):
    """Série de drawdown: queda percentual em relação ao pico anterior do
    patrimônio. Mostra 'quanto o investidor chegou a perder' desde o topo."""
    patrimonio = (1 + retornos).cumprod()
    return patrimonio / patrimonio.cummax() - 1


def calcular_metricas(ret, ret_preco, ret_mercado, cdi_diario, precos, dividendos):
    """Monta a tabela principal de risco e retorno de cada ativo.

    Parâmetros:
      ret         -> retornos totais diários dos FIIs (DataFrame)
      ret_preco   -> retornos só de preço (sem dividendos), para decomposição
      ret_mercado -> retornos diários do benchmark (IFIX)
      cdi_diario  -> taxa livre de risco diária alinhada às datas
    """
    rf_anual = anualizar_retorno_geometrico(cdi_diario)
    rm_anual = anualizar_retorno_geometrico(ret_mercado)
    var_mercado = ret_mercado.var()
    linhas = {}

    for fii in ret.columns:
        r = ret[fii].dropna()

        # ---------------- RETORNO ----------------
        retorno_acumulado = (1 + r).prod() - 1
        retorno_anual = anualizar_retorno_geometrico(r)
        retorno_preco_anual = anualizar_retorno_geometrico(ret_preco[fii].dropna())

        # Dividend Yield 12 meses = soma dos rendimentos do último ano / preço atual
        ult_data = precos[fii].dropna().index[-1]
        div_12m = dividendos[fii][dividendos.index > ult_data - pd.DateOffset(years=1)].sum()
        preco_atual = precos[fii].dropna().iloc[-1]
        dy_12m = div_12m / preco_atual

        # ---------------- RISCO TOTAL ----------------
        # Volatilidade anual = desvio-padrão diário x raiz(252)
        vol_anual = r.std() * np.sqrt(DIAS_UTEIS_ANO)
        # Coeficiente de variação: risco por unidade de retorno (quanto menor, melhor)
        retorno_medio_anual = r.mean() * DIAS_UTEIS_ANO
        cv = vol_anual / retorno_medio_anual if retorno_medio_anual > 0 else np.nan

        # ---------------- RISCO x RETORNO ----------------
        # Índice de Sharpe = (retorno do ativo - taxa livre de risco) / volatilidade
        sharpe = (retorno_anual - rf_anual) / vol_anual

        # ---------------- RISCO SISTEMÁTICO (BETA) E CAPM ----------------
        # Beta = Cov(Ri, Rm) / Var(Rm): sensibilidade do FII aos movimentos do mercado
        alinhado = pd.concat([r, ret_mercado], axis=1).dropna()
        beta = alinhado.iloc[:, 0].cov(alinhado.iloc[:, 1]) / var_mercado
        correl_mercado = alinhado.iloc[:, 0].corr(alinhado.iloc[:, 1])
        # CAPM: retorno exigido pelo risco sistemático assumido
        retorno_capm = rf_anual + beta * (rm_anual - rf_anual)
        # Alfa de Jensen: retorno obtido acima (ou abaixo) do exigido pelo CAPM
        alfa = retorno_anual - retorno_capm
        # R² = parcela da variância do FII explicada pelo mercado (risco sistemático);
        # (1 - R²) é a parcela de risco específico, que a diversificação elimina.
        r2 = correl_mercado ** 2

        # ---------------- RISCO DE PERDA ----------------
        max_dd = drawdown(r).min()
        # VaR histórico 95%: perda diária que só é superada em 5% dos dias
        corte = r.quantile(1 - NIVEL_CONFIANCA_VAR)
        var_95 = -corte
        # CVaR (Expected Shortfall): perda média nos 5% piores dias
        cvar_95 = -r[r <= corte].mean()

        linhas[fii.replace(".SA", "")] = {
            "Preço atual (R$)": preco_atual,
            "Retorno acumulado": retorno_acumulado,
            "Retorno anual (total)": retorno_anual,
            "Retorno anual (só cota)": retorno_preco_anual,
            "Dividend Yield 12m": dy_12m,
            "Volatilidade anual": vol_anual,
            "Coef. de variação": cv,
            "Índice de Sharpe": sharpe,
            "Beta (vs IFIX)": beta,
            "R² (risco sistemático)": r2,
            "Retorno exigido CAPM": retorno_capm,
            "Alfa de Jensen": alfa,
            "Máximo drawdown": max_dd,
            "VaR 95% diário": var_95,
            "CVaR 95% diário": cvar_95,
        }

    return pd.DataFrame(linhas).T, rf_anual, rm_anual


def simular_carteiras(ret, rf_anual):
    """Teoria de Carteiras de Markowitz por simulação de Monte Carlo.

    Para uma carteira com pesos w:
        Retorno esperado  E(Rp) = w' * mu           (mu = médias anualizadas)
        Variância         σp²   = w' * Σ * w        (Σ = matriz de covariâncias)

    A variância da carteira depende das COVARIÂNCIAS entre os ativos; quando a
    correlação é menor que 1, o risco da carteira fica abaixo da média ponderada
    dos riscos individuais -> este é o efeito da DIVERSIFICAÇÃO.

    Aqui o retorno esperado é a média aritmética anualizada (média diária x 252),
    que é a medida apropriada para a combinação linear de Markowitz.
    """
    ret = ret.dropna()
    mu = ret.mean().values * DIAS_UTEIS_ANO              # vetor de retornos esperados
    sigma = ret.cov().values * DIAS_UTEIS_ANO            # matriz de covariância anual
    n_ativos = len(mu)

    # Pesos aleatórios não negativos que somam 1 (sem venda a descoberto).
    # Metade é sorteada de forma uniforme e metade concentrada em poucos ativos
    # (Dirichlet com parâmetro 0,2), para a nuvem cobrir também as bordas.
    gerador = np.random.default_rng(SEMENTE_ALEATORIA)
    metade = N_CARTEIRAS_SIMULADAS // 2
    pesos = np.vstack([gerador.dirichlet(np.ones(n_ativos), metade),
                       gerador.dirichlet(np.full(n_ativos, 0.2), N_CARTEIRAS_SIMULADAS - metade)])
    # Inclui também as carteiras 100% em cada ativo e a igualmente ponderada
    pesos = np.vstack([pesos, np.eye(n_ativos), np.full(n_ativos, 1 / n_ativos)])

    retornos_cart = pesos @ mu
    vols_cart = np.sqrt(np.einsum("ij,jk,ik->i", pesos, sigma, pesos))
    sharpes_cart = (retornos_cart - rf_anual) / vols_cart

    i_min_var = int(np.argmin(vols_cart))
    i_max_sharpe = int(np.argmax(sharpes_cart))
    i_igual = len(pesos) - 1

    nomes = [c.replace(".SA", "") for c in ret.columns]

    def resumo(i, rotulo):
        return {"Carteira": rotulo, "Retorno esperado": retornos_cart[i],
                "Volatilidade": vols_cart[i], "Sharpe": sharpes_cart[i],
                **{n: pesos[i, k] for k, n in enumerate(nomes)}}

    tabela = pd.DataFrame([
        resumo(i_igual, "Pesos iguais"),
        resumo(i_min_var, "Mínima variância"),
        resumo(i_max_sharpe, "Máximo Sharpe"),
    ]).set_index("Carteira")

    # Média ponderada das volatilidades individuais (sem efeito da correlação),
    # usada para medir quanto risco a diversificação eliminou.
    vols_individuais = np.sqrt(np.diag(sigma))
    vol_sem_diversificacao = pesos[i_igual] @ vols_individuais

    return {
        "retornos": retornos_cart, "vols": vols_cart, "sharpes": sharpes_cart,
        "tabela": tabela, "mu": mu, "vols_individuais": vols_individuais,
        "nomes": nomes, "vol_sem_diversificacao": vol_sem_diversificacao,
    }


# =============================================================================
# 5. FUNÇÕES DE GRÁFICOS (cada uma salva um PNG e devolve o caminho)
# =============================================================================
def _salvar(fig, pasta, nome):
    caminho = os.path.join(pasta, nome)
    fig.tight_layout()
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    return caminho


def grafico_evolucao(ret, ret_mercado, cdi, pasta):
    """Evolução de R$ 100 investidos em cada FII (com reinvestimento dos
    dividendos), comparada ao IFIX e ao CDI."""
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for i, c in enumerate(ret.columns):
        ax.plot(100 * (1 + ret[c].fillna(0)).cumprod(), label=c.replace(".SA", ""),
                color=CORES[i % len(CORES)], lw=1.4)
    ax.plot(100 * (1 + ret_mercado.fillna(0)).cumprod(), label="IFIX (benchmark)",
            color="black", lw=2.2, ls="--")
    ax.plot(100 * (1 + cdi).cumprod(), label="CDI (livre de risco)", color="gray", lw=2.2, ls=":")
    ax.set_title("Evolução de R$ 100 investidos (retorno total, dividendos reinvestidos)")
    ax.set_ylabel("R$")
    ax.grid(alpha=0.3)
    ax.legend(ncol=3, fontsize=8)
    return _salvar(fig, pasta, "01_evolucao_patrimonio.png")


def grafico_risco_retorno(metricas, rf_anual, rm_anual, vol_mercado, pasta):
    """Gráfico de dispersão Risco (volatilidade) x Retorno de cada FII, com a
    reta que liga o ativo livre de risco ao mercado (Linha de Mercado de Capitais)."""
    fig, ax = plt.subplots(figsize=(9, 6))
    for i, (nome, linha) in enumerate(metricas.iterrows()):
        ax.scatter(linha["Volatilidade anual"], linha["Retorno anual (total)"], s=120,
                   color=CORES[i % len(CORES)], zorder=3)
        ax.annotate(nome, (linha["Volatilidade anual"], linha["Retorno anual (total)"]),
                    xytext=(6, 6), textcoords="offset points", fontsize=9)
    ax.scatter(vol_mercado, rm_anual, marker="D", s=120, color="black", zorder=3)
    ax.annotate("IFIX", (vol_mercado, rm_anual), xytext=(6, -12), textcoords="offset points")
    ax.scatter(0, rf_anual, marker="s", s=100, color="gray", zorder=3)
    ax.annotate("CDI", (0, rf_anual), xytext=(6, 6), textcoords="offset points")
    xmax = max(metricas["Volatilidade anual"].max(), vol_mercado) * 1.15
    inclinacao = (rm_anual - rf_anual) / vol_mercado
    ax.plot([0, xmax], [rf_anual, rf_anual + inclinacao * xmax], color="gray", lw=1,
            ls="--", label="Linha CDI → IFIX (Sharpe do mercado)")
    ax.axhline(0, color="black", lw=0.6)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_xlabel("Risco: volatilidade anual (desvio-padrão)")
    ax.set_ylabel("Retorno anual (total)")
    ax.set_title("Risco x Retorno dos FIIs")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    return _salvar(fig, pasta, "02_risco_retorno.png")


def grafico_correlacao(ret, pasta):
    """Mapa de calor da matriz de correlação dos retornos diários."""
    corr = ret.corr()
    nomes = [c.replace(".SA", "") for c in corr.columns]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    im = ax.imshow(corr.values, cmap="RdYlGn_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(nomes)), nomes, rotation=45, ha="right")
    ax.set_yticks(range(len(nomes)), nomes)
    for i in range(len(nomes)):
        for j in range(len(nomes)):
            ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title("Correlação entre os retornos diários")
    return _salvar(fig, pasta, "03_correlacao.png")


def grafico_drawdown(ret, pasta):
    """Drawdown ao longo do tempo: profundidade e duração das perdas."""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, c in enumerate(ret.columns):
        ax.plot(drawdown(ret[c].dropna()), label=c.replace(".SA", ""),
                color=CORES[i % len(CORES)], lw=1.2)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_title("Drawdown: queda em relação ao pico anterior")
    ax.grid(alpha=0.3)
    ax.legend(ncol=4, fontsize=8)
    return _salvar(fig, pasta, "04_drawdown.png")


def grafico_distribuicao(ret, metricas, pasta):
    """Histograma dos retornos diários de cada FII, com a linha do VaR 95%."""
    n = len(ret.columns)
    colunas = 3
    linhas_g = int(np.ceil(n / colunas))
    fig, eixos = plt.subplots(linhas_g, colunas, figsize=(12, 3.3 * linhas_g), squeeze=False)
    for k, c in enumerate(ret.columns):
        ax = eixos[k // colunas][k % colunas]
        nome = c.replace(".SA", "")
        ax.hist(ret[c].dropna(), bins=60, color=CORES[k % len(CORES)], alpha=0.8)
        var = metricas.loc[nome, "VaR 95% diário"]
        ax.axvline(-var, color="red", ls="--", lw=1.3, label=f"VaR 95% = {var:.2%}")
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
        ax.set_title(nome, fontsize=10)
        ax.legend(fontsize=7)
    for k in range(n, linhas_g * colunas):
        eixos[k // colunas][k % colunas].axis("off")
    fig.suptitle("Distribuição dos retornos diários e Value at Risk (VaR)")
    return _salvar(fig, pasta, "05_distribuicao_var.png")


def grafico_fronteira(sim, rf_anual, pasta):
    """Nuvem de carteiras simuladas, fronteira eficiente e carteiras ótimas."""
    fig, ax = plt.subplots(figsize=(10, 6.5))
    sc = ax.scatter(sim["vols"], sim["retornos"], c=sim["sharpes"], cmap="viridis", s=4, alpha=0.6)
    fig.colorbar(sc, ax=ax, label="Índice de Sharpe")
    for k, nome in enumerate(sim["nomes"]):
        ax.scatter(sim["vols_individuais"][k], sim["mu"][k], color="black", marker="x", s=60)
        ax.annotate(nome, (sim["vols_individuais"][k], sim["mu"][k]),
                    xytext=(5, 4), textcoords="offset points", fontsize=8)
    t = sim["tabela"]
    estilos = {"Pesos iguais": ("o", "orange"), "Mínima variância": ("*", "blue"),
               "Máximo Sharpe": ("*", "red")}
    for rotulo, (marca, cor) in estilos.items():
        ax.scatter(t.loc[rotulo, "Volatilidade"], t.loc[rotulo, "Retorno esperado"],
                   marker=marca, color=cor, s=300 if marca == "*" else 120,
                   edgecolor="black", zorder=4, label=rotulo)
    # Linha de Mercado de Capitais (CML): CDI até a carteira de máximo Sharpe
    v_ms, r_ms = t.loc["Máximo Sharpe", "Volatilidade"], t.loc["Máximo Sharpe", "Retorno esperado"]
    xs = np.linspace(0, sim["vols"].max(), 50)
    ax.plot(xs, rf_anual + (r_ms - rf_anual) / v_ms * xs, color="red", lw=1, ls="--",
            label="Linha de Mercado de Capitais")
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_xlim(left=0)
    ax.set_xlabel("Volatilidade anual")
    ax.set_ylabel("Retorno esperado anual")
    ax.set_title(f"Fronteira eficiente de Markowitz ({N_CARTEIRAS_SIMULADAS:,} carteiras simuladas)".replace(",", "."))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    return _salvar(fig, pasta, "06_fronteira_eficiente.png")


def grafico_dividendos(dividendos, precos, pasta):
    """Dividend yield mensal de cada FII (rendimento do mês / preço da cota)."""
    div_mes = dividendos.resample("ME").sum()
    preco_mes = precos.resample("ME").last()
    dy_mes = (div_mes / preco_mes).iloc[-24:]          # últimos 24 meses
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for i, c in enumerate(dy_mes.columns):
        ax.plot(dy_mes.index, dy_mes[c], marker="o", ms=3, lw=1.2,
                label=c.replace(".SA", ""), color=CORES[i % len(CORES)])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=2))
    ax.set_title("Dividend yield mensal (rendimento distribuído ÷ preço da cota)")
    ax.grid(alpha=0.3)
    ax.legend(ncol=4, fontsize=8)
    return _salvar(fig, pasta, "07_dividend_yield_mensal.png")


# =============================================================================
# 6. INTERPRETAÇÃO AUTOMÁTICA DOS RESULTADOS
# =============================================================================
def interpretar(metricas, sim, rf_anual, rm_anual, corr):
    """Gera frases de conclusão a partir dos números calculados, para que o
    relatório não seja apenas uma tabela, mas uma análise de risco e retorno."""
    m = metricas
    texto = []
    melhor_ret = m["Retorno anual (total)"].idxmax()
    menor_vol = m["Volatilidade anual"].idxmin()
    maior_vol = m["Volatilidade anual"].idxmax()
    melhor_sharpe = m["Índice de Sharpe"].idxmax()
    maior_dy = m["Dividend Yield 12m"].idxmax()

    texto.append(f"<b>{melhor_ret}</b> teve o maior retorno total anualizado "
                 f"({m.loc[melhor_ret, 'Retorno anual (total)']:.2%} a.a.).")
    texto.append(f"<b>{menor_vol}</b> foi o FII de menor risco total (volatilidade de "
                 f"{m.loc[menor_vol, 'Volatilidade anual']:.2%} a.a.), enquanto <b>{maior_vol}</b> "
                 f"foi o mais arriscado ({m.loc[maior_vol, 'Volatilidade anual']:.2%} a.a.).")
    texto.append(f"Considerando risco e retorno conjuntamente, o melhor Índice de Sharpe foi o de "
                 f"<b>{melhor_sharpe}</b> ({m.loc[melhor_sharpe, 'Índice de Sharpe']:.2f}): "
                 f"é o que mais remunerou cada unidade de risco acima do CDI.")

    venceram_cdi = list(m.index[m["Retorno anual (total)"] > rf_anual])
    if venceram_cdi:
        texto.append(f"No período, o CDI rendeu {rf_anual:.2%} a.a. e o IFIX {rm_anual:.2%} a.a. "
                     f"Superaram o CDI: <b>{', '.join(venceram_cdi)}</b>. Os demais não compensaram "
                     f"o risco assumido em relação a uma aplicação livre de risco.")
    else:
        texto.append(f"No período, o CDI rendeu {rf_anual:.2%} a.a. e o IFIX {rm_anual:.2%} a.a. "
                     "<b>Nenhum FII superou o CDI</b>: em períodos de juros altos, o ativo livre "
                     "de risco compete fortemente com os fundos imobiliários (prêmio de risco negativo).")

    texto.append(f"<b>{maior_dy}</b> apresentou o maior Dividend Yield nos últimos 12 meses "
                 f"({m.loc[maior_dy, 'Dividend Yield 12m']:.2%}). A diferença entre o retorno total "
                 "e o retorno só da cota mostra que, nos FIIs, a maior parte do retorno vem dos rendimentos.")

    alfas_pos = list(m.index[m["Alfa de Jensen"] > 0])
    texto.append("Pelo CAPM, " + (f"<b>{', '.join(alfas_pos)}</b> entregaram retorno acima do exigido "
                 "pelo seu risco sistemático (alfa positivo)." if alfas_pos else
                 "nenhum FII entregou retorno acima do exigido pelo seu beta (todos com alfa negativo).")
                 + " Betas menores que 1 indicam fundos menos sensíveis às oscilações do IFIX.")

    # Diversificação
    corr_media = corr.values[np.triu_indices_from(corr.values, k=1)].mean()
    t = sim["tabela"]
    vol_igual = t.loc["Pesos iguais", "Volatilidade"]
    reducao = 1 - vol_igual / sim["vol_sem_diversificacao"]
    texto.append(f"A correlação média entre os FIIs foi de {corr_media:.2f}. Por ser menor que 1, a "
                 f"carteira com pesos iguais teve volatilidade de {vol_igual:.2%}, contra "
                 f"{sim['vol_sem_diversificacao']:.2%} da média simples das volatilidades: a "
                 f"<b>diversificação eliminou {reducao:.0%} do risco</b> (risco não sistemático).")
    texto.append(f"Na fronteira eficiente, a carteira de <b>mínima variância</b> teria volatilidade de "
                 f"{t.loc['Mínima variância', 'Volatilidade']:.2%}, e a de <b>máximo Sharpe</b> "
                 f"retorno esperado de {t.loc['Máximo Sharpe', 'Retorno esperado']:.2%} com "
                 f"volatilidade de {t.loc['Máximo Sharpe', 'Volatilidade']:.2%}. "
                 "Lembrete: resultados passados não garantem retornos futuros.")
    return texto


# =============================================================================
# 7. GERAÇÃO DOS RELATÓRIOS (HTML + CSV)
# =============================================================================
PERCENTUAIS = {"Retorno acumulado", "Retorno anual (total)", "Retorno anual (só cota)",
               "Dividend Yield 12m", "Volatilidade anual", "Retorno exigido CAPM",
               "Alfa de Jensen", "Máximo drawdown", "VaR 95% diário", "CVaR 95% diário",
               "R² (risco sistemático)", "Retorno esperado", "Volatilidade"}


def formatar_tabela(df, colunas_peso=()):
    """Formata números para exibição: percentuais com '%', vírgula decimal."""
    saida = df.copy().astype(object)
    for col in df.columns:
        for idx in df.index:
            v = df.loc[idx, col]
            if pd.isna(v):
                txt = "—"
            elif col in PERCENTUAIS or col in colunas_peso:
                txt = f"{v:.2%}"
            elif col == "Preço atual (R$)":
                txt = f"R$ {v:,.2f}"
            else:
                txt = f"{v:.2f}"
            saida.loc[idx, col] = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return saida


def imagem_base64(caminho):
    with open(caminho, "rb") as f:
        return base64.b64encode(f.read()).decode()


def gerar_html(pasta, parametros, metricas, sim, corr, graficos, conclusoes):
    """Monta o relatório HTML autocontido (imagens embutidas)."""
    nomes = sim["nomes"]
    tabela_metricas = formatar_tabela(metricas).to_html(classes="tab", border=0)
    tabela_carteiras = formatar_tabela(sim["tabela"], colunas_peso=nomes).to_html(classes="tab", border=0)
    tabela_corr = corr.rename(index=lambda c: c.replace(".SA", ""),
                              columns=lambda c: c.replace(".SA", "")).round(2).to_html(classes="tab", border=0)

    def fig(chave, legenda):
        return (f'<figure><img src="data:image/png;base64,{imagem_base64(graficos[chave])}">'
                f"<figcaption>{legenda}</figcaption></figure>")

    p = parametros
    html = f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Risco e Retorno de FIIs</title>
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;max-width:1150px;margin:auto;padding:24px;color:#222;background:#fafafa}}
 h1{{color:#1f4e79;border-bottom:3px solid #1f4e79;padding-bottom:6px}}
 h2{{color:#1f4e79;margin-top:38px;border-bottom:1px solid #ccc}}
 .tab{{border-collapse:collapse;font-size:13px;margin:10px 0;background:white}}
 .tab th,.tab td{{padding:6px 10px;border-bottom:1px solid #ddd;text-align:right}}
 .tab th{{background:#1f4e79;color:white}} .tab tbody th{{background:#e8eef5;color:#1f4e79;text-align:left}}
 .scroll{{overflow-x:auto}}
 figure{{margin:18px 0;text-align:center}} img{{max-width:100%;border:1px solid #ddd;background:white}}
 figcaption{{font-size:13px;color:#555;margin-top:4px}}
 .box{{background:white;border-left:5px solid #1f4e79;padding:12px 18px;margin:12px 0}}
 li{{margin:6px 0}} small{{color:#666}}
</style></head><body>
<h1>Análise de Risco e Retorno de Fundos Imobiliários (FIIs)</h1>
<p><b>UFMG – FACE – CAD 167 Administração Financeira – Trabalho 1</b><br>
Relatório gerado automaticamente em {datetime.now():%d/%m/%Y às %H:%M}.</p>

<div class="box"><b>Parâmetros da análise</b><br>
FIIs analisados: {', '.join(nomes)}<br>
Período: {p['inicio']:%d/%m/%Y} a {p['fim']:%d/%m/%Y} ({p['n_dias']} pregões em comum)<br>
Benchmark de mercado (Rm): {p['benchmark']} (IFIX)<br>
Taxa livre de risco (Rf): CDI – {p['fonte_cdi']}<br>
Fonte de cotações e dividendos: Yahoo Finance (biblioteca yfinance)<br>
Tratamento de dados: {len(p['correcoes'])} cotação(ões) espúria(s) corrigida(s)
{'(' + '; '.join(f'{a} em {d:%d/%m/%Y}: R$ {v:.2f}' for a, d, v in p['correcoes']) + ')' if p['correcoes'] else ''}</div>

<h2>1. Principais conclusões</h2>
<ul>{''.join(f'<li>{c}</li>' for c in conclusoes)}</ul>

<h2>2. Tabela de risco e retorno</h2>
<div class="scroll">{tabela_metricas}</div>
<small>CDI no período: {p['rf']:.2%} a.a. | IFIX no período: {p['rm']:.2%} a.a. |
Volatilidade do IFIX: {p['vol_m']:.2%} a.a.</small>
<div class="box"><b>Como ler:</b>
<b>Retorno total</b> = valorização da cota + dividendos;
<b>Volatilidade</b> = desvio-padrão anualizado (risco total);
<b>Coef. de variação</b> = risco por unidade de retorno;
<b>Sharpe</b> = (Retorno − CDI) ÷ Volatilidade;
<b>Beta</b> = Cov(Ri,Rm) ÷ Var(Rm) (risco sistemático; &lt;1 = menos sensível que o IFIX);
<b>CAPM</b> = Rf + β·(Rm − Rf);
<b>Alfa de Jensen</b> = retorno obtido − retorno exigido pelo CAPM;
<b>R²</b> = parcela do risco explicada pelo mercado;
<b>Drawdown</b> = maior queda desde um pico;
<b>VaR 95%</b> = perda diária superada em apenas 5% dos dias;
<b>CVaR</b> = perda média nesses 5% piores dias.</div>

<h2>3. Evolução do investimento</h2>
{fig('evolucao', 'R$ 100 aplicados no início do período, com reinvestimento dos rendimentos.')}
{fig('dividendos', 'Rendimento mensal distribuído em relação ao preço da cota (últimos 24 meses).')}

<h2>4. Risco x Retorno</h2>
{fig('risco_retorno', 'Cada ponto é um FII. Ideal: mais acima (retorno) e mais à esquerda (risco). Pontos acima da linha tracejada tiveram Sharpe maior que o do IFIX.')}
{fig('drawdown', 'Quanto o investidor chegou a perder desde o último pico, em cada momento.')}
{fig('distribuicao', 'Frequência dos retornos diários. A linha vermelha marca o VaR histórico de 95%.')}

<h2>5. Diversificação e Teoria de Carteiras (Markowitz)</h2>
<p>Matriz de correlação dos retornos diários (quanto menor, maior o benefício da diversificação):</p>
<div class="scroll">{tabela_corr}</div>
{fig('correlacao', 'Correlação entre os retornos diários dos FIIs.')}
<p>Carteiras de destaque entre as {N_CARTEIRAS_SIMULADAS:,} simuladas (pesos sem venda a descoberto).
O retorno esperado aqui é a média aritmética anualizada dos retornos diários.</p>
<div class="scroll">{tabela_carteiras}</div>
{fig('fronteira', 'Cada ponto é uma carteira aleatória. A borda superior esquerda da nuvem é a fronteira eficiente.')}

<h2>6. Arquivos gerados</h2>
<p>Na mesma pasta deste relatório: gráficos em PNG; <code>metricas_risco_retorno.csv</code>,
<code>carteiras_otimas.csv</code>, <code>matriz_correlacao.csv</code>, <code>dados_capturados_precos.csv</code>,
<code>dados_capturados_dividendos.csv</code>, <code>dados_capturados_cdi.csv</code> (abrem no Excel).</p>
<small>Aviso: análise didática baseada em dados históricos. Retornos passados não garantem retornos futuros.</small>
</body></html>"""
    caminho = os.path.join(pasta, "relatorio.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    return caminho


def salvar_csv(df, pasta, nome):
    """Salva CSV no padrão brasileiro (';' e vírgula decimal) para o Excel."""
    df.to_csv(os.path.join(pasta, nome), sep=";", decimal=",", encoding="utf-8-sig")


# =============================================================================
# 8. ENTRADA DE DADOS PELO USUÁRIO
# =============================================================================
def ler_parametros():
    """Lê FIIs, período e benchmark: pela linha de comando ou perguntando ao
    usuário no terminal (ENTER aceita o valor padrão)."""
    parser = argparse.ArgumentParser(description="Análise de Risco e Retorno de FIIs")
    parser.add_argument("--fiis", nargs="+", help="códigos dos FIIs, ex.: HGLG11 KNRI11 MXRF11")
    parser.add_argument("--inicio", help="data inicial AAAA-MM-DD")
    parser.add_argument("--fim", help="data final AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--benchmark", default=None, help="ativo que representa o mercado (padrão XFIX11)")
    parser.add_argument("--padrao", action="store_true", help="usa os valores padrão sem perguntar")
    parser.add_argument("--nao-abrir", action="store_true", help="não abre o relatório no navegador")
    args = parser.parse_args()

    hoje = date.today()
    inicio_padrao = hoje.replace(year=hoje.year - ANOS_PADRAO)
    interativo = not args.padrao and args.fiis is None and sys.stdin.isatty()

    def perguntar(msg, padrao):
        if not interativo:
            return padrao
        resp = input(f"{msg} [ENTER = {padrao}]: ").strip()
        return resp or padrao

    if interativo:
        print("\nInforme os parâmetros (ou aperte ENTER para aceitar o padrão).")
    fiis_txt = " ".join(args.fiis) if args.fiis else perguntar(
        "FIIs separados por espaço ou vírgula", " ".join(FIIS_PADRAO))
    inicio_txt = args.inicio or perguntar("Data inicial (AAAA-MM-DD)", inicio_padrao.isoformat())
    fim_txt = args.fim or perguntar("Data final   (AAAA-MM-DD)", hoje.isoformat())
    bench_txt = args.benchmark or perguntar("Benchmark (índice de FIIs)", BENCHMARK_PADRAO)

    fiis = list(dict.fromkeys(normalizar_ticker(t) for t in fiis_txt.replace(",", " ").split() if t))
    try:
        inicio = datetime.strptime(inicio_txt, "%Y-%m-%d").date()
        fim = datetime.strptime(fim_txt, "%Y-%m-%d").date()
    except ValueError:
        sys.exit("ERRO: datas devem estar no formato AAAA-MM-DD (ex.: 2023-01-31).")
    if fim <= inicio:
        sys.exit("ERRO: a data final deve ser posterior à inicial.")
    if (fim - inicio).days > 365 * 10:
        sys.exit("ERRO: use um período de no máximo 10 anos (limite da API do Banco Central).")
    if len(fiis) < 2:
        sys.exit("ERRO: informe pelo menos 2 FIIs para a análise de diversificação.")
    return fiis, inicio, fim, normalizar_ticker(bench_txt), args.nao_abrir


# =============================================================================
# 9. PROGRAMA PRINCIPAL
# =============================================================================
def main():
    print("=" * 72)
    print(" ANÁLISE DE RISCO E RETORNO DE FUNDOS IMOBILIÁRIOS (FIIs)")
    print(" UFMG - CAD 167 Administração Financeira - Trabalho 1")
    print("=" * 72)

    fiis, inicio, fim, benchmark, nao_abrir = ler_parametros()

    # ---------- ETAPA 1: captura de dados ----------
    print("\n[1/4] Capturando dados da internet")
    precos, dividendos = capturar_cotacoes(fiis + [benchmark], inicio, fim)

    # Descarta ativos sem dados suficientes (código inválido ou fundo muito novo)
    minimo = 60
    validos = [c for c in precos.columns if precos[c].count() >= minimo]
    descartados = [c for c in fiis + [benchmark] if c not in validos]
    if descartados:
        print(f"     AVISO: ignorando ativos sem dados suficientes: {', '.join(descartados)}")
    if benchmark not in validos:
        sys.exit(f"ERRO: sem dados para o benchmark {benchmark}.")
    fiis = [f for f in fiis if f in validos]
    if len(fiis) < 2:
        sys.exit("ERRO: menos de 2 FIIs com dados válidos.")

    # Período comum: só datas em que todos os ativos têm cotação (preenche
    # pequenos buracos de dias sem negociação com o último preço conhecido)
    precos = precos[fiis + [benchmark]].ffill(limit=5).dropna()
    precos, correcoes = limpar_precos(precos)
    for ativo, dia, valor in correcoes:
        print(f"     AVISO: cotação espúria corrigida: {ativo} em {dia:%d/%m/%Y} (R$ {valor:.2f})")
    dividendos = dividendos.reindex(index=precos.index, columns=precos.columns).fillna(0.0)

    cdi, fonte_cdi = capturar_cdi(inicio, fim)

    # ---------- ETAPA 2: retornos ----------
    print("[2/4] Calculando retornos")
    ret_todos = retornos_totais(precos, dividendos)
    ret_preco_todos = precos.pct_change().iloc[1:]
    ret = ret_todos[fiis]
    ret_preco = ret_preco_todos[fiis]
    ret_mercado = ret_todos[benchmark]

    # Alinha o CDI às datas de pregão (taxa do dia anterior, quando faltar)
    if cdi is not None:
        cdi_diario = cdi.reindex(ret.index).ffill().bfill()
    else:
        cdi_diario = pd.Series((1 + CDI_ANUAL_RESERVA) ** (1 / DIAS_UTEIS_ANO) - 1, index=ret.index)

    # ---------- ETAPA 3: métricas de risco e retorno ----------
    print("[3/4] Calculando medidas de risco, CAPM e simulando carteiras (Markowitz)")
    metricas, rf_anual, rm_anual = calcular_metricas(ret, ret_preco, ret_mercado, cdi_diario,
                                                    precos[fiis], dividendos[fiis])
    vol_mercado = ret_mercado.std() * np.sqrt(DIAS_UTEIS_ANO)
    corr = ret.corr()
    sim = simular_carteiras(ret, rf_anual)
    conclusoes = interpretar(metricas, sim, rf_anual, rm_anual, corr)

    # ---------- ETAPA 4: relatórios ----------
    print("[4/4] Gerando gráficos e relatórios")
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relatorios",
                         datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(pasta, exist_ok=True)

    graficos = {
        "evolucao": grafico_evolucao(ret, ret_mercado, cdi_diario, pasta),
        "risco_retorno": grafico_risco_retorno(metricas, rf_anual, rm_anual, vol_mercado, pasta),
        "correlacao": grafico_correlacao(ret, pasta),
        "drawdown": grafico_drawdown(ret, pasta),
        "distribuicao": grafico_distribuicao(ret, metricas, pasta),
        "fronteira": grafico_fronteira(sim, rf_anual, pasta),
        "dividendos": grafico_dividendos(dividendos[fiis], precos[fiis], pasta),
    }

    # Tabelas em CSV (resultados e dados brutos capturados)
    salvar_csv(metricas, pasta, "metricas_risco_retorno.csv")
    salvar_csv(sim["tabela"], pasta, "carteiras_otimas.csv")
    salvar_csv(corr, pasta, "matriz_correlacao.csv")
    salvar_csv(precos, pasta, "dados_capturados_precos.csv")
    salvar_csv(dividendos[dividendos.sum(axis=1) > 0], pasta, "dados_capturados_dividendos.csv")
    salvar_csv(cdi_diario.rename("CDI diário"), pasta, "dados_capturados_cdi.csv")

    parametros = {"inicio": precos.index[0], "fim": precos.index[-1], "n_dias": len(ret),
                  "benchmark": benchmark.replace(".SA", ""), "fonte_cdi": fonte_cdi,
                  "rf": rf_anual, "rm": rm_anual, "vol_m": vol_mercado,
                  "correcoes": correcoes}
    relatorio = gerar_html(pasta, parametros, metricas, sim, corr, graficos, conclusoes)

    # ---------- Resumo no terminal ----------
    print("\n" + "=" * 72)
    print(" RESUMO")
    print("=" * 72)
    colunas_resumo = ["Retorno anual (total)", "Dividend Yield 12m", "Volatilidade anual",
                      "Índice de Sharpe", "Beta (vs IFIX)", "Alfa de Jensen", "Máximo drawdown"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(formatar_tabela(metricas[colunas_resumo]).to_string())
        pct = lambda v: f"{v:.2%}".replace(".", ",")
        print(f"\nCDI: {pct(rf_anual)} a.a. | IFIX ({benchmark.replace('.SA', '')}): {pct(rm_anual)} a.a.")
        print("\nCarteiras ótimas:")
        print(formatar_tabela(sim["tabela"], colunas_peso=sim["nomes"]).to_string())
    print(f"\nRelatório completo: {relatorio}")

    if not nao_abrir:
        webbrowser.open("file://" + os.path.abspath(relatorio))


if __name__ == "__main__":
    main()
