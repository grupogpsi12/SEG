"""F3-U05 (T6, revisión externa H3): quien decide sobre una solicitud la bloquea hasta confirmar.

CA-01 (dos altas simultáneas, una gana) ya está en `test_postgresql.py`. Aquí: dos decisiones
simultáneas sobre la MISMA solicitud. Sin `select_for_update`, las dos leían «pendiente» y se
confirmaban; con él, la segunda espera y ve el estado nuevo.
"""

import threading
import time
from dataclasses import replace

import pytest
from django.db import connections

from jml.adaptadores.salida.persistencia import models as m
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.dominio.tipos import EstadoSolicitud
from tests.dobles.reloj import RelojSimulado
from tests.fabricas import colaborador
from tests.integracion.test_postgresql import _vac

pytestmark = pytest.mark.seguridad


def test_U05_dos_decisiones_simultaneas_sobre_la_misma_solicitud_solo_una_aprueba(
    base_con_commit: None,
) -> None:
    repos = RepositoriosDjango(RelojSimulado())
    with repos.unidad_de_trabajo() as u:
        u.colaboradores.guardar(colaborador())
        u.solicitudes.guardar(_vac(1))
    sid = _vac(1).id
    salida: list[str] = []

    def decidir() -> None:
        try:
            with repos.unidad_de_trabajo() as u:
                s = u.solicitudes.obtener(sid)
                assert s is not None
                if s.estado is EstadoSolicitud.PENDIENTE_APROBACION:
                    time.sleep(1.0)  # ventana en la que el otro hilo habría leído lo mismo
                    u.solicitudes.guardar(replace(s, estado=EstadoSolicitud.APROBADA))
                    salida.append("aprobo")
                else:
                    salida.append("vio-aprobada")
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=decidir) for _ in (1, 2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert sorted(salida) == ["aprobo", "vio-aprobada"]
    assert m.Solicitud.objects.get(pk=sid.valor).estado == "aprobada"
