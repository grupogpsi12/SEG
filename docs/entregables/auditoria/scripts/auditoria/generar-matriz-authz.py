"""F5-01: genera auditoria/matriz-authz.csv (rutas × métodos × roles) con lo ESPERADO según el SRS.

    python auditoria/scripts/generar-matriz-authz.py

Lo esperado sale del SRS «Clases de usuarios y roles» y de los RF citados, NO de lo que hoy hace el
código. Donde el código se aparta del SRS, la fila lleva el ID del hallazgo y lo que se observa:
la prueba acepta ese resultado conocido y falla ante cualquier otro (una desviación nueva).

Formato de `esperado`: «200», «403», «404», «405» o «302:<destino>».
"""

import csv
from pathlib import Path

DESTINO = Path(__file__).resolve().parents[1] / "matriz-authz.csv"

ROLES = [
    "anonimo", "solicitante", "jefe", "rrhh",
    "tecnico_ad", "tecnico_comunicaciones", "tecnico_licencias", "tecnico_inventario",
    "auditor", "administrador",
]  # fmt: skip
TECNICOS = {r for r in ROLES if r.startswith("tecnico_")}

# ruta -> métodos que acepta la vista (el decorador de método va ANTES de la sesión: 405 para todos)
METODOS = {
    "salud": ["GET"], "inicio": ["GET"], "ingreso": ["GET", "POST"],
    "segundo_factor": ["GET", "POST"], "salir": ["POST"],
    "solicitudes": ["GET"], "nueva_indice": ["GET"], "nueva": ["GET", "POST"],
    "bandeja": ["GET"], "dashboard": ["GET"], "auditoria": ["GET", "POST"],
    "en_error": ["GET"], "admin_perfiles": ["GET"], "admin_perfil": ["GET", "POST"],
    "admin_usuarios": ["GET"], "admin_roles": ["POST"], "reintentar": ["POST"],
    "cuentas": ["GET"], "cuentas_csv": ["GET"], "ficha": ["GET"],
    "detalle": ["GET"], "decidir": ["POST"],
}  # fmt: skip

# ruta -> roles con acceso (SRS «Clases de usuarios y roles» y RF indicados)
ACCESO = {
    "nueva": (
        {"solicitante", "jefe", "rrhh", "administrador"},
        "SRS 3.3 y 4.1: registrar/emitir (S-08)",
    ),
    "bandeja": ({"rrhh"}, "SRS 3.3: RRHH aprueba o rechaza"),
    "dashboard": (TECNICOS, "RF-29: solo roles técnicos"),
    "cuentas": (TECNICOS, "RF-29: solo roles técnicos"),
    "cuentas_csv": (TECNICOS, "RF-33, T10: solo roles técnicos"),
    "ficha": (TECNICOS, "RF-34, T10: solo roles técnicos"),
    "auditoria": ({"auditor"}, "RF-36: el Auditor consulta y verifica"),
    "en_error": ({"administrador"}, "RF-38: el Administrador reintenta"),
    "admin_perfiles": ({"administrador"}, "RF-37"),
    "admin_perfil": ({"administrador"}, "RF-37"),
    "admin_usuarios": ({"administrador"}, "RF-37"),
}
POST_PERMITIDO = {
    "admin_roles": ("administrador", "302:/administracion/usuarios", "RF-37"),
    "reintentar": ("administrador", "302:/errores", "RF-38"),
    "decidir": ("rrhh", "302:/bandeja", "SRS 3.3: RRHH decide"),
}
# (ruta, rol) -> (hallazgo, resultado observado hoy)
EXCEPCIONES = {
    ("detalle", "auditor"): ("B-26", "404"),
}


def esperado(ruta: str, metodo: str, rol: str) -> tuple[str, str]:
    if metodo not in METODOS[ruta]:
        return "405", "el decorador de método va antes que la sesión"
    anon = rol == "anonimo"
    if ruta == "salud":
        return "200", "RNF-01: chequeo de salud público"
    if ruta == "inicio":
        return "302:/solicitudes", "el inicio lleva a «mis solicitudes»"
    if ruta == "ingreso":
        return ("200", "RF-01") if anon else ("302:/", "ya con sesión vuelve al inicio")
    if ruta == "segundo_factor":
        return "302:/ingreso", "sin desafío en la sesión vuelve al ingreso (RF-01)"
    if ruta == "salir":
        return "302:/ingreso", "cierra la sesión"
    if anon:
        return "302:/ingreso", "RF-03: sin sesión no hay acceso"
    if ruta in POST_PERMITIDO:
        permitido, destino, fuente = POST_PERMITIDO[ruta]
        return (
            (destino, fuente)
            if rol == permitido
            else ("302:/solicitudes", f"{fuente}: denegado con aviso")
        )
    if ruta in ("solicitudes", "nueva_indice"):
        return "200", "toda persona con sesión ve sus propias solicitudes (RF-11)"
    if ruta == "detalle":
        if rol in ("solicitante", "rrhh", "auditor"):
            return "200", "SRS 3.3: dueño, RRHH y Auditor (sin restringidos)"
        return "404", "ADR de ocultamiento: no se confirma que el id exista"
    roles, fuente = ACCESO[ruta]
    return ("200" if rol in roles else "403"), fuente


def main() -> None:
    filas = []
    for ruta in METODOS:
        for metodo in ("GET", "POST"):
            for rol in ROLES:
                valor, fuente = esperado(ruta, metodo, rol)
                excepcion, observado = (
                    EXCEPCIONES.get((ruta, rol), ("", "")) if metodo == "GET" else ("", "")
                )
                filas.append([ruta, metodo, rol, valor, fuente, excepcion, observado])
    with DESTINO.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            ["ruta", "metodo", "rol", "esperado", "fuente", "excepcion", "observado_conocido"]
        )
        w.writerows(filas)
    print(f"{len(filas)} celdas en {DESTINO.name}")


if __name__ == "__main__":
    main()
