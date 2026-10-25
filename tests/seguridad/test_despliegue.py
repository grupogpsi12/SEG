"""F3-U08: los avisos de `check --deploy` que se silencian son exactamente los que cubre BunkerWeb.

La salida real de `manage.py check --deploy` con los ajustes de producción se registra como
evidencia (contenedor `web`); aquí se impide que alguien silencie un aviso más sin que falle algo.
"""

import pytest
from django.conf import settings

pytestmark = pytest.mark.seguridad

# W004 HSTS, W006 nosniff, W008 redirección a HTTPS, W022 Referrer-Policy: las pone BunkerWeb (RS-07, RS-01)
CUBIERTOS_POR_EL_WAF = {"security.W004", "security.W006", "security.W008", "security.W022"}


def test_U08_solo_se_silencian_los_avisos_que_cubre_el_waf() -> None:
    from config import settings as produccion

    assert set(produccion.SILENCED_SYSTEM_CHECKS) == CUBIERTOS_POR_EL_WAF
    assert settings.configured
