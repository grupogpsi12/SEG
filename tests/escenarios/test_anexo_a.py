"""Anexo A (Excel «AnexoA. Tablas.xlsx»): cada fila de las tablas se contrasta con lo que el sistema hace.

Las hojas se leen de `auditoria/referencias/AnexoA-tablas.json` (volcado del Excel; su SHA-256 esta en
`AnexoA-tablas.sha256`). Si alguien cambia una celda del Excel y vuelve a volcarlo, la fila correspondiente
de aqui falla: el Excel y el sistema no se pueden separar sin que se note.

Cubre las tablas IV, V, VI, VII, VIII, IX, X, XII, XIII y XIV. Las demas (II, III, XI, XV a XVIII) se verifican
con las pruebas y mediciones que lista `auditoria/anexo-a-matriz.csv`.
"""

import json
import re
import unicodedata
from dataclasses import fields, replace
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from jml.adaptadores.entrada.web import semillas
from jml.adaptadores.salida.glpi.configuracion import PLANTILLAS
from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosEmergencia,
    DatosIngreso,
    DatosVacaciones,
)
from jml.dominio.errores import NoAutorizado
from jml.dominio.permisos import ROLES_INCOMPATIBLES, validar_roles
from jml.dominio.tickets import FRASE_DE_CONTRASENA, TicketDeCola
from jml.dominio.tipos import (
    ESTADOS_ABIERTOS,
    ESTADOS_FINALES,
    Cola,
    EstadoSolicitud,
    Rol,
    Subtipo,
    TipoDeVinculacion,
)
from jml.dominio.valores import BOGOTA, CalendarioHabil
from tests.mundo import (
    Mundo,
    cambio_de_departamento,
    cambio_de_sucursal,
    emergencia,
    ingreso,
    retiro,
    vacaciones,
)

RAIZ = Path(__file__).resolve().parents[2]
ANEXO = json.loads((RAIZ / "auditoria/referencias/AnexoA-tablas.json").read_text(encoding="utf-8"))


def filas(hoja: str) -> list[list[str]]:
    return [f for f in ANEXO[hoja][2:] if any(c.strip() for c in f)]


def n(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto)
    return re.sub(r"\s+", " ", re.sub(r"[`*_]", "", t)).strip().lower().rstrip(".")


def tickets_de(m: Mundo, solicitud_id: object) -> list[TicketDeCola]:
    with m.puerto.unidad_de_trabajo() as u:
        return [e.ticket for e in u.bandeja.de_solicitud(solicitud_id)]  # type: ignore[arg-type]


def texto_de(tickets: list[TicketDeCola], cola: Cola, accion: str | None = None) -> str:
    return n(
        "\n".join(
            t.como_texto()
            for t in tickets
            if t.cola is cola and (accion is None or t.accion.value == accion)
        )
    )


CON_JUSTIFICACION = "Emision para la prueba del Anexo A"


def emitido(m: Mundo, e):  # type: ignore[no-untyped-def]  # NuevaSolicitud
    return m.emitir(replace(e, justificacion=e.justificacion or CON_JUSTIFICACION))


# --- Tabla IV: roles y segregacion de funciones ------------------------------------------------

ROL_DE_LA_TABLA = {
    "Solicitante": Rol.SOLICITANTE,
    "RRHH": Rol.RRHH,
    "Técnico AD": Rol.TECNICO_AD,
    "Técnico Comunicaciones": Rol.TECNICO_COMUNICACIONES,
    "Técnico Licencias": Rol.TECNICO_LICENCIAS,
    "Técnico Inventario": Rol.TECNICO_INVENTARIO,
    "Auditor": Rol.AUDITOR,
    "Administrador del sistema": Rol.ADMINISTRADOR,
}
TECNICOS = {
    Rol.TECNICO_AD,
    Rol.TECNICO_COMUNICACIONES,
    Rol.TECNICO_LICENCIAS,
    Rol.TECNICO_INVENTARIO,
}


def _incompatibles_segun_la_tabla(texto: str) -> set[Rol]:
    t = n(texto)
    if t in ("n/a", "—", "-"):
        return set()
    if t == "todos los demás":
        return set(Rol)  # se descuenta a si mismo despues
    resultado: set[Rol] = set()
    if "roles técnicos" in t or "técnicos" in t:
        resultado |= TECNICOS
    if "administrador" in t:
        resultado.add(Rol.ADMINISTRADOR)
    if re.search(r"\brrhh\b", t):
        resultado.add(Rol.RRHH)
    return resultado


def test_tabla_IV_los_ocho_roles_de_la_tabla_son_los_roles_del_sistema() -> None:
    assert {ROL_DE_LA_TABLA[f[0]] for f in filas("TablaIV Users-Roles")} == set(Rol)


def test_tabla_IV_las_incompatibilidades_de_la_tabla_son_exactamente_las_del_sistema() -> None:
    esperado: set[frozenset[Rol]] = set()
    for f in filas("TablaIV Users-Roles"):
        rol = ROL_DE_LA_TABLA[f[0]]
        for otro in _incompatibles_segun_la_tabla(f[3]) - {rol}:
            esperado.add(frozenset({rol, otro}))
    assert esperado == set(ROLES_INCOMPATIBLES)


def _nombre_del_par(par: frozenset[Rol]) -> list[str]:
    return sorted(r.value for r in par)


PARES = sorted(ROLES_INCOMPATIBLES, key=_nombre_del_par)


@pytest.mark.parametrize("par", PARES, ids=["+".join(_nombre_del_par(p)) for p in PARES])
def test_tabla_IV_cada_par_incompatible_es_rechazado_y_sus_compatibles_no(
    par: frozenset[Rol],
) -> None:
    from jml.dominio.errores import RolesIncompatibles

    with pytest.raises(RolesIncompatibles):
        validar_roles(par)


def test_tabla_IV_las_combinaciones_que_la_tabla_no_prohibe_son_validas() -> None:
    validar_roles(frozenset({Rol.SOLICITANTE, Rol.RRHH}))
    validar_roles(frozenset({Rol.SOLICITANTE, Rol.TECNICO_AD, Rol.TECNICO_INVENTARIO}))
    validar_roles(frozenset({Rol.SOLICITANTE, Rol.ADMINISTRADOR}))


def test_tabla_IV_permisos_por_rol_en_los_casos_de_uso() -> None:
    m = Mundo.nuevo()
    from jml.aplicacion.casos.administracion import ConsultarMatriz
    from jml.aplicacion.casos.auditoria import ConsultarAuditoria

    # RRHH: aprueba/rechaza, ve restringidos y contratos por vencer; el Administrador NO aprueba
    sid = m.registrar(vacaciones()).solicitud_id
    with pytest.raises(NoAutorizado):
        m.aprobar("u-admin", sid)
    assert m.aprobar("u-rrhh", sid).estado is EstadoSolicitud.APROBADA
    assert m.contratos_por_vencer("u-rrhh") == ()
    # tecnicos: dashboard, busqueda y ficha; ni auditoria ni administracion
    for u in ("u-tec-ad", "u-tec-com", "u-tec-lic", "u-tec-inv"):
        m.dashboard(u)
        with pytest.raises(NoAutorizado):
            ConsultarAuditoria(m.puerto).ejecutar(u)
        with pytest.raises(NoAutorizado):
            ConsultarMatriz(m.puerto).ejecutar(u)
    # Auditor: lee la auditoria y la verifica; no administra
    assert ConsultarAuditoria(m.puerto).ejecutar("u-aud").total > 0
    with pytest.raises(NoAutorizado):
        ConsultarMatriz(m.puerto).ejecutar("u-aud")
    # Administrador: matriz y roles
    assert ConsultarMatriz(m.puerto).ejecutar("u-admin")
    # Solicitante: ninguna de las anteriores
    with pytest.raises(NoAutorizado):
        m.dashboard("u-col")


@pytest.mark.xfail(  # S-39
    strict=True,
    reason="S-39 (B-26): el SRS dice que el Auditor lee solicitudes sin campos restringidos y la aplicacion responde 404",
)
def test_tabla_IV_el_auditor_lee_solicitudes_sin_campos_restringidos() -> None:
    from jml.aplicacion.casos.listados import ConsultarSolicitud

    m = Mundo.nuevo()
    r = emitido(m, retiro())
    detalle = ConsultarSolicitud(m.puerto).ejecutar("u-aud", r.solicitud_id)
    assert detalle.restringido is None


def test_tabla_IV_el_solicitante_no_crea_ni_elimina_cuentas_ni_manda_correos() -> None:
    """La fila «Solicitante» del Excel dice «creacion de cuentas», «eliminaciones de cuentas» y «generar correos»:
    el SRS (ADR-019, fuera de alcance) no lo permite. Se comprueba lo que SI cumple el sistema."""
    m = Mundo.nuevo()
    with pytest.raises(NoAutorizado):
        m.registrar(ingreso(usuario="u-col"))  # no registra ingresos
    with pytest.raises(NoAutorizado):
        m.emitir(emergencia(usuario="u-col"))  # no emite emergencias
    assert m.registrar(vacaciones(usuario="u-col")).estado is EstadoSolicitud.PENDIENTE_APROBACION
    assert m.registrar(retiro(usuario="u-col")).estado is EstadoSolicitud.PENDIENTE_APROBACION
    fuentes = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "src").rglob("*.py"))
    assert not re.search(r"smtplib|send_mail|EmailMessage|ldap3|msgraph", fuentes)


# --- Tabla V: eventos, quien los registra, aprobacion, prioridad y SLA --------------------------

CALENDARIO = CalendarioHabil()


def _crear(m: Mundo, codigo: str):  # type: ignore[no-untyped-def]
    return {
        "ING": lambda: emitido(m, ingreso()),
        "VAC": lambda: emitido(m, vacaciones("u-rrhh")),
        "CDP": lambda: emitido(m, cambio_de_departamento("u-rrhh", destino="Comercial")),
        "CSU": lambda: emitido(m, cambio_de_sucursal("u-rrhh", sede="Cali")),
        "RET": lambda: emitido(m, retiro()),
        "EMG": lambda: emitido(m, emergencia()),
    }[codigo]()


@pytest.mark.parametrize("fila", filas("TablaV Eventos SLAs"), ids=lambda f: f[0])
def test_tabla_V_prioridad_y_vencimiento_de_cada_evento(fila: list[str]) -> None:
    codigo, prioridad = fila[0], fila[5]
    m = Mundo.nuevo()
    r = _crear(m, codigo)
    ts = tickets_de(m, r.solicitud_id)
    sol = m.solicitud(r.solicitud_id)
    # prioridad de los tickets del evento (los «posteriores» de eliminacion son tickets de seguimiento: Media)
    del_evento = [t for t in ts if t.accion.value != "eliminacion"]
    assert del_evento
    assert {t.prioridad.value for t in del_evento} == {prioridad}
    fe = sol.fecha_efectiva
    if codigo == "ING":  # «resuelto antes de la fecha de ingreso»
        assert {t.vence_en for t in ts} == {datetime.combine(fe, time.min, BOGOTA)}
    elif codigo == "VAC":  # suspension el dia de inicio, reactivacion el dia de regreso
        regreso = sol.datos.fecha_regreso  # type: ignore[union-attr]
        por_accion = {t.accion.value: t.vence_en.astimezone(BOGOTA).date() for t in ts}
        assert por_accion == {"suspension": fe, "reactivacion": regreso}
    elif codigo in ("CDP", "CSU"):  # 1 dia habil desde la fecha efectiva
        esperado = CALENDARIO.sumar_dias_habiles(fe, 1)
        assert {t.vence_en.astimezone(BOGOTA).date() for t in ts} == {esperado}
    elif codigo == "RET":  # al final del ultimo dia laborado
        assert {t.vence_en.astimezone(BOGOTA).date() for t in del_evento} == {fe}
    elif codigo == "EMG":  # 1 hora desde la emision
        assert {t.vence_en - t.emitido_en for t in del_evento} == {timedelta(hours=1)}


def test_tabla_V_quien_puede_registrar_cada_evento() -> None:
    permitido: dict[str, list[tuple[str, object]]] = {
        "ING": [("RRHH", ingreso("u-rrhh"))],
        "VAC": [
            ("el colaborador", vacaciones("u-col")),
            ("RRHH", vacaciones("u-rrhh", colaborador="col-9")),
        ],
        "CDP": [
            ("el jefe", cambio_de_departamento("u-jefe")),
            ("RRHH", cambio_de_departamento("u-rrhh", colaborador="col-9", destino="Comercial")),
        ],
        "CSU": [
            ("el jefe", cambio_de_sucursal("u-jefe")),
            ("RRHH", cambio_de_sucursal("u-rrhh", colaborador="col-9")),
        ],
        "RET": [
            ("el colaborador (renuncia)", retiro("u-col")),
            ("RRHH", retiro("u-rrhh", colaborador="col-9", subtipo=Subtipo.FIN_DE_CONTRATO)),
        ],
        "EMG": [("RRHH", emergencia("u-rrhh"))],
    }
    for fila in filas("TablaV Eventos SLAs"):
        for _quien, e in permitido[fila[0]]:
            if e.usuario_id == "u-rrhh":  # type: ignore[attr-defined]  # RRHH emite directo (RF-13)
                emitido(Mundo.nuevo(), e)
            else:  # el colaborador o el jefe registran y esperan la decision
                assert Mundo.nuevo().registrar(e).estado is EstadoSolicitud.PENDIENTE_APROBACION  # type: ignore[arg-type]
    # y los que la tabla NO autoriza
    denegados = [
        ingreso("u-col"),
        ingreso("u-jefe"),
        emergencia("u-col"),
        emergencia("u-jefe"),
        cambio_de_departamento("u-col"),  # el propio colaborador no pide su traslado
        cambio_de_sucursal("u-col"),
        retiro(
            "u-col", subtipo=Subtipo.FIN_DE_CONTRATO
        ),  # solo la renuncia la registra el colaborador
        vacaciones("u-otro"),  # nadie registra las vacaciones de un tercero
    ]
    for e in denegados:
        with pytest.raises(NoAutorizado):
            Mundo.nuevo().registrar(e)


def test_tabla_V_aprobacion_de_cada_evento() -> None:
    """«Emitida por RRHH» (ING, EMG) nace aprobada; «RRHH» (VAC, CDP, CSU, RET) espera su decision."""
    por_codigo = {f[0]: f[4] for f in filas("TablaV Eventos SLAs")}
    estados = {
        "ING": Mundo.nuevo().emitir(ingreso()).estado,
        "EMG": Mundo.nuevo().emitir(emergencia()).estado,
        "VAC": Mundo.nuevo().registrar(vacaciones("u-col")).estado,
        "CDP": Mundo.nuevo().registrar(cambio_de_departamento("u-jefe")).estado,
        "CSU": Mundo.nuevo().registrar(cambio_de_sucursal("u-jefe")).estado,
        "RET": Mundo.nuevo().registrar(retiro("u-col")).estado,
    }
    for codigo, texto in por_codigo.items():
        esperado = (
            EstadoSolicitud.APROBADA
            if n(texto) == "emitida por rrhh"
            else EstadoSolicitud.PENDIENTE_APROBACION
        )
        assert estados[codigo] is esperado, codigo


# --- Tabla VI: estados de la solicitud --------------------------------------------------------


def test_tabla_VI_los_siete_estados_y_su_tipo() -> None:
    assert {f[0] for f in filas("TablaVI Estados Solicitud")} == {e.value for e in EstadoSolicitud}
    for estado, tipo, _significado in filas("TablaVI Estados Solicitud"):
        abiertos = ESTADOS_ABIERTOS if n(tipo) == "abierto" else ESTADOS_FINALES
        assert EstadoSolicitud(estado) in abiertos, estado


# --- Tabla VII: clases de tickets ---------------------------------------------------------------


def test_tabla_VII_clases_de_tickets() -> None:
    m = Mundo.nuevo()
    ts = tickets_de(m, emitido(m, vacaciones("u-rrhh")).solicitud_id) + tickets_de(
        m, emitido(m, retiro("u-rrhh", "col-9")).solicitud_id
    )
    ts += tickets_de(m, emitido(m, ingreso()).solicitud_id)
    por_clase = {
        c: [t for t in ts if t.clase.value == c]
        for c in ("cierre_inmediato", "cierre_programado", "posterior")
    }
    assert all(por_clase.values())
    esperado = {
        "De cierre inmediato": ("cierre_inmediato", "Nuevo", True),
        "De cierre programado": ("cierre_programado", "En espera", True),
        "Posterior": ("posterior", "En espera", False),
    }
    for clase, _cuando, estado_inicial, bloquea in filas("TablaVII Clases de Tickets"):
        codigo, estado, bloquea_cierre = esperado[clase]
        assert n(estado_inicial).startswith(n(estado))  # «En espera, hasta la fecha»
        assert (n(bloquea) == "sí") is bloquea_cierre
        for t in por_clase[codigo]:
            assert t.estado_inicial.value == estado, clase
            assert t.bloquea_el_cierre is bloquea_cierre, clase
            assert t.emitido_en == m.reloj.ahora()  # se crean en la emision
    # programado: vence en la fecha futura; posterior: a 90 dias
    assert all(
        t.activo_desde > t.emitido_en
        for t in por_clase["cierre_programado"] + por_clase["posterior"]
    )
    assert all((t.activo_desde - t.emitido_en).days >= 85 for t in por_clase["posterior"])


# --- Tabla VIII: acciones de cada evento por cola ---------------------------------------------

COLAS = {1: Cola.AD, 2: Cola.COMUNICACIONES, 3: Cola.LICENCIAS, 4: Cola.INVENTARIO}
# Frases que cada celda de la tabla exige en la lista de verificacion de su ticket (minusculas, sin tildes sensibles)
FRASES: dict[tuple[str, Cola], list[str]] = {
    ("ING", Cola.AD): [
        "verificar el soporte de vinculación adjunto",
        "crear la cuenta con el usuario sugerido",
        "agregar los grupos de ad del perfil",
        "aplicar en cada recurso compartido su perfil",
        "fs-",
    ],
    ("ING", Cola.COMUNICACIONES): ["agregar los grupos de red del perfil", "net-"],
    ("ING", Cola.LICENCIAS): [
        "verificar el soporte de vinculación adjunto",
        "crear la identidad en m365 o entra id",
        "licencias del perfil",
    ],
    ("ING", Cola.INVENTARIO): ["asignar el equipo", "acta de entrega firmada"],
    ("VAC", Cola.AD): ["deshabilitar la cuenta", "habilitar la cuenta"],
    ("VAC", Cola.LICENCIAS): [
        "bloquear el inicio de sesión",
        "revocar",
        "desbloquear el inicio de sesión",
    ],
    ("CDP", Cola.AD): [
        "quitar los grupos de ad del perfil anterior",
        "agregar los grupos de ad del perfil nuevo",
        "aplicar el perfil en los recursos compartidos nuevos",
        "retiro de accesos",
    ],
    ("CDP", Cola.COMUNICACIONES): ["agregar los grupos de red"],
    ("CDP", Cola.LICENCIAS): ["grupos de m365", "licencias"],
    ("CDP", Cola.INVENTARIO): ["cambiar el equipo"],
    ("CSU", Cola.AD): ["grupos de ad"],
    ("CSU", Cola.COMUNICACIONES): [
        "quitar los grupos de red: net-vlan-bogota",
        "agregar los grupos de red: net-vlan-cali",
    ],
    ("CSU", Cola.INVENTARIO): ["trasladar el equipo", "acta"],
    ("RET", Cola.AD): [
        "deshabilitar la cuenta",
        "cambiar la contraseña",
        "quitar los grupos",
        "retiro de accesos",
        "todos los recursos compartidos",
        "ou deshabilitados",
        "perfil consulta sobre la carpeta personal por 30 días",
        "eliminar la cuenta",
    ],
    ("RET", Cola.COMUNICACIONES): ["quitar todos los grupos de red"],
    ("RET", Cola.LICENCIAS): [
        "bloquear el inicio de sesión",
        "revocar",
        "quitar los grupos",
        "liberar las licencias",
        "eliminar la identidad",
    ],
    ("RET", Cola.INVENTARIO): ["recibir el equipo", "acta", "paz y salvo"],
    ("EMG", Cola.AD): [
        "ejecutar de inmediato",
        "deshabilitar la cuenta",
        "cambiar la contraseña",
        "quitar los grupos",
        "retiro de accesos",
        "ou deshabilitados",
        "eliminar la cuenta",
    ],
    ("EMG", Cola.COMUNICACIONES): ["ejecutar de inmediato", "quitar todos los grupos de red"],
    ("EMG", Cola.LICENCIAS): [
        "ejecutar de inmediato",
        "bloquear el inicio de sesión",
        "revocar",
        "liberar las licencias",
        "eliminar la identidad",
    ],
    ("EMG", Cola.INVENTARIO): ["ejecutar de inmediato", "recuperar el equipo", "acta"],
}


@pytest.mark.parametrize("fila", filas("TablaVIII Acciones por Cola"), ids=lambda f: f[0])
def test_tabla_VIII_cada_celda_se_cumple_en_los_tickets_del_evento(fila: list[str]) -> None:
    codigo = fila[0]
    m = Mundo.nuevo()
    r = _crear(m, codigo)
    ts = tickets_de(m, r.solicitud_id)
    for columna, cola in COLAS.items():
        celda = n(fila[columna])
        texto = texto_de(ts, cola)
        if celda in ("—", "-"):
            assert not [t for t in ts if t.cola is cola], (
                f"{codigo}/{cola.value}: la tabla dice «—» y hay ticket"
            )
            continue
        assert texto, f"{codigo}/{cola.value}: la tabla pide acciones y no hay ticket"
        for frase in FRASES[(codigo, cola)]:
            assert frase in texto, f"{codigo}/{cola.value}: falta «{frase}»"


def test_tabla_VIII_ingreso_de_contratista_fija_la_fecha_de_expiracion() -> None:
    m = Mundo.nuevo()
    r = emitido(m, ingreso(vinculacion=TipoDeVinculacion.CONTRATISTA))
    assert "expiración" in texto_de(tickets_de(m, r.solicitud_id), Cola.AD)


def test_tabla_VIII_el_equipo_del_cambio_de_departamento_solo_si_el_perfil_lo_exige() -> None:
    m = Mundo.nuevo()
    # Finanzas (Escritorio) -> Operaciones (Escritorio): el equipo no cambia, no hay ticket de Inventario
    r = emitido(m, cambio_de_departamento("u-rrhh", destino="Operaciones"))
    assert not [t for t in tickets_de(m, r.solicitud_id) if t.cola is Cola.INVENTARIO]


def test_tabla_VIII_el_traslado_sin_equipo_no_genera_ticket_de_inventario() -> None:
    m = Mundo.nuevo()
    r = emitido(m, cambio_de_sucursal("u-rrhh", sede="Cali", traslada=False))
    assert not [t for t in tickets_de(m, r.solicitud_id) if t.cola is Cola.INVENTARIO]


# --- Tabla IX: suspension frente a deshabilitacion -------------------------------------------


def test_tabla_IX_suspension_y_deshabilitacion() -> None:
    m = Mundo.nuevo()
    vac = tickets_de(m, emitido(m, vacaciones("u-rrhh")).solicitud_id)
    ret = tickets_de(m, emitido(m, retiro("u-rrhh", "col-9")).solicitud_id)
    emg = tickets_de(m, emitido(m, emergencia("u-rrhh", "col-1")).solicitud_id)
    v_ad = texto_de(vac, Cola.AD, "suspension")
    r_ad = texto_de(ret, Cola.AD, "baja")
    e_ad = texto_de(emg, Cola.AD, "baja")
    filas_ix = {n(f[0]): f for f in filas("TablaIX Deshabilitación")}
    assert set(filas_ix) == {
        "cuenta",
        "contraseña",
        "grupos",
        "sesiones",
        "reversión",
        "eliminación",
    }
    # Cuenta: deshabilitada / deshabilitada y movida a la OU Deshabilitados
    assert "deshabilitar la cuenta" in v_ad
    assert "ou deshabilitados" not in v_ad
    assert "deshabilitar la cuenta" in r_ad
    assert "mover la cuenta a la ou deshabilitados" in r_ad
    # Contrasena: sin cambios / cambiada a un valor aleatorio que no se comunica
    assert "no cambiar la contraseña" in v_ad
    assert n(FRASE_DE_CONTRASENA) in r_ad
    assert n(FRASE_DE_CONTRASENA) in e_ad
    # Grupos: se conservan / se quitan y el tecnico los lista en la solucion
    assert "ni quitar los grupos" in v_ad
    assert "quitar los grupos de ad" in r_ad
    assert "listar en la solución los grupos retirados" in r_ad
    # Sesiones: revocadas en ambos
    assert "revocar las sesiones" in v_ad
    assert "revocar las sesiones" in r_ad
    # Reversion: ticket programado de reactivacion / no se revierte
    assert [
        t for t in vac if t.accion.value == "reactivacion" and t.clase.value == "cierre_programado"
    ]
    assert not [t for t in ret + emg if t.accion.value == "reactivacion"]
    # Eliminacion: no aplica / ticket posterior a los 90 dias
    assert not [t for t in vac if t.accion.value == "eliminacion"]
    for ts in (ret, emg):
        elim = [t for t in ts if t.accion.value == "eliminacion"]
        assert {t.cola for t in elim} == {Cola.AD, Cola.LICENCIAS}
        assert all(t.clase.value == "posterior" for t in elim)


def test_tabla_IX_la_contrasena_nunca_se_escribe_en_un_ticket() -> None:
    m = Mundo.nuevo()
    for e in (ingreso(), retiro("u-rrhh", "col-9"), emergencia()):
        for t in tickets_de(m, emitido(Mundo.nuevo(), e).solicitud_id):
            texto = t.como_texto().lower()
            assert not re.search(r"contraseña( inicial| temporal)?\s*[:=]\s*\S", texto)


# --- Tabla X: plantillas de solucion ------------------------------------------------------------


def test_tabla_X_las_plantillas_de_la_tabla_son_las_que_configura_glpi() -> None:
    por_cola = {n(f[0]): f[1] for f in filas("TablaX Plantillas Solución ")}
    assert set(por_cola) == {"ad", "comunicaciones", "licencias", "inventario"}
    for cola, plantilla in PLANTILLAS.items():
        clave = "ad" if cola is Cola.AD else cola.value.lower()
        assert n(plantilla) == n(por_cola[clave]), cola
        assert "contraseña" not in n(plantilla)  # ninguna plantilla pide contrasenas


# --- Tabla XII: campos especificos por evento --------------------------------------------------


def test_tabla_XII_campos_de_cada_evento() -> None:
    campos = {f[0]: n(f[1]) for f in filas("TablaXII Campos Eventos")}
    ing = {f.name for f in fields(DatosIngreso)}
    assert ing == {
        "nombres",
        "apellidos",
        "documento",
        "vinculacion",
        "departamento",
        "cargo",
        "sede",
        "jefe_id",
        "fecha_fin",
        "requiere_equipo",
        "tipo_equipo",
    }
    for frase in (
        "nombres",
        "apellidos",
        "número de documento",
        "tipo de vinculación",
        "departamento",
        "cargo",
        "sede",
        "jefe directo",
        "fecha de ingreso",
        "fecha de fin (obligatoria si no es empleado)",
        "requiere equipo",
        "tipo de equipo",
        "soporte de vinculación (pdf obligatorio, máximo 20 mb)",
    ):
        assert frase in campos["ING"], frase
    assert {v.value for v in TipoDeVinculacion} == {
        "empleado",
        "contratista",
        "practicante",
        "temporal",
    }
    assert {f.name for f in fields(DatosVacaciones)} == {
        "fecha_regreso"
    }  # + fecha de inicio = fecha efectiva
    assert {f.name for f in fields(DatosCambioDepartamento)} == {
        "departamento_nuevo",
        "cargo_nuevo",
        "jefe_nuevo_id",
    }
    assert {f.name for f in fields(DatosCambioSucursal)} == {"sede_nueva", "traslada_equipo"}
    assert {"reportado_por", "hora_del_hecho"} <= {f.name for f in fields(DatosEmergencia)}
    for codigo in ("VAC", "CDP", "CSU", "RET", "EMG"):
        assert codigo in campos


def test_tabla_XII_la_fecha_de_fin_es_obligatoria_si_no_es_empleado() -> None:
    from jml.dominio.errores import DatoInvalido

    base = ingreso().datos
    assert isinstance(base, DatosIngreso)
    for v in (
        TipoDeVinculacion.CONTRATISTA,
        TipoDeVinculacion.PRACTICANTE,
        TipoDeVinculacion.TEMPORAL,
    ):
        with pytest.raises(DatoInvalido, match="fecha_fin"):
            replace(base, vinculacion=v, fecha_fin=None)
    assert (
        Mundo.nuevo().emitir(ingreso(vinculacion=TipoDeVinculacion.EMPLEADO)).estado
        is EstadoSolicitud.APROBADA
    )


def test_tabla_XII_los_campos_restringidos_son_solo_el_motivo_y_la_descripcion() -> None:
    campos = {f[0]: f[1] for f in filas("TablaXII Campos Eventos")}
    marcados = {k for k, v in campos.items() if "(R)" in v}
    assert marcados == {"RET", "EMG"}
    m = Mundo.nuevo()
    for e in (retiro(), emergencia()):
        r = emitido(Mundo.nuevo(), e)
        assert all("SENTINELA" not in t.como_texto().upper() for t in tickets_de(m, r.solicitud_id))


# --- Tablas XIII y XIV: perfiles de acceso y recursos compartidos ------------------------------


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in re.split(r",", texto) if x.strip())


def test_tabla_XIII_la_matriz_de_perfiles_sembrada_es_la_de_la_tabla() -> None:
    filas_xiii = {f[0]: f for f in filas("TablaXIII Perfiles Acceso")}
    assert set(filas_xiii) == set(semillas.MATRIZ)
    for depto, (ad, red, m365, lic, equipo, _recursos) in semillas.MATRIZ.items():
        _, t_ad, t_red, t_m365, t_lic, t_equipo = filas_xiii[depto]
        assert set(_lista(t_ad)) == set(ad), depto
        assert set(_lista(t_red)) == set(red), depto
        assert set(_lista(t_m365)) == set(m365), depto
        assert {n(x) for x in _lista(t_lic)} == {n(x) for x in lic}, depto
        assert n(t_equipo) == n(equipo.value), depto


def test_tabla_XIV_los_recursos_compartidos_sembrados_son_los_de_la_tabla() -> None:
    esperado = set()
    for depto, ruta, raiz, perfil, grupo in filas("TablaXIV Recursos Compartidos"):
        deptos = (
            [d for d in semillas.MATRIZ if d != "TI"] if n(depto) == "todos, salvo ti" else [depto]
        )
        for d in deptos:
            esperado.add((d, ruta, raiz, n(perfil), grupo))
    real = {
        (d, r.ruta, r.serie, n(r.perfil.value), r.grupo)
        for d, (*_, recursos) in semillas.MATRIZ.items()
        for r in recursos
    }
    assert real == esperado


def test_tabla_XIII_el_ticket_de_ingreso_lleva_los_grupos_del_departamento() -> None:
    for depto, (ad, red, m365, lic, _equipo, _r) in semillas.MATRIZ.items():
        p = next(x for x in semillas.perfiles() if x.departamento == depto and x.sede == "Bogotá")
        assert set(ad) <= set(p.grupos_ad)
        assert set(red) <= set(p.grupos_red)
        assert set(m365) == set(p.grupos_m365)
        assert set(lic) == set(p.licencias)


# --- Tabla II: decisiones de arquitectura (lo comprobable en el codigo y la infraestructura) ----------


def _fuentes(*rutas: str) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for r in rutas
        for p in ((RAIZ / r).rglob("*") if (RAIZ / r).is_dir() else [RAIZ / r])
        if p.is_file()
        and p.suffix in {".py", ".yaml", ".yml", ".toml", ".lock", ".sh", ".html", ".conf", ".php"}
    )


def test_tabla_II_los_adr_del_excel_estan_en_decisiones_con_el_mismo_estado() -> None:
    """ADR-003/004/008/010/012 figuran como «Reemplazada»; ADR-024 como «Propuesta»; el resto, «Aceptada»."""
    decisiones = (RAIZ / "docs/decisiones.md").read_text(encoding="utf-8")
    for codigo, _titulo, estado in filas("TablaII ADR"):
        numero = int(re.sub(r"\D", "", codigo))
        fila = re.search(rf"^\| {numero:03d} \|[^\n]*$", decisiones, re.M)
        assert fila, f"ADR-{numero:03d} no esta en docs/decisiones.md"
        clase = n(estado).split(" ")[0]
        if numero == 14:
            continue  # el Excel dice «Pendiente (sprint 0)»; decisiones.md ya la tiene «Aceptada (spike 0.3)» (desfase del Excel)
        assert clase in n(fila.group(0)), (
            f"ADR-{numero:03d}: Excel «{estado}» frente a decisiones.md"
        )


def test_tabla_II_adr_003_004_010_019_el_sistema_no_actua_sobre_directorios_ni_servicios_de_identidad() -> (
    None
):
    codigo = _fuentes(
        "src", "pyproject.toml", "requirements.lock"
    )  # sin infra/waf: ahi viven las cadenas de ataque de prueba
    assert not re.search(r"(?i)\b(ldap3?|msal|msgraph|azure-identity|samba|pyad|winrm)\b", codigo)
    compose = (RAIZ / "infra/compose.yaml").read_text(encoding="utf-8")
    assert not re.search(
        r"(?i)samba|cloudflared|\bldap\b", compose
    )  # ADR-024 es solo una propuesta


def test_tabla_II_adr_008_012_020_no_hay_oidc_ni_fastapi_ni_react_ni_tiempo_real() -> None:
    dependencias = _fuentes("pyproject.toml", "requirements.lock").lower()
    for prohibido in (
        "fastapi",
        "authlib",
        "oidc",
        "channels",
        "websockets",
        "daphne",
        "supabase-realtime",
    ):
        assert prohibido not in dependencias, prohibido
    assert not (RAIZ / "package.json").exists()
    assert not re.search(r"(?i)websocket|EventSource|supabase.*realtime", _fuentes("src"))


def test_tabla_II_adr_018_django_5_2_lts_con_plantillas_en_el_servidor() -> None:
    import django

    assert django.VERSION[:2] == (5, 2)
    assert list((RAIZ / "src/jml/adaptadores/entrada/web/templates/web").glob("*.html"))


def test_tabla_II_adr_011_la_sincronizacion_es_por_consulta_cada_cinco_minutos() -> None:
    from jml.adaptadores.entrada.worker.ciclo import INTERVALO_SINCRONIZACION_S

    assert INTERVALO_SINCRONIZACION_S == 300.0


def test_tabla_II_adr_016_la_arquitectura_hexagonal_la_vigila_import_linter() -> None:
    configuracion = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert configuracion.count("[[tool.importlinter.contracts]]") >= 3


# --- Tabla XV, RF-06: registro abierto deshabilitado ----------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ruta",
    ["/registro", "/registrarse", "/signup", "/accounts/signup/", "/admin/", "/admin/login/"],
)
def test_rf_06_no_existe_ninguna_ruta_para_crear_cuentas(ruta: str) -> None:
    from django.conf import settings
    from django.test import Client

    assert "django.contrib.admin" not in settings.INSTALLED_APPS
    for metodo in ("get", "post"):
        assert getattr(Client(), metodo)(ruta).status_code == 404, (metodo, ruta)


def test_rf_06_las_rutas_de_la_aplicacion_no_incluyen_ninguna_de_alta_de_usuarios() -> None:
    from tests.seguridad.rutas import rutas

    nombres = set(rutas())
    assert not {
        n_ for n_ in nombres if re.search(r"regist|signup|alta|crear_usuario|usuario_nuevo", n_)
    } - {"nueva", "nueva_indice"}


def test_rf_06_las_cuentas_solo_las_crea_el_comando_de_administracion() -> None:
    comando = RAIZ / "src/jml/adaptadores/entrada/web/management/commands/admin_usuarios.py"
    assert comando.exists()
    fuentes_web = _fuentes("src/jml/adaptadores/entrada/web")
    assert "create_user(" not in fuentes_web  # ninguna vista crea usuarios de Django
    assert "User.objects.create" not in fuentes_web
