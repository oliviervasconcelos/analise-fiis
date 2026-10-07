@echo off
REM Abre o site de Preco Teto de FIIs no navegador (http://localhost:8501)
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python -m streamlit run app.py
pause
