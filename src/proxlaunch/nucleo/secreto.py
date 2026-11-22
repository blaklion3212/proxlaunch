"""Valor secreto en memoria (DT-B1, RF-B0.8): la contraseña de cloud-init.

Un ``Secreto`` nunca se imprime, se copia por valor, se serializa ni se compara por contenido:
``repr``, ``str`` y ``format`` dan la máscara; ``copy`` y ``deepcopy`` devuelven la MISMA
instancia (un único ``olvidar()`` vale para todas las copias del plan, el libro y la fila);
``pickle`` falla con ``TypeError`` y JSON tampoco lo admite. El valor en claro solo sale por
``revelar()``, que únicamente llama ``ClienteProxmox.configurar_contrasena``.

Al crearse se registra con ``registro.registrar_secreto`` para que cualquier eco (un error del
servidor que repita el cuerpo) salga enmascarado en el log.
"""

from __future__ import annotations

from typing import Final, NoReturn

from proxlaunch.nucleo.registro import olvidar_secreto, registrar_secreto

MASCARA: Final[str] = "••••••"
LONGITUD_MINIMA_REGISTRO: Final[int] = 8


class Secreto:
    """Valor secreto en memoria. Ver el módulo para el contrato completo."""

    __slots__ = ("_registrado", "_valor")

    def __init__(self, valor: str) -> None:
        self._valor = valor if isinstance(valor, str) else ""
        # Solo se registran valores aceptables (>= 8 caracteres): uno corto enmascararía
        # fragmentos legítimos del log y la validación ya no lo admite.
        self._registrado = len(self._valor) >= LONGITUD_MINIMA_REGISTRO
        if self._registrado:
            registrar_secreto(self._valor, cloudinit=True)

    def revelar(self) -> str:
        """Valor en claro (``""`` si ya se olvidó). Solo para ``configurar_contrasena``."""
        return self._valor

    def olvidar(self) -> None:
        """Vacía el valor y lo quita de los secretos del registro (mejor esfuerzo)."""
        valor = self._valor
        self._valor = ""
        if self._registrado:
            self._registrado = False
            olvidar_secreto(valor, cloudinit=True)

    @property
    def definido(self) -> bool:
        return bool(self._valor)

    def __bool__(self) -> bool:
        return self.definido

    def __repr__(self) -> str:
        return f"Secreto({MASCARA})"

    def __str__(self) -> str:
        return MASCARA

    def __format__(self, spec: str) -> str:
        return MASCARA

    def __copy__(self) -> Secreto:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Secreto:
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("un Secreto no se puede serializar")

    # ``__eq__`` y ``__hash__`` son los de ``object`` (identidad): nunca por contenido.
