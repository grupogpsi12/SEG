"""Doble en memoria del puerto AlmacenDeSoportes."""

from jml.aplicacion.puertos import SoporteNoDisponible


class AlmacenDeSoportesEnMemoria:
    def __init__(self) -> None:
        self._archivos: dict[str, bytes] = {}
        self._contador = 0

    def guardar(self, contenido: bytes) -> str:
        # Nombre que no depende del contenido ni del nombre original (RD-12); sin extension.
        self._contador += 1
        nombre = f"{(self._contador * 2654435761) % 2**32:08x}{self._contador:04x}"
        self._archivos[nombre] = contenido
        return nombre

    def leer(self, nombre: str) -> bytes:
        try:
            return self._archivos[nombre]
        except KeyError:
            raise SoporteNoDisponible(nombre) from None

    def borrar(self, nombre: str) -> None:
        self._archivos.pop(nombre, None)

    def existe(self, nombre: str) -> bool:
        return nombre in self._archivos

    # --- ayudas de prueba (no son parte del puerto) ---
    def perder(self, nombre: str) -> None:
        """Simula que la copia temporal desaparecio del volumen (RD-12)."""
        self._archivos.pop(nombre, None)

    def nombres(self) -> list[str]:
        return sorted(self._archivos)
