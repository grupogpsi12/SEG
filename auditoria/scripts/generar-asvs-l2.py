"""F8-05: genera auditoria/asvs-l2.csv desde el CSV OFICIAL de ASVS 5.0.0 (requisitos de nivel 1 y 2).

    python auditoria/scripts/generar-asvs-l2.py <OWASP_ASVS_5.0.0_en.csv>

El CSV oficial (github.com/OWASP/ASVS, etiqueta v5.0.0, sha256 98c8fe91…, licencia CC BY-SA) está en
`auditoria/referencias/ASVS-5.0.0-en.csv`. Cada
requisito hereda el estado de su SECCIÓN: la clasificación es por sección y no requisito por requisito
(75 secciones frente a 253 requisitos), y por eso el plan pide revisar una muestra del 10 % con otra
persona `[PENDIENTE: revisión de una segunda persona]`. Estados: verificado, parcial (con el hallazgo o el
límite), no aplica (con el motivo) y pendiente (con la fase que lo cierra).
"""

import csv
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parents[1] / "asvs-l2.csv"

V, P, N, X = "verificado", "parcial", "no aplica", "pendiente"
# sección -> (estado, evidencia o motivo)
S: dict[str, tuple[str, str]] = {
    "V1.1": (V, "Django decodifica una sola vez; sin decodificación propia (F2-08)"),
    "V1.2": (
        V,
        "ORM sin SQL crudo (F2-08 #11), ruff S y bandit (F2-01), defecto sembrado F5-sql-fstring; sqlmap nivel 5 en F6-04",
    ),
    "V1.3": (
        V,
        "escape automático; único mark_safe en graficos.py con escape() (F2-08 #12); ZAP F6-00",
    ),
    "V1.4": (N, "Python gestionado: la aplicación no tiene código nativo propio"),
    "V1.5": (V, "sin pickle, marshal, eval ni yaml.load en src (búsqueda en F2)"),
    "V2.1": (V, "reglas de negocio en SRS §4 y ADR"),
    "V2.2": (V, "formularios de Django en el servidor; fechas efectivas validadas en el dominio"),
    "V2.3": (
        V,
        "deduplicación en la base, inmutabilidad, doble firma: F3-U05, F3-BD, tests/dominio",
    ),
    "V2.4": (V, "límites de BunkerWeb (RS-08); control positivo F6-06"),
    "V3.2": (V, "nosniff y tipos de contenido fijos (BunkerWeb y Django); ZAP baseline"),
    "V3.3": (V, "SESSION/CSRF_COOKIE_SECURE, HTTPONLY y SAMESITE=Lax en settings.py; test_config"),
    "V3.4": (
        V,
        "CSP de Django, HSTS/Referrer/nosniff de BunkerWeb; ZAP baseline; check --deploy (F3-U08)",
    ),
    "V3.5": (V, "CORP/COEP, CORS cerrado, base-uri y form-action; ZAP"),
    "V3.7": (V, "sin JavaScript de terceros (invariante 11)"),
    "V4.1": (V, "métodos no previstos dan 405 (test_metodos.py)"),
    "V4.2": (V, "CRS 4 en bloqueo; pruebas.sh (F6-01)"),
    "V4.3": (N, "la aplicación no expone GraphQL"),
    "V4.4": (N, "sin WebSocket (invariante 11)"),
    "V5.1": (V, "ADR-021 y SRS RF-39/RF-40"),
    "V5.2": (
        P,
        "firma, 20 MiB y nombre validados antes de tocar el disco (F3-U02); un PDF políglota pasa por diseño: B-22 aceptado",
    ),
    "V5.3": (
        V,
        "nombre aleatorio con O_EXCL y 0600, volumen noexec, borrado tras verificar el hash",
    ),
    "V5.4": (V, "la aplicación nunca sirve el soporte; el CSV escapa fórmulas (test_tecnicos_web)"),
    "V6.1": (V, "ADR-017, SRS RF-01/RF-02"),
    "V6.2": (
        X,
        "la contraseña la gestiona Supabase Auth; su política mínima requiere acción humana en el panel (B-10, RS-16) [PENDIENTE: acción del equipo]",
    ),
    "V6.3": (V, "error genérico (RS-08), cinco intentos por desafío, 5/min en el WAF; F3-U01"),
    "V6.4": (
        P,
        "registro abierto deshabilitado; recuperación de cuenta por el Administrador con `admin-usuarios`; sin flujo de autoservicio",
    ),
    "V6.5": (
        V,
        "TOTP obligatorio (AAL2); la sesión solo nace tras verificarlo (F3-U01, Gherkin de ingreso)",
    ),
    "V6.6": (N, "no se usan SMS ni correo como factor"),
    "V6.8": (
        P,
        "Supabase Auth como proveedor; la aplicación lee `aal` y `sub` del JWT sin verificar su firma: B-28",
    ),
    "V7.1": (V, "SRS RF-04"),
    "V7.2": (V, "el id de sesión rota en cada paso; no se guardan tokens (test_ingreso_web)"),
    "V7.3": (V, "30 minutos de inactividad y 8 horas de duración total (RF-04, tests)"),
    "V7.4": (V, "POST /salir hace flush de la sesión; desactivar un usuario la cierra (RF-05)"),
    "V7.5": (
        P,
        "sin límite de sesiones simultáneas ni reautenticación para acciones sensibles; la doble firma de RRHH lo compensa",
    ),
    "V7.6": (N, "sin federación"),
    "V8.1": (V, "matriz de autorización de 440 celdas tomada del SRS (F5-01)"),
    "V8.2": (
        V,
        "denegar por defecto; permisos en los casos de uso; IDOR idéntico a «no existe» (F5-03)",
    ),
    "V8.3": (
        V,
        "cada operación que cambia estado verifica el rol en el caso de uso (matriz F5-02)",
    ),
    "V8.4": (P, "el Auditor no lee solicitudes pese al SRS: B-26 (falla hacia el lado seguro)"),
    "V9.1": (P, "los claims del JWT de Supabase se leen sin verificar la firma: B-28"),
    "V9.2": (P, "se comprueban `aal` y `sub`; no se comprueban `exp` ni `iss`: B-28"),
    "V10.1": (N, "la aplicación no es cliente ni servidor OAuth/OIDC"),
    "V10.2": (
        N,
        "no usa flujos OAuth de redirección; llama a la API de Supabase Auth desde el servidor",
    ),
    "V10.3": (N, "no es un servidor de recursos OAuth"),
    "V10.4": (N, "no es un servidor de autorización"),
    "V10.5": (N, "no es cliente OIDC"),
    "V10.6": (N, "no es proveedor OpenID"),
    "V10.7": (N, "sin gestión de consentimiento OAuth"),
    "V11.1": (
        X,
        "no hay un inventario criptográfico escrito [PENDIENTE: F8-04, ADR de inventario]",
    ),
    "V11.2": (
        V,
        "hashlib (SHA-256) y secrets; SHA-1 solo para buscar en GLPI con usedforsecurity=False (F2-03)",
    ),
    "V11.3": (
        N,
        "la aplicación no cifra datos: los secretos compartidos usan SOPS + age (ADR-029)",
    ),
    "V11.4": (V, "cadena SHA-256 (RD-03); las contraseñas las guarda Supabase"),
    "V11.5": (V, "secrets.token_urlsafe y token_hex para desafíos y nombres de archivo"),
    "V11.6": (N, "sin criptografía de clave pública propia"),
    "V12.1": (
        V,
        "solo TLS 1.2 y 1.3 con suites AEAD y PFS en el borde (testssl F7-07); autofirmado conforme a RS-01 (ADR-031); sin mTLS",
    ),
    "V12.2": (
        N,
        "sin servicios expuestos a internet: el borde solo atiende app.localhost y glpi.localhost (ADR-031, RS-01)",
    ),
    "V12.3": (
        P,
        "web y worker→PostgreSQL y worker→GLPI sin TLS dentro de redes internas de Docker (ADR-031): N-1, medido en F7-04",
    ),
    "V13.1": (V, "docs/estado.md y compose documentan servicios y comunicaciones"),
    "V13.2": (P, "API de BunkerWeb alcanzable desde la red app con token (N-2): F7-02"),
    "V13.3": (V, "secretos en /run/secrets; gitleaks 0 en historial (F2-05); SOPS + age"),
    "V13.4": (
        V,
        "DEBUG apagado, Server quitado, check --deploy limpio (F3-U08); errores genéricos (B-24)",
    ),
    "V14.1": (V, "RD-05 y SRS: campos restringidos y Ley 1581"),
    "V14.2": (V, "el centinela no sale de su tabla (Gherkin restringidos); filtro de logs (B-21)"),
    "V14.3": (V, "never_cache en el ingreso; sin almacenamiento en el navegador"),
    "V15.1": (V, "SRS, ADR y SBOM CycloneDX de 115 componentes (F2-07)"),
    "V15.2": (
        P,
        "pip-audit limpio tras B-15; imagen base con CVE del SO sin parche: B-18 aceptado",
    ),
    "V15.3": (V, "mypy strict; excepciones aisladas (B-19, B-20); revisión manual F2-08"),
    "V16.1": (V, "SRS RS-09"),
    "V16.2": (V, "logs JSON con correlation_id y filtro de campos prohibidos (B-21)"),
    "V16.3": (V, "sesion.fallida, decisiones, acceso.denegado (B-25), ficha.consultada"),
    "V16.4": (
        P,
        "la cadena de auditoría es inalterable; la copia al disco externo sin sobrescribir está verificada (L-01), pero no es almacenamiento inmutable (riesgo aceptado en ADR-031)",
    ),
    "V16.5": (V, "mensajes genéricos; B-19, B-20 y B-24 corregidos"),
    "V17.1": (N, "sin WebRTC"),
    "V17.2": (N, "sin WebRTC"),
    "V17.3": (N, "sin WebRTC"),
}


def main(origen: str) -> int:
    with Path(origen).open(encoding="utf-8") as f:
        filas = [r for r in csv.DictReader(f) if r["L"] in ("1", "2")]
    faltan = {r["section_id"] for r in filas} - set(S)
    if faltan:
        print("secciones sin clasificar:", sorted(faltan))
        return 1
    with DESTINO.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            [
                "req_id",
                "nivel",
                "capitulo",
                "seccion",
                "estado",
                "evidencia_o_motivo",
                "descripcion",
            ]
        )
        for r in filas:
            estado, nota = S[r["section_id"]]
            w.writerow(
                [
                    r["req_id"],
                    r["L"],
                    r["chapter_name"],
                    r["section_name"],
                    estado,
                    nota,
                    r["req_description"],
                ]
            )
    cuentas: dict[str, int] = {}
    for r in filas:
        cuentas[S[r["section_id"]][0]] = cuentas.get(S[r["section_id"]][0], 0) + 1
    total = len(filas)
    aplicables = total - cuentas.get(N, 0)
    print(f"{total} requisitos L1/L2 · {cuentas}")
    print(
        f"aplicables: {aplicables} · verificados: {cuentas.get(V, 0)} ({100 * cuentas.get(V, 0) / aplicables:.1f} % de los aplicables)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
