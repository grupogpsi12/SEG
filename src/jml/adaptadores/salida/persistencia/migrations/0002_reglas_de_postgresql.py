"""Reglas que el ORM no expresa y que garantiza PostgreSQL (RF-14, RD-02, RD-10; invariantes 3 y 8).

Solo se aplican en PostgreSQL: en SQLite (pruebas sin Docker) la operacion no hace nada. Las
pruebas de `tests/integracion` comprueban que, en PostgreSQL, estas reglas se cumplen de verdad.

Supuesto operativo (a confirmar en el spike 0.2): las migraciones las corre `app_backend`, que
queda como duenio de las tablas. Es agnostica de esquema (usa `current_schema()`). RLS sin politicas no lo bloquea a el (no se usa FORCE), pero si
a `anon` y `authenticated`. El REVOKE se aplica sobre `app_backend` aunque sea el duenio.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

INMUTABILIDAD = """
CREATE OR REPLACE FUNCTION app_solicitud_inmutable() RETURNS trigger AS $$
BEGIN
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

CREATE TRIGGER solicitud_inmutable BEFORE UPDATE ON solicitud
    FOR EACH ROW EXECUTE FUNCTION app_solicitud_inmutable();

CREATE OR REPLACE FUNCTION app_restringida_inmutable() RETURNS trigger AS $$
DECLARE estado_actual text;
BEGIN
    SELECT estado INTO estado_actual FROM solicitud WHERE id = OLD.solicitud_id;
    IF estado_actual IS NOT NULL AND estado_actual <> 'pendiente_aprobacion' THEN
        RAISE EXCEPTION 'el campo restringido de % es inmutable (RF-14)', OLD.solicitud_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER restringida_inmutable BEFORE UPDATE OR DELETE ON solicitud_restringida
    FOR EACH ROW EXECUTE FUNCTION app_restringida_inmutable();
"""

SOLO_INSERCION = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON auditoria, decision, cuenta_historial FROM app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM anon, authenticated, service_role',
                       current_schema());
    END IF;
END $$;
"""

TABLAS = [
    "colaborador", "usuario_perfil", "perfil_acceso", "recurso_perfil", "consecutivo", "solicitud",
    "solicitud_restringida", "decision", "soporte", "ticket", "cuenta", "cuenta_historial",
    "outbox", "activo_asignado", "licencia_asignada", "sincronizacion", "auditoria",
]  # fmt: skip
RLS = "\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;" for t in TABLAS)


def aplicar(apps: StateApps, editor: BaseDatabaseSchemaEditor) -> None:
    if editor.connection.vendor != "postgresql":
        return
    for sql in (INMUTABILIDAD, SOLO_INSERCION, RLS):
        editor.execute(sql, params=None)  # sin params: el SQL lleva `%` propios de plpgsql


class Migration(migrations.Migration):
    dependencies = [("persistencia", "0001_inicial")]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
