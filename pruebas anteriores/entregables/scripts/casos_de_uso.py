"""Recorrido de casos de uso a traves de BunkerWeb (entregable 5.7).

Corre contra el stack local (https://app.localhost). Cada rol usa una sesion de PRUEBA creada en la
base local (equivalente a force_login): el ingreso con TOTP necesita una cuenta real de Supabase y
se cubre en tests/adaptadores/test_ingreso_web.py y tests/integracion/test_supabase_auth.py.

    python casos_de_uso.py <archivo-de-sesiones> <salida.json>

El archivo de sesiones tiene lineas rol=clave_de_sesion. Las claves no se escriben en la salida.
"""

import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field

import httpx

BASE = "https://app.localhost"
PAUSA = 0.7  # RS-08: 2 peticiones por segundo por IP; sin pausa el WAF responde 429
SOL = re.compile(r"SOL-\d{4}-\d{6}")
CSRF = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
CENTINELA_RET = "CENTINELA-MOTIVO-RET-7f3a"
CENTINELA_EMG = "CENTINELA-DESCRIPCION-EMG-9c1b"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
NO_PDF = b"MZ\x90\x00 ejecutable disfrazado de PDF"


@dataclass
class Paso:
    cu: str
    descripcion: str
    rol: str
    metodo: str
    ruta: str
    esperado: str
    obtenido: str = ""
    resultado: str = ""
    evidencia: str = ""
    requisitos: list[str] = field(default_factory=list)


class Recorrido:
    def __init__(self, sesiones: dict[str, str]) -> None:
        self.clientes: dict[str, httpx.Client] = {}
        for rol, clave in [*sesiones.items(), ("anonimo", "")]:
            c = httpx.Client(base_url=BASE, verify=False, timeout=30, follow_redirects=False)
            if clave:
                c.cookies.set("sessionid", clave, domain="app.localhost")
            self.clientes[rol] = c
        self.pasos: list[Paso] = []

    def _pedir(self, rol: str, metodo: str, ruta: str, **kw: object) -> httpx.Response:
        time.sleep(PAUSA)
        # Django exige Referer del mismo origen en POST por HTTPS (CSRF); un navegador lo envia.
        cabeceras = {"Referer": BASE + "/"}
        r = self.clientes[rol].request(metodo, ruta, headers=cabeceras, **kw)  # type: ignore[arg-type]
        if r.status_code in (403, 404) and "bunkerweb" not in r.text.lower():
            # Los 403/404 esperados cuentan como mal comportamiento (RS-08: 10 en 60 s banean 1 h).
            # Artefacto de la prueba, no del sistema: se levanta el baneo para seguir el recorrido.
            subprocess.run(["docker", "exec", "jml-bw-scheduler-1", "bwcli", "unban", "10.20.40.1"],
                           capture_output=True, check=False)
        return r

    def csrf(self, rol: str, ruta: str) -> str:
        r = self._pedir(rol, "GET", ruta)
        m = CSRF.search(r.text)
        if not m:
            raise RuntimeError(f"sin token CSRF en {ruta} ({r.status_code})")
        return m.group(1)

    def paso(
        self,
        cu: str,
        descripcion: str,
        rol: str,
        metodo: str,
        ruta: str,
        esperado: int | tuple[int, ...],
        requisitos: list[str],
        contiene: str | None = None,
        no_contiene: str | None = None,
        **kw: object,
    ) -> httpx.Response:
        esperados = esperado if isinstance(esperado, tuple) else (esperado,)
        r = self._pedir(rol, metodo, ruta, **kw)
        cuerpo = r.text
        if r.is_redirect and r.headers.get("location"):
            destino = r.headers["location"]
            seguido = self._pedir(rol, "GET", destino)
            cuerpo = cuerpo + seguido.text
            evidencia = f"Location: {destino}"
        else:
            evidencia = ""
        ok = r.status_code in esperados
        if contiene is not None:
            ok = ok and contiene in cuerpo
            evidencia += f" | contiene «{contiene}»: {contiene in cuerpo}"
        if no_contiene is not None:
            ok = ok and no_contiene not in cuerpo
            evidencia += f" | sin «{no_contiene}»: {no_contiene not in cuerpo}"
        msg = re.search(r'class="mensaje[^"]*"[^>]*>([^<]{3,160})<', cuerpo)
        if msg:
            evidencia += f" | mensaje: {msg.group(1).strip()}"
        self.pasos.append(
            Paso(cu, descripcion, rol, metodo, ruta, "/".join(map(str, esperados)),
                 str(r.status_code), "PASA" if ok else "FALLA", evidencia.strip(" |"), requisitos)
        )
        print(f"{'PASA ' if ok else 'FALLA'} {cu} {r.status_code} {metodo} {ruta} [{rol}] {descripcion}")
        return r

    def ultimo_id(self, rol: str) -> str:
        r = self._pedir(rol, "GET", "/solicitudes")
        ids = sorted(set(SOL.findall(r.text)))
        return ids[-1] if ids else ""


def ejecutar(sesiones: dict[str, str]) -> list[Paso]:
    t = Recorrido(sesiones)

    # CU-01 Acceso publico, TLS y proteccion de rutas
    t.paso("CU-01", "Pagina de ingreso por HTTPS", "anonimo", "GET", "/ingreso", 200, ["RF-01", "RS-01"],
           contiene="csrfmiddlewaretoken")
    t.paso("CU-01", "Ruta protegida sin sesion redirige al ingreso", "anonimo", "GET", "/bandeja", 302,
           ["RF-03"])
    t.paso("CU-01", "Formulario de ingreso invalido: error del formulario, sin llamar a Supabase",
           "anonimo", "POST", "/ingreso", 200, ["RF-01", "RS-05"],
           data={"csrfmiddlewaretoken": t.csrf("anonimo", "/ingreso"), "correo": "no-es-correo",
                 "contrasena": "x"})
    t.paso("CU-01", "POST sin token CSRF es rechazado", "anonimo", "POST", "/ingreso", 403, ["RS-04"],
           data={"correo": "a@b.co", "contrasena": "x"})

    # CU-02 Solicitante registra sus vacaciones
    tok = t.csrf("sol", "/solicitudes/nueva/VAC")
    t.paso("CU-02", "Solicitante registra vacaciones con fecha futura", "sol", "POST",
           "/solicitudes/nueva/VAC", 302, ["RF-07", "RF-08"],
           data={"csrfmiddlewaretoken": tok, "fecha_efectiva": "2026-11-09", "fecha_regreso": "2026-11-23"})
    vac = t.ultimo_id("sol")

    # CU-03 Deduplicacion
    tok = t.csrf("sol", "/solicitudes/nueva/VAC")
    t.paso("CU-03", "Segunda VAC abierta del mismo colaborador es rechazada con el id existente", "sol",
           "POST", "/solicitudes/nueva/VAC", (200, 302), ["RF-09", "RD-01"], contiene=vac,
           data={"csrfmiddlewaretoken": tok, "fecha_efectiva": "2026-12-01", "fecha_regreso": "2026-12-10"})

    # CU-04 Jefe registra cambio de departamento de un subordinado
    tok = t.csrf("jefe", "/solicitudes/nueva/CDP")
    t.paso("CU-04", "Jefe registra CDP de su subordinado", "jefe", "POST", "/solicitudes/nueva/CDP", 302,
           ["RF-07", "§4.1"],
           data={"csrfmiddlewaretoken": tok, "colaborador": "col-013", "fecha_efectiva": "2026-11-03",
                 "departamento_nuevo": "Tecnología", "cargo_nuevo": "Analista"})
    cdp = t.ultimo_id("jefe")

    # CU-05 RRHH aprueba y rechaza
    t.paso("CU-05", "Bandeja de RRHH lista las pendientes", "rrhh", "GET", "/bandeja", 200, ["RF-12", "RF-28"],
           contiene=vac)
    tok = t.csrf("rrhh", "/bandeja")
    t.paso("CU-05", "RRHH aprueba la VAC", "rrhh", "POST", f"/solicitudes/{vac}/aprobar", 302, ["RF-12"],
           data={"csrfmiddlewaretoken": tok, "justificacion": ""})
    tok = t.csrf("rrhh", "/bandeja")
    t.paso("CU-05", "RRHH rechaza el CDP con justificacion", "rrhh", "POST", f"/solicitudes/{cdp}/rechazar",
           302, ["RF-12"], data={"csrfmiddlewaretoken": tok, "justificacion": "Falta aval de Finanzas"})
    tok = t.csrf("sol", "/solicitudes")
    t.paso("CU-05", "Solicitante no puede aprobar (control de rol)", "sol", "POST",
           f"/solicitudes/{vac}/aprobar", (302, 403), ["RF-03", "T15"],
           data={"csrfmiddlewaretoken": tok, "justificacion": ""})

    # CU-06 RRHH emite un ingreso con soporte PDF
    tok = t.csrf("rrhh", "/solicitudes/nueva/ING")
    ing = {"csrfmiddlewaretoken": tok, "fecha_efectiva": "2026-11-03", "nombres": "Prueba",
           "apellidos": "Entrega Tres", "documento": "90000077", "vinculacion": "empleado",
           "departamento": "Finanzas", "cargo": "Analista", "sede": "Bogotá", "jefe_id": "col-011",
           "requiere_equipo": "on", "tipo_equipo": "Portátil", "justificacion": "Contratación aprobada"}
    t.paso("CU-06", "Ingreso con archivo no PDF renombrado .pdf es rechazado", "rrhh", "POST",
           "/solicitudes/nueva/ING", 200, ["RF-39", "RS-17", "CA-18", "T17"],
           data=ing, files={"soporte_pdf": ("contrato.pdf", NO_PDF, "application/pdf")})
    ing["csrfmiddlewaretoken"] = t.csrf("rrhh", "/solicitudes/nueva/ING")
    t.paso("CU-06", "RRHH emite el ingreso con soporte PDF valido", "rrhh", "POST",
           "/solicitudes/nueva/ING", 302, ["RF-13", "RF-39"],
           data=ing, files={"soporte_pdf": ("contrato.pdf", PDF, "application/pdf")})

    # CU-07 RRHH emite un retiro con motivo restringido
    tok = t.csrf("rrhh", "/solicitudes/nueva/RET")
    t.paso("CU-07", "RRHH emite RET de un contratista con motivo restringido", "rrhh", "POST",
           "/solicitudes/nueva/RET", 302, ["RF-13", "RD-05"],
           data={"csrfmiddlewaretoken": tok, "documento_del_colaborador": "10000014",
                 "subtipo_elegido": "fin_de_contrato", "fecha_efectiva": "2026-10-27",
                 "motivo": CENTINELA_RET, "justificacion": "Fin de contrato"})
    ret = t.ultimo_id("rrhh")
    t.paso("CU-07", "RRHH ve el motivo restringido en el detalle", "rrhh", "GET", f"/solicitudes/{ret}", 200,
           ["RD-05"], contiene=CENTINELA_RET)

    # CU-08 RRHH emite una emergencia
    tok = t.csrf("rrhh", "/solicitudes/nueva/EMG")
    t.paso("CU-08", "RRHH emite EMG (fuga detectada)", "rrhh", "POST", "/solicitudes/nueva/EMG", 302,
           ["RF-10", "RF-13", "CA-06"],
           data={"csrfmiddlewaretoken": tok, "documento_del_colaborador": "10000003",
                 "subtipo_elegido": "fuga_detectada", "reportado_por": "Seguridad física",
                 "hora_del_hecho": "2026-10-24T08:30", "fecha_efectiva": "2026-10-24",
                 "descripcion": CENTINELA_EMG, "justificacion": "Emergencia"})

    # CU-09 Tecnicos: dashboard, busqueda, ficha y CSV (sin campos restringidos)
    t.paso("CU-09", "Dashboard del tecnico", "tec_ad", "GET", "/dashboard", 200, ["RF-29", "RF-30"],
           no_contiene=CENTINELA_EMG)
    t.paso("CU-09", "Busqueda de cuentas con filtro", "tec_ad", "GET", "/cuentas?departamento=Finanzas", 200,
           ["RF-32"])
    t.paso("CU-09", "Ficha del colaborador retirado sin el motivo", "tec_ad", "GET", "/colaboradores/col-014",
           200, ["RF-33", "CA-10", "T7"], no_contiene=CENTINELA_RET)
    t.paso("CU-09", "Exportacion CSV auditada", "tec_inv", "GET", "/cuentas.csv", 200, ["RF-34", "T10"])
    t.paso("CU-09", "Tecnico no ve el detalle restringido del RET", "tec_ad", "GET", f"/solicitudes/{ret}",
           (403, 404), ["RD-05", "CA-10"], no_contiene=CENTINELA_RET)

    # CU-10 Control de acceso por rol
    for rol, ruta in [("sol", "/bandeja"), ("sol", "/dashboard"), ("tec_ad", "/auditoria"),
                      ("rrhh", "/administracion/perfiles"), ("auditor", "/bandeja"), ("admin", "/dashboard")]:
        t.paso("CU-10", f"{rol} no accede a {ruta}", rol, "GET", ruta, 403, ["RF-03"])

    # CU-11 Auditor
    t.paso("CU-11", "Auditor consulta la auditoria", "auditor", "GET", "/auditoria", 200, ["RF-36", "RF-35"],
           no_contiene=CENTINELA_RET)
    tok = t.csrf("auditor", "/auditoria")
    t.paso("CU-11", "Auditor verifica la cadena de hashes", "auditor", "POST", "/auditoria", 200,
           ["RF-36", "CA-09"], contiene="ntegra", data={"csrfmiddlewaretoken": tok})

    # CU-12 Administrador
    t.paso("CU-12", "Matriz de perfiles", "admin", "GET", "/administracion/perfiles", 200, ["RF-37"])
    t.paso("CU-12", "Usuarios y roles", "admin", "GET", "/administracion/usuarios", 200, ["RF-37"])
    t.paso("CU-12", "Solicitudes en error (reintento)", "admin", "GET", "/errores", 200, ["RF-38"])

    # CU-13 Cierre de sesion
    tok = t.csrf("jefe", "/solicitudes")
    t.paso("CU-13", "Cerrar sesion", "jefe", "POST", "/salir", 302, ["RF-04"],
           data={"csrfmiddlewaretoken": tok})
    t.paso("CU-13", "La sesion cerrada ya no da acceso", "jefe", "GET", "/solicitudes", 302, ["RF-04"])
    return t.pasos


if __name__ == "__main__":
    sesiones = dict(
        linea.strip().split("=", 1) for linea in open(sys.argv[1], encoding="utf-8") if "=" in linea
    )
    pasos = ejecutar(sesiones)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in pasos], f, ensure_ascii=False, indent=2)
    fallas = sum(p.resultado == "FALLA" for p in pasos)
    print(f"\n{len(pasos)} pasos, {fallas} fallas")
