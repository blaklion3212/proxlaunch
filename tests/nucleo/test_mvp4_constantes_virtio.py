"""MVP 4: constantes de virtio-win (LAB-M4-07, DT-O10)."""

import re

from proxlaunch.nucleo.origen import constantes


def test_la_url_de_virtio_win_no_esta_vacia_y_es_https_versionada():
    url = constantes.URL_VIRTIO_WIN
    assert url.startswith("https://")
    assert "stable" not in url  # la «stable» cambia de contenido con cada versión
    assert re.search(r"/virtio-win-\d+\.\d+\.\d+(-\d+)?/", url)
    assert len(url) <= constantes.MAX_LONG_URL


def test_el_nombre_del_archivo_cumple_la_deteccion_del_catalogo():
    nombre = constantes.URL_VIRTIO_WIN.rsplit("/", 1)[1]
    assert nombre.startswith(constantes.PREFIJO_VIRTIO_WIN) and nombre.endswith(".iso")


def test_el_sha256_de_virtio_win_son_64_hexadecimales_en_minuscula():
    assert re.fullmatch(r"[0-9a-f]{64}", constantes.SHA256_VIRTIO_WIN)
