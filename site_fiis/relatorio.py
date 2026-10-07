# -*- coding: utf-8 -*-
"""
relatorio.py - GERAÇÃO DO RELATÓRIO da análise de preço teto
============================================================

Monta um relatório HTML autocontido (um único arquivo) a partir da tabela
calculada pelo site. O relatório é pensado para ser lido por quem não usou o
site: começa pelas conclusões, explica o raciocínio financeiro em três passos
e só depois mostra a tabela e os gráficos.

Estrutura:
  1. Resumo        - números principais e conclusões em frases simples
  2. O raciocínio  - custo de oportunidade -> taxa exigida -> perpetuidade
                     (os conceitos de "valor do dinheiro no tempo" e de
                     "risco e retorno" aplicados ao caso)
  3. Os fundos     - tabela enxuta e gráfico preço x preço teto
  4. Destaques     - três fundos comentados (mais barato, mais caro, mais arriscado)
  5. Método e fontes

O visual segue o sistema de design do site (estilo.py).
"""
import html
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from estilo import (LINHA, PAPEL, PAPEL_2, PAPEL_CLARO, TERRA_CLARA, TERRA_ESCURA, TERRACOTA, TINTA,
                    TINTA_45, TINTA_70, CORES_TIPO)


# -----------------------------------------------------------------------------
# Formatação (padrão brasileiro)
# -----------------------------------------------------------------------------
def _br(texto):
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v):
    return "—" if pd.isna(v) else _br(f"R$ {v:,.2f}")


def pct(v, casas=2):
    return "—" if pd.isna(v) else _br(f"{v * 100:,.{casas}f}%")


def _e(texto):
    return html.escape(str(texto))


def leitura(margem):
    """Tradução da margem de segurança em uma frase curta."""
    if pd.isna(margem):
        return "sem dados"
    if margem >= 0.15:
        return "abaixo do teto, com folga"
    if margem >= 0.05:
        return "abaixo do teto"
    if margem > -0.05:
        return "perto do teto"
    return "acima do teto"


# -----------------------------------------------------------------------------
# Gráfico: preço atual x preço teto (gráfico de halteres)
# -----------------------------------------------------------------------------
def _grafico_preco_teto(t):
    """Para cada fundo, um ponto no preço atual e outro no preço teto, ligados
    por uma linha. Como os preços têm escalas muito diferentes (R$ 9 a R$ 160),
    mostramos ambos como % do preço teto: o teto fica sempre em 100%."""
    d = t.sort_values("margem").copy()
    d["preco_rel"] = d["preco"] / d["teto"]
    fig = go.Figure()
    for _, r in d.iterrows():
        cor = TINTA if r["margem"] >= 0 else TERRACOTA
        fig.add_shape(type="line", x0=r["preco_rel"], x1=1, y0=r["fii"], y1=r["fii"],
                      line=dict(color=cor, width=2.4))
    fig.add_scatter(x=[1] * len(d), y=d["fii"], mode="markers", name="Preço teto",
                    marker=dict(symbol="line-ns", size=14, line=dict(width=2.2, color=TINTA_45)),
                    hovertemplate="%{y}: teto<extra></extra>")
    fig.add_scatter(x=d["preco_rel"], y=d["fii"], mode="markers", name="Preço atual",
                    marker=dict(size=9, color=[TINTA if m >= 0 else TERRACOTA for m in d["margem"]]),
                    customdata=np.stack([d["preco"].map(brl), d["teto"].map(brl), d["margem"].map(pct)], axis=-1),
                    hovertemplate="<b>%{y}</b><br>preço %{customdata[0]} · teto %{customdata[1]}"
                                  "<br>margem %{customdata[2]}<extra></extra>")
    fig.add_vline(x=1, line=dict(color=LINHA, width=1))
    fig.update_layout(
        template="teto", height=max(320, 26 * len(d) + 90), showlegend=False,
        paper_bgcolor=PAPEL, plot_bgcolor=PAPEL, separators=",.", hovermode="closest",
        margin=dict(l=8, r=16, t=10, b=40),
        xaxis=dict(tickformat=".0%", title="preço atual como % do preço teto (à esquerda de 100% = abaixo do teto)",
                   automargin=True),
        yaxis=dict(automargin=True, showgrid=False))
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})


# -----------------------------------------------------------------------------
# Textos automáticos
# -----------------------------------------------------------------------------
def _conclusoes(t, taxas, ipca):
    n = len(t)
    abaixo = t[t["margem"] > 0]
    barato = t.loc[t["margem"].idxmax()]
    caro = t.loc[t["margem"].idxmin()]
    frases = [
        f"<b>{len(abaixo)} de {n} fundos</b> estão abaixo do preço teto: no preço de hoje, o rendimento "
        f"deles supera o de um título IPCA+ líquido de IR somado ao prêmio que o risco de cada um exige.",
        f"O título de referência rende <b>{pct(taxas['bruta'])}</b> ao ano antes do IR e "
        f"<b>{pct(taxas['liquida'])}</b> depois; descontada a inflação esperada ({pct(ipca)}), sobra um ganho real "
        f"de <b>{pct(taxas['equivalente'])}</b>. É o mínimo que um fundo precisa render acima da inflação.",
        f"A maior margem é a de <b>{_e(barato['fii'])}</b>: preço de {brl(barato['preco'])} contra teto de "
        f"{brl(barato['teto'])} ({pct(barato['margem'])}).",
        f"O fundo mais acima do teto é <b>{_e(caro['fii'])}</b>: o preço de {brl(caro['preco'])} só se justificaria "
        f"com dividendos maiores ou um prêmio de risco menor que {pct(caro['premio'])}.",
    ]
    return frases


def _destaque(r, titulo, comentario):
    riscos = r["riscos"] if r["riscos"] != "—" else "nenhum fator de risco somou pontos"
    return f"""<article class="destaque">
      <div class="olho">{_e(titulo)}</div>
      <h3>{_e(r['fii'])} <span>{_e(r['tipo'])} · {_e(r['segmento'])}</span></h3>
      <dl>
        <div><dt>Preço</dt><dd>{brl(r['preco'])}</dd></div>
        <div><dt>Preço teto</dt><dd>{brl(r['teto'])}</dd></div>
        <div><dt>Margem</dt><dd class="{'pos' if r['margem'] >= 0 else 'neg'}">{pct(r['margem'])}</dd></div>
        <div><dt>Yield 12m</dt><dd>{pct(r['dy_atual'])}</dd></div>
      </dl>
      <p>{comentario}</p>
      <p class="riscos">Prêmio de {pct(r['premio'])}, formado por: {_e(riscos)}.</p>
    </article>"""


# -----------------------------------------------------------------------------
# Relatório completo
# -----------------------------------------------------------------------------
def gerar_html(t, taxas, ipca, premissas, hora_cotacao, autores="", universo=""):
    """Gera o HTML do relatório.

    t          : linhas da tabela do site para os fundos escolhidos
    taxas      : dicionário com 'bruta', 'liquida', 'equivalente'
    ipca       : IPCA usado (decimal)
    premissas  : dict com ipca_mais, ir, modo_premio, modo_ipca, premio_base, peso
    """
    t = t[t["teto"].notna() & t["preco"].notna()].copy()
    if t.empty:
        raise ValueError("Nenhum fundo com preço e preço teto calculáveis.")
    t = t.sort_values("margem", ascending=False)
    agora = datetime.now()
    n, abaixo = len(t), int((t["margem"] > 0).sum())
    eq = taxas["equivalente"]

    # Exemplo numérico do passo 3 com o fundo de maior liquidez da lista
    ex = t.loc[t["liquidez"].fillna(0).idxmax()]

    # Destaques
    barato = t.iloc[0]
    caro = t.iloc[-1]
    arriscado = t.loc[t["premio"].idxmax()]
    destaques = [
        _destaque(barato, "Maior margem de segurança",
                  f"Rende {pct(barato['dy_atual'])} em dividendos no preço atual, contra uma exigência de "
                  f"{pct(barato['taxa_exigida'])}. Margem alta pode ser oportunidade ou sinal de um risco que "
                  f"o mercado enxerga: vale ler os riscos abaixo antes de concluir."),
        _destaque(caro, "Mais acima do teto",
                  f"Para valer o preço atual com o mesmo dividendo, o investidor teria de aceitar uma taxa de "
                  f"{pct(caro['dy_atual'])}, abaixo dos {pct(caro['taxa_exigida'])} exigidos."),
    ]
    if arriscado["fii"] not in (barato["fii"], caro["fii"]):
        destaques.append(_destaque(arriscado, "Maior prêmio de risco exigido",
                                   f"É o fundo com mais fatores de risco nos dados; por isso exigimos "
                                   f"{pct(arriscado['premio'])} acima do título, e o teto fica mais baixo."))

    # Tabela enxuta
    linhas = "".join(
        f"<tr><td class='fii'>{_e(r['fii'])}</td>"
        f"<td><i style='background:{CORES_TIPO.get(r['tipo'], TINTA_45)}'></i>{_e(r['tipo'])}</td>"
        f"<td class='n'>{brl(r['preco'])}</td><td class='n'>{brl(r['div_12m'])}</td>"
        f"<td class='n'>{pct(r['taxa_exigida'])}</td><td class='n forte'>{brl(r['teto'])}</td>"
        f"<td class='n {'pos' if r['margem'] >= 0 else 'neg'}'>{pct(r['margem'])}</td>"
        f"<td class='leitura'>{leitura(r['margem'])}</td></tr>"
        for _, r in t.iterrows())

    p = premissas
    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preço teto de FIIs · relatório de {agora:%d/%m/%Y}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{ --tinta:{TINTA}; --tinta-70:{TINTA_70}; --tinta-45:{TINTA_45}; --papel:{PAPEL}; --papel-2:{PAPEL_2};
        --papel-claro:{PAPEL_CLARO}; --terra:{TERRACOTA}; --terra-clara:{TERRA_CLARA}; --terra-escura:{TERRA_ESCURA};
        --linha:{LINHA}; --serif: Fraunces, Georgia, serif; --sans: 'IBM Plex Sans', system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--papel); color: var(--tinta); font: 15px/1.65 var(--sans);
       font-variant-numeric: tabular-nums; }}
main {{ max-width: 980px; margin: 0 auto; padding: 4rem 2rem 6rem; }}
.olho {{ font-size: .7rem; font-weight: 600; letter-spacing: .18em; text-transform: uppercase; color: var(--terra); }}
h1 {{ font: 500 3.2rem/1.04 var(--serif); letter-spacing: -.025em; margin: .9rem 0 1rem; }}
h1 em, h2 em {{ font-style: italic; color: var(--terra); }}
h2 {{ font: 500 1.75rem/1.2 var(--serif); letter-spacing: -.01em; margin: 0 0 .4rem; }}
h3 {{ font: 500 1.35rem/1.2 var(--serif); margin: .4rem 0 .9rem; }}
h3 span {{ font: 400 .8rem var(--sans); color: var(--tinta-45); margin-left: .4rem; }}
p {{ margin: 0 0 .9rem; }}
.lead {{ font-size: 1.08rem; color: var(--tinta-70); max-width: 54ch; }}
.ficha {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-top: 2.2rem; padding-top: 1rem;
         border-top: 1px solid var(--linha); font-size: .8rem; color: var(--tinta-70); }}
.ficha b {{ display: block; color: var(--tinta); font-weight: 500; font-size: .9rem; }}
section {{ margin-top: 4.5rem; }}
.cab {{ display: grid; grid-template-columns: 3rem 1fr; border-top: 1px solid var(--linha); padding-top: 1.1rem;
       margin-bottom: 1.6rem; }}
.cab .n {{ font: italic 1.05rem var(--serif); color: var(--terra); padding-top: .35rem; }}
.cab p {{ color: var(--tinta-70); font-size: .9rem; margin: 0; max-width: 62ch; }}
.cifras {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1.5px solid var(--tinta);
          border-bottom: 1px solid var(--linha); margin-bottom: 1.8rem; }}
.cifras div {{ padding: 1rem 1rem 1.1rem 0; }} .cifras div + div {{ padding-left: 1rem; border-left: 1px solid var(--linha); }}
.cifras small {{ display: block; font-size: .7rem; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--tinta-70); }}
.cifras b {{ font: 500 1.9rem/1.2 var(--serif); }}
ul.conclusoes {{ list-style: none; padding: 0; margin: 0; }}
ul.conclusoes li {{ padding: .8rem 0 .8rem 1.4rem; border-bottom: 1px solid var(--linha); position: relative; }}
ul.conclusoes li::before {{ content: ""; position: absolute; left: 0; top: 1.45rem; width: .55rem; height: 1.5px; background: var(--terra); }}
.passos {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.6rem; }}
.passo {{ border-top: 1.5px solid var(--tinta); padding-top: 1rem; }}
.passo .num {{ font: italic 2.2rem/1 var(--serif); color: var(--terra); }}
.passo h4 {{ font: 500 1.1rem/1.3 var(--serif); margin: .6rem 0 .5rem; }}
.passo p {{ font-size: .88rem; color: var(--tinta-70); }}
.eq {{ font: 1.02rem/1.5 var(--serif); background: var(--papel-claro); border-left: 2px solid var(--terra);
      padding: .6rem .9rem; margin: .8rem 0; }}
.eq small {{ display: block; font: .75rem var(--sans); color: var(--tinta-45); margin-top: .25rem; }}
.conceito {{ font-size: .72rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--tinta-45); }}
table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
th {{ text-align: left; font-size: .68rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
     color: var(--tinta-70); border-bottom: 1.5px solid var(--tinta); padding: .55rem .6rem .55rem 0; }}
td {{ border-bottom: 1px solid var(--linha); padding: .55rem .6rem .55rem 0; }}
th.n, td.n {{ text-align: right; }}
td.fii {{ font-weight: 600; }} td.forte {{ font-weight: 600; }}
td i {{ display: inline-block; width: .5rem; height: .5rem; border-radius: 50%; margin-right: .45rem; }}
td.leitura {{ color: var(--tinta-70); font-size: .82rem; padding-left: 1rem; }}
.pos {{ color: var(--tinta); font-weight: 600; }} .neg {{ color: var(--terra); font-weight: 600; }}
.grafico {{ margin-top: 2rem; }}
.destaques {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 1.6rem; }}
.destaque {{ border-top: 1.5px solid var(--tinta); padding-top: 1rem; }}
.destaque dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: .6rem 1rem; margin: 0 0 1rem; }}
.destaque dt {{ font-size: .7rem; color: var(--tinta-45); text-transform: uppercase; letter-spacing: .06em; }}
.destaque dd {{ margin: 0; font: 500 1.15rem var(--serif); }}
.destaque p {{ font-size: .88rem; }}
.destaque .riscos {{ color: var(--tinta-70); font-size: .8rem; border-left: 2px solid var(--linha); padding-left: .8rem; }}
.metodo {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; font-size: .86rem; color: var(--tinta-70); }}
.metodo ul {{ padding-left: 1.1rem; margin: 0; }} .metodo li {{ margin-bottom: .4rem; }}
footer {{ margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--linha); font-size: .78rem; color: var(--tinta-45); }}
@media (max-width: 760px) {{ .passos, .metodo, .ficha, .cifras {{ grid-template-columns: 1fr 1fr; }} h1 {{ font-size: 2.3rem; }} }}
@media print {{ body {{ background: white; }} main {{ padding: 0; }} section {{ break-inside: avoid; }} }}
</style></head><body><main>

<div class="olho">Administração Financeira · CAD 167 · Trabalho 1</div>
<h1>Preço teto de<br><em>fundos imobiliários</em></h1>
<p class="lead">Quanto vale a pena pagar por cada FII para que ele renda mais do que um título público atrelado
à inflação, levando em conta o risco de cada fundo.</p>
<div class="ficha">
  <div>Dupla<b>{_e(autores) or "—"}</b></div>
  <div>Data<b>{agora:%d/%m/%Y, %H:%M}</b></div>
  <div>Fundos analisados<b>{n} · {_e(universo)}</b></div>
  <div>Cotações<b>{hora_cotacao:%d/%m %H:%M} · Yahoo</b></div>
</div>

<section>
  <div class="cab"><span class="n">01</span><div><h2>Resumo</h2><p>O que a análise mostra hoje.</p></div></div>
  <div class="cifras">
    <div><small>Fundos analisados</small><b>{n}</b></div>
    <div><small>Abaixo do teto</small><b>{abaixo}</b></div>
    <div><small>Margem mediana</small><b class="{'pos' if t['margem'].median() >= 0 else 'neg'}">{pct(t['margem'].median())}</b></div>
    <div><small>Ganho real exigido</small><b>{pct(eq)}</b></div>
  </div>
  <ul class="conclusoes">{''.join(f'<li>{f}</li>' for f in _conclusoes(t, taxas, ipca))}</ul>
</section>

<section>
  <div class="cab"><span class="n">02</span><div><h2>O raciocínio em <em>três passos</em></h2>
  <p>O preço teto aplica dois temas da disciplina: o valor do dinheiro no tempo (passos 1 e 3) e a relação
  entre risco e retorno (passo 2).</p></div></div>
  <div class="passos">
    <div class="passo"><div class="num">1</div><div class="conceito">Custo de oportunidade</div>
      <h4>Quanto rende a alternativa segura?</h4>
      <p>Comparamos o fundo com um título do Tesouro que paga inflação mais uma taxa fixa. Como o título paga IR e o
      dividendo do FII é isento, usamos a taxa líquida; e, para comparar ganhos reais, tiramos a inflação
      (equação de Fisher).</p>
      <div class="eq">(1 + {pct(ipca)}) × (1 + {pct(p['ipca_mais'])}) − 1 = {pct(taxas['bruta'])}
        <small>bruto · após {pct(p['ir'], 0)} de IR: {pct(taxas['liquida'])} · real: {pct(eq)}</small></div>
    </div>
    <div class="passo"><div class="num">2</div><div class="conceito">Risco e retorno</div>
      <h4>Quanto a mais o risco exige?</h4>
      <p>Um FII é mais arriscado que o Tesouro, então exigimos um prêmio: mais alto para fundos pequenos, pouco
      líquidos, com vacância ou dividendos instáveis. Fundos de papel somam também a inflação, porque parte do
      dividendo deles é só correção monetária.</p>
      <div class="eq">{pct(eq)} + prêmio + ajuste IPCA = taxa exigida
        <small>prêmio {p['modo_premio'].lower()} · ajuste {p['modo_ipca'].lower()}</small></div>
    </div>
    <div class="passo"><div class="num">3</div><div class="conceito">Valor presente de uma perpetuidade</div>
      <h4>Quanto vale essa renda hoje?</h4>
      <p>Um FII paga dividendos indefinidamente. O valor presente de uma renda perpétua é o pagamento dividido pela
      taxa: esse é o preço máximo que entrega a taxa exigida. Exemplo com {_e(ex['fii'])}:</p>
      <div class="eq">{brl(ex['div_12m'])} ÷ {pct(ex['taxa_exigida'])} = {brl(ex['teto'])}
        <small>preço atual {brl(ex['preco'])} · margem {pct(ex['margem'])}</small></div>
    </div>
  </div>
</section>

<section>
  <div class="cab"><span class="n">03</span><div><h2>Os fundos</h2>
  <p>Ordenados da maior para a menor margem de segurança (preço teto ÷ preço − 1).</p></div></div>
  <table><thead><tr><th>Fundo</th><th>Tipo</th><th class="n">Preço</th><th class="n">Dividendo 12m</th>
  <th class="n">Taxa exigida</th><th class="n">Preço teto</th><th class="n">Margem</th><th style="padding-left:1rem">Leitura</th></tr></thead>
  <tbody>{linhas}</tbody></table>
  <div class="grafico">{_grafico_preco_teto(t)}</div>
</section>

<section>
  <div class="cab"><span class="n">04</span><div><h2>Destaques</h2>
  <p>Três fundos que ajudam a entender o resultado.</p></div></div>
  <div class="destaques">{''.join(destaques)}</div>
</section>

<section>
  <div class="cab"><span class="n">05</span><div><h2>Método e fontes</h2></div></div>
  <div class="metodo">
    <ul>
      <li>Dividendo 12m: soma dos pagamentos com data-ex nos últimos 12 meses.</li>
      <li>Tipo do fundo (papel, tijolo, híbrido, FoF): composição dos ativos informada mensalmente à CVM.</li>
      <li>Prêmio automático: base de {pct(p['premio_base'])} mais pontos por fator de risco
          (liquidez, porte, imóveis, vacância, volatilidade, estabilidade e tendência dos dividendos, yield frente aos pares),
          com peso {_br(f"{p['peso']:.2f}")}.</li>
    </ul>
    <ul>
      <li>Cotações e dividendos: Yahoo Finance (cerca de 15 minutos de atraso).</li>
      <li>Indicadores dos fundos: Fundamentus. Composição e cadastro: CVM, Informe Mensal de FII.</li>
      <li>IPCA esperado: Banco Central (Focus). Taxas do Tesouro IPCA+: Tesouro Transparente.</li>
    </ul>
  </div>
</section>

<footer>Relatório gerado automaticamente pelo site Teto em {agora:%d/%m/%Y às %H:%M}. Ferramenta educacional;
não é recomendação de investimento.</footer>
</main></body></html>"""


def gerar_csv(t):
    """Tabela completa dos fundos do relatório, no padrão do Excel brasileiro."""
    colunas = {"fii": "FII", "tipo": "Tipo", "segmento": "Segmento", "preco": "Preço", "div_12m": "Dividendo 12m",
               "dy_atual": "Yield 12m", "pvp_atual": "P/VP", "premio": "Prêmio", "ajuste_ipca": "Ajuste IPCA",
               "taxa_exigida": "Taxa exigida", "teto": "Preço teto", "margem": "Margem", "riscos": "Riscos do prêmio"}
    return (t[list(colunas)].rename(columns=colunas)
            .to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"))
