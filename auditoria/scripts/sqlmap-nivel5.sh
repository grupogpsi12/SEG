#!/usr/bin/env bash
# F6-04: sqlmap NIVEL 5 (incluye la cabecera Host, B-05) y segundo orden, contra la aplicacion DIRECTA
# del stack local (sin WAF, para ver si resiste por si misma). Reemplaza a la corrida preliminar (B-02).
#
#   auditoria/scripts/sqlmap-nivel5.sh
#
# Neutraliza antes y despues; antes de restaurar comprueba que la cadena de auditoria siga integra.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
SQLMAP="sqlmap==1.10.10 --hash=sha256:32c4b516735c1c1a3183effd0d50a9217c9f22fc9e8b17ca4c4f6a5f2028bd93"
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
S="$RAIZ/.contrato-tmp/sqlmap5"
LAB="lab-f6-sqlmap5"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"

bash auditoria/scripts/neutralizar.sh pre
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 > "$S/sesiones.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$S/sesiones.json"; }
RRHH="$(clave rrhh)"; TEC="$(clave tecnico)"; AUD="$(clave auditor)"; ADM="$(clave administrador)"
COL="$(sed -E 's/.*"colaborador": "([^"]+)".*/\1/' "$S/sesiones.json")"; SOL="$(sed -E 's/.*"solicitud": "([^"]+)".*/\1/' "$S/sesiones.json")"

printf '%s\n' "$SQLMAP" > "$S/req-sqlmap.txt"
cat > "$S/sqlmap.sh" << SH
set -u
pip install -q --disable-pip-version-check --root-user-action=ignore --require-hashes -r /salida/req-sqlmap.txt
# Host: la aplicacion solo acepta app.localhost (ALLOWED_HOSTS); nivel 5 tambien prueba esa cabecera
B="--batch --level=5 --risk=1 --flush-session --output-dir=/salida/sqlmap --disable-coloring --host=app.localhost --headers=X-Request-ID:$LAB --timeout=20 --retries=1"
probar() { echo "### \$1"; shift; timeout 1500 sqlmap "\$@" \$B 2>&1 | grep -E "is vulnerable|injectable|all tested|not injectable|CRITICAL|ERROR|Host" | sort | uniq -c | sort -rn | head -8; }
probar "GET /cuentas (tecnico)" -u "http://web:8000/cuentas?nombre=Ana&documento=81000001&usuario=ana&departamento=Finanzas&sede=Cali&sistema=AD&estado_de_cuenta=activa&pagina=1" --cookie="sessionid=$TEC"
probar "ruta /colaboradores/<id> (tecnico)" -u "http://web:8000/colaboradores/$COL*" --cookie="sessionid=$TEC"
probar "GET /solicitudes?pagina (rrhh)" -u "http://web:8000/solicitudes?pagina=1" --cookie="sessionid=$RRHH"
probar "ruta /solicitudes/<id> (rrhh)" -u "http://web:8000/solicitudes/$SOL*" --cookie="sessionid=$RRHH"
probar "GET /auditoria?pagina (auditor)" -u "http://web:8000/auditoria?pagina=1" --cookie="sessionid=$AUD"
probar "GET /administracion/usuarios (administrador)" -u "http://web:8000/administracion/usuarios" --cookie="sessionid=$ADM"
probar "POST /ingreso (sin sesion)" -u "http://web:8000/ingreso" --data="correo=ana@andina.example&contrasena=clave&csrfmiddlewaretoken=x" --csrf-token=csrfmiddlewaretoken --cookie="csrftoken=$CSRF"
probar "POST /solicitudes/nueva/RET (rrhh), segundo orden en /solicitudes" -u "http://web:8000/solicitudes/nueva/RET" --data="fecha_efectiva=2026-12-01&documento_del_colaborador=81000001&subtipo_elegido=fin_de_contrato&motivo=prueba&justificacion=prueba&csrfmiddlewaretoken=x" --csrf-token=csrfmiddlewaretoken --cookie="sessionid=$RRHH; csrftoken=$CSRF" --second-url="http://web:8000/solicitudes"
SH
echo "== sqlmap nivel 5 contra web:8000 (directo)"
docker run --rm --network jml_app -v "$S:/salida" "$PY" sh /salida/sqlmap.sh > "$S/sqlmap.log" 2>&1
cat "$S/sqlmap.log"

echo "== cadena de auditoria despues de la corrida (antes de restaurar)"
docker exec -i jml-web-1 python manage.py shell -c "
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
from jml.dominio.auditoria import verificar_cadena
with RepositoriosDjango(RelojDelSistema()).unidad_de_trabajo() as u:
    r = u.auditoria.registros()
v = verificar_cadena(r)
print('registros:', len(r), '· valida:', v.valida, '· primer afectado:', v.primer_afectado)
" 2>&1 | tail -1

echo "== neutralizar al terminar"
bash auditoria/scripts/neutralizar.sh post
