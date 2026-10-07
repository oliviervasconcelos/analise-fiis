# -*- coding: utf-8 -*-
"""
===============================================================================
 TETO - preço teto e risco de fundos imobiliários (site interativo)
===============================================================================
Como executar (na pasta site_fiis):
    pip install -r requirements.txt
    streamlit run app.py
O navegador abre em http://localhost:8501

Páginas (navegação no topo):
  Mercado   -> todos os FIIs com preço atual, preço teto e margem de segurança,
               com filtros e busca; clique em uma linha para abrir o fundo
  Fundo     -> análise de um FII: como o teto é calculado, tipo do fundo,
               composição do prêmio, cotação x teto, dividendos, risco e retorno
  Comparar  -> vários FIIs lado a lado (retorno, risco, correlação)
  Panorama  -> visão do mercado de FIIs por tipo e segmento
  Método    -> fórmulas, regras e fontes de dados

  Relatório -> gera o relatório da análise (HTML + CSV) e salva em relatorios/

Temas da disciplina abordados:
  - Valor do dinheiro no tempo: custo de oportunidade (Tesouro IPCA+), taxa
    real x nominal (Fisher), taxa líquida de IR e valor presente de uma
    perpetuidade (preço teto = dividendo / taxa exigida). Ver calculos.py.
  - Risco e retorno: prêmio de risco somado à taxa exigida, medidas de risco
    (volatilidade, Beta, Sharpe, drawdown, VaR) e diversificação (correlação).

Captura de dados (dados.py): Fundamentus, Yahoo Finance, CVM, Banco Central e
Tesouro Transparente. Cada captura bem-sucedida guarda uma cópia local em
dados_salvos/, usada se a fonte estiver fora do ar.

Painel lateral: premissas (título IPCA+ de referência, prêmio, ajuste de IPCA).
Os parâmetros ficam salvos em config_fiis.json. O visual (paleta, tipografia,
componentes) está em estilo.py e .streamlit/config.toml.
"""
import json
import os
import re
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as componentes_html

import calculos
import dados
import estilo
import relatorio
from estilo import (CORES_TIPO, LINHA, PAPEL_CLARO, SALVIA, SALVIA_CLARA, TERRA_CLARA, TERRA_ESCURA,
                    TERRACOTA, TINTA, TINTA_45, TINTA_70, cabecalho, cifras, etiqueta, grafico, nota,
                    secao, sinal)

st.set_page_config(page_title="Teto · preço teto de FIIs", page_icon=":material/roofing:", layout="wide",
                   initial_sidebar_state="expanded")
estilo.aplicar_css()

AUTORES = "Olivier Menezes Vasconcelos e Lucas Oliveira Frade Ribeiro Cordeiro"
PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_CONFIG = os.path.join(PASTA, "config_fiis.json")
PERIODOS = {"1 ano": 1, "2 anos": 2, "3 anos": 3, "5 anos": 5, "10 anos": 10}
CORES_SERIES = [TERRACOTA, SALVIA, "#4D6B62", TERRA_CLARA, TERRA_ESCURA, SALVIA_CLARA, "#9C8A72",
                TINTA_70, "#C9B79C", "#2F5D50"]


# =============================================================================
# Formatação no padrão brasileiro
# =============================================================================
def _br(texto):
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v, casas=2):
    return "—" if pd.isna(v) else _br(f"R$ {v:,.{casas}f}")


def pct(v, casas=2):
    return "—" if pd.isna(v) else _br(f"{v * 100:,.{casas}f}%")


def num(v, casas=2):
    return "—" if pd.isna(v) else _br(f"{v:,.{casas}f}")


def compacto(v):
    """R$ 1,2 mi / R$ 3,4 bi para valores grandes."""
    if pd.isna(v):
        return "—"
    for limite, sufixo in [(1e9, "bi"), (1e6, "mi"), (1e3, "mil")]:
        if abs(v) >= limite:
            return _br(f"R$ {v / limite:,.1f} {sufixo}")
    return brl(v, 0)


def nome_curto(nome):
    """'PÁTRIA LOG - FUNDO DE INVESTIMENTO IMOBILIÁRIO - RESP. LTDA' -> 'Pátria Log'."""
    if not isinstance(nome, str) or not nome.strip():
        return ""
    base = re.split(r"\s+-\s+", nome)[0]
    base = re.sub(r"FUNDO DE INVESTIMENTO IMOBILI[ÁA]RIO|RESPONSABILIDADE LIMITADA|RESP\.? LTDA|\bFII\b",
                  "", base, flags=re.I).strip(" -")
    return base.title() if base else nome.title()


# =============================================================================
# Premissas salvas (config_fiis.json)
# =============================================================================
COLUNAS_PARAM = ["FII", "Tipo (manual)", "Prêmio (%)", "Ajuste IPCA (%)", "IPCA cheio", "Div. 12m manual (R$)"]
TIPOS = ["Papel", "Híbrido", "FoF", "Tijolo", "Indefinido"]
MODO_AUTO, MODO_MANUAL = "Automático", "Minha planilha"


def ler_config():
    padrao = {"ipca": 0.0439, "ipca_mais": 0.0836, "aliquota_ir": 0.15, "premio_base": 0.01,
              "peso_fatores": 1.0, "modo_premio": MODO_AUTO, "modo_ipca": MODO_AUTO,
              "fator_ipca": calculos.FATOR_IPCA_PADRAO, "minha_lista": []}
    try:
        with open(ARQ_CONFIG, encoding="utf-8") as f:
            padrao.update(json.load(f))
    except (OSError, json.JSONDecodeError):
        pass
    return padrao


def salvar_config():
    """Grava as premissas globais e a minha lista em config_fiis.json."""
    s = st.session_state
    params = s.params_editados.copy()
    params["FII"] = params["FII"].astype(str).str.upper().str.strip()
    params = params[params["FII"].str.len() > 0].drop_duplicates("FII")
    params = params.astype(object).where(params.notna(), None)
    cfg = {"ipca": s.ipca / 100, "ipca_mais": s.ipca_mais / 100, "aliquota_ir": s.ir / 100,
           "premio_base": s.premio_base / 100, "peso_fatores": s.peso_fatores,
           "modo_premio": s.modo_premio, "modo_ipca": s.modo_ipca,
           "fator_ipca": {t: s[f"fator_{t}"] / 100 for t in TIPOS},
           "minha_lista": params[COLUNAS_PARAM].to_dict("records")}
    with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    s.params_base = params[COLUNAS_PARAM].reset_index(drop=True)
    s.params_editados = s.params_base.copy()
    s.versao_editor += 1
    st.toast("Premissas salvas em config_fiis.json")


# Inicialização do estado da sessão (só na primeira execução)
if "params_base" not in st.session_state:
    cfg = ler_config()
    s = st.session_state
    s.ipca = round(cfg["ipca"] * 100, 4)
    s.ipca_mais = round(cfg["ipca_mais"] * 100, 4)
    s.ir = round(cfg["aliquota_ir"] * 100, 4)
    s.premio_base = round(cfg["premio_base"] * 100, 4)
    s.peso_fatores = float(cfg["peso_fatores"])
    s.modo_premio = cfg["modo_premio"]
    s.modo_ipca = cfg["modo_ipca"]
    for tipo in TIPOS:
        s[f"fator_{tipo}"] = round(cfg["fator_ipca"].get(tipo, calculos.FATOR_IPCA_PADRAO[tipo]) * 100, 1)
    base = pd.DataFrame(cfg["minha_lista"]).reindex(columns=COLUNAS_PARAM)
    base["IPCA cheio"] = base["IPCA cheio"].eq(True)
    base["Tipo (manual)"] = base["Tipo (manual)"].where(base["Tipo (manual)"].isin(TIPOS), None)
    for c in ["Prêmio (%)", "Ajuste IPCA (%)", "Div. 12m manual (R$)"]:
        base[c] = pd.to_numeric(base[c], errors="coerce")
    s.params_base = base
    s.params_editados = base.copy()
    s.versao_editor = 0
    s.versao_tabela = 0


# =============================================================================
# Painel lateral: premissas
# =============================================================================
with st.sidebar:
    st.markdown("<div class='marca'>Teto<span>.</span></div>"
                "<div class='marca-sub'>Preço teto e risco de fundos imobiliários</div>", unsafe_allow_html=True)

    st.markdown("<div class='olho-lateral'>Título de referência · IPCA+</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.number_input("IPCA %", step=0.05, format="%.2f", key="ipca")
    c2.number_input("IPCA+ %", step=0.05, format="%.2f", key="ipca_mais")
    c3.number_input("IR %", step=2.5, format="%.1f", key="ir")
    IPCA = st.session_state.ipca / 100
    TAXAS = calculos.taxas_referencia(IPCA, st.session_state.ipca_mais / 100, st.session_state.ir / 100)
    st.markdown(f"<div class='razao-lateral'><div>Bruto<b>{pct(TAXAS['bruta'])}</b></div>"
                f"<div>Líquido<b>{pct(TAXAS['liquida'])}</b></div>"
                f"<div class='ativo'>Real líq.<b>{pct(TAXAS['equivalente'])}</b></div></div>",
                unsafe_allow_html=True)

    with st.expander("Referências de mercado hoje"):
        focus, data_focus = dados.ipca_focus_12m()
        ipca_12m, data_ipca = dados.serie_sgs_ultimo(13522)
        selic, _ = dados.serie_sgs_ultimo(432)
        tesouro = dados.taxas_tesouro_ipca()
        st.markdown(f"IPCA esperado 12m (Focus) **{pct(focus)}**  \nIPCA últimos 12m **{pct(ipca_12m)}**  \n"
                    f"Selic meta **{pct(selic)}**")
        if not tesouro.empty:
            st.caption(f"Tesouro IPCA+, taxa de compra em {tesouro['Data'].iloc[0]:%d/%m/%Y}")
            st.dataframe(tesouro.assign(Taxa=tesouro["Taxa"].map(pct))[["Vencimento", "Taxa"]],
                         hide_index=True, width="stretch")
            venc = st.selectbox("Vencimento", tesouro["Vencimento"].tolist(), index=len(tesouro) - 1)

            def _usar_mercado():
                if focus is not None:
                    st.session_state.ipca = round(focus * 100, 2)
                st.session_state.ipca_mais = round(
                    float(tesouro.loc[tesouro["Vencimento"] == venc, "Taxa"].iloc[0]) * 100, 2)

            st.button("Usar Focus e Tesouro", on_click=_usar_mercado, width="stretch")
        else:
            st.caption("Tesouro Transparente indisponível no momento.")

    st.markdown("<div class='olho-lateral'>Prêmio de risco</div>", unsafe_allow_html=True)
    st.segmented_control("Prêmio usado", [MODO_AUTO, MODO_MANUAL], key="modo_premio",
                         label_visibility="collapsed",
                         help="Automático: score com dados do fundo. Minha planilha: o prêmio definido "
                              "na sua lista (os demais fundos seguem o automático).")
    c1, c2 = st.columns(2)
    c1.number_input("Base %", step=0.25, format="%.2f", key="premio_base",
                    help="Prêmio mínimo, somado aos pontos dos fatores de risco.")
    c2.number_input("Peso", min_value=0.0, max_value=3.0, step=0.25, format="%.2f",
                    key="peso_fatores", help="Multiplica os pontos dos fatores de risco. 1 = padrão; 2 = mais conservador.")

    st.markdown("<div class='olho-lateral'>Ajuste de IPCA</div>", unsafe_allow_html=True)
    st.segmented_control("Ajuste usado", [MODO_AUTO, MODO_MANUAL], key="modo_ipca",
                         label_visibility="collapsed",
                         help="Automático: IPCA × fração do tipo do fundo (composição informada à CVM). "
                              "Minha planilha: o ajuste da sua lista, quando definido.")
    with st.expander("Fração do IPCA por tipo"):
        for tipo in TIPOS:
            st.number_input(f"{tipo} %", min_value=0.0, max_value=200.0, step=10.0, format="%.0f",
                            key=f"fator_{tipo}")
    FATOR_IPCA = {t: st.session_state[f"fator_{t}"] / 100 for t in TIPOS}

    st.markdown("<div class='olho-lateral'>Dados</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("Atualizar", width="stretch", help="Baixa as cotações novamente (Yahoo Finance)."):
        dados.carregar_mercado.clear()
        st.rerun()
    c2.button("Salvar", type="primary", on_click=salvar_config, width="stretch",
              help="Grava premissas e minha lista em config_fiis.json.")
    st.markdown("<div class='rodape-lateral'>Fundamentus, Yahoo Finance, CVM, Banco Central e Tesouro "
                "Transparente. Cotações com cerca de 15 minutos de atraso.<br>Ferramenta educacional; "
                "não é recomendação de investimento.</div>", unsafe_allow_html=True)

# Os modos podem ficar vazios se o usuário desmarcar o controle segmentado
MODO_PREMIO = st.session_state.modo_premio or MODO_AUTO
MODO_IPCA = st.session_state.modo_ipca or MODO_AUTO


# =============================================================================
# Montagem da tabela principal (todos os FIIs + cotações + preço teto)
# =============================================================================
COLUNAS_CVM = ["cnpj", "nome_cvm", "data_cvm", "gestao_cvm", "administrador", "pct_papel", "pct_tijolo",
               "pct_fof", "cotistas", "pl", "taxa_adm_mes"]


def descrever_riscos(linha_componentes):
    """Texto curto com os fatores que somaram prêmio, do maior para o menor."""
    itens = linha_componentes[linha_componentes > 0].sort_values(ascending=False)
    return " · ".join(f"{fator} +{_br(f'{v * 100:.2f}')}" for fator, v in itens.items()) or "—"


def montar_tabela(params):
    """Junta Fundamentus + Yahoo + CVM + parâmetros do usuário e calcula, para
    cada FII: tipo, ajuste de IPCA, prêmio de risco, preço teto e margem.
    Retorna (tabela, componentes do prêmio automático, horário das cotações,
    origem de cada fonte: "online" ou "cópia de ...")."""
    s = st.session_state
    origens = {}
    params = params.copy()
    params["FII"] = params["FII"].astype(str).str.upper().str.strip()
    params = params[params["FII"].str.len() > 0].drop_duplicates("FII")
    minha = params["FII"].tolist()

    # Lista de FIIs (Fundamentus). Sem internet e sem cópia salva, o site ainda
    # funciona com a minha lista, buscando cada fundo direto no Yahoo.
    try:
        lista, origens["Fundamentus"] = dados.carregar_lista_fiis()
        lista = lista.copy()
    except Exception:
        origens["Fundamentus"] = "indisponível"
        lista = pd.DataFrame(columns=["fii", "segmento", "preco_ref", "ffo_yield", "dy", "pvp", "valor_mercado",
                                      "liquidez", "qtd_imoveis", "preco_m2", "aluguel_m2", "cap_rate", "vacancia",
                                      "div_12m", "vp_cota", "fonte"])

    # FIIs da minha lista ausentes no Fundamentus: busca no Yahoo
    faltantes = [t for t in minha if t not in set(lista["fii"])]
    extras = [d for d in (dados.dados_yahoo_avulso(t) for t in faltantes) if d]
    if extras:
        lista = pd.concat([lista, pd.DataFrame(extras)], ignore_index=True)

    # Cotações, dividendos e métricas de 1 ano (Yahoo)
    negociados = sorted(set(lista.loc[lista["liquidez"].fillna(0) > 0, "fii"]) | set(minha))
    try:
        mercado, hora, origens["Yahoo Finance"] = dados.carregar_mercado(tuple(negociados))
    except Exception:
        origens["Yahoo Finance"] = "indisponível"
        hora = datetime.now()
        mercado = pd.DataFrame(columns=["preco", "var_dia", "data_preco", "div_12m_y", "vol_1a", "dd_1a",
                                        "cv_div", "tend_div", "meses_pagos"])
    tab = lista.merge(mercado, left_on="fii", right_index=True, how="left")
    for col in mercado.columns.drop("data_preco"):
        tab[col] = pd.to_numeric(tab[col], errors="coerce")
    tab["fonte_preco"] = np.where(tab["preco"].notna(), "Yahoo", "Fundamentus")
    tab["preco"] = tab["preco"].fillna(tab["preco_ref"])

    # Composição dos ativos e cadastro (CVM)
    try:
        cvm, origens["CVM"] = dados.carregar_cvm()
    except Exception:
        cvm, origens["CVM"] = pd.DataFrame(), "indisponível"
    tab = tab.merge(cvm.reindex(columns=COLUNAS_CVM), left_on="fii", right_index=True, how="left")

    # Parâmetros da minha lista
    tab = tab.merge(params, left_on="fii", right_on="FII", how="left")
    tab["na_lista"] = tab["FII"].notna()

    # Dividendo 12m: soma real dos pagamentos (Yahoo) > DY × cotação (Fundamentus) > manual
    tab["fonte_div"] = "Fundamentus (DY × cotação)"
    yahoo = tab["div_12m_y"] > 0
    tab.loc[yahoo, "div_12m"] = tab.loc[yahoo, "div_12m_y"]
    tab.loc[yahoo, "fonte_div"] = "Yahoo (soma dos pagamentos)"
    manual = tab["Div. 12m manual (R$)"].notna()
    tab.loc[manual, "div_12m"] = tab.loc[manual, "Div. 12m manual (R$)"]
    tab.loc[manual, "fonte_div"] = "manual"
    tab["dy_atual"] = tab["div_12m"] / tab["preco"]
    tab["pvp_atual"] = tab["preco"] / tab["vp_cota"]

    # Tipo do fundo (CVM, estimado ou definido manualmente)
    tipos = [calculos.classificar_tipo(*v) for v in
             zip(tab["pct_papel"], tab["pct_tijolo"], tab["pct_fof"], tab["qtd_imoveis"], tab["segmento"])]
    tab["tipo"] = [t[0] for t in tipos]
    tab["origem_tipo"] = [t[1] for t in tipos]
    tipo_manual = tab["Tipo (manual)"].isin(TIPOS)
    tab.loc[tipo_manual, "tipo"] = tab.loc[tipo_manual, "Tipo (manual)"]
    tab.loc[tipo_manual, "origem_tipo"] = "manual"

    # Ajuste de IPCA
    tab["ajuste_auto"] = tab["tipo"].map(FATOR_IPCA).fillna(0.5) * IPCA
    tab["ajuste_ipca"], tab["origem_ajuste"] = tab["ajuste_auto"], "automático"
    if MODO_IPCA == MODO_MANUAL:
        manual_ipca = tab["IPCA cheio"].eq(True) | tab["Ajuste IPCA (%)"].notna()
        valor = np.where(tab["IPCA cheio"].eq(True), IPCA, tab["Ajuste IPCA (%)"] / 100)
        tab.loc[manual_ipca, "ajuste_ipca"] = valor[manual_ipca.to_numpy()]
        tab.loc[manual_ipca, "origem_ajuste"] = "minha planilha"

    # Prêmio de risco (score automático e, se escolhido, o da minha planilha)
    tab["premio_auto"], componentes = calculos.premio_automatico(tab, s.premio_base / 100, s.peso_fatores)
    componentes.index = tab["fii"]
    tab["riscos"] = [descrever_riscos(componentes.iloc[i]) for i in range(len(tab))]
    tab["premio"], tab["origem_premio"] = tab["premio_auto"], "automático"
    if MODO_PREMIO == MODO_MANUAL:
        manual_pr = tab["Prêmio (%)"].notna()
        tab.loc[manual_pr, "premio"] = tab.loc[manual_pr, "Prêmio (%)"] / 100
        tab.loc[manual_pr, "origem_premio"] = "minha planilha"
    tab["premio_planilha"] = tab["Prêmio (%)"] / 100

    # Preço teto, margem e prêmio implícito
    tab["teto"], tab["taxa_exigida"] = calculos.preco_teto(tab["div_12m"], TAXAS["equivalente"],
                                                            tab["premio"], tab["ajuste_ipca"])
    tab["margem"] = tab["teto"] / tab["preco"] - 1
    tab["premio_impl"] = calculos.premio_implicito(tab["div_12m"], tab["preco"],
                                                   TAXAS["equivalente"], tab["ajuste_ipca"])
    tab = tab.drop(columns=COLUNAS_PARAM).sort_values("fii").reset_index(drop=True)
    return tab, componentes, hora, origens


TABELA, COMPONENTES, HORA_COTACAO, ORIGENS = montar_tabela(st.session_state.params_editados)
if TABELA.empty:
    st.error("Nenhuma fonte de dados respondeu e não há cópia salva. Verifique a conexão com a internet.")
    st.stop()
# Fontes que não responderam e estão usando a cópia local (plano B)
AVISO_FONTES = " · ".join(f"{fonte}: {origem}" for fonte, origem in ORIGENS.items() if origem != "online")
TODOS = TABELA["fii"].tolist()
MINHA_LISTA = TABELA.loc[TABELA["na_lista"], "fii"].tolist()
LINHAS = TABELA.set_index("fii")


# =============================================================================
# Estilos de célula das tabelas (Pandas Styler)
# =============================================================================
def cor_margem(v):
    """Fundo tingido: verde-tinta para margem positiva, terracota para negativa;
    a intensidade cresce com o tamanho da margem."""
    if pd.isna(v):
        return ""
    alfa = 0.07 + min(abs(v), 0.6) * 0.45
    if v >= 0:
        return f"background-color: rgba(28,53,48,{alfa:.2f}); color: {TINTA}; font-weight: 600"
    return f"background-color: rgba(180,83,42,{alfa:.2f}); color: {TERRA_ESCURA}; font-weight: 600"


def cor_variacao(v):
    if pd.isna(v) or v == 0:
        return f"color: {TINTA_45}"
    return f"color: {TINTA if v > 0 else TERRACOTA}"


CORES_TIPO_TEXTO = {**CORES_TIPO, "FoF": "#A8693F", "Híbrido": "#557167", "Indefinido": TINTA_45}


def cor_tipo(v):
    return f"color: {CORES_TIPO_TEXTO.get(v, TINTA_70)}; font-weight: 600"


def folga_barras(fig, valores, folga=0.22):
    """Amplia o eixo x de um gráfico de barras horizontais para os rótulos
    de valor caberem nas pontas."""
    mini, maxi = min(0.0, float(np.nanmin(valores))), max(0.0, float(np.nanmax(valores)))
    largura = (maxi - mini) or 1.0
    fig.update_xaxes(range=[mini - (folga * largura if mini < 0 else 0), maxi + (folga * largura if maxi > 0 else 0)])


def sinal_pct(v):
    return sinal(pct(v), v >= 0) if pd.notna(v) else "—"


# =============================================================================
# PÁGINA: MERCADO (preço teto de todos os FIIs)
# =============================================================================
def pagina_mercado():
    cabecalho(
        olho=f"Mercado · {len(TABELA)} fundos listados na B3",
        titulo="Quanto pagar<br>por cada <em>FII</em>",
        lead="O preço teto é o maior preço que ainda faz o fundo render mais do que um título IPCA+ "
             "líquido de IR, somado ao prêmio que o risco de cada fundo exige.",
        razao=[("Taxa real exigida, base", pct(TAXAS["equivalente"])),
               ("Prêmio de risco", MODO_PREMIO),
               ("Ajuste de IPCA", MODO_IPCA),
               ("Cotações", f"{HORA_COTACAO:%H:%M}<small>Yahoo Finance · ~15 min de atraso</small>")])
    if AVISO_FONTES:
        nota(f"Algumas fontes não responderam agora e o site está usando a última cópia salva: {AVISO_FONTES}.",
             atencao=True)

    # --------- Minha lista ---------
    with st.expander("Minha lista e parâmetros por fundo"):
        st.caption("Inclua ou remova fundos na última linha; deixe em branco o que deve ser automático. "
                   "Tipo (manual) corrige a classificação da CVM. Prêmio e Ajuste IPCA valem no modo "
                   "Minha planilha. Para manter as alterações, use Salvar no painel lateral.")
        chave = f"editor_{st.session_state.versao_editor}"
        editado = st.data_editor(
            st.session_state.params_base, num_rows="dynamic", hide_index=True, width="stretch", key=chave,
            column_config={
                "FII": st.column_config.TextColumn(required=True),
                "Tipo (manual)": st.column_config.SelectboxColumn(options=TIPOS[:-1]),
                "Prêmio (%)": st.column_config.NumberColumn(min_value=-5.0, max_value=30.0, step=0.25, format="%.2f"),
                "Ajuste IPCA (%)": st.column_config.NumberColumn(min_value=0.0, max_value=20.0, step=0.1, format="%.2f"),
                "IPCA cheio": st.column_config.CheckboxColumn(default=False),
                "Div. 12m manual (R$)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
            })
        # Recalcula a tabela quando a edição muda (assinatura das alterações do editor)
        assinatura = json.dumps(st.session_state.get(chave, {}), sort_keys=True, default=str)
        if assinatura != st.session_state.get("assinatura_editor"):
            st.session_state.assinatura_editor = assinatura
            st.session_state.params_editados = editado
            st.rerun()

    # --------- Filtros ---------
    with st.container(border=True):
        f1, f2, f3, f4, f5 = st.columns([2.2, 2.2, 1.8, 3, 1.8])
        busca = f1.text_input("Buscar código", placeholder="HGLG, KNCR…")
        escopo = f2.segmented_control("Universo", ["Minha lista", "Todos"], default="Minha lista") or "Minha lista"
        tipos_sel = f3.multiselect("Tipo", TIPOS, placeholder="Todos")
        segmentos = f4.multiselect("Segmento", sorted(TABELA["segmento"].dropna().unique()), placeholder="Todos")
        liq_opcoes = {"Qualquer": 0, "R$ 100 mil": 1e5, "R$ 500 mil": 5e5, "R$ 1 mi": 1e6, "R$ 5 mi": 5e6}
        liq_min = liq_opcoes[f5.selectbox("Liquidez mín./dia", list(liq_opcoes), index=1,
                                          disabled=escopo == "Minha lista")]
        g1, g2, g3, g4 = st.columns([3, 3, 2, 2], vertical_alignment="bottom")
        pvp_faixa = g1.slider("P/VP", 0.0, 2.0, (0.0, 2.0), 0.05)
        dy_faixa = g2.slider("Dividend yield 12m, %", 0.0, 25.0, (0.0, 25.0), 0.5)
        so_margem = g3.toggle("Só abaixo do teto")
        sem_div = g4.toggle("Ocultar sem dividendos", value=True)

    t = TABELA.copy()
    t = t[t["na_lista"]] if escopo == "Minha lista" else t[(t["liquidez"].fillna(0) >= liq_min) | t["na_lista"]]
    if busca:
        t = t[t["fii"].str.contains(busca.strip().upper(), regex=False)]
    if tipos_sel:
        t = t[t["tipo"].isin(tipos_sel)]
    if segmentos:
        t = t[t["segmento"].isin(segmentos)]
    pvp = t["pvp_atual"]
    t = t[pvp.isna() | ((pvp >= pvp_faixa[0]) & ((pvp <= pvp_faixa[1]) | (pvp_faixa[1] >= 2.0)))]
    dy = t["dy_atual"] * 100
    t = t[(dy >= dy_faixa[0]) & ((dy <= dy_faixa[1]) | (dy_faixa[1] >= 25.0))]
    if so_margem:
        t = t[t["margem"] > 0]
    if sem_div:
        t = t[t["div_12m"] > 0]
    t = t.sort_values("margem", ascending=False).reset_index(drop=True)

    abaixo = int((t["margem"] > 0).sum())
    cifras([("Fundos na seleção", f"{len(t)}", escopo.lower()),
            ("Abaixo do teto", f"{abaixo}", f"{pct(abaixo / len(t), 0) if len(t) else '—'} da seleção"),
            ("Margem mediana", sinal_pct(t["margem"].median()), "teto ÷ preço − 1"),
            ("Yield 12m mediano", pct(t["dy_atual"].median()), "dividendos ÷ preço"),
            ("P/VP mediano", num(t["pvp_atual"].median()), "preço ÷ valor patrimonial")])

    # --------- Tabela ---------
    secao(1, "Fundos", "Ordenados pela margem de segurança. Selecione uma linha para abrir a análise completa.")
    exibir = pd.DataFrame({
        "FII": t["fii"], "Tipo": t["tipo"], "Segmento": t["segmento"], "Preço": t["preco"],
        "Dia": t["var_dia"], "Teto": t["teto"], "Margem": t["margem"], "Div. 12m": t["div_12m"],
        "Yield": t["dy_atual"], "P/VP": t["pvp_atual"], "Prêmio": t["premio"], "IPCA": t["ajuste_ipca"],
        "Prêmio implícito": t["premio_impl"], "Riscos que compõem o prêmio": t["riscos"],
        "% Papel": t["pct_papel"], "Liquidez/dia": t["liquidez"], "Vacância": t["vacancia"],
        "Volat. 12m": t["vol_1a"], "Valor de mercado": t["valor_mercado"],
        "Lista": np.where(t["na_lista"], "sim", ""),
    })
    estilo_tab = (exibir.style
                  .format({"Preço": brl, "Dia": pct, "Teto": brl, "Margem": pct, "Div. 12m": brl, "Yield": pct,
                           "P/VP": num, "Prêmio": pct, "IPCA": pct, "Prêmio implícito": pct,
                           "% Papel": lambda v: pct(v, 0), "Liquidez/dia": compacto, "Vacância": pct,
                           "Volat. 12m": pct, "Valor de mercado": compacto})
                  .map(cor_tipo, subset=["Tipo"])
                  .map(cor_margem, subset=["Margem"])
                  .map(cor_variacao, subset=["Dia"])
                  .set_properties(subset=["FII", "Teto"], **{"font-weight": "600"}))
    evento = st.dataframe(estilo_tab, hide_index=True, width="stretch", height=640,
                          on_select="rerun", selection_mode="single-row",
                          key=f"tabela_{st.session_state.versao_tabela}",
                          column_config={"FII": st.column_config.TextColumn(width=80, pinned=True),
                                         "Riscos que compõem o prêmio": st.column_config.TextColumn(width="large")})
    if evento.selection.rows:
        st.session_state.fii_atual = t.iloc[evento.selection.rows[0]]["fii"]
        st.session_state.versao_tabela += 1          # limpa a seleção ao voltar
        st.switch_page(PG_FUNDO)

    c1, c2 = st.columns([7, 2], vertical_alignment="center")
    c1.caption("IPCA: ajuste somado à taxa exigida conforme o tipo do fundo · Prêmio implícito: o prêmio que o "
               "preço atual paga · % Papel: parcela em CRI/LCI segundo a CVM.")
    c2.download_button("Exportar CSV", t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                       file_name=f"preco_teto_fiis_{date.today()}.csv", mime="text/csv", width="stretch")


# =============================================================================
# PÁGINA: FUNDO (análise de um FII)
# =============================================================================
def pagina_fundo():
    atual = st.session_state.get("fii_atual")
    if atual not in TODOS:
        atual = MINHA_LISTA[0] if MINHA_LISTA else TODOS[0]
    st.session_state.fii_atual = atual
    if st.session_state.get("fii_sel") != atual:      # chegou por um clique na tabela
        st.session_state.fii_sel = atual

    def _mudou_fundo():
        st.session_state.fii_atual = st.session_state.fii_sel

    c1, c2, _ = st.columns([2, 4, 4])
    fii = c1.selectbox("Fundo", TODOS, key="fii_sel", on_change=_mudou_fundo)
    periodo = c2.segmented_control("Janela do histórico", list(PERIODOS), default="3 anos") or "3 anos"
    linha = LINHAS.loc[fii]
    info = dados.carregar_detalhes(fii)
    nome = nome_curto(info.get("Nome") or linha.get("nome_cvm"))

    tags = [etiqueta(linha["tipo"], CORES_TIPO.get(linha["tipo"])), etiqueta(linha["segmento"])]
    tags += [etiqueta(f"{k}: {info[k]}") for k in ("Mandato", "Gestão") if k in info]
    if linha["na_lista"]:
        tags.append(etiqueta("Na sua lista", TERRACOTA))
    links = {"Fundamentus": f"https://www.fundamentus.com.br/detalhes.php?papel={fii}",
             "Status Invest": f"https://statusinvest.com.br/fundos-imobiliarios/{fii.lower()}",
             "Funds Explorer": f"https://www.fundsexplorer.com.br/funds/{fii.lower()}",
             "Investidor10": f"https://investidor10.com.br/fiis/{fii.lower()}/"}
    extra = (f"<div class='etiquetas'>{''.join(tags)}</div><div class='ligacoes'>"
             + "".join(f"<a href='{u}' target='_blank' rel='noopener'>{n} <span>↗</span></a>" for n, u in links.items())
             + "</div>")
    var = linha["var_dia"]
    cabecalho(
        olho=f"{linha['tipo']} · {linha['segmento']}",
        titulo=fii, lead=nome, extra_html=extra,
        razao=[("Preço atual", f"{brl(linha['preco'])}<small>{sinal_pct(var) if pd.notna(var) else '—'} no dia</small>"),
               ("Preço teto", brl(linha["teto"])),
               ("Margem de segurança", sinal_pct(linha["margem"]), "grande")])

    cifras([("Dividendo 12m", brl(linha["div_12m"]), linha["fonte_div"].split(" (")[0]),
            ("Yield 12m", pct(linha["dy_atual"]), "no preço atual"),
            ("P/VP", num(linha["pvp_atual"]), f"VP/cota {brl(linha['vp_cota'])}"),
            ("Liquidez diária", compacto(linha["liquidez"]), "média de 2 meses"),
            ("Valor de mercado", compacto(linha["valor_mercado"]), f"{num(linha['cotistas'], 0)} cotistas"
             if pd.notna(linha["cotistas"]) else ""),
            ("Vacância", pct(linha["vacancia"]), f"{num(linha['qtd_imoveis'], 0)} imóveis"
             if pd.notna(linha["qtd_imoveis"]) and linha["qtd_imoveis"] > 0 else "")])

    # --------- 01 Como o teto é calculado ---------
    secao(1, "Como o teto é calculado", "Dividendos dos últimos 12 meses divididos pela taxa que o fundo "
                                        "precisa render para valer mais que o título de referência.")
    st.markdown(f"""<div class="formula"><div class="eq">{brl(linha['div_12m'])} <span class="op">÷</span> (
      {pct(TAXAS['equivalente'])} <span class="op">+</span> {pct(linha['premio'])} <span class="op">+</span>
      {pct(linha['ajuste_ipca'])} ) <span class="op">=</span> <b>{brl(linha['teto'])}</b></div>
      <div class="leg">dividendo 12m ({linha['fonte_div']}) ÷ ( título IPCA+ real líquido
      + prêmio de risco ({linha['origem_premio']}) + ajuste de IPCA ({linha['origem_ajuste']}, tipo {linha['tipo'].lower()}) ).
      <br>No preço de hoje, o mercado paga um prêmio implícito de <b>{pct(linha['premio_impl'])}</b>.</div></div>""",
                unsafe_allow_html=True)

    # --------- 02 Tipo e 03 Prêmio (lado a lado, assimétrico) ---------
    esq, dir_ = st.columns([4, 7], gap="large")
    with esq:
        secao(2, "Tipo do fundo", "Composição dos ativos no Informe Mensal entregue à CVM.", compacta=True)
        if pd.notna(linha["pct_papel"]):
            comp = pd.DataFrame({"Classe": ["Papel", "Tijolo", "Cotas de FIIs"],
                                 "Parcela": [linha["pct_papel"], linha["pct_tijolo"], linha["pct_fof"]]})
            fig = go.Figure(go.Bar(x=comp["Parcela"], y=comp["Classe"], orientation="h",
                                   marker_color=[CORES_TIPO["Papel"], CORES_TIPO["Tijolo"], CORES_TIPO["FoF"]],
                                   text=comp["Parcela"].map(lambda v: pct(v, 0)), textposition="outside",
                                   cliponaxis=False, hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
            fig.update_layout(xaxis=dict(tickformat=".0%", range=[0, 1.12], showticklabels=False),
                              yaxis=dict(autorange="reversed", showgrid=False), margin=dict(t=8), bargap=0.45)
            grafico(fig, 190, hover="closest")
            nota(f"Classificado como <b>{linha['tipo'].lower()}</b> ({linha['origem_tipo']}). Ajuste de IPCA "
                 f"automático: IPCA × {pct(FATOR_IPCA[linha['tipo']], 0)} = {pct(linha['ajuste_auto'])}. "
                 f"Referência {linha['data_cvm']}.")
            cad = [("Administrador", linha["administrador"]), ("Gestão", linha["gestao_cvm"]),
                   ("Patrimônio líquido", compacto(linha["pl"])),
                   ("Taxa de adm. (mês)", pct(linha["taxa_adm_mes"], 3))]
            st.markdown("<div class='razao' style='border-left:0;padding-left:0'>" + "".join(
                f"<div class='linha'><span class='rot'>{r}</span><span class='val' style='font-family:var(--sans);"
                f"font-size:.85rem'>{v if pd.notna(v) else '—'}</span></div>" for r, v in cad) + "</div>",
                unsafe_allow_html=True)
        else:
            nota("Fundo fora do Informe Mensal da CVM (por exemplo, Fiagros ou código diferente do ISIN). "
                 f"Tipo estimado pelo Fundamentus: <b>{linha['tipo'].lower()}</b>. Corrija em Tipo (manual) "
                 "na sua lista, se necessário.", atencao=True)
    with dir_:
        secao(3, "Do que é feito o prêmio", "Prêmio-base mais pontos por fator de risco observado nos dados.", compacta=True)
        componentes = COMPONENTES.loc[fii]
        excesso = linha["dy_atual"] - calculos.mediana_dy_pares(TABELA).loc[TABELA["fii"] == fii].iloc[0]
        medidas = {"Baixa liquidez": compacto(linha["liquidez"]) + "/dia",
                   "Fundo pequeno": compacto(linha["valor_mercado"]),
                   "Poucos imóveis": num(linha["qtd_imoveis"], 0) + " imóveis",
                   "Vacância": pct(linha["vacancia"]),
                   "Volatilidade da cota": pct(linha["vol_1a"]) + " a.a.",
                   "Dividendos instáveis": "CV " + pct(linha["cv_div"], 0),
                   "Dividendos em queda": pct(linha["tend_div"]) + " nos últimos 6",
                   "Yield acima dos pares": f"{_br(f'{excesso * 100:+.1f}')} p.p. vs {linha['tipo'].lower()}"}
        peso = st.session_state.peso_fatores
        nomes = ["Base"] + [f.replace(" da cota", "").replace("Dividendos ", "Div. ") for f in componentes.index] + ["Total"]
        fig = go.Figure(go.Waterfall(
            orientation="v", measure=["absolute"] + ["relative"] * len(componentes) + ["total"], x=nomes,
            y=[st.session_state.premio_base] + list(componentes.values * 100 * peso) + [0],
            text=[pct(st.session_state.premio_base / 100)] + [f"+{pct(v * peso)}" if v > 0 else ""
                                                                for v in componentes.values] + [pct(linha["premio_auto"])],
            textposition="outside", cliponaxis=False,
            connector=dict(line=dict(color=LINHA, width=1)),
            increasing=dict(marker=dict(color=TERRACOTA)), totals=dict(marker=dict(color=TINTA)),
            customdata=[""] + [medidas.get(f, "") for f in componentes.index] + [""],
            hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>"))
        fig.update_layout(yaxis=dict(ticksuffix="%", rangemode="tozero"), showlegend=False, margin=dict(t=20))
        grafico(fig, 300, hover="closest")
        ativos = componentes[componentes > 0].sort_values(ascending=False)
        if len(ativos):
            st.markdown("<div class='razao' style='border-left:0;padding-left:0'>" + "".join(
                f"<div class='linha'><span class='rot'><b>{f}</b> · {medidas.get(f, '')}<br>"
                f"<span style='color:var(--tinta-45);font-size:.74rem'>{calculos.DESCRICAO_REGRAS[f]}</span></span>"
                f"<span class='val'>+{pct(v * peso)}</span></div>" for f, v in ativos.items()) + "</div>",
                unsafe_allow_html=True)
        else:
            nota("Nenhum fator de risco somou pontos: o prêmio é só a base.")
        if pd.notna(linha["premio_planilha"]):
            nota(f"Na sua planilha: <b>{pct(linha['premio_planilha'])}</b> · automático: "
                 f"<b>{pct(linha['premio_auto'])}</b>. O modo em uso fica no painel lateral.")

    # --------- 04 Cotação x teto ---------
    anos = PERIODOS[periodo]
    inicio = date.today() - timedelta(days=365 * anos)
    precos, divs = dados.carregar_historico((fii, dados.BENCHMARK), inicio - timedelta(days=365))
    secao(4, "Cotação e preço teto", "O teto ao longo do tempo usa os dividendos dos 12 meses anteriores a cada "
                                     "data e a taxa exigida de hoje.")
    if fii not in precos.columns:
        nota("Sem histórico de cotações no Yahoo Finance para este fundo.", atencao=True)
        return
    p, d = precos[fii].dropna(), divs[fii]
    # Soma móvel de 12 meses, suavizada: quando uma data-ex escorrega de mês, a
    # janela conta 11 ou 13 pagamentos e cria picos artificiais no teto
    div_movel = d.rolling("365D").sum().rolling("45D").median()
    teto_hist = (div_movel / linha["taxa_exigida"]).where(div_movel.index >= p.index[0] + pd.Timedelta(days=360))
    corte = pd.Timestamp(inicio)
    p, d, teto_hist = p[p.index >= corte], d[d.index >= corte], teto_hist[teto_hist.index >= corte]

    fig = go.Figure()
    fig.add_scatter(x=teto_hist.index, y=teto_hist, name="Preço teto", line=dict(color=TERRACOTA, width=1.6, dash="dash"))
    fig.add_scatter(x=p.index, y=p, name="Cotação", line=dict(color=TINTA, width=2))
    if pd.notna(linha["vp_cota"]):
        fig.add_hline(y=linha["vp_cota"], line=dict(color=TINTA_45, width=1, dash="dot"),
                      annotation_text=f"VP/cota {brl(linha['vp_cota'])}", annotation_font_color=TINTA_70)
    fig.update_layout(yaxis_tickprefix="R$ ", margin=dict(t=16))
    grafico(fig, 420)

    # --------- 05 Rendimentos e 06 Sensibilidade ---------
    esq, dir_ = st.columns([7, 5], gap="large")
    with esq:
        secao(5, "Rendimentos", "Dividendo por cota em cada mês e o yield do mês sobre o preço.", compacta=True)
        div_mes = d.resample("ME").sum()
        dy_mes = (div_mes / p.resample("ME").last()).dropna()
        dy_mes = dy_mes[dy_mes > 0]                      # ignora meses ainda sem pagamento
        fig = go.Figure()
        fig.add_bar(x=div_mes.index, y=div_mes, name="Dividendo por cota", marker_color=SALVIA_CLARA,
                    marker_line_width=0, hovertemplate="R$ %{y:.2f}<extra></extra>")
        fig.add_scatter(x=dy_mes.index, y=dy_mes * 100, name="Yield do mês", yaxis="y2",
                        line=dict(color=TINTA, width=1.6), mode="lines",
                        hovertemplate="%{y:.2f}%<extra></extra>")
        fig.update_layout(yaxis=dict(tickprefix="R$ "), margin=dict(t=16),
                          yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False,
                                      tickfont=dict(color=TINTA_70)))
        grafico(fig, 340)
    with dir_:
        secao(6, "Sensibilidade ao prêmio", "Quanto o teto muda conforme o prêmio exigido.", compacta=True)
        premios = np.linspace(-0.01, 0.08, 91)
        tetos = [calculos.preco_teto(linha["div_12m"], TAXAS["equivalente"], pr, linha["ajuste_ipca"])[0]
                 for pr in premios]
        fig = go.Figure()
        fig.add_scatter(x=premios * 100, y=tetos, name="Preço teto", line=dict(color=TERRACOTA, width=2.2),
                        hovertemplate="prêmio %{x:.2f}%<br>teto R$ %{y:.2f}<extra></extra>")
        fig.add_hline(y=linha["preco"], line=dict(color=TINTA, width=1, dash="dash"),
                      annotation_text=f"preço {brl(linha['preco'])}", annotation_font_color=TINTA_70)
        fig.add_vline(x=linha["premio"] * 100, line=dict(color=TINTA_45, width=1, dash="dot"))
        fig.update_layout(xaxis_ticksuffix="%", yaxis_tickprefix="R$ ", showlegend=False, margin=dict(t=16))
        fig.update_yaxes(range=[0, max(linha["preco"] * 2.2, 1)])
        grafico(fig, 340, hover="closest")

    # --------- 07 Risco e retorno ---------
    secao(7, f"Risco e retorno, últimos {periodo}", "Retorno total com dividendos reinvestidos, comparado ao "
                                                    "IFIX (XFIX11) e ao CDI.")
    pt, dv = precos[precos.index >= corte], divs[divs.index >= corte]
    r_total = calculos.retornos_totais(pt, dv)
    r_preco = pt.pct_change().iloc[1:]
    rf = dados.cdi_diario(inicio)
    mk = r_total[dados.BENCHMARK] if dados.BENCHMARK in r_total else pd.Series(dtype=float)
    met = calculos.metricas_risco_retorno(r_total[fii], r_preco[fii], mk, rf)
    met_ifix = calculos.metricas_risco_retorno(mk, r_preco.get(dados.BENCHMARK, mk), mk, rf) if len(mk) else {}
    if met:
        itens = [("Retorno total", "Retorno anual (total)", pct, " a.a."), ("Só a cota", "Retorno anual (só cota)", pct, " a.a."),
                 ("Volatilidade", "Volatilidade anual", pct, " a.a."), ("Sharpe", "Índice de Sharpe", num, ""),
                 ("Beta", "Beta (vs IFIX)", num, ""), ("Pior queda", "Máximo drawdown", pct, ""),
                 ("VaR 95%", "VaR 95% diário", pct, " ao dia")]
        cifras([(rot, fmt(met[ch]), f"IFIX {fmt(met_ifix[ch])}{suf}" if met_ifix and ch in met_ifix else suf.strip())
                for rot, ch, fmt, suf in itens])
        esq, dir_ = st.columns([7, 5], gap="large")
        acum = pd.DataFrame({fii: (1 + r_total[fii].fillna(0)).cumprod() * 100})
        if len(mk):
            acum["IFIX"] = (1 + mk.fillna(0)).cumprod() * 100
        if rf is not None:
            acum["CDI"] = (1 + rf.reindex(acum.index).ffill().fillna(0)).cumprod() * 100
        fig = go.Figure()
        estilos = {fii: dict(color=TERRACOTA, width=2.2), "IFIX": dict(color=TINTA, width=1.4, dash="dot"),
                   "CDI": dict(color=TINTA_45, width=1.4, dash="dash")}
        for col in acum.columns:
            fig.add_scatter(x=acum.index, y=acum[col], name=col, line=estilos[col],
                            hovertemplate="R$ %{y:.1f}<extra>" + col + "</extra>")
        fig.update_layout(title="R$ 100 investidos", yaxis_tickprefix="R$ ")
        grafico(fig, 360, onde=esq)
        dd = calculos.drawdown(r_total[fii]) * 100
        fig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy", fillcolor="rgba(180,83,42,0.14)",
                                   line=dict(color=TERRACOTA, width=1.2), name="Queda desde o pico",
                                   hovertemplate="%{y:.1f}%<extra></extra>"))
        fig.update_layout(title="Queda desde o pico", yaxis_ticksuffix="%", showlegend=False)
        grafico(fig, 360, onde=dir_)
        st.caption(f"CDI no período: {pct(met['CDI no período (a.a.)'])} a.a. · Sharpe = (retorno − CDI) ÷ "
                   "volatilidade · Beta abaixo de 1: o fundo oscila menos que o IFIX.")

    if info:
        with st.expander("Todos os indicadores do Fundamentus"):
            st.dataframe(pd.DataFrame({"Indicador": list(info.keys()), "Valor": [str(v) for v in info.values()]}),
                         hide_index=True, width="stretch")


# =============================================================================
# PÁGINA: COMPARAR
# =============================================================================
def pagina_comparar():
    cabecalho(olho="Comparar", titulo="Lado a <em>lado</em>",
              lead="Valuation de hoje e o histórico de risco e retorno de até dez fundos, contra o IFIX e o CDI.",
              razao=[("Mercado", "IFIX · XFIX11"), ("Livre de risco", "CDI"),
                     ("Retorno", "total<small>com dividendos reinvestidos</small>")])
    c1, c2 = st.columns([8, 3])
    escolhidos = c1.multiselect("Fundos", TODOS, default=MINHA_LISTA[:5], max_selections=10,
                                placeholder="Escolha até 10 fundos")
    periodo = c2.segmented_control("Janela", list(PERIODOS)[:4], default="3 anos") or "3 anos"
    if len(escolhidos) < 2:
        nota("Escolha pelo menos dois fundos para comparar.")
        return

    inicio = date.today() - timedelta(days=365 * PERIODOS[periodo])
    precos, divs = dados.carregar_historico(tuple(escolhidos) + (dados.BENCHMARK,), inicio)
    validos = [f for f in escolhidos if f in precos.columns]
    r_total = calculos.retornos_totais(precos, divs)
    r_preco = precos.pct_change().iloc[1:]
    rf = dados.cdi_diario(inicio)
    mk = r_total.get(dados.BENCHMARK, pd.Series(dtype=float))

    linhas = []
    for f in validos:
        met = calculos.metricas_risco_retorno(r_total[f], r_preco[f], mk, rf)
        lt = LINHAS.loc[f]
        linhas.append({"FII": f, "Tipo": lt["tipo"], "Preço": lt["preco"], "Teto": lt["teto"],
                       "Margem": lt["margem"], "Prêmio": lt["premio"], "Yield 12m": lt["dy_atual"],
                       "P/VP": lt["pvp_atual"], **met})
    comp = pd.DataFrame(linhas).drop(columns=["CDI no período (a.a.)", "Retorno acumulado"], errors="ignore")
    comp = comp.rename(columns={"Retorno anual (total)": "Retorno a.a.", "Retorno anual (só cota)": "Só cota a.a.",
                                "Volatilidade anual": "Volatilidade", "Índice de Sharpe": "Sharpe",
                                "Beta (vs IFIX)": "Beta", "Máximo drawdown": "Pior queda", "VaR 95% diário": "VaR 95%"})

    secao(1, "Quadro comparativo", "Valuation com as premissas atuais; risco e retorno na janela escolhida.")
    formatos = {c: pct for c in comp.columns if c not in ("FII", "Tipo", "Preço", "Teto", "P/VP", "Sharpe", "Beta")}
    formatos.update({"Preço": brl, "Teto": brl, "P/VP": num, "Sharpe": num, "Beta": num})
    st.dataframe(comp.style.format(formatos).map(cor_margem, subset=["Margem"]).map(cor_tipo, subset=["Tipo"])
                 .set_properties(subset=["FII"], **{"font-weight": "600"}), hide_index=True, width="stretch")

    secao(2, "Trajetória", "R$ 100 investidos no início da janela e a relação entre risco e retorno.")
    esq, dir_ = st.columns([3, 2], gap="large")
    acum = (1 + r_total[validos].fillna(0)).cumprod() * 100
    fig = go.Figure()
    for i, f in enumerate(validos):
        fig.add_scatter(x=acum.index, y=acum[f], name=f, line=dict(color=CORES_SERIES[i % 10], width=1.8),
                        hovertemplate="R$ %{y:.1f}<extra>" + f + "</extra>")
    if len(mk):
        fig.add_scatter(x=acum.index, y=(1 + mk.fillna(0)).cumprod() * 100, name="IFIX",
                        line=dict(color=TINTA, width=1.4, dash="dot"))
    if rf is not None:
        fig.add_scatter(x=acum.index, y=(1 + rf.reindex(acum.index).ffill().fillna(0)).cumprod() * 100,
                        name="CDI", line=dict(color=TINTA_45, width=1.4, dash="dash"))
    fig.update_layout(yaxis_tickprefix="R$ ", margin=dict(t=16))
    grafico(fig, 430, onde=esq)
    fig = px.scatter(comp, x="Volatilidade", y="Retorno a.a.", text="FII", size=comp["Yield 12m"].fillna(0).clip(lower=0), color="Tipo",
                     color_discrete_map=CORES_TIPO, size_max=28)
    fig.update_traces(textposition="top center", marker=dict(line=dict(width=0), opacity=0.9),
                      textfont=dict(size=11, color=TINTA_70))
    fig.update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%", margin=dict(t=16),
                      xaxis_title="Volatilidade anual", yaxis_title="Retorno anual")
    grafico(fig, 430, onde=dir_, hover="closest")

    secao(3, "Diversificação e margem", "Correlação baixa entre fundos reduz o risco da carteira.")
    esq, dir_ = st.columns([1, 1], gap="large")
    corr = r_total[validos].corr()
    fig = px.imshow(corr, text_auto=".2f", color_continuous_scale=estilo.ESCALA_DIVERGENTE, zmin=-1, zmax=1)
    fig.update_traces(textfont=dict(color=TINTA, size=11), xgap=2, ygap=2)
    fig.update_layout(margin=dict(t=16), coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
    grafico(fig, 420, onde=esq, hover="closest")
    ordem = comp.sort_values("Margem")
    fig = go.Figure(go.Bar(x=ordem["Margem"], y=ordem["FII"], orientation="h",
                           marker_color=[TINTA if m > 0 else TERRACOTA for m in ordem["Margem"]],
                           text=ordem["Margem"].map(pct), textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
    fig.update_layout(xaxis_tickformat=".0%", margin=dict(t=16), bargap=0.4)
    folga_barras(fig, ordem["Margem"])
    grafico(fig, 420, onde=dir_, hover="closest")


# =============================================================================
# PÁGINA: PANORAMA
# =============================================================================
def pagina_panorama():
    liq = st.session_state.get("liq_panorama", 5e5)
    t = TABELA[(TABELA["liquidez"].fillna(0) >= liq) & (TABELA["div_12m"] > 0)
               & TABELA["pvp_atual"].between(0.2, 2.5) & TABELA["dy_atual"].between(0, 0.3)]
    cabecalho(olho="Panorama", titulo="O mercado de<br><em>FIIs</em> hoje",
              lead="Como os fundos negociados se distribuem entre yield, desconto sobre o patrimônio e tipo "
                   "de ativo, com as premissas atuais de preço teto.",
              razao=[("Fundos considerados", f"{len(t)}"), ("Yield 12m mediano", pct(t["dy_atual"].median())),
                     ("P/VP mediano", num(t["pvp_atual"].median())),
                     ("Abaixo do teto", f"{pct((t['margem'] > 0).mean(), 0)}<small>dos fundos</small>")])
    c1, c2, _ = st.columns([4, 2, 4])
    c1.select_slider("Liquidez diária mínima", [0, 1e5, 5e5, 1e6, 5e6], key="liq_panorama", value=liq,
                     format_func=compacto)
    cor_por = c2.segmented_control("Cor", ["Tipo", "Segmento"], default="Tipo") or "Tipo"

    secao(1, "Yield × P/VP", "Cada ponto é um fundo; o tamanho é o valor de mercado. A linha tracejada é a "
                             "taxa real líquida do título de referência.")
    fig = px.scatter(t, x="pvp_atual", y="dy_atual", color="tipo" if cor_por == "Tipo" else "segmento",
                     color_discrete_map=CORES_TIPO if cor_por == "Tipo" else None, size="valor_mercado", size_max=34,
                     hover_name="fii", hover_data={"preco": ":.2f", "margem": ":.1%", "premio": ":.2%",
                                                   "valor_mercado": False, "pvp_atual": ":.2f", "dy_atual": ":.1%"},
                     labels={"pvp_atual": "P/VP", "dy_atual": "Yield 12m", "segmento": "Segmento", "tipo": "Tipo",
                             "premio": "Prêmio", "margem": "Margem", "preco": "Preço"})
    fig.update_traces(marker=dict(line=dict(width=0.6, color=PAPEL_CLARO), opacity=0.82))
    fig.add_vline(x=1, line=dict(color=TINTA_45, width=1, dash="dot"), annotation_text="P/VP = 1",
                  annotation_font_color=TINTA_70)
    fig.add_hline(y=TAXAS["equivalente"], line=dict(color=TERRACOTA, width=1, dash="dash"),
                  annotation_text="título IPCA+ real líquido", annotation_font_color=TERRACOTA)
    fig.update_layout(yaxis_tickformat=".0%", margin=dict(t=16))
    grafico(fig, 540, hover="closest")

    secao(2, "Por tipo de fundo", "Medianas de cada grupo.")
    esq, dir_ = st.columns([7, 5], gap="large")
    por_tipo = (t.groupby("tipo").agg(FIIs=("fii", "count"), DY=("dy_atual", "median"), PVP=("pvp_atual", "median"),
                                      Premio=("premio", "median"), Margem=("margem", "median"),
                                      Vol=("vol_1a", "median")).reset_index())
    por_tipo.columns = ["Tipo", "Fundos", "Yield", "P/VP", "Prêmio", "Margem", "Volatilidade"]
    esq.dataframe(por_tipo.style.format({"Yield": pct, "P/VP": num, "Prêmio": pct, "Margem": pct, "Volatilidade": pct})
                  .map(cor_tipo, subset=["Tipo"]).map(cor_margem, subset=["Margem"]), hide_index=True, width="stretch")
    fig = go.Figure(go.Histogram(x=t["dy_atual"], nbinsx=36, marker_color=SALVIA, marker_line_width=0,
                                 hovertemplate="%{x}<br>%{y} fundos<extra></extra>"))
    fig.add_vline(x=t["dy_atual"].median(), line=dict(color=TERRACOTA, width=1.4),
                  annotation_text=f"mediana {pct(t['dy_atual'].median(), 1)}", annotation_font_color=TERRACOTA)
    fig.update_layout(xaxis_tickformat=".0%", bargap=0.08, margin=dict(t=16), showlegend=False)
    grafico(fig, 300, onde=dir_, hover="closest")

    secao(3, "Por segmento", "Classificação do Fundamentus; ordenado pelo valor de mercado somado.")
    resumo = (t.groupby("segmento").agg(FIIs=("fii", "count"), DY=("dy_atual", "median"), PVP=("pvp_atual", "median"),
                                         Margem=("margem", "median"), VM=("valor_mercado", "sum"))
              .sort_values("VM", ascending=False).reset_index())
    resumo.columns = ["Segmento", "Fundos", "Yield", "P/VP", "Margem", "Valor de mercado"]
    st.dataframe(resumo.style.format({"Yield": pct, "P/VP": num, "Margem": pct, "Valor de mercado": compacto})
                 .map(cor_margem, subset=["Margem"]), hide_index=True, width="stretch")

    secao(4, "Extremos", "Os 12 fundos com maior margem de segurança e os 12 mais acima do teto.")
    esq, dir_ = st.columns(2, gap="large")
    for onde, asc, cor in [(esq, False, TINTA), (dir_, True, TERRACOTA)]:
        top = t.sort_values("margem", ascending=asc).head(12).iloc[::-1]
        fig = go.Figure(go.Bar(x=top["margem"], y=top["fii"], orientation="h", marker_color=cor,
                               text=top["margem"].map(pct), textposition="outside", cliponaxis=False,
                               customdata=top["segmento"], hovertemplate="%{y} · %{customdata}<br>%{x:.1%}<extra></extra>"))
        fig.update_layout(xaxis_tickformat=".0%", margin=dict(t=16), bargap=0.38)
        folga_barras(fig, top["margem"])
        grafico(fig, 430, onde=onde, hover="closest")
    st.caption(f"Prêmio: {MODO_PREMIO.lower()} · ajuste de IPCA: {MODO_IPCA.lower()} (painel lateral).")


# =============================================================================
# PÁGINA: MÉTODO
# =============================================================================
def pagina_metodo():
    eq = TAXAS["equivalente"]
    cabecalho(olho="Método", titulo="Como os números<br>são <em>calculados</em>",
              lead="As fórmulas, regras e fontes por trás de cada coluna do site, com os valores das premissas atuais.",
              razao=[("Taxa bruta do título", pct(TAXAS["bruta"])), ("Líquida de IR", pct(TAXAS["liquida"])),
                     ("Real líquida (base)", pct(eq), "grande")])
    sumario, corpo = st.columns([1, 3.4], gap="large")
    sumario.markdown("<div class='sumario'><a href='#preco-teto'>Preço teto</a><a href='#tipo'>Tipo e ajuste de IPCA</a>"
                     "<a href='#premio'>Prêmio de risco</a><a href='#fontes'>Fontes de dados</a>"
                     "<a href='#risco'>Risco e retorno</a></div>", unsafe_allow_html=True)
    # "\$" evita que o Markdown do Streamlit leia "R$ ... R$" como fórmula LaTeX
    linhas_regras = "\n".join(f"| {f} | {d.replace('$', chr(92) + '$')} |"
                              for f, d in calculos.DESCRICAO_REGRAS.items())
    linhas_tipo = "\n".join(
        f"| {t} | {r} | IPCA × {pct(FATOR_IPCA[t], 0)} = {pct(IPCA * FATOR_IPCA[t])} |"
        for t, r in [("Papel", "papel ≥ 67%"), ("Tijolo", "tijolo ≥ 67%"), ("FoF", "cotas de FIIs ≥ 50%"),
                     ("Híbrido", "demais casos"), ("Indefinido", "fora da CVM e sem pista no Fundamentus")])
    with corpo:
        st.markdown(f"""
<div id="preco-teto"></div>

### Preço teto
O fundo é comparado a um **título atrelado à inflação** (IPCA + taxa fixa). Ele só vale a pena se render mais
que o título **mais um prêmio pelo risco**.

| Passo | Fórmula | Hoje |
|---|---|---|
| Taxa bruta do título | (1 + IPCA) × (1 + IPCA+) − 1 | {pct(TAXAS['bruta'])} |
| Taxa líquida | Bruta × (1 − IR) | {pct(TAXAS['liquida'])} |
| Real líquida | (1 + Líquida) ÷ (1 + IPCA) − 1 | {pct(eq)} |
| Taxa exigida do fundo | Real líquida + Prêmio + Ajuste IPCA | tijolo com prêmio de 2%: {pct(eq + 0.02)} |
| Preço teto | Dividendo 12m ÷ Taxa exigida | |
| Margem de segurança | Preço teto ÷ Preço − 1 | |
| Prêmio implícito | Yield atual − Real líquida − Ajuste IPCA | |

O título paga IR e o rendimento do FII é isento para pessoa física; por isso a comparação usa a taxa líquida.

<div id="tipo"></div>

### Tipo do fundo e ajuste de IPCA
Fundos de papel (CRI) distribuem a correção monetária como rendimento: parte do dividendo é só reposição da
inflação. O ajuste soma uma fração do IPCA à taxa exigida conforme o tipo, apurado no **Informe Mensal** que
todo FII entrega à CVM. Papel reúne CRI, CRA, LCI, letras hipotecárias, LIG e debêntures; tijolo reúne imóveis
e participações em SPEs imobiliárias.

| Tipo | Regra | Ajuste hoje |
|---|---|---|
{linhas_tipo}

Fundos fora da base da CVM (como Fiagros) são estimados pelo Fundamentus. Qualquer caso pode ser corrigido em
Tipo (manual), na sua lista.

<div id="premio"></div>

### Prêmio de risco automático
Prêmio = base ({pct(st.session_state.premio_base / 100)}) + peso ({num(st.session_state.peso_fatores)}) × soma dos
pontos abaixo, limitado entre {pct(calculos.PREMIO_MIN)} e {pct(calculos.PREMIO_MAX)}. Dados ausentes não somam pontos.

| Fator | Regra, em pontos de % a.a. |
|---|---|
{linhas_regras}

O score foi calibrado para ficar próximo de uma planilha manual (correlação de cerca de 0,7 em 21 fundos). É um
ponto de partida objetivo: qualidade da gestão, contratos atípicos, inquilinos e garantias dos CRIs não estão nos
dados públicos. Para isso existe o modo Minha planilha.

<div id="fontes"></div>

### Fontes de dados
| Dado | Fonte | Atualização |
|---|---|---|
| Lista de FIIs, segmento, P/VP, liquidez, vacância | Fundamentus | a cada hora |
| Composição dos ativos, cotistas, PL, taxa de administração | CVM, Informe Mensal de FII | diária |
| Cotação, histórico e dividendos | Yahoo Finance, cerca de 15 min de atraso | 5 minutos ou Atualizar |
| Expectativa de IPCA 12m | Banco Central, Boletim Focus | diária |
| IPCA 12m, Selic, CDI | Banco Central, SGS | diária |
| Taxas do Tesouro IPCA+ | Tesouro Transparente | diária |

O dividendo 12m é a soma dos pagamentos com data-ex nos últimos 12 meses (Yahoo); na falta dela, yield do
Fundamentus × cotação. O valor manual da sua lista tem prioridade.

<div id="risco"></div>

### Risco e retorno
Retorno total diário = (Pₜ + Dₜ) ÷ Pₜ₋₁ − 1 · Volatilidade = desvio-padrão × √252 · Sharpe = (retorno − CDI) ÷
volatilidade · Beta = Cov(fundo, IFIX) ÷ Var(IFIX) · Pior queda = maior perda desde um pico · VaR 95% = perda
diária superada em apenas 5% dos dias.

Ferramenta educacional; não é recomendação de investimento.
""", unsafe_allow_html=True)


# =============================================================================
# PÁGINA: RELATÓRIO (gera o relatório da análise e salva em relatorios/)
# =============================================================================
def pagina_relatorio():
    cabecalho(olho="Relatório", titulo="O relatório<br>da <em>análise</em>",
              lead="Um documento para ler sem abrir o site: conclusões em frases simples, o raciocínio financeiro "
                   "em três passos, a tabela dos fundos e três destaques comentados.",
              razao=[("Formato", "HTML<small>abre em qualquer navegador; imprime em PDF</small>"),
                     ("Salvo em", "relatorios/<small>na pasta do site, com uma planilha CSV</small>"),
                     ("Premissas", f"{pct(TAXAS['equivalente'])}<small>ganho real exigido, base</small>")])

    # Fundos com preço e preço teto calculáveis (sem dividendos o teto seria zero)
    calculaveis = TABELA[(TABELA["teto"] > 0) & (TABELA["preco"] > 0)]
    liq_opcoes = {"Qualquer": 0, "R$ 100 mil": 1e5, "R$ 500 mil": 5e5, "R$ 1 mi": 1e6}

    with st.container(border=True):
        c1, c2 = st.columns([4, 5], vertical_alignment="bottom")
        universo = c1.segmented_control("Fundos do relatório", ["Minha lista", "Todos os fundos", "Escolher fundos"],
                                        default="Minha lista") or "Minha lista"
        if universo == "Minha lista":
            escolhidos = MINHA_LISTA
            c2.caption(f"{len(escolhidos)} fundos da sua lista.")
        elif universo == "Todos os fundos":
            liq_min = liq_opcoes[c2.selectbox("Liquidez mínima por dia", list(liq_opcoes), index=0,
                                              help="Fundos quase sem negociação costumam ter preços e dividendos "
                                                   "pouco confiáveis.")]
            escolhidos = calculaveis.loc[calculaveis["liquidez"].fillna(0) >= liq_min, "fii"].tolist()
        else:
            escolhidos = st.multiselect("Fundos", TODOS, default=MINHA_LISTA, placeholder="Escolha os fundos")
        validos, excluidos = relatorio.filtrar(TABELA[TABELA["fii"].isin(escolhidos)])
        st.caption(f"{len(validos)} fundos entrarão no relatório"
                   + (f"; {len(excluidos)} ficam de fora por yield fora da faixa de 1% a 40% (dados suspeitos)."
                      if len(excluidos) else "."))
        gerar = st.button("Gerar relatório", type="primary")

    if gerar:
        if len(escolhidos) < 2:
            nota("Escolha pelo menos dois fundos.", atencao=True)
            return
        t = TABELA[TABELA["fii"].isin(escolhidos)]
        s = st.session_state
        premissas = {"ipca_mais": s.ipca_mais / 100, "ir": s.ir / 100, "modo_premio": MODO_PREMIO,
                     "modo_ipca": MODO_IPCA, "premio_base": s.premio_base / 100, "peso": s.peso_fatores,
                     "fator_ipca": FATOR_IPCA}
        universo = {"Minha lista": "minha lista", "Todos os fundos": "todos os fundos"}.get(universo, "seleção")
        try:
            pagina = relatorio.gerar_html(t, TAXAS, IPCA, premissas, HORA_COTACAO, AUTORES, universo)
        except ValueError as erro:
            nota(str(erro), atencao=True)
            return
        planilha = relatorio.gerar_csv(t)

        # Salva os arquivos (é o "relatório decorrente da execução" pedido no trabalho)
        pasta = os.path.join(PASTA, "relatorios")
        os.makedirs(pasta, exist_ok=True)
        base = os.path.join(pasta, f"relatorio_{datetime.now():%Y-%m-%d_%H-%M-%S}")
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(pagina)
        with open(base + ".csv", "wb") as f:
            f.write(planilha)
        s.ultimo_relatorio = {"html": pagina, "csv": planilha, "caminho": base + ".html"}

    ultimo = st.session_state.get("ultimo_relatorio")
    if ultimo:
        secao(1, "Relatório gerado", f"Salvo em {ultimo['caminho']}")
        c1, c2, _ = st.columns([2, 2, 5])
        c1.download_button("Baixar HTML", ultimo["html"].encode("utf-8"), file_name=os.path.basename(ultimo["caminho"]),
                           mime="text/html", width="stretch")
        c2.download_button("Baixar planilha", ultimo["csv"], mime="text/csv", width="stretch",
                           file_name=os.path.basename(ultimo["caminho"]).replace(".html", ".csv"))
        componentes_html.html(ultimo["html"], height=1600, scrolling=True)
    else:
        nota("Escolha os fundos e clique em Gerar relatório. O arquivo é salvo automaticamente e aparece aqui "
             "logo abaixo.")


# =============================================================================
# Navegação (no topo)
# =============================================================================
PG_MERCADO = st.Page(pagina_mercado, title="Mercado", url_path="mercado", default=True)
PG_FUNDO = st.Page(pagina_fundo, title="Fundo", url_path="fundo")
PG_COMPARAR = st.Page(pagina_comparar, title="Comparar", url_path="comparar")
PG_PANORAMA = st.Page(pagina_panorama, title="Panorama", url_path="panorama")
PG_METODO = st.Page(pagina_metodo, title="Método", url_path="metodo")
PG_RELATORIO = st.Page(pagina_relatorio, title="Relatório", url_path="relatorio")
st.navigation([PG_MERCADO, PG_FUNDO, PG_COMPARAR, PG_PANORAMA, PG_RELATORIO, PG_METODO], position="top").run()
