"""Compara dos instantáneas de `catalogo.py` sección por sección y lista las diferencias.

    python comparar-catalogos.py local.json supabase.json
Sale con 0 si no hay diferencias, 1 si las hay (el resultado se triagea a mano en F3-PAR).
"""

import json
import sys
from pathlib import Path


def main(a: str, b: str) -> int:
    x, y = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a, b))
    hay = False
    for seccion in sorted(set(x) | set(y)):
        va, vb = x.get(seccion), y.get(seccion)
        if va == vb:
            print(f"IGUAL      {seccion}")
            continue
        hay = True
        if isinstance(va, list) and isinstance(vb, list):
            sa, sb = {tuple(f) for f in va}, {tuple(f) for f in vb}
            print(
                f"DIFERENTE  {seccion}: solo en {Path(a).stem}={len(sa - sb)}, solo en {Path(b).stem}={len(sb - sa)}"
            )
            for f in sorted(sa - sb)[:25]:
                print(f"   < {' | '.join(f)[:220]}")
            for f in sorted(sb - sa)[:25]:
                print(f"   > {' | '.join(f)[:220]}")
        else:
            print(f"DIFERENTE  {seccion}: {va!r} / {vb!r}")
    return int(hay)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
