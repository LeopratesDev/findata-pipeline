"""Dashboard Streamlit (v2.0) que consome a API REST do FinData Pipeline.

A logica de consulta (client.py) e de formatacao (format.py) fica em funcoes
puras e testaveis; app.py apenas orquestra a UI. O dashboard NUNCA consulta o
SQLite direto nem a API publica do BCB - fala somente com a API da aplicacao.
"""
