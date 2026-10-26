"""Anexo A (Excel, Tablas I a XVIII): matriz fila por fila de «que exige», «con que se verifica» y «resultado».

    python auditoria/scripts/anexo-a-matriz.py

Entradas: `auditoria/referencias/AnexoA-tablas.json` (volcado del Excel), la comparacion de texto con el SRS
(`anexo-a-tablas-vs-srs.py`), el informe JUnit de la suite (`evidencia/funcionales/ANEXO-A-JUNIT/junit.xml`) y las
carpetas de evidencia. Salida: `auditoria/anexo-a-matriz.csv` y `auditoria/verificacion-anexo-a-excel.md`.

El resultado de una fila NUNCA es mas favorable que lo que dicen sus pruebas: si una prueba referenciada falla, la
fila sale «FALLA»; si una referencia no existe, el script se detiene.
"""

import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AUD = RAIZ / "auditoria"
HOJAS = json.loads((AUD / "referencias/AnexoA-tablas.json").read_text(encoding="utf-8"))
EVID = AUD / "evidencia"
T = "tests/escenarios/test_anexo_a.py::"

# --- resultados de las pruebas ------------------------------------------------------------------


def leer_junit() -> dict[tuple[str, str], str]:
    resultados: dict[tuple[str, str], str] = {}
    for caso in ET.parse(EVID / "funcionales/ANEXO-A-JUNIT/junit.xml").getroot().iter("testcase"):  # noqa: S314  # lo escribio pytest en esta máquina
        hijos = {h.tag: h for h in caso}
        if "failure" in hijos or "error" in hijos:
            estado = "failed"
        elif "skipped" in hijos:
            estado = "xfail" if "xfail" in str(hijos["skipped"].get("type")) else "skipped"
        else:
            estado = "passed"
        resultados[(caso.get("classname", ""), caso.get("name", ""))] = estado
    return resultados


JUNIT = leer_junit()


def probar(prefijo: str) -> dict[str, int]:
    """Cuenta las pruebas que empiezan por `ruta.py` o `ruta.py::nombre`."""
    ruta, _, nombre = prefijo.partition("::")
    modulo = ruta.removesuffix(".py").replace("/", ".")
    cuenta = {"passed": 0, "failed": 0, "xfail": 0, "skipped": 0}
    for (clase, n), estado in JUNIT.items():
        if clase == modulo and (not nombre or n.startswith(nombre)):
            cuenta[estado] += 1
    if sum(cuenta.values()) == 0:
        sys.exit(f"la referencia «{prefijo}» no corresponde a ninguna prueba del informe JUnit")
    return cuenta


def evidencia(carpeta: str) -> str:
    """Resumen de una carpeta de evidencia: su codigo de salida y la ultima linea con 'passed'/'failed' si la hay."""
    ruta = next((EVID / g / carpeta for g in EVID.iterdir() if (EVID / g / carpeta).is_dir()), None)
    if ruta is None:
        sys.exit(f"la evidencia «{carpeta}» no existe")
    codigo = (
        (ruta / "codigo.txt").read_text(encoding="utf-8").strip()
        if (ruta / "codigo.txt").exists()
        else "?"
    )
    return f"{carpeta} (codigo {codigo})"


# --- especificaciones por fila ---------------------------------------------------------------------
# estado base: CUMPLE | PARCIAL | NO CUMPLE | NO VERIFICABLE EN LOCAL. `nota` explica las salvedades.
SPEC = {}


def fila(
    tabla: str,
    clave: str,
    pruebas: list[str] | None = None,
    evid: list[str] | None = None,
    estado: str = "CUMPLE",
    nota: str = "",
) -> None:
    SPEC[(tabla, clave)] = dict(pruebas=pruebas or [], evid=evid or [], estado=estado, nota=nota)


# I
fila(
    "I",
    "F1. Autenticación y roles",
    [
        "tests/adaptadores/test_ingreso_web.py",
        "tests/aplicacion/test_ingreso.py",
        "tests/seguridad/test_matriz_authz.py",
        "tests/seguridad/test_segundo_factor.py",
    ],
    nota="B-28: el JWT se lee sin verificar la firma (riesgo acotado por TLS verify-full)",
)
fila(
    "I",
    "F2. Gestión de solicitudes",
    ["tests/aplicacion/test_registro_y_decision.py"],
    ["F1-02-INTEGRACION"],
)
fila(
    "I",
    "F3. Emisión de tickets",
    ["tests/dominio/test_tickets.py", T + "test_tabla_VIII", T + "test_tabla_V_prioridad"],
    ["F1-03-GLPI-REAL-3"],
)
fila(
    "I",
    "F4. Sincronización",
    ["tests/aplicacion/test_sincronizacion.py", T + "test_tabla_II_adr_011"],
    ["F1-03-GLPI-REAL-3"],
)
fila(
    "I",
    "F5. Registro de cuentas",
    ["tests/dominio/test_resolucion_cuentas.py", "tests/bdd/test_cuentas_derivadas.py"],
)
fila(
    "I",
    "F6. DashBoards",
    ["tests/aplicacion/test_consultas.py", "tests/adaptadores/test_tecnicos_web.py"],
)
fila(
    "I",
    "F7. Auditoría",
    [
        "tests/dominio/test_auditoria.py",
        "tests/bdd/test_inmutabilidad.py",
        "tests/adaptadores/test_auditor_web.py",
    ],
    ["F7-05-RESPALDO-Y-RESTAURACION"],
)
fila(
    "I",
    "F8. Administración",
    ["tests/aplicacion/test_administracion.py", "tests/adaptadores/test_administracion_web.py"],
)

# II
ADR_LOCAL = {
    "1": (["tests/contratos/test_sistema_de_tickets.py"], ["F1-03-GLPI-REAL-3"], "CUMPLE", ""),
    "2": (
        [],
        ["F7-01-NMAP"],
        "PARCIAL",
        "Docker Compose: sí (10 servicios, `infra/compose.yaml`); la VM de Azure no se puede verificar en local",
    ),
    "3": (
        [T + "test_tabla_II_adr_003_004_010_019"],
        [],
        "CUMPLE",
        "reemplazada: no hay código ni dependencias de Samba, LDAP ni Graph",
    ),
    "4": ([T + "test_tabla_II_adr_003_004_010_019"], [], "CUMPLE", "reemplazada por ADR-019"),
    "5": (
        ["tests/dominio/test_catalogo_permisos.py"],
        [],
        "PARCIAL",
        "la «cuenta única» de RRHH se cumple por operación (el Administrador asigna el rol); el sistema no impide dar el rol a dos personas",
    ),
    "6": (
        [
            "tests/aplicacion/test_registro_y_decision.py::test_CA_01",
            "tests/bdd/test_inmutabilidad.py",
        ],
        ["F1-02-INTEGRACION"],
        "CUMPLE",
        "",
    ),
    "7": (
        ["tests/dominio/test_auditoria.py", "tests/bdd/test_inmutabilidad.py"],
        ["F7-05-RESPALDO-Y-RESTAURACION"],
        "CUMPLE",
        "",
    ),
    "8": (
        [T + "test_tabla_II_adr_008_012_020"],
        [],
        "CUMPLE",
        "reemplazada por ADR-017: no hay OIDC",
    ),
    "9": (
        ["tests/adaptadores/test_secretos.py", "tests/seguridad/test_despliegue.py"],
        [],
        "PARCIAL",
        "secretos como archivos en /run/secrets: sí; Key Vault de Azure: no verificable en local (aquí SOPS + age, ADR-029)",
    ),
    "10": ([T + "test_tabla_II_adr_003_004_010_019"], [], "CUMPLE", "reemplazada por ADR-019"),
    "11": ([T + "test_tabla_II_adr_011"], [], "CUMPLE", ""),
    "12": (
        [T + "test_tabla_II_adr_008_012_020"],
        [],
        "CUMPLE",
        "reemplazada: no hay FastAPI ni React",
    ),
    "13": (
        [T + "test_tabla_II_adr_003_004_010_019"],
        [],
        "CUMPLE",
        "no existe código de monitoreo del DC (fuera de alcance)",
    ),
    "14": (
        ["tests/adaptadores/test_glpi_cliente.py"],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "el Excel dice «Pendiente (sprint 0)»; `docs/decisiones.md` ya la tiene «Aceptada (spike 0.3)» y el adaptador la implementa (API v1, App-Token y token de usuario): desfase del Excel",
    ),
    "15": (
        [],
        ["F3-PAR", "F1-02-INTEGRACION"],
        "CUMPLE",
        "paridad de catálogo PostgreSQL local frente a Supabase medida en F3 (solo lectura)",
    ),
    "16": ([T + "test_tabla_II_adr_016"], ["F2-02-RUFF-MYPY-IMPORTS"], "CUMPLE", ""),
    "17": (
        [
            "tests/adaptadores/test_identidad_supabase.py",
            "tests/adaptadores/test_identidad_exacta.py",
            "tests/seguridad/test_segundo_factor.py",
        ],
        [],
        "CUMPLE",
        "B-28 abierto; el servicio real de Supabase Auth no se ejerció en esta auditoría (solo simulado)",
    ),
    "18": ([T + "test_tabla_II_adr_018"], [], "CUMPLE", ""),
    "19": ([T + "test_tabla_II_adr_003_004_010_019"], [], "CUMPLE", ""),
    "20": ([T + "test_tabla_II_adr_008_012_020"], [], "CUMPLE", ""),
    "21": (["tests/bdd/test_soporte_pdf.py", "tests/seguridad/test_soporte.py"], [], "CUMPLE", ""),
    "22": (
        [T + "test_tabla_XIV", T + "test_tabla_XIII", "tests/dominio/test_tickets.py"],
        [],
        "CUMPLE",
        "",
    ),
    "23": (
        ["tests/bdd/test_borde.py"],
        ["F6-01-PRUEBAS-SH", "F6-02-ESCANER-EXENTO", "F7-02-API-BUNKERWEB", "F7-07-TESTSSL"],
        "CUMPLE",
        "",
    ),
    "24": (
        [T + "test_tabla_II_adr_003_004_010_019"],
        [],
        "CUMPLE",
        "es una propuesta: correctamente no desplegada (no hay `cloudflared` en el compose)",
    ),
    "25": (["tests/contratos/test_repositorios.py"], [], "CUMPLE", ""),
    "26": (
        ["tests/aplicacion/test_listados.py", "tests/adaptadores/test_reintento_web.py"],
        [],
        "CUMPLE",
        "",
    ),
    "27": (
        ["tests/aplicacion/test_administracion.py", "tests/adaptadores/test_administracion_web.py"],
        [],
        "CUMPLE",
        "",
    ),
    "28": (
        ["tests/bdd/test_inmutabilidad.py"],
        ["F1-02-INTEGRACION", "bases-config.txt"],
        "CUMPLE",
        "",
    ),
}
for numero, (pruebas, evid, estado, nota) in ADR_LOCAL.items():
    fila("II", numero, pruebas, [e for e in evid if not e.endswith(".txt")], estado, nota)

# III: la clave es el numero de fila (1..20) del Excel
PUERTOS = {
    1: ("CUMPLE", "TLS autofirmado en local; Let's Encrypt solo en Azure"),
    2: ("CUMPLE", "responde 301 hacia HTTPS"),
    3: ("NO VERIFICABLE EN LOCAL", "sshd y NSG son de la VM de Azure"),
    4: ("CUMPLE", ""),
    5: ("CUMPLE", ""),
    6: (
        "CUMPLE",
        "el puerto 5000 es alcanzable por TCP desde `bw-universe` y exige `API_TOKEN` (F7-02)",
    ),
    7: ("CUMPLE", "B-32: los tokens de GLPI viajan en claro en este tramo"),
    8: ("CUMPLE", "B-30: sin TLS entre GLPI y MariaDB (red `internal: true`)"),
    9: (
        "PARCIAL",
        "TLS `verify-full` y puerto 5432 comprobados en la configuración; catálogo de Supabase leído en F3; no se abre una conexión desde los contenedores",
    ),
    10: ("NO VERIFICABLE EN LOCAL", "Supabase Auth solo se prueba con un servidor simulado"),
    11: ("NO VERIFICABLE EN LOCAL", "idem; `admin-usuarios` se prueba con el servidor simulado"),
    12: ("NO VERIFICABLE EN LOCAL", "Azure Key Vault"),
    13: ("NO VERIFICABLE EN LOCAL", "Azure Blob Storage"),
    14: ("NO VERIFICABLE EN LOCAL", "Let's Encrypt (en local, certificado autofirmado)"),
    15: ("CUMPLE", ""),
    16: ("CUMPLE", ""),
    17: (
        "CUMPLE",
        "Grafana solo en 127.0.0.1 (B-27: es una excepción no escrita al invariante 14)",
    ),
    18: ("NO VERIFICABLE EN LOCAL", "Loki con identidad administrada hacia Blob (Azure)"),
    19: ("NO VERIFICABLE EN LOCAL", "Cloudflare es una propuesta (ADR-024), no desplegada"),
    20: ("CUMPLE", ""),
}
for i, (estado, nota) in PUERTOS.items():
    fila(
        "III",
        str(i),
        ["tests/adaptadores/test_config.py"] if i == 9 else [],
        ["ANEXO-A-TABLA-III-PUERTOS"] if estado in ("CUMPLE",) or i == 9 else [],
        estado,
        nota,
    )

# IV
fila(
    "IV",
    "Solicitante",
    [T + "test_tabla_IV_el_solicitante_no_crea", T + "test_tabla_V_quien_puede"],
    estado="PARCIAL",
    nota="la fila del Excel NO es la del SRS: promete «creación de cuentas», «eliminaciones de cuentas» y «generar correos»; el sistema no lo hace ni debe (ADR-019, sin correos). Lo que sí cumple es lo del SRS: sus vacaciones y renuncia, los cambios de sus subordinados, consultar y cancelar sus pendientes",
)
fila(
    "IV",
    "RRHH",
    [T + "test_tabla_IV_permisos_por_rol", "tests/aplicacion/test_registro_y_decision.py"],
)
for rol in ("Técnico AD", "Técnico Comunicaciones", "Técnico Licencias", "Técnico Inventario"):
    fila("IV", rol, [T + "test_tabla_IV_permisos_por_rol", "tests/seguridad/test_matriz_authz.py"])
fila(
    "IV",
    "Auditor",
    [T + "test_tabla_IV_permisos_por_rol", T + "test_tabla_IV_el_auditor_lee"],
    estado="PARCIAL",
    nota="lee la auditoría y verifica su integridad; NO lee solicitudes (responde 404): B-26 / S-39, decisión del equipo (P-8)",
)
fila(
    "IV",
    "Administrador del sistema",
    [T + "test_tabla_IV_permisos_por_rol", "tests/aplicacion/test_administracion.py"],
)

# V a XIV (todas por pruebas dirigidas por el Excel)
for codigo in ("ING", "VAC", "CDP", "CSU", "RET", "EMG"):
    fila(
        "V",
        codigo,
        [
            T + "test_tabla_V_prioridad_y_vencimiento",
            T + "test_tabla_V_quien_puede_registrar",
            T + "test_tabla_V_aprobacion",
        ],
    )
for estado in (
    "pendiente_aprobacion",
    "aprobada",
    "en_ejecucion",
    "error",
    "cerrada",
    "rechazada",
    "cancelada",
):
    fila("VI", estado, [T + "test_tabla_VI", "tests/dominio/test_solicitud.py"])
for clase in ("De cierre inmediato", "De cierre programado", "Posterior"):
    fila("VII", clase, [T + "test_tabla_VII"])
for codigo in ("ING", "VAC", "CDP", "CSU", "RET", "EMG"):
    fila("VIII", codigo, [T + "test_tabla_VIII"], ["F1-03-GLPI-REAL-3"] if codigo == "RET" else [])
for aspecto in ("Cuenta", "Contraseña", "Grupos", "Sesiones", "Reversión", "Eliminación"):
    fila("IX", aspecto, [T + "test_tabla_IX"])
for cola in ("AD", "Comunicaciones", "Licencias", "Inventario"):
    fila("X", cola, [T + "test_tabla_X"], ["F1-03-GLPI-REAL-3"])
for ticket in (
    "ING",
    "VAC, suspensión",
    "VAC, reactivación (programado)",
    "CDP o CSU",
    "RET o EMG",
    "Eliminación (posterior)",
):
    fila(
        "XI",
        ticket,
        [
            "tests/aplicacion/test_sincronizacion.py",
            "tests/dominio/test_resolucion_cuentas.py",
            "tests/bdd/test_cuentas_derivadas.py",
        ],
    )
for codigo in ("ING", "VAC", "CDP", "CSU", "RET", "EMG"):
    fila("XII", codigo, [T + "test_tabla_XII"])
for depto in ("Gerencia", "RRHH", "Finanzas", "Comercial", "TI", "Operaciones"):
    fila("XIII", depto, [T + "test_tabla_XIII"])
for i in range(1, 10):
    fila("XIV", str(i), [T + "test_tabla_XIV"])

# XV a XVII (requisitos)
RF = {
    "RF-01": (
        [
            "tests/contratos/test_soportes_identidad_reloj.py::test_contrasena_y_totp",
            "tests/adaptadores/test_identidad_exacta.py",
            "tests/seguridad/test_segundo_factor.py",
        ],
        [],
        "CUMPLE",
        "B-28",
    ),
    "RF-02": (
        [
            "tests/adaptadores/test_ingreso_web.py::test_RF_02",
            "tests/contratos/test_soportes_identidad_reloj.py::test_el_primer_ingreso",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-03": (
        [
            "tests/seguridad/test_matriz_authz.py",
            "tests/seguridad/test_idor_csrf.py",
            "tests/bdd/test_autorizacion.py",
        ],
        [],
        "CUMPLE",
        "matriz de 100 % de las celdas ruta × rol; B-26 (Auditor) es la excepción documentada",
    ),
    "RF-04": (["tests/adaptadores/test_ingreso_web.py::test_RF_04"], [], "CUMPLE", ""),
    "RF-05": (
        [
            "tests/aplicacion/test_ingreso.py::test_RF_05",
            "tests/dominio/test_catalogo_permisos.py::test_roles_incompatibles_RF_05",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-06": (
        [T + "test_rf_06", "tests/adaptadores/test_admin_usuarios.py"],
        [],
        "CUMPLE",
        "no hay `django.contrib.admin` ni ruta de registro; el alta solo la hace `admin-usuarios`",
    ),
    "RF-07": (
        ["tests/aplicacion/test_registro_y_decision.py", "tests/dominio/test_catalogo_permisos.py"],
        [],
        "CUMPLE",
        "",
    ),
    "RF-08": (
        ["tests/dominio/test_catalogo_permisos.py::test_fecha_efectiva_pasada"],
        [],
        "CUMPLE",
        "",
    ),
    "RF-09": (
        ["tests/aplicacion/test_registro_y_decision.py::test_RF_09"],
        ["F1-02-INTEGRACION"],
        "CUMPLE",
        "",
    ),
    "RF-10": (
        [
            "tests/aplicacion/test_registro_y_decision.py::test_RF_10",
            "tests/aplicacion/test_defensas.py::test_RF_10",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-11": (
        [
            "tests/aplicacion/test_registro_y_decision.py::test_el_solicitante_cancela",
            "tests/aplicacion/test_registro_y_decision.py::test_rrhh_cancela",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-39": (
        ["tests/bdd/test_soporte_pdf.py", "tests/seguridad/test_soporte.py"],
        [],
        "CUMPLE",
        "",
    ),
    "RF-12": (
        [
            "tests/dominio/test_solicitud.py::test_aprobar_acepta",
            "tests/aplicacion/test_registro_y_decision.py",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-13": (
        [
            "tests/aplicacion/test_registro_y_decision.py::test_RF_13",
            "tests/dominio/test_catalogo_permisos.py::test_matriz_rol_sujeto",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-14": (
        [
            "tests/bdd/test_inmutabilidad.py",
            "tests/aplicacion/test_registro_y_decision.py::test_corregir",
        ],
        ["F1-02-INTEGRACION"],
        "CUMPLE",
        "el disparador se prueba contra PostgreSQL (integración)",
    ),
    "RF-15": (
        [
            "tests/aplicacion/test_registro_y_decision.py::test_RF_15",
            "tests/dominio/test_catalogo_permisos.py::test_matriz_rol_sujeto",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-16": (
        [
            T + "test_tabla_VIII",
            "tests/dominio/test_tickets.py",
            "tests/dominio/test_tickets_golden.py",
        ],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "",
    ),
    "RF-17": (
        [
            "tests/aplicacion/test_bandeja.py::test_RF_17",
            "tests/contratos/test_sistema_de_tickets.py::test_un_ticket_programado",
        ],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "",
    ),
    "RF-18": (
        ["tests/aplicacion/test_bandeja.py", "tests/bdd/test_resiliencia.py"],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "",
    ),
    "RF-19": (
        ["tests/adaptadores/test_glpi_configuracion.py"],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "contra GLPI real: `test_CA_03_cada_ticket_llega_al_grupo_de_su_cola` y `..._una_categoria_desconocida_va_a_revision_manual`",
    ),
    "RF-20": (
        [
            "tests/adaptadores/test_glpi_cliente.py::test_RF_20",
            "tests/dominio/test_tickets.py::test_datos_tecnicos_RF_20",
            "tests/bdd/test_restringidos.py",
        ],
        ["F7-04-CAPTURA-TRAFICO"],
        "CUMPLE",
        "0 tramas con el centinela entre 31 240 capturadas",
    ),
    "RF-40": (
        [
            "tests/aplicacion/test_bandeja.py::test_RF_40",
            "tests/aplicacion/test_registro_y_decision.py::test_rechazar_un_ingreso",
            "tests/aplicacion/test_registro_y_decision.py::test_cancelar_un_ingreso",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-21": (
        ["tests/aplicacion/test_bandeja.py::test_RF_21"],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "",
    ),
    "RF-22": (
        [
            "tests/contratos/test_sistema_de_tickets.py::test_leer_tickets",
            "tests/aplicacion/test_sincronizacion.py",
        ],
        ["F1-03-GLPI-REAL-3"],
        "CUMPLE",
        "",
    ),
    "RF-23": (["tests/aplicacion/test_sincronizacion.py::test_RF_23"], [], "CUMPLE", ""),
    "RF-24": (["tests/dominio/test_resolucion_cuentas.py"], [], "CUMPLE", ""),
    "RF-25": (
        [
            "tests/aplicacion/test_sincronizacion.py::test_RF_25",
            "tests/dominio/test_resolucion_cuentas.py::test_reabierto",
        ],
        [],
        "CUMPLE",
        "",
    ),
    "RF-26": (
        [
            "tests/aplicacion/test_sincronizacion.py::test_retiro_cierra",
            "tests/dominio/test_resolucion_cuentas.py::test_los_posteriores",
        ],
        [],
        "CUMPLE",
        "",
    ),
}
for rid, (pruebas, evid, estado, nota) in RF.items():
    tabla = {
        "RF-01": "XV",
        "RF-02": "XV",
        "RF-03": "XV",
        "RF-04": "XV",
        "RF-05": "XV",
        "RF-06": "XV",
    }.get(rid)
    if tabla is None:
        tabla = "XVI" if rid in ("RF-07", "RF-08", "RF-09", "RF-10", "RF-11", "RF-39") else "XVII"
    fila(tabla, rid, pruebas, evid, estado, nota)

# XVIII
fila(
    "XVIII",
    "RI-01",
    ["tests/adaptadores/test_accesibilidad.py"],
    ["B-34-VERDE"],
    "PARCIAL",
    nota="contraste de texto (≥ 6,09:1), de componentes (≥ 3:1 tras B-34), idioma, etiquetas, foco, orden de tabulación, sin JavaScript ni recursos externos: 50 de 50. La conformidad WCAG 2.1 AA completa exige además una evaluación manual con lector de pantalla, que no se hizo",
)
fila(
    "XVIII",
    "RI-02",
    ["tests/contratos/test_sistema_de_tickets.py", "tests/adaptadores/test_glpi_cliente.py"],
    ["F1-03-GLPI-REAL-3", "RI-02-PERFIL-GLPI"],
    "PARCIAL",
    nota="todas las operaciones de la fila funcionan contra GLPI 11 real (30 de 30); el perfil de la cuenta de servicio sobra en BORRAR y PURGAR de tickets: B-35 / P-11",
)
fila(
    "XVIII",
    "RI-03",
    [
        "tests/adaptadores/test_config.py::test_la_base_de_produccion",
        "tests/bdd/test_supabase_aislada.py",
    ],
    ["F1-02-INTEGRACION", "F3-PAR"],
    "CUMPLE",
    nota="TLS verify-full y session pooler (5432) en la configuración; permisos de `app_backend` medidos en PostgreSQL local y en el catálogo de Supabase (solo lectura); B-10: asesor de Supabase",
)
fila(
    "XVIII",
    "RI-04",
    [
        "tests/adaptadores/test_admin_usuarios.py",
        "tests/adaptadores/test_infra.py::test_invariante_8",
        "tests/adaptadores/test_identidad_supabase.py",
    ],
    [],
    "PARCIAL",
    nota="`service_role` solo en `admin-usuarios` (probado en el compose); el servicio real de Supabase Auth no se ejerció desde el servidor en esta auditoría",
)
fila(
    "XVIII",
    "RI-05",
    [],
    [],
    "NO VERIFICABLE EN LOCAL",
    "Azure Key Vault con identidad administrada; en local los secretos salen de `/run/secrets` (SOPS + age, ADR-029)",
)
fila(
    "XVIII",
    "RI-06",
    ["tests/adaptadores/test_exportacion_auditoria.py"],
    ["F7-05-RESPALDO-Y-RESTAURACION"],
    "NO VERIFICABLE EN LOCAL",
    "Azure Blob (contenedores inmutables e identidad administrada) no existe en local; la exportación de auditoría escribe a un directorio y su cadena se verifica sin la base",
)


# --- generacion ----------------------------------------------------------------------------------------

TABLAS = [
    ("I", "TablaI Matriz funcion"), ("II", "TablaII ADR"), ("III", "TablaIII Puertos"), ("IV", "TablaIV Users-Roles"),
    ("V", "TablaV Eventos SLAs"), ("VI", "TablaVI Estados Solicitud"), ("VII", "TablaVII Clases de Tickets"),
    ("VIII", "TablaVIII Acciones por Cola"), ("IX", "TablaIX Deshabilitación"), ("X", "TablaX Plantillas Solución "),
    ("XI", "TablaXI Estados Cuentas"), ("XII", "TablaXII Campos Eventos"), ("XIII", "TablaXIII Perfiles Acceso"),
    ("XIV", "TablaXIV Recursos Compartidos"), ("XV", "TablaXV RF Autenticación"), ("XVI", "TablaXVI RF Solicitudes"),
    ("XVII", "TablaXVII RF Tickets"), ("XVIII", "TablaXVIII RI Interfaces"),
]  # fmt: skip


def clave_de(tabla: str, f: list[str], indice: int) -> str:
    if tabla == "II":
        return str(int("".join(c for c in f[0] if c.isdigit())))
    if tabla in ("III", "XIV"):
        return str(indice)
    return f[0]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    texto_vs_srs: dict[tuple[str, str], str] = {}
    with (AUD / "evidencia/funcionales/anexo-a-tablas/comparacion-con-el-srs.csv").open(
        encoding="utf-8", newline=""
    ) as f:
        for r in csv.DictReader(f):
            texto_vs_srs[(r["tabla"], r["fila"])] = r["estado"]
    filas_csv = []
    faltan = []
    for tabla, hoja in TABLAS:
        datos = [f for f in HOJAS[hoja][2:] if any(c.strip() for c in f)]
        for i, f in enumerate(datos, start=1):
            clave = clave_de(tabla, f, i)
            spec = SPEC.get((tabla, clave))
            if spec is None:
                faltan.append((tabla, clave))
                continue
            cuentas = {"passed": 0, "failed": 0, "xfail": 0, "skipped": 0}
            for p in spec["pruebas"]:
                for k, v in probar(p).items():
                    cuentas[k] += v
            evid = [evidencia(e) for e in spec["evid"]]
            estado = spec["estado"]
            if cuentas["failed"]:
                estado = "FALLA"
            origen = texto_vs_srs.get((tabla, f[0]), texto_vs_srs.get((tabla, clave), ""))
            filas_csv.append(
                dict(
                    tabla=tabla, fila=f[0] if tabla not in ("III", "XIV") else " → ".join(c for c in f[:2]),
                    exigencia=" | ".join(c.replace("\n", " ") for c in f[1:] if c)[:230],
                    texto_frente_al_srs=origen or "sin tabla equivalente en el SRS",
                    pruebas_que_pasan=cuentas["passed"], pruebas_que_fallan=cuentas["failed"], xfail=cuentas["xfail"],
                    evidencias="; ".join(evid), resultado=estado, nota=spec["nota"],
                )
            )  # fmt: skip
    if faltan:
        sys.exit(f"filas del Excel sin especificacion: {faltan}")
    campos = [
        "tabla",
        "fila",
        "exigencia",
        "texto_frente_al_srs",
        "pruebas_que_pasan",
        "pruebas_que_fallan",
        "xfail",
        "evidencias",
        "resultado",
        "nota",
    ]
    with (AUD / "anexo-a-matriz.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas_csv)
    from collections import Counter

    por_resultado = Counter(r["resultado"] for r in filas_csv)
    por_tabla: dict[str, Counter[str]] = {}
    for r in filas_csv:
        por_tabla.setdefault(r["tabla"], Counter())[r["resultado"]] += 1
    print(f"filas: {len(filas_csv)} · " + " · ".join(f"{k}: {v}" for k, v in por_resultado.items()))
    for t, c in por_tabla.items():
        print(f"  Tabla {t:6}", dict(c))
    json.dump({"filas": len(filas_csv), "resultados": dict(por_resultado), "por_tabla": {t: dict(c) for t, c in por_tabla.items()}},
              (AUD / "evidencia/funcionales/anexo-a-tablas/resumen.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)  # fmt: skip
    return 1 if por_resultado.get("FALLA") else 0


if __name__ == "__main__":
    sys.exit(main())
