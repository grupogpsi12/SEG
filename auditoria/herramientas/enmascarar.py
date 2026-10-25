"""Enmascarado de secretos de la evidencia de la auditoría (plan §9.2, punto 4).

UNA sola función decide qué es secreto: `enmascarar(texto)`. Todo guion de la auditoría pasa por
ella antes de escribir evidencia. Es solo por PATRÓN, a propósito: no lee `secrets/` (la auditoría
no necesita los valores y las reglas del repositorio piden que no se lean). La red de seguridad es
`gitleaks` sobre la carpeta de evidencia antes de empaquetar (`verificar-entrega.py`).

    python auditoria/herramientas/enmascarar.py < entrada.txt > salida.txt
    python auditoria/herramientas/enmascarar.py --probar          # autoprueba con valores falsos
"""

import re
import sys

MARCA = "***enmascarado***"

# (nombre, expresión, reemplazo). Los reemplazos conservan el contexto (la cabecera o el nombre del
# campo) para que la evidencia siga diciendo QUE había un secreto y DÓNDE, sin su valor.
_REGLAS: list[tuple[str, re.Pattern[str], str]] = [
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), MARCA),
    (
        "supabase",
        re.compile(r"\bsb_(?:publishable|secret)_[A-Za-z0-9_-]{8,}"),
        "sb_***enmascarado***",
    ),
    ("age", re.compile(r"\bAGE-SECRET-KEY-[A-Z0-9]{20,}\b"), MARCA),
    ("github", re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}\b"), MARCA),
    ("bearer", re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {MARCA}"),
    (
        "cabecera-secreta",
        re.compile(
            r"(?i)\b(App-Token|Session-Token|X-Api-Key|API_TOKEN|Authorization|Proxy-Authorization"
            r"|X-CSRFToken)(\s*[:=]\s*)(?:(?:user_token|Basic|Token)\s+)?[^\s\"',;]{6,}"
        ),
        rf"\1\2{MARCA}",
    ),
    (
        "cookie",
        re.compile(
            r"(?i)\b(sessionid|csrftoken|csrfmiddlewaretoken|glpi_[0-9a-f]{20,})(\s*[=:]\s*)[^\s;\"',&]{6,}"
        ),
        rf"\1\2{MARCA}",
    ),
    (
        "campo-sensible",
        re.compile(
            r"(?i)\b([A-Za-z_]*(?:password|passwd|contrasena|secret|totp|api[_-]?key|token)[A-Za-z_]*)"
            r"(\"?\s*[:=]\s*\"?)(?!\*\*\*)[^\s\"',;&]{4,}"
        ),
        rf"\1\2{MARCA}",
    ),
    (
        "pem",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        MARCA,
    ),
]


def enmascarar(texto: str) -> str:
    """Devuelve `texto` sin valores secretos. Idempotente: enmascarar dos veces da lo mismo."""
    for _, patron, reemplazo in _REGLAS:
        texto = patron.sub(reemplazo, texto)
    return texto


def _probar() -> int:
    """Cada entrada trae los fragmentos que NO deben sobrevivir al enmascarado (todos falsos).

    Los valores se ARMAN aquí a partir de trozos: el código fuente no contiene ninguna cadena con
    forma de secreto, para que `gitleaks` (que revisa todo el historial en la CI) no los confunda
    con uno real y no haga falta ninguna excepción.
    """

    def j(*trozos: str) -> str:
        return "".join(trozos)

    firma = "firmaFalsa1234567890"
    hexa = "0123456789abcdef"
    casos = {
        "jwt": (
            "token "
            + j("eyJ", "hbGciOiJIUzI1NiJ9", ".", "eyJ", "zdWIiOiJ4eHh4eHh4eCJ9", ".", firma),
            [firma],
        ),
        "supabase": (
            "clave " + j("sb_", "publishable_", "FALSA", hexa, "abcdef"),
            [j("FALSA", hexa)],
        ),
        "bearer": ("Authorization: " + j("Bea", "rer ", "abcdef", hexa), [j("abcdef", hexa)]),
        "app-token": (j("App-", "Token: ", hexa * 2), [hexa + "0123"]),
        "session-token": (
            j("Session-", "Token: ", "QnJYY3d1ZzY3YUdpTGhWenlK"),
            ["QnJYY3d1ZzY3YUdpTGhWenlK"],
        ),
        "cookie": (
            j("Cookie: ", "session", "id=", "abcdef", hexa, "; ", "csrf", "token=", "Z" * 16),
            [j("abcdef", hexa), "Z" * 16],
        ),
        "json": (
            "{" + j('"contra', 'sena": ') + '"clave-super-secreta-123"}',
            ["clave-super-secreta-123"],
        ),
        "formulario": (
            "correo=a@b.co&" + j("pass", "word=", "hunter2hunter2") + "&x=1",
            ["hunter2hunter2"],
        ),
        "age": (j("AGE-", "SECRET-", "KEY-1", "Q" * 58), ["Q" * 20]),
    }
    fallos: list[str] = []
    for nombre, (entrada, prohibidos) in casos.items():
        salida = enmascarar(entrada)
        fallos += [f"{nombre}: sobrevive «{p}» en «{salida}»" for p in prohibidos if p in salida]
        if MARCA.replace("*", "") not in salida.replace("*", ""):
            fallos.append(f"{nombre}: no dejó la marca en «{salida}»")
        if enmascarar(salida) != salida:
            fallos.append(f"{nombre}: no es idempotente")
    normal = "GET /cuentas?nombre=Ana&pagina=2 HTTP/1.1 200 15 sha256:" + "a" * 64
    if enmascarar(normal) != normal:
        fallos.append(f"altera texto normal: {enmascarar(normal)}")
    for f in fallos:
        print("FALLA", f)
    print("autoprueba:", "OK" if not fallos else f"{len(fallos)} fallos")
    return 1 if fallos else 0


if __name__ == "__main__":
    if "--probar" in sys.argv:
        sys.exit(_probar())
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stdout.write(enmascarar(sys.stdin.buffer.read().decode("utf-8", errors="replace")))
