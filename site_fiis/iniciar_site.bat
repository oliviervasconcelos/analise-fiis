@echo off
REM Abre o site Teto (preco teto de FIIs) no navegador: http://localhost:8501
REM Roda a partir da raiz do projeto, onde fica a pasta .streamlit (tema e configuracoes)
cd /d "%~dp0.."
python -m pip install -q -r site_fiis\requirements.txt
python -m streamlit run site_fiis\app.py
pause
