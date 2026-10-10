"""Objetos de valor. Toda construccion invalida lanza `DatoInvalido`, nunca `ValueError`."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import NoReturn

from jml.dominio.errores import CampoRestringidoProhibido, DatoInvalido

# S-02: Colombia no tiene horario de verano, asi que UTC-5 fijo equivale a America/Bogota y
# evita depender de la base de zonas horarias (no existe en Windows ni en imagenes minimas).
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")

MAX_SOPORTE_BYTES = 20 * 1024 * 1024  # S-12: 20 MiB exactos se aceptan


# --- tiempo -----------------------------------------------------------------------------------


def a_utc(momento: datetime, campo: str = "fecha") -> datetime:
    """Exige un instante con zona horaria y lo normaliza a UTC (S-02)."""
    if momento.tzinfo is None or momento.utcoffset() is None:
        raise DatoInvalido(campo, "debe incluir zona horaria")
    return momento.astimezone(UTC)


def hoy_en_bogota(ahora: datetime) -> date:
    return a_utc(ahora, "ahora").astimezone(BOGOTA).date()


def inicio_del_dia(dia: date) -> datetime:
    """00:00 en Bogota, en UTC (S-02)."""
    return datetime.combine(dia, time(0, 0, 0), BOGOTA).astimezone(UTC)


def fin_del_dia(dia: date) -> datetime:
    """23:59:59 en Bogota, en UTC (S-02)."""
    return datetime.combine(dia, time(23, 59, 59), BOGOTA).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FechaEfectiva:
    valor: date

    def __post_init__(self) -> None:
        # `datetime` es subclase de `date`: se rechaza para no mezclar instantes con fechas.
        if type(self.valor) is not date:
            raise DatoInvalido("fecha_efectiva", "debe ser una fecha, sin hora")

    def inicio_del_dia(self) -> datetime:
        return inicio_del_dia(self.valor)

    def fin_del_dia(self) -> datetime:
        return fin_del_dia(self.valor)

    def mas_dias(self, dias: int) -> "FechaEfectiva":
        return FechaEfectiva(self.valor + timedelta(days=dias))


@dataclass(frozen=True, slots=True)
class CalendarioHabil:
    """S-01: lunes a viernes; los festivos entran como datos."""

    festivos: frozenset[date] = frozenset()

    def es_habil(self, dia: date) -> bool:
        return dia.weekday() < 5 and dia not in self.festivos

    def sumar_dias_habiles(self, desde: date, dias: int) -> date:
        """Primer dia habil estrictamente posterior a `desde`, repetido `dias` veces."""
        if dias < 0:
            raise DatoInvalido("dias", "no puede ser negativo")
        actual = desde
        restantes = dias
        while restantes > 0:
            actual += timedelta(days=1)
            if self.es_habil(actual):
                restantes -= 1
        return actual


# --- texto ------------------------------------------------------------------------------------


def texto_no_vacio(campo: str, valor: str, maximo: int = 200) -> str:
    limpio = valor.strip()
    if not limpio:
        raise DatoInvalido(campo, "no puede estar vacio")
    if len(limpio) > maximo:
        raise DatoInvalido(campo, f"no puede superar {maximo} caracteres")
    return limpio


def ascii_minuscula(texto: str) -> str:
    """Quita tildes (n con tilde -> n), pasa a minusculas y descarta lo que no sea ASCII."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_marcas.encode("ascii", "ignore").decode("ascii").lower()


# --- identificadores y cuentas ----------------------------------------------------------------

_RE_SOLICITUD = re.compile(r"^SOL-(\d{4})-(\d{6})$")


@dataclass(frozen=True, slots=True)
class SolicitudId:
    valor: str

    def __post_init__(self) -> None:
        if not _RE_SOLICITUD.fullmatch(self.valor):
            raise DatoInvalido("solicitud_id", "formato esperado SOL-AAAA-NNNNNN")

    @classmethod
    def de(cls, anio: int, numero: int) -> "SolicitudId":
        if not 1000 <= anio <= 9999 or not 0 <= numero <= 999_999:
            raise DatoInvalido("solicitud_id", "anio o numero fuera de rango")
        return cls(f"SOL-{anio:04d}-{numero:06d}")

    def __str__(self) -> str:
        return self.valor


_RE_DOCUMENTO = re.compile(r"^[A-Z0-9]{5,15}$")


@dataclass(frozen=True, slots=True)
class Documento:
    valor: str

    def __post_init__(self) -> None:
        normalizado = self.valor.strip().upper()
        if not _RE_DOCUMENTO.fullmatch(normalizado):
            raise DatoInvalido("documento", "entre 5 y 15 letras o digitos")
        object.__setattr__(self, "valor", normalizado)

    def __str__(self) -> str:
        return self.valor


_RE_USUARIO = re.compile(r"^[a-z0-9]([a-z0-9.]{0,18}[a-z0-9])?$")
DOMINIO_UPN_AD = "ad.andina.test"
DOMINIO_UPN_M365 = "andina.example"
_RE_UPN = re.compile(r"^[a-z0-9]([a-z0-9.]{0,18}[a-z0-9])?@[a-z0-9.]+$")


@dataclass(frozen=True, slots=True)
class CorreoUPN:
    valor: str

    def __post_init__(self) -> None:
        if not _RE_UPN.fullmatch(self.valor):
            raise DatoInvalido("upn", "formato usuario@dominio")
        if self.valor.split("@", 1)[1] not in (DOMINIO_UPN_AD, DOMINIO_UPN_M365):
            raise DatoInvalido("upn", "dominio no reconocido")

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True, slots=True)
class Usuario:
    """`sAMAccountName` sugerido (SRS 4.10): ASCII en minusculas, de 1 a 20 caracteres."""

    valor: str

    def __post_init__(self) -> None:
        if not _RE_USUARIO.fullmatch(self.valor) or ".." in self.valor:
            raise DatoInvalido("usuario", "1 a 20 caracteres [a-z0-9.], sin punto al borde")

    def upn_ad(self) -> CorreoUPN:
        return CorreoUPN(f"{self.valor}@{DOMINIO_UPN_AD}")

    def upn_m365(self) -> CorreoUPN:
        return CorreoUPN(f"{self.valor}@{DOMINIO_UPN_M365}")

    def __str__(self) -> str:
        return self.valor


# --- soportes ---------------------------------------------------------------------------------

_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class Sha256:
    valor: str

    def __post_init__(self) -> None:
        if not _RE_SHA256.fullmatch(self.valor):
            raise DatoInvalido("sha256", "64 caracteres hexadecimales en minusculas")

    @classmethod
    def de_bytes(cls, contenido: bytes) -> "Sha256":
        return cls(hashlib.sha256(contenido).hexdigest())

    def __str__(self) -> str:
        return self.valor


_RE_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9._ -]")
NOMBRE_POR_DEFECTO = "soporte.pdf"
_MAX_NOMBRE = 100


@dataclass(frozen=True, slots=True)
class NombreDeSoporteSaneado:
    """Nombre original del archivo, sin rutas ni caracteres peligrosos (RF-39, T17)."""

    valor: str

    def __post_init__(self) -> None:
        if not self.valor or len(self.valor) > _MAX_NOMBRE or _RE_NO_PERMITIDO.search(self.valor):
            raise DatoInvalido("nombre_soporte", "nombre no saneado")
        if self.valor.startswith(".") or "/" in self.valor or "\\" in self.valor:
            raise DatoInvalido("nombre_soporte", "nombre no saneado")

    @classmethod
    def sanear(cls, original: str) -> "NombreDeSoporteSaneado":
        base = re.split(r"[\\/]", original)[-1]
        base = unicodedata.normalize("NFKD", base)
        base = "".join(c for c in base if not unicodedata.combining(c))
        base = _RE_NO_PERMITIDO.sub("_", base).strip(" .")
        if len(base) > _MAX_NOMBRE:
            raiz, punto, extension = base.rpartition(".")
            base = (
                (raiz[: _MAX_NOMBRE - len(extension) - 1] + punto + extension)
                if punto
                else (base[:_MAX_NOMBRE])
            )
        return cls(base or NOMBRE_POR_DEFECTO)

    def __str__(self) -> str:
        return self.valor


# --- campos restringidos ----------------------------------------------------------------------


class CampoRestringido:
    """Motivo de retiro o descripcion de una emergencia (RD-05, CA-10).

    No es un dataclass a proposito: `dataclasses.asdict` lo trata como hoja opaca. No se puede
    imprimir, formatear, copiar a texto ni serializar (json y pickle fallan), de modo que no
    llegue por accidente a un ticket, un log, la auditoria o una ficha. Solo `revelar()`
    entrega el contenido, y solo debe usarlo la persistencia y la vista de RRHH.
    """

    __slots__ = ("_valor",)
    _valor: str

    def __init__(self, valor: str) -> None:
        texto = valor.strip()
        if not texto:
            raise DatoInvalido("campo_restringido", "no puede estar vacio")
        if len(texto) > 4000:
            raise DatoInvalido("campo_restringido", "no puede superar 4000 caracteres")
        object.__setattr__(self, "_valor", texto)

    def revelar(self) -> str:
        return self._valor

    def __setattr__(self, nombre: str, valor: object) -> NoReturn:
        raise DatoInvalido("campo_restringido", "es inmutable")

    def __repr__(self) -> str:
        return "CampoRestringido(<oculto>)"

    __str__ = __repr__

    def __format__(self, especificacion: str) -> str:
        return "CampoRestringido(<oculto>)"

    def __reduce__(self) -> NoReturn:
        raise CampoRestringidoProhibido("serializacion")

    def __reduce_ex__(self, protocolo: object) -> NoReturn:
        raise CampoRestringidoProhibido("serializacion")

    def __copy__(self) -> "CampoRestringido":
        return self

    def __deepcopy__(self, memo: object) -> "CampoRestringido":
        return self

    def __eq__(self, otro: object) -> bool:
        return isinstance(otro, CampoRestringido) and self._valor == otro._valor

    def __hash__(self) -> int:
        return hash(("CampoRestringido", self._valor))
