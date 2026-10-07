# Teto: preço teto e risco de fundos imobiliários

**UFMG · FACE · CAD 167 Administração Financeira · Trabalho 1**
Dupla: Olivier Menezes Vasconcelos e Lucas Oliveira Frade Ribeiro Cordeiro

Aplicação web que calcula, para cada fundo imobiliário (FII) da B3, o **preço teto**: o maior preço que ainda faz o fundo render mais do que um título do Tesouro atrelado à inflação, somado a um prêmio pelo risco do fundo.

## Temas da disciplina

| Tema | Onde aparece |
|---|---|
| **Valor do dinheiro no tempo** | Custo de oportunidade (Tesouro IPCA+ como taxa de desconto), composição de taxas e equação de Fisher (taxa nominal × real), taxa bruta × líquida de IR e **valor presente de uma perpetuidade**: preço teto = dividendo ÷ taxa exigida. |
| **Risco e retorno** | Prêmio de risco somado à taxa exigida, calculado a partir de fatores de risco de cada fundo. Volatilidade, Beta, índice de Sharpe, maior queda (drawdown), VaR e correlação entre fundos. |

As fórmulas estão comentadas em `site_fiis/calculos.py` e explicadas na página **Método** do site.

## Como executar

Requisitos: Python 3.9 ou mais recente e conexão com a internet.

**Windows:** dê dois cliques em `site_fiis/iniciar_site.bat`. Ele instala as bibliotecas e abre o site no navegador.

**Qualquer sistema:**
Na pasta raiz do projeto (onde está este README):
```bash
pip install -r site_fiis/requirements.txt
streamlit run site_fiis/app.py
```

O site abre em http://localhost:8501. A primeira carga leva cerca de 30 segundos, porque baixa as cotações de cerca de 400 fundos.

## Roteiro sugerido

1. **Mercado**: a tabela de preço teto dos fundos. Selecione uma linha para abrir o fundo.
2. **Fundo**: a conta do preço teto passo a passo, o tipo do fundo, de que é feito o prêmio de risco, o histórico e as medidas de risco e retorno.
3. **Relatório**: preencha a dupla, clique em **Gerar relatório**. O relatório (HTML) e uma planilha (CSV) são salvos em `site_fiis/relatorios/`.
4. No painel lateral, mude o IPCA ou a taxa IPCA+ e veja os preços teto mudarem.

## Captura de dados

| Dado | Fonte |
|---|---|
| Lista de FIIs, P/VP, liquidez, vacância | Fundamentus |
| Cotações e dividendos (cerca de 15 min de atraso) | Yahoo Finance |
| Composição dos ativos (papel, tijolo, cotas de FIIs), cotistas, patrimônio | CVM, Informe Mensal de FII |
| Expectativa de IPCA (Focus), CDI, Selic | Banco Central |
| Taxas do Tesouro IPCA+ | Tesouro Transparente |

Cada captura bem-sucedida guarda uma cópia em `site_fiis/dados_salvos/`. Se uma fonte estiver fora do ar, o site usa a última cópia e mostra um aviso.

## Arquivos

```
site_fiis/
  app.py              páginas do site e montagem da tabela principal
  calculos.py         fórmulas: preço teto, tipo do fundo, prêmio de risco, risco e retorno
  dados.py            captura de dados e cópias locais (plano B)
  relatorio.py        geração do relatório HTML e da planilha CSV
  estilo.py           visual (cores, tipografia, gráficos)
  config_fiis.json    premissas e lista de fundos acompanhados
  dados_salvos/       cópias locais das fontes de dados
  relatorios/         relatórios gerados pelo site (criada no primeiro relatório)
```

---
Ferramenta educacional; não é recomendação de investimento.
