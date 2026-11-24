"""Lectura segura del XML de dominio de libvirt (D1, 0.9) y su traslado al formulario.

El paquete es puro: solo interpreta bytes que el usuario eligió y nunca ejecuta nada, abre
rutas leídas del XML ni usa la red (RF-D1.13). El ``__init__`` queda vacío a propósito para no
crear importaciones circulares.
"""
