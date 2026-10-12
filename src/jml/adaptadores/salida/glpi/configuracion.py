"""Configuracion de GLPI como codigo (item 3.1, RF-19, SRS 4.6). Idempotente: busca por nombre
y solo crea lo que falta, asi que se puede correr en cada despliegue.

Confirmado contra GLPI 11.0.11 real (spike 0.3): los codigos de condicion y de accion de las
reglas (RuleTicket, RuleCriteria, RuleAction, SLM/SLA/SlaLevel) enrutan cada cola a su grupo
(CA-03). Necesita un token de un usuario administrador de GLPI, no el de servicio.

Lo que NO configura (pasos manuales documentados en docs/operacion.md): habilitar la API, el
perfil de la cuenta de servicio y el doble factor de los tecnicos.
"""

from dataclasses import dataclass

from jml.adaptadores.salida.glpi.cliente import ClienteGlpiV1
from jml.dominio.tickets import categoria_del_ticket
from jml.dominio.tipos import AccionDeTicket, Cola, TipoEvento

GRUPOS = {
    Cola.AD: "JML - AD",
    Cola.COMUNICACIONES: "JML - Comunicaciones",
    Cola.LICENCIAS: "JML - Licencias",
    Cola.INVENTARIO: "JML - Inventario",
    Cola.REVISION_MANUAL: "JML - Revisión manual",
}

# GLPI: RuleCriteria.condition 6 = «coincide con la expresion regular», 9 = «no existe».
# RuleTicket.condition 1 = al crear. Prioridad 5 = muy alta. (Spike 0.3.)
_REGEX, _NO_EXISTE, _ES = 6, 9, 0
_AL_CREAR = 1

# SRS 4.6: ninguna plantilla tiene campo de contrasena (T9).
PLANTILLAS = {
    Cola.AD: (
        "Acción realizada; usuario (sAMAccountName); soporte de vinculación verificado (sí/no, "
        "solo en ingresos); grupos agregados; grupos retirados; recursos compartidos (ruta – "
        "perfil aplicado o retirado); OU final; fecha y hora de ejecución; observaciones."
    ),
    Cola.COMUNICACIONES: (
        "Acción realizada; grupos de red agregados; grupos de red retirados; fecha y hora; "
        "observaciones."
    ),
    Cola.LICENCIAS: (
        "Acción realizada; identidad (UPN); soporte de vinculación verificado (sí/no, solo en "
        "ingresos); grupos agregados o retirados; licencias asignadas o liberadas en GLPI; "
        "sesiones revocadas (sí/no); fecha y hora."
    ),
    Cola.INVENTARIO: (
        "Acción realizada; número de serie; modelo; entregado o recibido; acta adjunta (sí/no); "
        "paz y salvo (sí/no)."
    ),
}


def categorias() -> list[str]:
    """Todas las categorias que el dominio puede producir (`categoria_del_ticket`). Inventario
    solo trabaja equipos y los equipos solo van a Inventario; el resto, todas las acciones."""
    resultado = []
    for tipo in TipoEvento:
        for cola in (Cola.AD, Cola.COMUNICACIONES, Cola.LICENCIAS, Cola.INVENTARIO):
            for accion in AccionDeTicket:
                if (cola is Cola.INVENTARIO) == (accion is AccionDeTicket.EQUIPO):
                    resultado.append(categoria_del_ticket(tipo, cola, accion))
    return resultado


@dataclass(frozen=True, slots=True)
class ResumenDeConfiguracion:
    grupos: int
    categorias: int
    reglas: int
    plantillas: int
    sla_de_emergencia: str


class ConfiguradorGlpi(ClienteGlpiV1):
    def configurar(self) -> ResumenDeConfiguracion:
        grupos = {
            cola: self._asegurar("Group", nombre, {"is_assign": 1, "is_requester": 0})
            for cola, nombre in GRUPOS.items()
        }
        cats = [
            self._asegurar("ITILCategory", c, {"is_incident": 1, "is_request": 1})
            for c in categorias()
        ]
        reglas = 0
        for rango, (cola, grupo) in enumerate(grupos.items(), start=1):
            if cola is Cola.REVISION_MANUAL:
                # RF-19: sin categoria reconocida -> Revision manual.
                criterio = ("itilcategories_id", _NO_EXISTE, "0")
            else:
                criterio = ("itilcategories_id", _REGEX, f"/^JML\\/[A-Z]+\\/{cola.value}\\//")
            reglas += self._regla(
                f"JML - asignar {GRUPOS[cola]}", rango, criterio, "_groups_id_assign", grupo
            )
        sla = self._sla_de_emergencia(grupos[Cola.REVISION_MANUAL])
        reglas += self._regla(
            "JML - SLA de emergencia", len(grupos) + 1, ("priority", _ES, "5"), "slas_id_ttr", sla
        )
        plantillas = [
            self._asegurar("SolutionTemplate", f"JML - {GRUPOS[cola][6:]}", {"content": texto})
            for cola, texto in PLANTILLAS.items()
        ]
        return ResumenDeConfiguracion(len(grupos), len(cats), reglas, len(plantillas), sla)

    def _regla(
        self, nombre: str, rango: int, criterio: tuple[str, int, str], campo: str, valor: str
    ) -> int:
        """Crea la regla con su criterio y su accion solo si no existe (idempotente)."""
        if self._unico("RuleTicket", nombre) is not None:
            return 1
        regla = self._crear(
            "RuleTicket",
            {
                "name": nombre,
                "sub_type": "RuleTicket",
                "match": "AND",
                "is_active": 1,
                "condition": _AL_CREAR,
                "ranking": rango,
            },
        )
        self._crear(
            "RuleCriteria",
            {
                "rules_id": regla,
                "criteria": criterio[0],
                "condition": criterio[1],
                "pattern": criterio[2],
            },
        )
        self._crear(
            "RuleAction",
            {"rules_id": regla, "action_type": "assign", "field": campo, "value": valor},
        )
        return 1

    def _sla_de_emergencia(self, grupo_de_escalamiento: str) -> str:
        """EMG: resolver en 1 hora; al vencer se escala a «Revision manual» (S-33, CA-06)."""
        slm = self._asegurar("SLM", "JML", {})
        sla = self._asegurar(
            "SLA",
            "JML - Emergencia 1 h",
            {"slms_id": slm, "type": 0, "number_time": 1, "definition_time": "hour"},
        )
        nivel = "JML - Escalar emergencia vencida"
        if self._unico("SlaLevel", nivel) is None:
            id_nivel = self._crear(
                "SlaLevel",
                {
                    "name": nivel,
                    "slas_id": sla,
                    "execution_time": 0,
                    "match": "AND",
                    "is_active": 1,
                },
            )
            self._crear(
                "SlaLevelAction",
                {
                    "slalevels_id": id_nivel,
                    "action_type": "assign",
                    "field": "_groups_id_assign",
                    "value": grupo_de_escalamiento,
                },
            )
        return sla
