"""Activos y licencias asignados en GLPI (RF-23, RF-33). Son copias de lo que GLPI informa."""

from dataclasses import dataclass
from datetime import date

from jml.dominio.valores import texto_no_vacio


@dataclass(frozen=True, slots=True)
class ActivoAsignado:
    id_glpi: str
    tipo: str
    serie: str
    modelo: str
    asignado_desde: date
    tiene_acta: bool

    def __post_init__(self) -> None:
        for campo in ("id_glpi", "tipo", "serie", "modelo"):
            texto_no_vacio(campo, getattr(self, campo))


@dataclass(frozen=True, slots=True)
class LicenciaAsignada:
    id_glpi: str
    software: str
    licencia: str

    def __post_init__(self) -> None:
        for campo in ("id_glpi", "software", "licencia"):
            texto_no_vacio(campo, getattr(self, campo))
