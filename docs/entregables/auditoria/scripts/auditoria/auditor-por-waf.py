"""F6-06 (D-02, D-03): el Auditor verifica la cadena A TRAVÉS DEL WAF, a ritmo humano y a ritmo de guion.

    python auditoria/scripts/auditor-por-waf.py <clave de sesión del Auditor>

Contra el stack LOCAL (https://127.0.0.1 con SNI y Host `app.localhost`). Ritmo humano: abre la
página, verifica la cadena y carga la hoja de estilos, con unos segundos de pausa entre cada
verificación. Ritmo de guion: doce verificaciones seguidas. Sale con 0 si el ritmo humano no recibe
ningún 429 y el de guion sí lo recibe (control positivo: el límite existe y actúa).
"""

import re
import subprocess
import sys
import time

import httpx

HOST = "app.localhost"
BASE = "https://127.0.0.1"
CSRF = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def levantar_baneos() -> None:
    for ip in ("10.20.30.1", "10.20.40.128", "127.0.0.1"):
        subprocess.run(
            ["docker", "compose", "-f", "infra/compose.yaml", "exec", "-T", "bw-scheduler",
             "bwcli", "unban", ip],
            capture_output=True, check=False,
        )  # fmt: skip


def cliente(sesion: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE,
        verify=False,  # noqa: S501 - certificado autofirmado del stack LOCAL de laboratorio
        timeout=20,
        headers={"Host": HOST},
        cookies={"sessionid": sesion, "csrftoken": CSRF},
    )


SNI = {"sni_hostname": HOST}  # el WAF elige el sitio por SNI y por Host


def token_del_formulario(html: str) -> str:
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    assert m, "la página del Auditor debe traer el formulario de verificación"
    return m.group(1)


def verificar(c: httpx.Client) -> list[int]:
    estados = []
    pagina = c.get("/auditoria", extensions=SNI)
    estados.append(pagina.status_code)
    if pagina.status_code != 200:
        return estados
    token = token_del_formulario(pagina.text)
    css = re.search(r'href="(/static/[^"]+\.css)"', pagina.text)
    if css:
        estados.append(c.get(css.group(1), extensions=SNI).status_code)
    r = c.post(
        "/auditoria",
        data={"csrfmiddlewaretoken": token},
        headers={"Referer": f"https://{HOST}/auditoria"},
        extensions=SNI,
    )
    estados.append(r.status_code)
    if r.status_code == 200:
        assert "La cadena es íntegra" in r.text, "la verificación no dice «íntegra»"
    return estados


def main(sesion: str) -> int:
    levantar_baneos()
    print("== ritmo humano: cinco verificaciones, una cada 12 segundos")
    humano: list[int] = []
    with cliente(sesion) as c:
        for i in range(5):
            time.sleep(12)
            estados = verificar(c)
            humano += estados
            print(f"   verificación {i + 1}: {estados}")
    levantar_baneos()
    print("== ritmo de guion: doce verificaciones seguidas, sin pausa")
    guion: list[int] = []
    with cliente(sesion) as c:
        for _ in range(12):
            guion += verificar(c)
    print(f"   códigos: {sorted(set(guion))} · 429: {guion.count(429)} de {len(guion)}")
    levantar_baneos()
    sin_429_humano = 429 not in humano and all(s == 200 for s in humano)
    con_429_guion = 429 in guion
    print(f"RESULTADO humano sin 429 y todo 200: {sin_429_humano} · guion con 429: {con_429_guion}")
    return 0 if sin_429_humano and con_429_guion else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
