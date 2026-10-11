"""El disparador de RF-14 tambien valida el cambio de estado (revision externa H2).

Antes solo comparaba el contenido cuando la solicitud ya no estaba pendiente: alcanzaba con
devolverla a `pendiente_aprobacion`, editarla y volver a cerrarla. Ahora cualquier cambio de
estado debe estar en `TRANSICIONES_PERMITIDAS`, que es el cierre transitivo de la tabla del
dominio (`dominio/solicitud.py: TRANSICIONES`): un caso de uso puede encadenar varios pasos en una
transaccion (p. ej. S-05, aprobar y cerrar sin tickets). Asi nunca se vuelve a pendiente y un
estado final no cambia. `tests/adaptadores/test_migraciones.py` comprueba que esta lista es
identica al cierre calculado desde el dominio, para que no se separen.

Solo PostgreSQL; en SQLite no hace nada.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

TRANSICIONES_PERMITIDAS = (
    ("aprobada", "cancelada"),
    ("aprobada", "cerrada"),
    ("aprobada", "en_ejecucion"),
    ("aprobada", "error"),
    ("en_ejecucion", "cerrada"),
    ("error", "aprobada"),
    ("error", "cancelada"),
    ("error", "cerrada"),
    ("error", "en_ejecucion"),
    ("pendiente_aprobacion", "aprobada"),
    ("pendiente_aprobacion", "cancelada"),
    ("pendiente_aprobacion", "cerrada"),
    ("pendiente_aprobacion", "en_ejecucion"),
    ("pendiente_aprobacion", "error"),
    ("pendiente_aprobacion", "rechazada"),
)

_PARES = ", ".join(f"('{a}', '{b}')" for a, b in TRANSICIONES_PERMITIDAS)

INMUTABILIDAD = f"""
CREATE OR REPLACE FUNCTION app_solicitud_inmutable() RETURNS trigger AS $$
BEGIN
    -- H2: el estado solo avanza por la tabla del dominio (nunca vuelve a pendiente).
    IF NEW.estado IS DISTINCT FROM OLD.estado
       AND (OLD.estado, NEW.estado) NOT IN ({_PARES}) THEN
        RAISE EXCEPTION 'solicitud %: transicion % -> % no permitida (RF-14)',
            OLD.id, OLD.estado, NEW.estado USING ERRCODE = 'check_violation';
    END IF;
    -- RF-14: tras la aprobacion solo cambian estado, tickets y la marca de revision.
    IF OLD.estado <> 'pendiente_aprobacion' AND (
        NEW.colaborador_id IS DISTINCT FROM OLD.colaborador_id
        OR NEW.tipo IS DISTINCT FROM OLD.tipo
        OR NEW.subtipo IS DISTINCT FROM OLD.subtipo
        OR NEW.fecha_efectiva IS DISTINCT FROM OLD.fecha_efectiva
        OR NEW.datos IS DISTINCT FROM OLD.datos
        OR NEW.solicitante_id IS DISTINCT FROM OLD.solicitante_id
        OR NEW.creada_en IS DISTINCT FROM OLD.creada_en
        OR NEW.solicitud_origen_id IS DISTINCT FROM OLD.solicitud_origen_id
    ) THEN
        RAISE EXCEPTION 'solicitud % aprobada: su contenido es inmutable (RF-14)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def aplicar(apps: StateApps, editor: BaseDatabaseSchemaEditor) -> None:
    if editor.connection.vendor != "postgresql":
        return
    editor.execute(INMUTABILIDAD, params=None)  # sin params: el SQL lleva `%` de plpgsql


class Migration(migrations.Migration):
    dependencies = [("persistencia", "0002_reglas_de_postgresql")]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
