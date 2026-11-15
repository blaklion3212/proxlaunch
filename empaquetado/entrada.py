"""Punto de entrada del ejecutable congelado (PyInstaller): equivale a ``python -m proxlaunch``."""

from proxlaunch.interfaz.app import main

if __name__ == "__main__":
    raise SystemExit(main())
