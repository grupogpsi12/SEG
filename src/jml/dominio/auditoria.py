"""Auditoria encadenada (RD-03, RF-35, RF-36, ADR-007, CA-09).

Formato canonico (definido UNA sola vez, aqui; el adaptador de PostgreSQL debe reproducirlo):

    contenido = JSON de {"secuencia", "fecha", "actor", "accion", "objeto", "datos"} con
                claves ordenadas, separadores "," y ":" sin espacios, UTF-8 sin escapar,
                fecha en UTC como AAAA-MM-DDTHH:MM:SS.ffffffZ, tuplas como listas.
    hash      = SHA-256( hash_anterior_en_hex_ascii  ||  contenido )   [concatenacion de bytes]
    genesis   = 64 ceros: es el `hash_anterior` del primer registro (secuencia 1).

La auditoria nunca recibe campos restringidos (RD-05): `EventoDeAuditoria` los rechaza.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TypeAlias

from jml.dominio.errores import CampoRestringidoProhibido, DatoInvalido
from jml.dominio.valores import CampoRestringido, a_utc, texto_no_vacio

HASH_GENESIS = "0" * 64

# TypeAlias y no `type X = ...`: mutmut 2 (parso) no entiende la sintaxis de PEP 695.
Escalar: TypeAlias = str | int | bool | None
ValorAuditable: TypeAlias = Escalar | tuple[Escalar, ...]

# Nombres que jamas viajan a la auditoria (SRS 6.3 y CLAUDE.md, reglas de seguridad de codigo).
CLAVES_PROHIBIDAS = frozenset(
    {"password", "contrasena", "contraseña", "token", "totp", "secret", "motivo", "descripcion"}
)


def _validar_valor(clave: str, valor: object) -> ValorAuditable:
    if isinstance(valor, CampoRestringido):
        raise CampoRestringidoProhibido("auditoria")
    if valor is None or isinstance(valor, str | int | bool):
        return valor
    if isinstance(valor, tuple):
        for elemento in valor:
            if isinstance(elemento, CampoRestringido):
                raise CampoRestringidoProhibido("auditoria")
            if not (elemento is None or isinstance(elemento, str | int | bool)):
                raise DatoInvalido(f"datos.{clave}", "tipo no auditable")
        return valor
    raise DatoInvalido(f"datos.{clave}", "tipo no auditable")


@dataclass(frozen=True, slots=True)
class EventoDeAuditoria:
    """Lo que un caso de uso o una operacion del dominio quiere dejar en la cadena."""

    accion: str
    objeto: str
    datos: Mapping[str, ValorAuditable]

    def __post_init__(self) -> None:
        texto_no_vacio("accion", self.accion)
        texto_no_vacio("objeto", self.objeto)
        limpios: dict[str, ValorAuditable] = {}
        for clave, valor in self.datos.items():
            if clave.lower() in CLAVES_PROHIBIDAS:
                raise CampoRestringidoProhibido("auditoria")
            limpios[clave] = _validar_valor(clave, valor)
        object.__setattr__(self, "datos", MappingProxyType(limpios))


def _a_json(valor: object) -> object:
    if isinstance(valor, tuple):
        return [_a_json(v) for v in valor]
    return valor


def formatear_fecha(fecha: datetime) -> str:
    return a_utc(fecha).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def contenido_canonico(
    secuencia: int,
    fecha: datetime,
    actor: str,
    accion: str,
    objeto: str,
    datos: Mapping[str, ValorAuditable],
) -> bytes:
    cuerpo = {
        "secuencia": secuencia,
        "fecha": formatear_fecha(fecha),
        "actor": actor,
        "accion": accion,
        "objeto": objeto,
        "datos": {k: _a_json(v) for k, v in datos.items()},
    }
    return json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def calcular_hash(hash_anterior: str, contenido: bytes) -> str:
    return hashlib.sha256(hash_anterior.encode("ascii") + contenido).hexdigest()


@dataclass(frozen=True, slots=True)
class RegistroDeAuditoria:
    secuencia: int
    fecha: datetime
    actor: str
    accion: str
    objeto: str
    datos: Mapping[str, ValorAuditable]
    hash_anterior: str
    hash: str

    def contenido(self) -> bytes:
        return contenido_canonico(
            self.secuencia, self.fecha, self.actor, self.accion, self.objeto, self.datos
        )


def encadenar(
    anterior: RegistroDeAuditoria | None, fecha: datetime, actor: str, evento: EventoDeAuditoria
) -> RegistroDeAuditoria:
    """Construye el registro siguiente de la cadena."""
    secuencia = 1 if anterior is None else anterior.secuencia + 1
    hash_anterior = HASH_GENESIS if anterior is None else anterior.hash
    contenido = contenido_canonico(
        secuencia, fecha, actor, evento.accion, evento.objeto, evento.datos
    )
    return RegistroDeAuditoria(
        secuencia=secuencia,
        fecha=a_utc(fecha),
        actor=texto_no_vacio("actor", actor),
        accion=evento.accion,
        objeto=evento.objeto,
        datos=evento.datos,
        hash_anterior=hash_anterior,
        hash=calcular_hash(hash_anterior, contenido),
    )


@dataclass(frozen=True, slots=True)
class ResultadoDeVerificacion:
    valida: bool
    primer_afectado: int | None  # posicion 1-based del primer registro que falla
    motivo: str | None


def verificar_cadena(registros: Sequence[RegistroDeAuditoria]) -> ResultadoDeVerificacion:
    """Recorre la cadena completa desde el genesis e indica el PRIMER registro afectado (CA-09).

    Limite conocido: quitar los registros del final no se detecta por la cadena sola; para eso
    existe la copia inmutable en Blob (RD-04).
    """
    previo = HASH_GENESIS
    for posicion, registro in enumerate(registros, start=1):
        if registro.secuencia != posicion:
            return ResultadoDeVerificacion(False, posicion, "secuencia")
        if registro.hash_anterior != previo:
            return ResultadoDeVerificacion(False, posicion, "enlace")
        if registro.hash != calcular_hash(previo, registro.contenido()):
            return ResultadoDeVerificacion(False, posicion, "hash")
        previo = registro.hash
    return ResultadoDeVerificacion(True, None, None)
