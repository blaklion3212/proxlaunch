"""Espera de la IP de cada máquina mediante el agente invitado (B3, fase B 0.7).

Este paquete contiene los módulos puros (modelos, selección de IP, clasificación de errores,
calendario de sondeos y validación); ``espera.py`` y ``exportacion.py`` los usan. El ``__init__``
queda vacío a propósito para no crear importaciones circulares con ``lote.modelos``.
"""
