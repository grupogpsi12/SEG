"""`app_backend` deja de ser duenio: solo los permisos que la aplicacion usa (revision externa H1,
ADR-028).

Un duenio puede volver a darse cualquier privilegio y desactivar sus disparadores, asi que el
REVOKE de RD-02 y el disparador de RF-14 no frenaban a quien controlara `app_backend`. Desde ahora
las migraciones las corre `app_owner` (contenedor `migrar`), duenio del esquema y las tablas, y
esta migracion le da a `app_backend` solo:

- USAGE en el esquema (sin CREATE);
- SELECT, INSERT, UPDATE y DELETE en las tablas, y USAGE en las secuencias;
- nada de UPDATE, DELETE ni TRUNCATE en `auditoria`, `decision` y `cuenta_historial` (RD-02);
- lo mismo por defecto para las tablas que `app_owner` cree en el futuro.

Si la corre el propio `app_backend` (una base sin aprovisionar, ver docs/spikes/supabase.md), no
hace nada y lo avisa: darse permisos a si mismo no tiene sentido. Solo PostgreSQL.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

PERMISOS = """
DO $$
DECLARE esquema text := current_schema();
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        RETURN;
    END IF;
    IF current_user = 'app_backend' THEN
        RAISE NOTICE 'migracion corrida por app_backend: base sin aprovisionar (ADR-028)';
        RETURN;
    END IF;
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM app_backend', esquema);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_backend', esquema);
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM app_backend', esquema);
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO app_backend', esquema);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO app_backend', esquema);
    REVOKE UPDATE, DELETE, TRUNCATE ON auditoria, decision, cuenta_historial FROM app_backend;
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_backend', esquema);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
        'GRANT USAGE, SELECT ON SEQUENCES TO app_backend', esquema);
END $$;
"""


def aplicar(apps: StateApps, editor: BaseDatabaseSchemaEditor) -> None:
    if editor.connection.vendor != "postgresql":
        return
    editor.execute(PERMISOS, params=None)


class Migration(migrations.Migration):
    dependencies = [("persistencia", "0003_transiciones_en_el_disparador")]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
