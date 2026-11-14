#!/usr/bin/env python3
"""Wrapper temporário de compatibilidade para `python better_docimage.py`.

A implementação vive no pacote `better_docimage`; este arquivo permanece até o
fim da Fase 3 e pode ser removido depois que `python -m better_docimage` for o
único ponto de entrada documentado.
"""
from __future__ import annotations

from better_docimage.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
