"""Camada de API REST (FastAPI) da v2.0 do FinData Pipeline.

As rotas apenas traduzem HTTP <-> servico; a logica de negocio (coleta,
validacao, persistencia) continua no pipeline existente e e reutilizada
pela camada de servicos. Nenhuma regra de negocio e reimplementada aqui.
"""
