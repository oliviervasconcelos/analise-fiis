# -*- coding: utf-8 -*-
"""
relatorio.py - GERAÇÃO DO RELATÓRIO da análise de preço teto
============================================================

Monta um relatório HTML (um único arquivo) a partir da tabela calculada pelo
site. Ele foi pensado para quem não usou o site: começa pelas conclusões,
explica o raciocínio financeiro com um exemplo numérico e só depois mostra
tabelas e gráficos.

Estrutura:
  01 Resumo                 - números principais e conclusões em frases simples
  02 O raciocínio           - custo de oportunidade -> taxa exigida -> perpetuidade,
                              com o mesmo fundo de exemplo nos três passos
                              (valor do dinheiro no tempo + risco e retorno)
  03 Os fundos              - tabela (yield x taxa exigida) e gráfico preço x teto
  04 Oportunidade ou risco? - volatilidade x margem e resumo por tipo de fundo
                              (relação entre risco e retorno)
  05 E se a taxa mudar?     - sensibilidade do preço teto à taxa exigida
                              (valor presente cai quando a taxa de desconto sobe)
  06 Destaques              - três fundos comentados
  07 Premissas, método e fontes

O visual segue o sistema de design do site (estilo.py).
"""
import html
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from estilo import (CORES_TIPO, LINHA, PAPEL, PAPEL_2, PAPEL_CLARO, TERRA_CLARA, TERRA_ESCURA, TERRACOTA,
                    TINTA, TINTA_45, TINTA_70)

NOME_TIPO = {"Papel": "os fundos de papel", "Tijolo": "os fundos de tijolo", "Híbrido": "os fundos híbridos",
             "FoF": "os fundos de fundos (FoF)", "Indefinido": "os fundos sem tipo definido"}
# Filtro de qualidade: yields fora desta faixa indicam erro na fonte (preço ou
# dividendo errado) ou fundo que praticamente não distribui. Nesses casos o
# preço teto não tem significado e distorceria medianas e destaques.
YIELD_MINIMO, YIELD_MAXIMO = 0.01, 0.40
MAX_NO_GRAFICO = 40          # acima disso, o gráfico preço x teto mostra só os extremos
EXTREMOS_NO_GRAFICO = 15     # quantos fundos de cada ponta aparecem nesse caso


# -----------------------------------------------------------------------------
# Formatação (padrão brasileiro)
# -----------------------------------------------------------------------------
def _br(texto):
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v):
    return "—" if pd.isna(v) else _br(f"R$ {v:,.2f}")


def pct(v, casas=2):
    return "—" if pd.isna(v) else _br(f"{v * 100:,.{casas}f}%")


def pp(v, casas=1):
    """Diferença em pontos percentuais, com sinal (ex.: +1,0 p.p.)."""
    return "—" if pd.isna(v) else _br(f"{v * 100:+.{casas}f}") + " p.p."


def _e(texto):
    return html.escape(str(texto))


def _classe(v):
    return "pos" if v >= 0 else "neg"


def leitura(margem):
    """Tradução da margem de segurança em uma expressão curta."""
    if pd.isna(margem):
        return "sem dados"
    if margem >= 0.15:
        return "abaixo do teto, com folga"
    if margem >= 0.05:
        return "abaixo do teto"
    if margem > -0.05:
        return "perto do teto"
    return "acima do teto"


def _layout(fig, altura):
    """Aparência comum dos gráficos do relatório (mesmo template do site)."""
    fig.update_layout(template="teto", height=altura, paper_bgcolor=PAPEL, plot_bgcolor=PAPEL,
                      separators=",.", hovermode="closest", margin=dict(l=8, r=16, t=10, b=44))
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


def _html_grafico(fig, primeiro):
    """Converte o gráfico em HTML. A biblioteca Plotly é carregada só uma vez."""
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if primeiro else False,
                       config={"displayModeBar": False})


def filtrar(t):
    """Separa os fundos que entram no relatório dos que ficam de fora.
    Retorna (fundos válidos, fundos excluídos com o motivo)."""
    calculavel = (t["teto"] > 0) & (t["preco"] > 0)
    t = t[calculavel]
    fora_faixa = (t["dy_atual"] < YIELD_MINIMO) | (t["dy_atual"] > YIELD_MAXIMO)
    excluidos = t[fora_faixa].assign(
        motivo=np.where(t.loc[fora_faixa, "dy_atual"] > YIELD_MAXIMO, "yield acima de 40%", "yield abaixo de 1%"))
    return t[~fora_faixa].copy(), excluidos


# -----------------------------------------------------------------------------
# Gráficos
# -----------------------------------------------------------------------------
def _grafico_preco_teto(t):
    """Para cada fundo, um ponto no preço atual e um traço no preço teto, ligados
    por uma linha. Como os preços têm escalas muito diferentes (R$ 9 a R$ 160),
    mostramos o preço como % do preço teto: o teto fica sempre em 100%.
    Com muitos fundos, mostra só as pontas (maiores e menores margens)."""
    d = t.sort_values("margem")
    recorte = len(d) > MAX_NO_GRAFICO
    if recorte:
        d = pd.concat([d.head(EXTREMOS_NO_GRAFICO), d.tail(EXTREMOS_NO_GRAFICO)])
    d = d.assign(preco_rel=d["preco"] / d["teto"])
    # Um fundo com preço muito acima do teto (ex.: 900%) achataria todos os outros:
    # o eixo vai até 200% e quem passa disso fica na borda, com o valor real escrito
    limite = 2.0
    d["x"] = d["preco_rel"].clip(upper=limite)
    fig = go.Figure()
    for _, r in d.iterrows():
        fig.add_shape(type="line", x0=r["x"], x1=1, y0=r["fii"], y1=r["fii"],
                      line=dict(color=TINTA if r["margem"] >= 0 else TERRACOTA, width=2.4))
    fig.add_scatter(x=[1] * len(d), y=d["fii"], mode="markers", hoverinfo="skip",
                    marker=dict(symbol="line-ns", size=14, line=dict(width=2.2, color=TINTA_45)))
    fora = d["preco_rel"] > limite
    fig.add_scatter(x=d["x"], y=d["fii"], mode="markers+text",
                    text=[f"{pct(v, 0)} →" if f else "" for v, f in zip(d["preco_rel"], fora)],
                    textposition="top left", textfont=dict(size=10, color=TERRA_ESCURA),
                    marker=dict(size=9, color=[TINTA if m >= 0 else TERRACOTA for m in d["margem"]],
                                symbol=["triangle-right" if f else "circle" for f in fora]),
                    customdata=np.stack([d["preco"].map(brl), d["teto"].map(brl), d["margem"].map(pct)], axis=-1),
                    hovertemplate="<b>%{y}</b><br>preço %{customdata[0]} · teto %{customdata[1]}"
                                  "<br>margem %{customdata[2]}<extra></extra>")
    fig.add_vline(x=1, line=dict(color=LINHA, width=1))
    _layout(fig, max(320, 26 * len(d) + 90))
    minimo = min(0.5, float(d["x"].min()) - 0.05)
    fig.update_layout(showlegend=False,
                      xaxis=dict(tickformat=".0%", range=[minimo, limite + 0.06],
                                 title="preço atual em % do preço teto (abaixo de 100% = abaixo do teto)"),
                      yaxis=dict(showgrid=False, type="category"))
    return fig, recorte


def _grafico_risco_margem(t):
    """Volatilidade da cota (risco) x margem de segurança, colorido pelo tipo.
    Se os fundos com mais margem forem também os mais voláteis, parte do
    "desconto" é só a compensação pelo risco maior."""
    d = t.dropna(subset=["vol_1a", "margem"])
    # Só os pontos que contam a história recebem rótulo (os outros aparecem ao passar o mouse):
    # as 3 maiores e as 3 menores margens e os 3 fundos mais voláteis
    rotulados = set(d.nlargest(3, "margem")["fii"]) | set(d.nsmallest(3, "margem")["fii"]) | \
        set(d.nlargest(3, "vol_1a")["fii"])
    fig = go.Figure()
    for tipo, grupo in d.groupby("tipo"):
        fig.add_scatter(x=grupo["vol_1a"], y=grupo["margem"], mode="markers+text", name=tipo,
                        text=[f if f in rotulados else "" for f in grupo["fii"]], customdata=grupo["fii"],
                        textposition="top center", textfont=dict(size=10, color=TINTA_70),
                        marker=dict(size=10, color=CORES_TIPO.get(tipo, TINTA_45), line=dict(width=0)),
                        hovertemplate="<b>%{customdata}</b><br>volatilidade %{x:.1%}<br>margem %{y:.1%}<extra></extra>")
    fig.add_hline(y=0, line=dict(color=LINHA, width=1))
    _layout(fig, 420)
    fig.update_layout(xaxis=dict(tickformat=".0%", title="volatilidade da cota nos últimos 12 meses (risco)"),
                      yaxis=dict(tickformat=".0%", title="margem de segurança"),
                      legend=dict(orientation="h", y=-0.2, x=0))
    return fig


# -----------------------------------------------------------------------------
# Análises auxiliares
# -----------------------------------------------------------------------------
def _sensibilidade(t, deslocamentos=(-0.02, -0.01, 0.0, 0.01, 0.02)):
    """Recalcula o preço teto somando 'd' à taxa exigida de cada fundo.
    Retorna uma lista de dicionários, um por deslocamento."""
    linhas = []
    for d in deslocamentos:
        taxa = t["taxa_exigida"] + d
        teto = (t["div_12m"] / taxa).where(taxa > 0)
        margem = teto / t["preco"] - 1
        linhas.append({"d": d, "abaixo": int((margem > 0).sum()), "margem": margem.median(),
                       "var_teto": (teto / t["teto"] - 1).median()})
    return linhas


def _por_tipo(t):
    return (t.groupby("tipo").agg(fundos=("fii", "count"), yield_=("dy_atual", "median"),
                                  premio=("premio", "median"), vol=("vol_1a", "median"),
                                  margem=("margem", "median"))
            .sort_values("fundos", ascending=False))


def _conclusoes(t, taxas, ipca, sens, corr_risco, tipos):
    n = len(t)
    abaixo = int((t["margem"] > 0).sum())
    barato, caro = t.iloc[0], t.iloc[-1]
    mais_1pp = next(s for s in sens if abs(s["d"] - 0.01) < 1e-9)
    frases = [
        f"<b>{abaixo} de {n} fundos</b> estão abaixo do preço teto: no preço de hoje, o rendimento deles supera o "
        f"de um título IPCA+ líquido de IR somado ao prêmio que o risco de cada um exige.",
        f"O título de referência rende <b>{pct(taxas['bruta'])}</b> ao ano antes do IR e <b>{pct(taxas['liquida'])}</b> "
        f"depois. Tirando a inflação esperada ({pct(ipca)}), sobra um ganho real de <b>{pct(taxas['equivalente'])}</b>: "
        f"é o mínimo que um fundo precisa entregar acima da inflação.",
        f"A maior margem é a de <b>{_e(barato['fii'])}</b> ({pct(barato['margem'])}) e o fundo mais acima do teto é "
        f"<b>{_e(caro['fii'])}</b> ({pct(caro['margem'])}).",
    ]
    if pd.notna(corr_risco):
        if corr_risco > 0.3:
            texto = ("os fundos com mais desconto tendem a ser os mais voláteis: parte da margem é compensação "
                     "pelo risco, não oportunidade")
        elif corr_risco < -0.3:
            texto = "os fundos mais voláteis tendem a ter margens menores: o mercado não está pagando pelo risco extra"
        else:
            texto = "a margem tem pouca relação com a volatilidade da cota: o desconto não se explica só pelo risco de preço"
        frases.append(f"A correlação entre risco (volatilidade da cota) e margem é de "
                      f"<b>{_br(f'{corr_risco:.2f}')}</b>. Ou seja, {texto}.")
    definidos = tipos.drop(index="Indefinido", errors="ignore")
    if len(definidos) > 1:
        melhor = definidos["margem"].idxmax()
        frases.append(f"Por tipo, <b>{NOME_TIPO.get(melhor, _e(melhor))}</b> têm a maior margem mediana "
                      f"({pct(tipos.loc[melhor, 'margem'])}, com {int(tipos.loc[melhor, 'fundos'])} na seleção).")
    frases.append(f"O resultado depende da taxa exigida: com <b>1 ponto percentual a mais</b>, os preços teto caem cerca "
                  f"de {pct(-mais_1pp['var_teto'], 0)} e os fundos abaixo do teto passam de {abaixo} para "
                  f"{mais_1pp['abaixo']}.")
    return frases


def _destaque(r, titulo, comentario):
    riscos = r["riscos"] if r["riscos"] != "—" else "nenhum fator de risco somou pontos"
    return f"""<article class="destaque">
      <div class="olho">{_e(titulo)}</div>
      <h3>{_e(r['fii'])} <span>{_e(r['tipo'])} · {_e(r['segmento'])}</span></h3>
      <dl>
        <div><dt>Preço</dt><dd>{brl(r['preco'])}</dd></div>
        <div><dt>Preço teto</dt><dd>{brl(r['teto'])}</dd></div>
        <div><dt>Yield 12m</dt><dd>{pct(r['dy_atual'])}</dd></div>
        <div><dt>Margem</dt><dd class="{_classe(r['margem'])}">{pct(r['margem'])}</dd></div>
      </dl>
      <p>{comentario}</p>
      <p class="riscos">Prêmio de {pct(r['premio'])}: {_e(riscos)}.</p>
    </article>"""


# -----------------------------------------------------------------------------
# Relatório completo
# -----------------------------------------------------------------------------
def gerar_html(t, taxas, ipca, premissas, hora_cotacao, autores="", universo=""):
    """Gera o HTML do relatório.

    t            : linhas da tabela do site para os fundos escolhidos
    taxas        : dicionário com 'bruta', 'liquida', 'equivalente'
    ipca         : IPCA usado (decimal)
    premissas    : dict com ipca_mais, ir, modo_premio, modo_ipca, premio_base, peso, fator_ipca
    hora_cotacao : horário das cotações usadas
    """
    # Só entram fundos com dividendos (teto > 0), preço conhecido e yield plausível
    t, excluidos = filtrar(t)
    if len(t) < 2:
        raise ValueError("É preciso pelo menos dois fundos com preço e preço teto calculáveis.")
    t = t.sort_values("margem", ascending=False)
    agora = datetime.now()
    p = premissas
    n, abaixo = len(t), int((t["margem"] > 0).sum())
    eq = taxas["equivalente"]

    # Análises
    sens = _sensibilidade(t)
    tipos = _por_tipo(t)
    corr_risco = t[["vol_1a", "margem"]].dropna().corr().iloc[0, 1] if t["vol_1a"].notna().sum() > 3 else np.nan

    # Fundo de exemplo dos três passos: o mais negociado da seleção
    ex = t.loc[t["liquidez"].fillna(0).idxmax()]

    # Gráficos
    fig_teto, recorte = _grafico_preco_teto(t)
    html_teto = _html_grafico(fig_teto, primeiro=True)
    html_risco = _html_grafico(_grafico_risco_margem(t), primeiro=False)
    nota_recorte = (f"<p class='legenda'>Com {n} fundos, o gráfico mostra as {EXTREMOS_NO_GRAFICO} maiores e as "
                    f"{EXTREMOS_NO_GRAFICO} menores margens. A tabela acima traz todos.</p>") if recorte else ""
    if len(excluidos):
        lista_excl = ", ".join(f"{_e(r['fii'])} ({r['motivo']}: {pct(r['dy_atual'], 1)})"
                               for _, r in excluidos.sort_values("dy_atual", ascending=False).head(12).iterrows())
        mais = f" e outros {len(excluidos) - 12}" if len(excluidos) > 12 else ""
        nota_excluidos = (f"<p class='legenda'>{len(excluidos)} fundo(s) ficaram de fora por terem yield fora da faixa "
                          f"de 1% a 40%, o que indica erro nos dados da fonte ou fundo que praticamente não distribui: "
                          f"{lista_excl}{mais}.</p>")
    else:
        nota_excluidos = ""

    # Destaques
    barato, caro = t.iloc[0], t.iloc[-1]
    arriscado = t.loc[t["premio"].idxmax()]
    destaques = [
        _destaque(barato, "Maior margem de segurança",
                  f"Rende {pct(barato['dy_atual'])} no preço atual, contra uma exigência de {pct(barato['taxa_exigida'])}. "
                  f"Margem alta pode ser oportunidade ou sinal de um risco que o mercado enxerga: leia os riscos abaixo "
                  f"antes de concluir."),
        _destaque(caro, "Mais acima do teto",
                  f"Rende {pct(caro['dy_atual'])} no preço atual, abaixo dos {pct(caro['taxa_exigida'])} exigidos. "
                  f"Para valer esse preço, os dividendos teriam de crescer ou o risco teria de ser menor."),
    ]
    if arriscado["fii"] not in (barato["fii"], caro["fii"]):
        destaques.append(_destaque(
            arriscado, "Maior prêmio de risco",
            f"É o fundo com mais fatores de risco nos dados. Por isso exigimos {pct(arriscado['premio'])} acima do "
            f"título, o que leva o teto para {brl(arriscado['teto'])}."))

    # Tabelas
    linhas_fundos = "".join(
        f"<tr><td class='fii'>{_e(r['fii'])}</td>"
        f"<td><i style='background:{CORES_TIPO.get(r['tipo'], TINTA_45)}'></i>{_e(r['tipo'])}</td>"
        f"<td class='n'>{brl(r['preco'])}</td><td class='n'>{brl(r['div_12m'])}</td>"
        f"<td class='n'>{pct(r['dy_atual'])}</td><td class='n'>{pct(r['taxa_exigida'])}</td>"
        f"<td class='n forte'>{brl(r['teto'])}</td>"
        f"<td class='n {_classe(r['margem'])}'>{pct(r['margem'])}</td>"
        f"<td class='leitura'>{leitura(r['margem'])}</td></tr>"
        for _, r in t.iterrows())
    linhas_tipo = "".join(
        f"<tr><td><i style='background:{CORES_TIPO.get(tipo, TINTA_45)}'></i>{_e(tipo)}</td>"
        f"<td class='n'>{int(r['fundos'])}</td><td class='n'>{pct(r['yield_'])}</td><td class='n'>{pct(r['premio'])}</td>"
        f"<td class='n'>{pct(r['vol'])}</td><td class='n {_classe(r['margem'])}'>{pct(r['margem'])}</td></tr>"
        for tipo, r in tipos.iterrows())
    cab_sens = "".join(f"<th class='n{' atual' if s['d'] == 0 else ''}'>"
                       f"{'atual' if s['d'] == 0 else pp(s['d'], 0)}</th>" for s in sens)
    taxa_sens = "".join(f"<td class='n{' atual' if s['d'] == 0 else ''}'>{pct(ex['taxa_exigida'] + s['d'])}</td>"
                        for s in sens)
    teto_sens = "".join(f"<td class='n{' atual' if s['d'] == 0 else ''}'>"
                        f"{brl(ex['div_12m'] / (ex['taxa_exigida'] + s['d']))}</td>" for s in sens)
    abaixo_sens = "".join(f"<td class='n{' atual' if s['d'] == 0 else ''}'>{s['abaixo']} de {n}</td>" for s in sens)
    margem_sens = "".join(f"<td class='n {_classe(s['margem'])}{' atual' if s['d'] == 0 else ''}'>{pct(s['margem'])}</td>"
                          for s in sens)
    fator = p.get("fator_ipca", {})
    peso = _br(f"{p['peso']:.2f}")
    premissas_linhas = [
        ("IPCA esperado", pct(ipca)), ("Taxa do título IPCA+", pct(p["ipca_mais"])), ("IR sobre o título", pct(p["ir"], 1)),
        ("Ganho real líquido exigido (base)", pct(eq)),
        ("Prêmio de risco", f"{p['modo_premio']} · base {pct(p['premio_base'])} · peso {peso}"),
        ("Ajuste de IPCA", p["modo_ipca"] + (" · " + ", ".join(f"{k} {pct(v, 0)}" for k, v in fator.items())
                                             if fator else "")),
        ("Cotações usadas", f"{hora_cotacao:%d/%m/%Y %H:%M} (Yahoo Finance)"),
    ]

    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preço teto de FIIs · relatório de {agora:%d/%m/%Y}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{ --tinta:{TINTA}; --tinta-70:{TINTA_70}; --tinta-45:{TINTA_45}; --papel:{PAPEL}; --papel-2:{PAPEL_2};
        --papel-claro:{PAPEL_CLARO}; --terra:{TERRACOTA}; --terra-clara:{TERRA_CLARA}; --terra-escura:{TERRA_ESCURA};
        --linha:{LINHA}; --serif: Fraunces, Georgia, serif; --sans: 'IBM Plex Sans', system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--papel); color: var(--tinta); font: 15px/1.65 var(--sans);
       font-variant-numeric: tabular-nums; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 4rem 2rem 6rem; }}
.olho {{ font-size: .7rem; font-weight: 600; letter-spacing: .18em; text-transform: uppercase; color: var(--terra); }}
h1 {{ font: 500 3.2rem/1.04 var(--serif); letter-spacing: -.025em; margin: .9rem 0 1rem; }}
h1 em, h2 em {{ font-style: italic; color: var(--terra); }}
h2 {{ font: 500 1.75rem/1.2 var(--serif); letter-spacing: -.01em; margin: 0 0 .4rem; }}
h3 {{ font: 500 1.35rem/1.2 var(--serif); margin: .4rem 0 .9rem; }}
h3 span {{ font: 400 .8rem var(--sans); color: var(--tinta-45); margin-left: .4rem; }}
p {{ margin: 0 0 .9rem; }}
.lead {{ font-size: 1.08rem; color: var(--tinta-70); max-width: 56ch; }}
.ficha {{ display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 1.2rem; margin-top: 2.2rem; padding-top: 1rem;
         border-top: 1px solid var(--linha); font-size: .8rem; color: var(--tinta-70); }}
.ficha b {{ display: block; color: var(--tinta); font-weight: 500; font-size: .9rem; }}
.sumario {{ display: flex; flex-wrap: wrap; gap: .4rem 1.4rem; margin-top: 1.4rem; font-size: .8rem; }}
.sumario a {{ color: var(--tinta-70); text-decoration: none; border-bottom: 1px solid var(--linha); }}
.sumario a:hover {{ color: var(--terra); border-color: var(--terra); }}
section {{ margin-top: 4.5rem; }}
.cab {{ display: grid; grid-template-columns: 3rem 1fr; border-top: 1px solid var(--linha); padding-top: 1.1rem;
       margin-bottom: 1.6rem; }}
.cab .n {{ font: italic 1.05rem var(--serif); color: var(--terra); padding-top: .35rem; }}
.cab p {{ color: var(--tinta-70); font-size: .9rem; margin: 0; max-width: 66ch; }}
.cifras {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1.5px solid var(--tinta);
          border-bottom: 1px solid var(--linha); margin-bottom: 1.8rem; }}
.cifras div {{ padding: 1rem 1rem 1.1rem 0; }} .cifras div + div {{ padding-left: 1rem; border-left: 1px solid var(--linha); }}
.cifras small {{ display: block; font-size: .7rem; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--tinta-70); }}
.cifras b {{ font: 500 1.9rem/1.2 var(--serif); }}
.cifras span {{ display: block; font-size: .75rem; color: var(--tinta-45); }}
ul.conclusoes {{ list-style: none; padding: 0; margin: 0; }}
ul.conclusoes li {{ padding: .8rem 0 .8rem 1.4rem; border-bottom: 1px solid var(--linha); position: relative; }}
ul.conclusoes li::before {{ content: ""; position: absolute; left: 0; top: 1.45rem; width: .55rem; height: 1.5px; background: var(--terra); }}
.passos {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.8rem; }}
.passo {{ border-top: 1.5px solid var(--tinta); padding-top: 1rem; display: flex; flex-direction: column; }}
.passo .num {{ font: italic 2.2rem/1 var(--serif); color: var(--terra); }}
.passo h4 {{ font: 500 1.1rem/1.3 var(--serif); margin: .6rem 0 .5rem; }}
.passo p {{ font-size: .88rem; color: var(--tinta-70); }}
.conceito {{ font-size: .7rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--tinta-45); margin-top: .5rem; }}
.conta {{ margin-top: auto; background: var(--papel-claro); border-left: 2px solid var(--terra); padding: .7rem .9rem; }}
.conta div {{ display: flex; justify-content: space-between; gap: .8rem; font-size: .8rem; color: var(--tinta-70);
             padding: .2rem 0; }}
.conta div b {{ font: 500 .98rem var(--serif); color: var(--tinta); white-space: nowrap; }}
.conta div.total {{ border-top: 1px solid var(--linha); margin-top: .25rem; padding-top: .4rem; }}
.conta div.total b {{ font-weight: 600; }}
.exemplo {{ font-size: .85rem; color: var(--tinta-70); margin-top: 1.4rem; }}
table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
th {{ text-align: left; font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
     color: var(--tinta-70); border-bottom: 1.5px solid var(--tinta); padding: .55rem .6rem .55rem 0; vertical-align: bottom; }}
td {{ border-bottom: 1px solid var(--linha); padding: .5rem .6rem .5rem 0; }}
th.n, td.n {{ text-align: right; }}
td.fii {{ font-weight: 600; }} td.forte {{ font-weight: 600; }}
.duas td:first-child {{ white-space: nowrap; }}
td i {{ display: inline-block; width: .5rem; height: .5rem; border-radius: 50%; margin-right: .45rem; }}
td.leitura {{ color: var(--tinta-70); font-size: .8rem; padding-left: 1rem; }}
th.atual, td.atual {{ background: var(--papel-claro); }}
.pos {{ color: var(--tinta); font-weight: 600; }} .neg {{ color: var(--terra); font-weight: 600; }}
.grafico {{ margin-top: 2rem; }}
.legenda {{ font-size: .8rem; color: var(--tinta-45); margin-top: .5rem; }}
.duas {{ display: grid; grid-template-columns: 3fr 2fr; gap: 2.2rem; align-items: start; }}
.duas h4 {{ font: 500 1.05rem var(--serif); margin: 0 0 .7rem; }}
.texto {{ font-size: .9rem; color: var(--tinta-70); max-width: 70ch; }}
.destaques {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.8rem; }}
.destaque {{ border-top: 1.5px solid var(--tinta); padding-top: 1rem; }}
.destaque dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: .6rem 1rem; margin: 0 0 1rem; }}
.destaque dt {{ font-size: .68rem; color: var(--tinta-45); text-transform: uppercase; letter-spacing: .06em; }}
.destaque dd {{ margin: 0; font: 500 1.15rem var(--serif); }}
.destaque p {{ font-size: .88rem; }}
.destaque .riscos {{ color: var(--tinta-70); font-size: .8rem; border-left: 2px solid var(--linha); padding-left: .8rem; }}
.metodo {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2.2rem; font-size: .86rem; color: var(--tinta-70); }}
.metodo h4 {{ font: 500 1.05rem var(--serif); color: var(--tinta); margin: 0 0 .6rem; }}
.metodo ul {{ padding-left: 1.1rem; margin: 0; }} .metodo li {{ margin-bottom: .4rem; }}
.metodo table td {{ font-size: .84rem; }} .metodo table td:last-child {{ color: var(--tinta); text-align: right; }}
footer {{ margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--linha); font-size: .78rem; color: var(--tinta-45); }}
@media (max-width: 800px) {{ .passos, .metodo, .duas {{ grid-template-columns: 1fr; }}
  .ficha, .cifras {{ grid-template-columns: 1fr 1fr; }} h1 {{ font-size: 2.3rem; }} }}
@media print {{ body {{ background: white; font-size: 12px; }} main {{ padding: 0; max-width: none; }}
  section {{ break-inside: avoid-page; }} .sumario {{ display: none; }} }}
</style></head><body><main>

<div class="olho">Administração Financeira · CAD 167 · Trabalho 1</div>
<h1>Preço teto de<br><em>fundos imobiliários</em></h1>
<p class="lead">Quanto vale a pena pagar por cada FII para que ele renda mais do que um título público atrelado
à inflação, levando em conta o risco de cada fundo.</p>
<div class="ficha">
  <div>Autores<b>{_e(autores) or "—"}</b></div>
  <div>Data<b>{agora:%d/%m/%Y, %H:%M}</b></div>
  <div>Fundos analisados<b>{n} · {_e(universo)}</b></div>
  <div>Cotações<b>{hora_cotacao:%d/%m %H:%M}</b></div>
</div>
<nav class="sumario"><a href="#resumo">Resumo</a><a href="#raciocinio">O raciocínio</a><a href="#fundos">Os fundos</a>
<a href="#risco">Oportunidade ou risco?</a><a href="#sensibilidade">E se a taxa mudar?</a><a href="#destaques">Destaques</a>
<a href="#metodo">Premissas e método</a></nav>

<section id="resumo">
  <div class="cab"><span class="n">01</span><div><h2>Resumo</h2><p>O que a análise mostra hoje.</p></div></div>
  <div class="cifras">
    <div><small>Fundos analisados</small><b>{n}</b><span>{_e(universo)}</span></div>
    <div><small>Abaixo do teto</small><b>{abaixo}</b><span>{pct(abaixo / n, 0)} da seleção</span></div>
    <div><small>Margem mediana</small><b class="{_classe(t['margem'].median())}">{pct(t['margem'].median())}</b><span>preço teto ÷ preço − 1</span></div>
    <div><small>Ganho real exigido</small><b>{pct(eq)}</b><span>antes do prêmio de risco</span></div>
  </div>
  <ul class="conclusoes">{''.join(f'<li>{f}</li>' for f in _conclusoes(t, taxas, ipca, sens, corr_risco, tipos))}</ul>
</section>

<section id="raciocinio">
  <div class="cab"><span class="n">02</span><div><h2>O raciocínio em <em>três passos</em></h2>
  <p>O preço teto junta dois temas da disciplina: o valor do dinheiro no tempo (passos 1 e 3) e a relação entre
  risco e retorno (passo 2). As contas seguem um mesmo fundo de exemplo, {_e(ex['fii'])}, o mais negociado da seleção.</p></div></div>
  <div class="passos">
    <div class="passo"><div class="num">1</div><div class="conceito">Custo de oportunidade · equação de Fisher</div>
      <h4>Quanto rende a alternativa segura?</h4>
      <p>O dinheiro posto no fundo deixa de render no Tesouro IPCA+. Como o título paga IR e o dividendo do FII é isento,
      usamos a taxa líquida; e, para comparar ganhos reais, tiramos a inflação.</p>
      <div class="conta">
        <div>bruta: (1 + {pct(ipca)}) × (1 + {pct(p['ipca_mais'])}) − 1<b>{pct(taxas['bruta'])}</b></div>
        <div>líquida: {pct(taxas['bruta'])} × (1 − {pct(p['ir'], 0)})<b>{pct(taxas['liquida'])}</b></div>
        <div class="total">real: (1 + {pct(taxas['liquida'])}) ÷ (1 + {pct(ipca)}) − 1<b>{pct(eq)}</b></div>
      </div>
    </div>
    <div class="passo"><div class="num">2</div><div class="conceito">Risco e retorno · prêmio de risco</div>
      <h4>Quanto a mais o risco exige?</h4>
      <p>Um FII é mais arriscado que o Tesouro, então exigimos um prêmio, maior para fundos pequenos, pouco líquidos, com
      vacância ou dividendos instáveis. Fundos de papel somam também a inflação, pois parte do dividendo é só correção.</p>
      <div class="conta">
        <div>ganho real do título<b>{pct(eq)}</b></div>
        <div>+ prêmio de risco de {_e(ex['fii'])}<b>{pct(ex['premio'])}</b></div>
        <div>+ ajuste de IPCA ({_e(ex['tipo'].lower())})<b>{pct(ex['ajuste_ipca'])}</b></div>
        <div class="total">taxa exigida<b>{pct(ex['taxa_exigida'])}</b></div>
      </div>
    </div>
    <div class="passo"><div class="num">3</div><div class="conceito">Valor presente de uma perpetuidade</div>
      <h4>Quanto vale essa renda hoje?</h4>
      <p>Um FII paga dividendos sem prazo para acabar. O valor presente de uma renda perpétua é o pagamento dividido
      pela taxa (VP = PMT ÷ i): é o maior preço que ainda entrega a taxa exigida.</p>
      <div class="conta">
        <div>dividendos dos últimos 12 meses<b>{brl(ex['div_12m'])}</b></div>
        <div>÷ taxa exigida<b>{pct(ex['taxa_exigida'])}</b></div>
        <div class="total">preço teto<b>{brl(ex['teto'])}</b></div>
      </div>
    </div>
  </div>
  <p class="exemplo">Com a cota de {_e(ex['fii'])} a {brl(ex['preco'])}, a margem de segurança é de
  <b class="{_classe(ex['margem'])}">{pct(ex['margem'])}</b>: {leitura(ex['margem'])}.</p>
</section>

<section id="fundos">
  <div class="cab"><span class="n">03</span><div><h2>Os fundos</h2>
  <p>A comparação central é entre o <b>yield</b> (dividendos ÷ preço) e a <b>taxa exigida</b>: quando o yield é maior,
  o fundo está abaixo do teto. Ordenados da maior para a menor margem.</p></div></div>
  <table><thead><tr><th>Fundo</th><th>Tipo</th><th class="n">Preço</th><th class="n">Dividendo 12m</th>
  <th class="n">Yield</th><th class="n">Taxa exigida</th><th class="n">Preço teto</th><th class="n">Margem</th>
  <th style="padding-left:1rem">Leitura</th></tr></thead>
  <tbody>{linhas_fundos}</tbody></table>
  {nota_excluidos}
  <div class="grafico">{html_teto}{nota_recorte}</div>
</section>

<section id="risco">
  <div class="cab"><span class="n">04</span><div><h2>Oportunidade ou <em>risco</em>?</h2>
  <p>Uma margem grande pode ser uma pechincha ou o preço de um risco maior. Se os fundos com mais desconto forem também os
  que mais oscilam, o "desconto" é, em parte, a compensação que o mercado exige pelo risco.</p></div></div>
  <div class="duas">
    <div>{html_risco}</div>
    <div><h4>Medianas por tipo de fundo</h4>
      <table><thead><tr><th>Tipo</th><th class="n">Fundos</th><th class="n">Yield</th><th class="n">Prêmio</th>
      <th class="n">Volat.</th><th class="n">Margem</th></tr></thead><tbody>{linhas_tipo}</tbody></table>
      <p class="legenda">Volatilidade: desvio-padrão anualizado dos retornos diários (cota + dividendos) nos últimos 12 meses.</p>
    </div>
  </div>
</section>

<section id="sensibilidade">
  <div class="cab"><span class="n">05</span><div><h2>E se a <em>taxa</em> mudar?</h2>
  <p>No valor presente, taxa de desconto e valor andam em sentidos opostos. A tabela soma ou subtrai pontos percentuais da
  taxa exigida de todos os fundos, como aconteceria se os juros do Tesouro subissem ou caíssem.</p></div></div>
  <table><thead><tr><th>Taxa exigida</th>{cab_sens}</tr></thead><tbody>
    <tr><td>Taxa de {_e(ex['fii'])}</td>{taxa_sens}</tr>
    <tr><td>Preço teto de {_e(ex['fii'])}</td>{teto_sens}</tr>
    <tr><td>Fundos abaixo do teto</td>{abaixo_sens}</tr>
    <tr><td>Margem mediana da seleção</td>{margem_sens}</tr>
  </tbody></table>
</section>

<section id="destaques">
  <div class="cab"><span class="n">06</span><div><h2>Destaques</h2>
  <p>Três fundos que ajudam a entender o resultado.</p></div></div>
  <div class="destaques">{''.join(destaques)}</div>
</section>

<section id="metodo">
  <div class="cab"><span class="n">07</span><div><h2>Premissas, método e fontes</h2>
  <p>O suficiente para reproduzir a análise.</p></div></div>
  <div class="metodo">
    <div><h4>Premissas usadas</h4>
      <table><tbody>{''.join(f'<tr><td>{_e(r)}</td><td>{_e(v)}</td></tr>' for r, v in premissas_linhas)}</tbody></table>
    </div>
    <div><h4>Método e fontes</h4><ul>
      <li>Dividendo 12m: soma dos pagamentos com data-ex nos últimos 12 meses (Yahoo Finance).</li>
      <li>Tipo do fundo (papel, tijolo, híbrido, FoF): composição dos ativos no Informe Mensal entregue à CVM.</li>
      <li>Prêmio automático: base mais pontos por fator de risco (liquidez, porte, número de imóveis, vacância,
          volatilidade, estabilidade e tendência dos dividendos, yield frente aos pares).</li>
      <li>Cotações: Yahoo Finance (cerca de 15 minutos de atraso). Indicadores: Fundamentus.
          IPCA esperado: Banco Central (Focus). Taxas do Tesouro IPCA+: Tesouro Transparente.</li>
    </ul></div>
  </div>
</section>

<footer>Relatório gerado pelo site Teto em {agora:%d/%m/%Y às %H:%M}. Ferramenta educacional; não é recomendação
de investimento.</footer>
</main></body></html>"""


def gerar_csv(t):
    """Tabela completa dos fundos do relatório, no padrão do Excel brasileiro."""
    colunas = {"fii": "FII", "tipo": "Tipo", "segmento": "Segmento", "preco": "Preço", "div_12m": "Dividendo 12m",
               "dy_atual": "Yield 12m", "pvp_atual": "P/VP", "vol_1a": "Volatilidade 12m", "premio": "Prêmio",
               "ajuste_ipca": "Ajuste IPCA", "taxa_exigida": "Taxa exigida", "teto": "Preço teto",
               "margem": "Margem", "riscos": "Riscos do prêmio"}
    t, _ = filtrar(t)   # mesmos fundos do relatório
    return (t.sort_values("margem", ascending=False)[list(colunas)].rename(columns=colunas)
            .to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"))
