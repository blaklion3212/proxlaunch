"""Configuración inicial (cloud-init) al clonar, de la fase B (0.7): modelos, claves, red, serie,
detección de la unidad, construcción de la petición, validación y disponibilidad.

Todo el paquete es Python puro, sin E/S. El ``__init__`` queda vacío a propósito: ``modelos.vm``
y ``modelos.catalogo`` importan ``cloudinit.modelos`` y reexportar aquí crearía importaciones
circulares con ``validacion``.
"""
