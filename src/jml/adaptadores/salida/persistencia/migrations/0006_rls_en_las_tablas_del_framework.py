"""RLS tambien en las tablas de Django (invariante 8, B-23).

La migracion 0002 activo RLS solo en las tablas de la aplicacion; las nueve del framework
(`auth_*`, `django_content_type`, `django_migrations`, `django_session`) quedaron sin RLS. No eran
alcanzables (ni `anon` ni `authenticated` tienen permisos y el esquema no esta expuesto), pero el
invariante pide RLS activo sin politicas en todo el esquema: es la segunda barrera si algun dia se
expone por error. `app_backend` tiene BYPASSRLS, asi que la aplicacion no cambia. Solo PostgreSQL.
"""

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

RLS = """
DO $$
DECLARE tabla record;
BEGIN
    FOR tabla IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema() AND c.relkind = 'r' AND NOT c.relrowsecurity
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tabla.relname);
    END LOOP;
END $$;
"""


def aplicar(apps: StateApps, editor: BaseDatabaseSchemaEditor) -> None:
    if editor.connection.vendor != "postgresql":
        return
    editor.execute(RLS, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("persistencia", "0005_indices_del_dashboard"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
