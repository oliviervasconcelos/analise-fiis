# -*- coding: utf-8 -*-
"""
estilo.py - SISTEMA DE DESIGN do site "Teto"
============================================

Paleta (2 cores principais + 1 de destaque):
    TINTA      #1C3530  verde-tinta profundo: texto, painel lateral, sinal favorável
    PAPEL      #F2EDE3  marfim quente: fundo
    TERRACOTA  #B4532A  cor do tijolo: ações, foco e sinal de atenção
Todos os demais tons são variações (mais claras/escuras) dessas três.

Tipografia:
    Fraunces (serifa, eixo óptico)  -> títulos e números de destaque
    IBM Plex Sans (sem serifa)      -> corpo, rótulos e tabelas (algarismos tabulares)

Este módulo concentra:
    - o CSS complementar ao tema nativo (.streamlit/config.toml);
    - o template dos gráficos Plotly;
    - componentes HTML reutilizáveis (cabeçalho, cifras, seções, fórmula, notas).
"""
import html

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# -----------------------------------------------------------------------------
# Paleta
# -----------------------------------------------------------------------------
TINTA = "#1C3530"
PAPEL = "#F2EDE3"
TERRACOTA = "#B4532A"

# Variações das três cores principais
TINTA_70 = "#4D625C"        # texto secundário
TINTA_45 = "#8A9792"        # texto terciário, eixos
SALVIA = "#7E968C"          # verde-tinta clareado
SALVIA_CLARA = "#B8C5BE"
TERRA_CLARA = "#D9A486"     # terracota clareada
TERRA_ESCURA = "#7E3517"
PAPEL_2 = "#E9E2D4"         # papel um tom abaixo (campos, cabeçalho de tabela)
PAPEL_CLARO = "#F8F5EE"     # papel um tom acima (superfícies)
LINHA = "#D8CFBD"           # filete
GRADE = "#E3DBCB"           # grade dos gráficos

CATEGORICAS = [TINTA, TERRACOTA, SALVIA, TERRA_CLARA, "#4D6B62", TERRA_ESCURA, SALVIA_CLARA, "#9C8A72"]

# Cada tipo de fundo tem uma cor fixa em todo o site
CORES_TIPO = {"Papel": TINTA, "Tijolo": TERRACOTA, "Híbrido": SALVIA, "FoF": TERRA_CLARA,
              "Indefinido": TINTA_45}

FONTE_TITULO = "Fraunces, Georgia, serif"
FONTE_CORPO = "'IBM Plex Sans', system-ui, sans-serif"


# -----------------------------------------------------------------------------
# CSS complementar
# -----------------------------------------------------------------------------
CSS = f"""
<style>
:root {{
  --tinta:{TINTA}; --tinta-70:{TINTA_70}; --tinta-45:{TINTA_45};
  --papel:{PAPEL}; --papel-2:{PAPEL_2}; --papel-claro:{PAPEL_CLARO};
  --terra:{TERRACOTA}; --terra-clara:{TERRA_CLARA}; --terra-escura:{TERRA_ESCURA};
  --linha:{LINHA}; --serif:{FONTE_TITULO}; --sans:{FONTE_CORPO};
  --curva: cubic-bezier(.2,.7,.2,1);
}}
html, body, .stApp {{ font-variant-numeric: tabular-nums; }}
::selection {{ background: var(--terra-clara); color: var(--tinta); }}
*:focus-visible {{ outline: 2px solid var(--terra) !important; outline-offset: 2px; }}

/* ---------- Estrutura ---------- */
[data-testid="stMainBlockContainer"] {{ padding: 3rem 3.5rem 6rem; max-width: 1380px; }}
header[data-testid="stHeader"] {{ background: var(--papel); border-bottom: 1px solid var(--linha); }}
[data-testid="stTopNav"] a, [data-testid="stTopNavLink"] {{
  font-weight: 500; letter-spacing: .01em; transition: color .18s var(--curva);
}}

/* ---------- Painel lateral (premissas) ---------- */
[data-testid="stSidebarContent"] {{ padding-top: .5rem; }}
.marca {{ font-family: var(--serif); font-size: 2.1rem; font-weight: 500; letter-spacing: -.02em;
         color: #F2EDE3; line-height: 1; margin: .25rem 0 .35rem; }}
.marca span {{ color: #D9774B; }}
.marca-sub {{ font-size: .8rem; color: #A9BCB4; line-height: 1.45; margin-bottom: 1.75rem; max-width: 22ch; }}
.olho-lateral {{ font-size: .68rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
                color: #A9BCB4; border-top: 1px solid #3A5A52; padding-top: 1.1rem; margin: 1.6rem 0 .6rem; }}
.razao-lateral {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .25rem; margin: .4rem 0 .2rem; }}
.razao-lateral div {{ font-size: .68rem; color: #A9BCB4; text-transform: uppercase; letter-spacing: .08em; }}
.razao-lateral b {{ display: block; font-family: var(--serif); font-weight: 500; font-size: 1.15rem;
                   color: #F2EDE3; letter-spacing: 0; text-transform: none; margin-top: .15rem; }}
.razao-lateral .ativo b {{ color: #E9A37F; }}
.rodape-lateral {{ font-size: .72rem; color: #8FA69D; line-height: 1.6; margin-top: 2rem; }}

/* ---------- Tipografia de página ---------- */
.olho {{ font-size: .7rem; font-weight: 600; letter-spacing: .18em; text-transform: uppercase;
        color: var(--terra); margin-bottom: .9rem; }}
.display {{ font-family: var(--serif); font-weight: 500; font-size: clamp(2.4rem, 4.2vw, 3.6rem);
           line-height: 1.02; letter-spacing: -.025em; color: var(--tinta); margin: 0 0 1rem; }}
.display em {{ font-style: italic; color: var(--terra); }}
.lead {{ font-size: 1.04rem; line-height: 1.65; color: var(--tinta-70); max-width: 52ch; margin: 0; }}

/* ---------- Cabeçalho assimétrico ---------- */
.cabecalho {{ display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 4fr); gap: 3.5rem;
             align-items: end; padding: 1.5rem 0 2.25rem; animation: surgir .55s var(--curva) both; }}
.razao {{ border-left: 1px solid var(--linha); padding-left: 1.75rem; }}
.razao .linha {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
                padding: .55rem 0; border-bottom: 1px solid var(--linha); }}
.razao .linha:last-child {{ border-bottom: 0; }}
.razao .rot {{ font-size: .78rem; color: var(--tinta-70); }}
.razao .val {{ font-family: var(--serif); font-size: 1.25rem; font-weight: 500; text-align: right; }}
.razao .val small {{ display: block; font-family: var(--sans); font-size: .72rem; color: var(--tinta-45); font-weight: 400; }}
.razao .val.grande {{ font-size: 2.2rem; line-height: 1; }}

/* ---------- Cifras (números em linha, sem cartões) ---------- */
.cifras {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          border-top: 1.5px solid var(--tinta); border-bottom: 1px solid var(--linha); margin: .5rem 0 1.25rem; }}
.cifra {{ position: relative; padding: 1rem 1.25rem 1.15rem 0; animation: surgir .5s var(--curva) both; }}
.cifra + .cifra {{ padding-left: 1.25rem; border-left: 1px solid var(--linha); }}
.cifra .rot {{ font-size: .72rem; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--tinta-70); }}
.cifra .val {{ font-family: var(--serif); font-size: 1.85rem; font-weight: 500; letter-spacing: -.01em;
              margin-top: .35rem; line-height: 1.1; transition: color .25s var(--curva); }}
.cifra .obs {{ font-size: .76rem; color: var(--tinta-45); margin-top: .25rem; }}
.cifra::after {{ content: ""; position: absolute; left: 0; bottom: -1px; height: 2px; width: 0;
                background: var(--terra); transition: width .35s var(--curva); }}
.cifra + .cifra::after {{ left: 1.25rem; }}
.cifra:hover::after {{ width: 2.5rem; }}
.cifra:nth-child(2) {{ animation-delay: .04s }} .cifra:nth-child(3) {{ animation-delay: .08s }}
.cifra:nth-child(4) {{ animation-delay: .12s }} .cifra:nth-child(5) {{ animation-delay: .16s }}
.cifra:nth-child(6) {{ animation-delay: .2s }}  .cifra:nth-child(7) {{ animation-delay: .24s }}
.positivo {{ color: var(--tinta); }}
.negativo {{ color: var(--terra); }}

/* ---------- Seções numeradas ---------- */
.secao {{ display: grid; grid-template-columns: 3.25rem minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; align-items: baseline;
         border-top: 1px solid var(--linha); padding-top: 1.1rem; margin: 3.25rem 0 1.25rem;
         animation: surgir .5s var(--curva) both; }}
.secao.compacta {{ grid-template-columns: 2.5rem minmax(0, 1fr); row-gap: .35rem; }}
.secao.compacta p {{ grid-column: 2; }}
.secao .n {{ font-family: var(--serif); font-style: italic; color: var(--terra); font-size: 1.05rem; }}
.secao h3 {{ font-family: var(--serif); font-weight: 500; font-size: 1.5rem; margin: 0; padding: 0; letter-spacing: -.01em; }}
.secao p {{ font-size: .86rem; color: var(--tinta-70); margin: 0; line-height: 1.55; }}

/* ---------- Fórmula, notas e etiquetas ---------- */
.formula {{ border-left: 2px solid var(--terra); padding: .2rem 0 .2rem 1.4rem; margin: .5rem 0 1rem; }}
.formula .eq {{ font-family: var(--serif); font-size: 1.4rem; line-height: 1.4; }}
.formula .eq b {{ font-weight: 600; }}
.formula .eq .op {{ color: var(--tinta-45); padding: 0 .2rem; }}
.formula .leg {{ font-size: .8rem; color: var(--tinta-70); margin-top: .4rem; line-height: 1.6; }}
.nota {{ border-left: 2px solid var(--linha); padding: .15rem 0 .15rem 1rem; font-size: .86rem;
        color: var(--tinta-70); line-height: 1.6; margin: .75rem 0; }}
.nota.atencao {{ border-left-color: var(--terra); }}
.etiquetas {{ display: flex; flex-wrap: wrap; gap: .45rem; margin-top: 1.1rem; }}
.etiqueta {{ display: inline-flex; align-items: center; gap: .45rem; padding: .22rem .7rem;
            border: 1px solid var(--linha); border-radius: 999px; font-size: .76rem; color: var(--tinta-70);
            background: var(--papel-claro); transition: border-color .2s var(--curva); }}
.etiqueta:hover {{ border-color: var(--tinta-45); }}
.etiqueta i {{ width: .5rem; height: .5rem; border-radius: 50%; display: inline-block; }}

/* ---------- Links externos ---------- */
.ligacoes {{ display: flex; flex-wrap: wrap; gap: 1.5rem; margin-top: 1.25rem; font-size: .85rem; }}
.ligacoes a, .ligacoes a:visited {{ color: var(--tinta) !important; text-decoration: none;
  border-bottom: 1px solid var(--linha); padding-bottom: 2px; transition: color .2s var(--curva), border-color .2s var(--curva); }}
.ligacoes a:hover {{ color: var(--terra) !important; border-color: var(--terra); }}
.ligacoes a span {{ display: inline-block; transition: transform .2s var(--curva); }}
.ligacoes a:hover span {{ transform: translate(2px, -2px); }}

/* ---------- Componentes nativos ---------- */
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button, [data-testid="stLinkButton"] a {{
  font-weight: 500; letter-spacing: .01em; box-shadow: none;
  transition: background-color .18s var(--curva), border-color .18s var(--curva), transform .12s var(--curva);
}}
[data-testid="stButton"] button:active, [data-testid="stDownloadButton"] button:active {{ transform: translateY(1px); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--linha); border-radius: .3rem; overflow: hidden; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ border-color: var(--linha); border-radius: .3rem; background: var(--papel-claro); }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: transparent; border-color: #3A5A52; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{ color: #E9A37F; }}
[data-testid="stExpander"] summary {{ transition: color .18s var(--curva); }}
[data-testid="stExpander"] summary:hover {{ color: var(--terra); }}
[data-testid="stPlotlyChart"] {{ animation: surgir .6s var(--curva) both; }}
.stMarkdown table {{ border-collapse: collapse; width: 100%; font-size: .88rem; margin: .5rem 0 1.25rem; }}
.stMarkdown th {{ text-align: left; font-weight: 600; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase;
                 color: var(--tinta-70); border-bottom: 1.5px solid var(--tinta); padding: .5rem .75rem .5rem 0; background: none; }}
.stMarkdown td {{ border: 0; border-bottom: 1px solid var(--linha); padding: .6rem .75rem .6rem 0; vertical-align: top; }}

/* ---------- Documentação (página Método) ---------- */
.sumario {{ position: sticky; top: 5rem; font-size: .85rem; line-height: 2.1; }}
.sumario a, .sumario a:visited {{ color: var(--tinta-70) !important; text-decoration: none; display: block;
  border-left: 1px solid var(--linha); padding-left: .9rem; transition: color .18s var(--curva), border-color .18s var(--curva); }}
.sumario a:hover {{ color: var(--terra) !important; border-left-color: var(--terra); }}

@keyframes surgir {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
@media (max-width: 900px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 1.5rem 1.1rem 4rem; }}
  .cabecalho {{ grid-template-columns: 1fr; gap: 1.5rem; }}
  .razao {{ border-left: 0; padding-left: 0; border-top: 1px solid var(--linha); }}
  .secao {{ grid-template-columns: 2.5rem 1fr; }} .secao p {{ grid-column: 2; }}
}}
</style>
"""


def aplicar_css():
    st.markdown(CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Template dos gráficos
# -----------------------------------------------------------------------------
pio.templates["teto"] = go.layout.Template(layout=dict(
    font=dict(family=FONTE_CORPO, size=12.5, color=TINTA),
    title=dict(font=dict(family=FONTE_TITULO, size=17, color=TINTA), x=0, xanchor="left", y=0.97),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=CATEGORICAS,
    xaxis=dict(automargin=True, showgrid=False, zeroline=False, linecolor=LINHA, ticks="outside", tickcolor=LINHA,
               ticklen=4, tickfont=dict(color=TINTA_70), title=dict(font=dict(size=12, color=TINTA_70))),
    yaxis=dict(automargin=True, gridcolor=GRADE, zeroline=False, showline=False, tickfont=dict(color=TINTA_70),
               title=dict(font=dict(size=12, color=TINTA_70))),
    hoverlabel=dict(bgcolor=PAPEL_CLARO, bordercolor=TINTA, font=dict(family=FONTE_CORPO, color=TINTA, size=12)),
    legend=dict(orientation="h", x=0, y=-0.16, font=dict(size=12, color=TINTA_70), title=dict(text="")),
    margin=dict(l=4, r=4, t=52, b=8),
    separators=",.",            # vírgula decimal e ponto de milhar (padrão brasileiro)
    bargap=0.35,
    coloraxis=dict(colorbar=dict(outlinewidth=0, tickfont=dict(color=TINTA_70))),
))
pio.templates.default = "teto"

# Escala divergente para correlação: verde-tinta (baixa) -> papel -> terracota (alta)
ESCALA_DIVERGENTE = [[0, TINTA], [0.5, PAPEL_CLARO], [1, TERRACOTA]]


def grafico(fig, altura=380, onde=None, hover="x unified"):
    """Desenha um gráfico Plotly com o template do site (sem a barra de ferramentas)."""
    fig.update_layout(height=altura, hovermode=hover, template="teto", paper_bgcolor=PAPEL, plot_bgcolor=PAPEL)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    (onde or st).plotly_chart(fig, theme=None, width="stretch", config={"displayModeBar": False})


# -----------------------------------------------------------------------------
# Componentes HTML
# -----------------------------------------------------------------------------
def _e(texto):
    return html.escape(str(texto))


def cabecalho(olho, titulo, lead="", razao=None, extra_html=""):
    """Cabeçalho assimétrico: título e texto à esquerda (7/11), quadro de
    números-chave à direita (4/11). 'razao' é uma lista de (rótulo, valor_html)
    ou (rótulo, valor_html, "grande") para o valor em destaque."""
    linhas = "".join(f"<div class='linha'><span class='rot'>{_e(item[0])}</span>"
                     f"<span class='val {item[2] if len(item) > 2 else ''}'>{item[1]}</span></div>"
                     for item in (razao or []))
    st.markdown(f"""<div class="cabecalho">
      <div><div class="olho">{olho}</div><h1 class="display">{titulo}</h1>
           {f'<p class="lead">{lead}</p>' if lead else ''}{extra_html}</div>
      <div class="razao">{linhas}</div></div>""", unsafe_allow_html=True)


def cifras(itens):
    """Linha de números de destaque. itens = [(rótulo, valor_html, nota)]."""
    blocos = "".join(f"<div class='cifra'><div class='rot'>{_e(r)}</div><div class='val'>{v}</div>"
                     f"{f'<div class=obs>{n}</div>' if n else ''}</div>" for r, v, n in itens)
    st.markdown(f"<div class='cifras'>{blocos}</div>", unsafe_allow_html=True)


def secao(numero, titulo, descricao="", compacta=False):
    """Título de seção numerado (estilo publicação de research). 'compacta'
    empilha a descrição sob o título, para uso em colunas estreitas."""
    st.markdown(f"<div class='secao{' compacta' if compacta else ''}'><span class='n'>{numero:02d}</span><h3>{_e(titulo)}</h3>"
                f"<p>{descricao}</p></div>", unsafe_allow_html=True)


def nota(texto, atencao=False):
    st.markdown(f"<div class='nota{' atencao' if atencao else ''}'>{texto}</div>", unsafe_allow_html=True)


def etiqueta(texto, cor=None):
    ponto = f"<i style='background:{cor}'></i>" if cor else ""
    return f"<span class='etiqueta'>{ponto}{_e(texto)}</span>"


def sinal(valor_txt, positivo):
    """Envolve um valor com a cor semântica (verde-tinta = favorável, terracota = atenção)."""
    return f"<span class='{'positivo' if positivo else 'negativo'}'>{valor_txt}</span>"
