"""Doble en memoria del puerto ProveedorDeIdentidad (Supabase Auth con TOTP)."""

from dataclasses import dataclass

from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadVerificada, PrimerFactor

CODIGO_VALIDO = "123456"


@dataclass
class _Cuenta:
    usuario_id: str
    contrasena: str
    totp_inscrito: bool = False


class ProveedorDeIdentidadEnMemoria:
    def __init__(self) -> None:
        self._por_correo: dict[str, _Cuenta] = {}
        self._desafios: dict[str, str] = {}  # desafio_id -> correo
        self._inscribiendo: set[str] = set()
        self._contador = 0

    def registrar(self, correo: str, contrasena: str, usuario_id: str) -> None:
        """Ayuda de prueba: equivale al comando `admin-usuarios` (RF-06)."""
        self._por_correo[correo] = _Cuenta(usuario_id, contrasena)

    def autenticar(self, correo: str, contrasena: str) -> PrimerFactor:
        cuenta = self._por_correo.get(correo)
        if cuenta is None or cuenta.contrasena != contrasena:
            raise CredencialesInvalidas  # mismo error para correo desconocido y clave mala (RS-08)
        self._contador += 1
        desafio = f"desafio-{self._contador}"
        self._desafios[desafio] = correo
        return PrimerFactor(
            cuenta.usuario_id, desafio, requiere_inscripcion=not cuenta.totp_inscrito
        )

    def inscribir_totp(self, desafio_id: str) -> str:
        correo = self._desafios.get(desafio_id)
        if correo is None:
            raise CredencialesInvalidas
        self._inscribiendo.add(desafio_id)
        return f"otpauth://totp/Andina:{correo}?secret=SECRETO-DE-PRUEBA"

    def verificar_totp(self, desafio_id: str, codigo: str) -> IdentidadVerificada:
        correo = self._desafios.get(desafio_id)
        if correo is None or codigo != CODIGO_VALIDO:
            raise CredencialesInvalidas
        cuenta = self._por_correo[correo]
        if not cuenta.totp_inscrito and desafio_id not in self._inscribiendo:
            raise CredencialesInvalidas  # hay que inscribir el TOTP antes (RF-02)
        cuenta.totp_inscrito = True
        del self._desafios[desafio_id]
        self._inscribiendo.discard(desafio_id)
        return IdentidadVerificada(cuenta.usuario_id, nivel=2)
