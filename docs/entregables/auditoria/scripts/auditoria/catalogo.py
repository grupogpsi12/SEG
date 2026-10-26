"""F3-PAR: instantánea SOLO LECTURA del catálogo del esquema `app`, para compararla entre bases.

Corre dentro del contenedor de la aplicación (la clave y la CA salen de /run/secrets; nada se
imprime de ellas). Abre la transacción en modo de solo lectura y consulta únicamente catálogos:

    python catalogo.py > catalogo-<origen>.json

Variables: JML_DB_HOST, JML_DB_USUARIO, JML_DB_SSLMODE (por defecto verify-full), JML_DB_NAME.
Compara con `auditoria/scripts/comparar-catalogos.py`.
"""

import json
import os
import sys
from pathlib import Path

import psycopg

CONSULTAS = {
    "columnas": """
        SELECT c.relname, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = 'app' AND c.relkind IN ('r','p') AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY 1, 2""",
    "restricciones": """
        SELECT c.relname, k.conname, pg_get_constraintdef(k.oid)
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' ORDER BY 1, 2""",
    "indices": """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = 'app' ORDER BY 1, 2""",
    "disparadores": """
        SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid), t.tgenabled
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND NOT t.tgisinternal ORDER BY 1, 2""",
    "funciones": """
        SELECT p.proname, pg_get_functiondef(p.oid), p.prosecdef
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'app' ORDER BY 1""",
    "rls": """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND c.relkind IN ('r','p') ORDER BY 1""",
    "politicas": """
        SELECT tablename, policyname, cmd, roles::text, qual, with_check
        FROM pg_policies WHERE schemaname = 'app' ORDER BY 1, 2""",
    # Privilegios por tabla y rol: lo que realmente puede hacer cada rol (REVOKE, anon, authenticated)
    "privilegios": """
        SELECT c.relname, r.rolname, p.priv,
               has_table_privilege(r.rolname, c.oid, p.priv)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
             (SELECT rolname FROM pg_roles
              WHERE rolname IN ('anon','authenticated','service_role','app_backend','app_owner')) r,
             (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),
                     ('REFERENCES'),('TRIGGER')) p(priv)
        WHERE n.nspname = 'app' AND c.relkind IN ('r','p') ORDER BY 1, 2, 3""",
    "esquema": """
        SELECT nspname, pg_get_userbyid(nspowner),
               has_schema_privilege('anon', oid, 'USAGE'),
               has_schema_privilege('authenticated', oid, 'USAGE')
        FROM pg_namespace WHERE nspname IN ('app')""",
    "roles": """
        SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
               rolbypassrls, rolreplication, rolconfig::text
        FROM pg_roles WHERE rolname IN ('app_backend','app_owner','anon','authenticated','service_role')
        ORDER BY 1""",
    "extensiones": "SELECT extname FROM pg_extension ORDER BY 1",
    "version": "SELECT current_setting('server_version_num')::int / 10000",
}


def main() -> int:
    conexion = psycopg.connect(
        host=os.environ["JML_DB_HOST"],
        port=5432,
        dbname=os.environ.get("JML_DB_NAME", "postgres"),
        user=os.environ.get("JML_DB_USUARIO", "app_backend"),
        password=Path("/run/secrets/db_password").read_text(encoding="utf-8").strip(),
        sslmode=os.environ.get("JML_DB_SSLMODE", "verify-full"),
        sslrootcert="/run/secrets/supabase_ca_crt",
        options="-c search_path=app -c default_transaction_read_only=on",
        connect_timeout=15,
    )
    conexion.read_only = True
    salida: dict[str, object] = {}
    with conexion, conexion.cursor() as cur:
        cur.execute("SELECT current_user")
        row = cur.fetchone()
        assert row is not None
        salida["conectado_como"] = row[0].split(".")[0]  # sin el ref del proyecto
        for nombre, sql in CONSULTAS.items():
            cur.execute(sql)  # catalogos fijos: sin parametros ni entrada externa
            salida[nombre] = [list(map(str, fila)) for fila in cur.fetchall()]
    json.dump(salida, sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
