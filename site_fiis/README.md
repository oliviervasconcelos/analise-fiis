# Teto: site de preço teto de FIIs

## Como abrir
Dê dois cliques em `iniciar_site.bat`, ou rode na **pasta raiz do projeto** (um nível acima desta), onde fica a pasta `.streamlit` com o tema:
```bash
pip install -r site_fiis/requirements.txt
streamlit run site_fiis/app.py
```
O site abre em http://localhost:8501. A primeira carga leva uns 30 segundos, porque baixa as cotações de cerca de 400 FIIs.

## Páginas
- **Mercado**: todos os FIIs da B3 com preço, dividendo 12m, preço teto e margem de segurança. Dá para buscar, filtrar por tipo, segmento, liquidez, P/VP, DY e margem, e alternar entre a minha lista e todos os FIIs. Selecione uma linha para abrir o fundo.
- **Fundo**: a conta do preço teto, o tipo do fundo, a composição do prêmio de risco, a cotação comparada com o preço teto histórico, os dividendos mensais, a sensibilidade ao prêmio, risco e retorno (Sharpe, Beta, maior queda) e links para Fundamentus, Status Invest, Funds Explorer e Investidor10.
- **Comparar**: até 10 fundos lado a lado.
- **Panorama**: DY × P/VP, resumos por tipo e por segmento, maiores e menores margens.
- **Relatório**: gera um relatório HTML (resumo, raciocínio em 3 passos, tabela, destaques) e uma planilha CSV, salvos em `relatorios/`.
- **Método**: fórmulas, regras e fontes de dados.

## Prêmio e ajuste de IPCA automáticos
- **Tipo do fundo**: a classificação usa a composição dos ativos que cada FII informa todo mês à CVM.
  - Papel: CRI/LCI ≥ 67% do que o fundo investe.
  - Tijolo: imóveis ≥ 67%.
  - FoF: cotas de outros FIIs ≥ 50%.
  - Híbrido: os demais casos.
- **Ajuste de IPCA** = IPCA × fração do tipo. O padrão é Papel 100%, Híbrido 50%, FoF 50% e Tijolo 0%; as frações mudam no painel lateral.
- **Prêmio automático** = 1% de base mais pontos por fator de risco: baixa liquidez, fundo pequeno, poucos imóveis, vacância, volatilidade da cota, dividendos instáveis, dividendos em queda e yield acima dos pares. As regras estão na página Método.
- No painel lateral dá para escolher entre **Automático** e **Minha planilha** (usa os seus valores quando definidos), separadamente para o prêmio e para o ajuste de IPCA.

## Premissas
No painel lateral ficam IPCA, IPCA+, IR, a base e o peso do prêmio. Em "Referências de mercado hoje", um botão preenche o IPCA com o Focus e o IPCA+ com o Tesouro IPCA+.
Os parâmetros de cada fundo (tipo, prêmio, ajuste de IPCA, dividendo manual) ficam em "Minha lista e parâmetros por fundo", na página Mercado.
O botão **Salvar** grava tudo em `config_fiis.json`.

## Fontes e plano B
Fundamentus (lista e indicadores), Yahoo Finance (cotações com cerca de 15 min de atraso e dividendos), CVM (Informe Mensal de FII), Banco Central (Focus, IPCA, Selic, CDI) e Tesouro Transparente (taxas do IPCA+).
Cada captura bem-sucedida guarda uma cópia em `dados_salvos/`. Se uma fonte estiver fora do ar, o site usa a última cópia e avisa.

Ao editar o código, feche e abra o site de novo: ele não recarrega sozinho.
