"""Usuario sugerido y UPN (SRS 4.10, S-23). Funcion pura y determinista."""

import re
from collections.abc import Collection

from jml.dominio.errores import DatoInvalido
from jml.dominio.valores import Usuario, ascii_minuscula

MAX_USUARIO = 20


def _primer_token(campo: str, texto: str) -> tuple[str, str]:
    """Devuelve (primer token, resto) ya en ASCII minuscula y solo [a-z0-9]."""
    tokens = [re.sub(r"[^a-z0-9]", "", t) for t in ascii_minuscula(texto).split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        raise DatoInvalido(campo, "no contiene letras ni digitos validos")
    return tokens[0], "".join(tokens[1:2])


def _recortar(base: str, sufijo: str = "") -> str:
    # El sufijo siempre cabe: se recorta la base, nunca el sufijo, y no queda un punto al borde.
    return base[: MAX_USUARIO - len(sufijo)].rstrip(".") + sufijo


def usuario_sugerido(nombres: str, apellidos: str, existentes: Collection[str]) -> Usuario:
    """`nombre.apellido`; si existe, `.inicial` del segundo apellido; luego sufijo numerico."""
    nombre, _ = _primer_token("nombres", nombres)
    apellido, segundo = _primer_token("apellidos", apellidos)
    ocupados = {e.lower() for e in existentes}
    base = f"{nombre}.{apellido}"

    candidatos = [_recortar(base)]
    if segundo:
        candidatos.append(_recortar(base, f".{segundo[0]}"))
    for candidato in candidatos:
        if candidato not in ocupados:
            return Usuario(candidato)
    numero = 2
    while True:
        candidato = _recortar(base, str(numero))
        if candidato not in ocupados:
            return Usuario(candidato)
        numero += 1
