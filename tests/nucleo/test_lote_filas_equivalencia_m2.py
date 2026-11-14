"""No regresión del lote homogéneo (CA-C08.12, CA-P12.1; arquitectura §13 «No regresión M2» y
§14.2): ``construir_plan``, ``validar_definicion``, ``repartir``, ``capacidad_maxima`` y
``uso_de_nodos`` generalizados a filas dan EXACTAMENTE los mismos resultados que el código del
MVP 2 (commit ``6cce74b``, cierre aprobado) sobre cientos de lotes homogéneos generados con
semilla fija (3 nodos con storages y bridges distintos, thin y compartidos, destinos y
algoritmos).

La prueba es diferencial: extrae el árbol de fuentes del commit del MVP 2 con ``git archive``,
ejecuta el mismo guion en un subproceso contra cada árbol y compara las salidas. Se salta si
``git`` o el commit no están disponibles (p. ej. un clon superficial).
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

import pytest

import proxlaunch

RAIZ_REPO = Path(proxlaunch.__file__).resolve().parents[2]
COMMIT_M2 = "6cce74b"
CASOS = 600

GUION = textwrap.dedent(
    """
    import dataclasses, json, random, sys
    from enum import Enum

    import proxlaunch
    from proxlaunch.nucleo.lote.modelos import (
        Algoritmo, ClavePresupuesto, DefinicionLote, Destino, ModoDestino, PatronNombres,
        PoliticaThin,
    )
    from proxlaunch.nucleo.lote.planificador import construir_plan, validar_definicion
    from proxlaunch.nucleo.lote.presupuesto import capacidad_maxima, uso_de_nodos
    from proxlaunch.nucleo.lote.reparto import repartir
    from proxlaunch.nucleo.modelos.inventario import (
        Bridge, Inventario, Nodo, Storage, Topologia, Version, VMRemota,
    )
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed

    GIB = 1024 ** 3
    NUEVOS_M4 = {"tipo_so": None, "tpm": False, "agente_qemu": False, "detalle_origen": None}

    def norm(o):
        if isinstance(o, Enum):
            return o.value
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            d = {f.name: norm(getattr(o, f.name)) for f in dataclasses.fields(o)}
            # Campos nuevos de ConfiguracionVM en el MVP 4 (RF-O01/RF-O13): en M2 no existían.
            # Solo se descartan si valen su valor por defecto; si un lote sin origen los dejara
            # distintos del defecto, la diferencia SÍ se detecta (RF-O03, CA-O03.1).
            for campo, defecto in NUEVOS_M4.items():
                if campo in d and d[campo] == defecto:
                    del d[campo]
            return d
        if isinstance(o, dict):
            def clave(k):
                return f"{k.ambito}|{k.storage}" if isinstance(k, ClavePresupuesto) else str(k)
            return {clave(k): norm(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
        if isinstance(o, (list, tuple, set, frozenset)):
            return [norm(x) for x in o]
        return o

    def plan_norm(p):
        d = norm(p)
        d.pop("definicion", None)
        d.pop("filas_excedentes", None)  # campo nuevo del MVP 3 (siempre vacío en homogéneo)
        d.pop("catalogo", None)  # campo nuevo del MVP 4 (None sin origen, RF-O03/CA-O03.1)
        return d

    def redes_posibles(rng):
        if rng.random() > 0.1:
            return [InterfazRed(rng.choice(["vmbr0", "vmbr0", "vmbr0", "vmbr1", "vmbr9"]))]
        return []

    def gen(rng):
        k = rng.randint(1, 5)
        nodos = tuple(
            Nodo(f"pve{i+1}", rng.random() > 0.15, rng.choice([None, 1024 * rng.randint(1, 96)]),
                 rng.choice([None, rng.randint(2, 32)]))
            for i in range(k)
        )
        catalogo = [("datos", "dir", False), ("lv", "lvmthin", False), ("nfs", "nfs", True),
                    ("zfs", "zfspool", False), ("bloque", "lvm", False)]
        storages = {}
        for n in nodos:
            lst = []
            for sid, tipo, comp in catalogo:
                if rng.random() < 0.85:
                    libre = rng.randint(5, 600)
                    contenido = frozenset({"images"}) if rng.random() > 0.1 else frozenset({"iso"})
                    activo = rng.random() > 0.1
                    total, libre_b = libre * 2 * GIB, libre * GIB
                    lst.append(Storage(sid, tipo, contenido, comp, activo, total, libre_b))
            storages[n.nombre] = tuple(lst)
        bridges = {
            n.nombre: tuple(
                b for b in (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "OVSBridge", True))
                if rng.random() < 0.8
            )
            for n in nodos
        }
        topologia = Topologia(k > 1, "lab" if k > 1 else None, nodos)
        inv = Inventario(Version("9.2.1", 9, 2, 1), topologia, 100, storages, bridges, {})
        nombres_storage = ["datos", "datos", "datos", "lv", "nfs", "zfs", "bloque", "nada"]
        discos = [
            Disco(rng.choice(nombres_storage), rng.choice([1, 5, 10, 32, 64, 120, 300]))
            for _ in range(rng.randint(0, 3))
        ]
        cfg = ConfiguracionVM(
            vmid=0, nombre=rng.choice(["plantilla", "pl"]), nodo="",
            cores=rng.choice([1, 2, 4, 4, 2, 1, 8, 200]),
            memoria_mib=rng.choice([512, 2048, 8192, 32768, 100000]), discos=discos,
            con_disco=bool(discos) or rng.random() < 0.3,
            redes=redes_posibles(rng),
        )
        cantidad = rng.choice([0, 1, 1, 2, 3, 5, 8, 12, 25])
        prefijo = rng.choice(["web", "web", "srv", "", "a b"])
        patron = PatronNombres(prefijo, "-", rng.randint(0, 3), rng.randint(0, 3))
        modo = rng.choice(list(ModoDestino))
        seleccion = tuple(rng.sample(["pve1", "pve2", "pve3", "pve4", "pveX"], rng.randint(0, 3)))
        destino = Destino(modo, seleccion, rng.choice(list(Algoritmo)))
        d = DefinicionLote(cfg, cantidad, patron, destino, rng.choice([None, 150]),
                           rng.random() > 0.3, rng.choice(list(PoliticaThin)))
        visibles = None if rng.random() < 0.4 else [
            VMRemota(900 + i, rng.choice(["web-01", "pl", "srv-02", "x"]), "pve1", "qemu")
            for i in range(rng.randint(0, 3))
        ]
        saltados = sorted(rng.sample(range(100, 140), rng.randint(0, 3)))
        version = rng.choice([(9, 2), (8, 0), (9, 2), (9, 9)])
        return inv, d, visibles, saltados, version

    def intentar(f):
        try:
            return norm(f())
        except Exception as e:  # noqa: BLE001
            return {"excepcion": type(e).__name__}

    rng = random.Random(424242)
    salida = []
    for i in range(int(sys.argv[1])):
        inv, d, visibles, saltados, version = gen(rng)
        n = d.cantidad
        vmids = list(range(100, 100 + max(n, 0)))
        caso = {"i": i, "n": n}
        caso["validar"] = intentar(lambda: validar_definicion(d, inv, version))
        caso["plan"] = intentar(lambda: plan_norm(construir_plan(
            d, inv, vmids, saltados, id_lote="abcd1234", ahora=12.5,
            version_validacion=version, vms_visibles=visibles)))
        caso["repartir"] = intentar(lambda: repartir(d, inv, max(n, 0)))
        caso["capacidad"] = intentar(lambda: capacidad_maxima(d, inv))
        r = intentar(lambda: repartir(d, inv, max(n, 0)))
        if isinstance(r, list) and r and isinstance(r[0], list):
            caso["uso"] = intentar(lambda: uso_de_nodos(d.plantilla, [x for x in r[0]], inv))
        salida.append(caso)
    print(json.dumps({"origen": proxlaunch.__file__, "casos": salida}, sort_keys=True))
    """
)


def _ejecutar(raiz_src: Path) -> dict:
    entorno = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    entorno["PYTHONPATH"] = str(raiz_src)
    entorno["PYTHONHASHSEED"] = "0"
    r = subprocess.run(
        [sys.executable, "-c", GUION, str(CASOS)],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert r.returncode == 0, r.stderr[-3000:]
    datos = json.loads(r.stdout)
    assert Path(datos["origen"]).resolve().is_relative_to(raiz_src.resolve()), datos["origen"]
    return datos


@pytest.fixture(scope="module")
def arbol_m2(tmp_path_factory):
    """Fuentes del MVP 2 extraídas del historial de git (se salta si no se puede)."""
    if shutil.which("git") is None:
        pytest.skip("git no está disponible")
    destino = tmp_path_factory.mktemp("arbol_m2")
    try:
        proceso = subprocess.run(
            ["git", "-C", str(RAIZ_REPO), "archive", COMMIT_M2, "src"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        pytest.skip(f"el commit {COMMIT_M2} del MVP 2 no está en el historial (¿clon superficial?)")
    paquete = destino / "src.tar"
    paquete.write_bytes(proceso.stdout)
    with tarfile.open(paquete) as tar:
        tar.extractall(destino, filter="data")
    assert (destino / "src" / "proxlaunch" / "nucleo" / "lote" / "planificador.py").exists()
    return destino / "src"


def test_el_arbol_del_mvp_2_no_tiene_lotes_por_filas(arbol_m2):
    """Sanidad de la prueba: el árbol extraído es de verdad el anterior a D-22."""
    modelos = (arbol_m2 / "proxlaunch" / "nucleo" / "lote" / "modelos.py").read_text(
        encoding="utf-8"
    )
    assert "FilaLote" not in modelos and "filas_excedentes" not in modelos


def test_el_lote_homogeneo_da_los_mismos_resultados_que_el_codigo_del_mvp_2(arbol_m2):
    """CA-C08.12: validación, plan completo, reparto, capacidad y uso, caso por caso."""
    antes = _ejecutar(arbol_m2)
    despues = _ejecutar(RAIZ_REPO / "src")
    assert len(antes["casos"]) == len(despues["casos"]) == CASOS
    diferencias = []
    for a, d in zip(antes["casos"], despues["casos"], strict=True):
        for clave in a:
            # Con 0 máquinas ``repartir`` ya no evalúa nodos (devuelve vacío): diferencia benigna
            # e inalcanzable desde el plan, que rechaza cantidad < 1 con V-L01 antes de repartir.
            if a["n"] < 1 and clave in {"repartir", "uso"}:
                continue
            if a[clave] != d.get(clave):
                diferencias.append((a["i"], clave))
    assert diferencias == [], (
        f"{len(diferencias)} diferencias; la primera: caso {diferencias[0] if diferencias else None}"  # noqa: E501
    )


def test_la_muestra_cubre_planes_validos_bloqueados_y_las_reglas_principales(arbol_m2):
    """La comparación no es vacía: hay variedad real de resultados."""
    plan = _ejecutar(RAIZ_REPO / "src")["casos"]
    validos = [c for c in plan if c["plan"].get("elementos")]
    bloqueados = [c for c in plan if not c["plan"].get("elementos")]
    assert len(validos) > CASOS * 0.15 and len(bloqueados) > CASOS * 0.1
    reglas = {p["regla"] for c in plan for p in c["plan"].get("problemas", [])}
    assert {"V-L09", "V-L10", "V-L11", "V-L12", "V-L13", "E-L01"} <= reglas
