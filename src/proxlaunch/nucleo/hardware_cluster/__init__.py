"""Hardware del clúster (D3, 0.9): mapeos PCI/USB y modelos de CPU personalizados.

El ``__init__`` queda vacío a propósito: ``modelos.vm`` y ``modelos.catalogo`` importan
``hardware_cluster.modelos`` y reexportar aquí crearía importaciones circulares.
"""
