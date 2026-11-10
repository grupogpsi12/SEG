#!/usr/bin/env bash
# DS-5 (complemento de F6-04): repite SOLO el objetivo de segundo orden que el tope de tiempo cortó en
# la corrida completa. sqlmap nivel 5 sobre POST /solicitudes/nueva/RET con re-lectura en /solicitudes.
# Neutraliza antes y después; comprueba la cadena de auditoría antes de restaurar. Stack LOCAL.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
SQLMAP="sqlmap==1.10.10 --hash=sha256:32c4b516735c1c1a3183effd0d50a9217c9f22fc9e8b17ca4c4f6a5f2028bd93"
CSRF="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
S="$RAIZ/.contrato-tmp/sqli2o"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"
bash auditoria/scripts/neutralizar.sh pre
RRHH=$(docker exec -i jml-web-1 python - <<'PY' 2>/dev/null | tail -1
import time, django
django.setup()
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
u = User.objects.filter(groups__name="rrhh", is_active=True).first()
s = SessionStore(); s["usuario_id"] = u.username; s["inicio"] = time.time(); s.save()
print(s.session_key)
PY
)
printf '%s\n' "$SQLMAP" > "$S/req.txt"
cat > "$S/run.sh" <<SH
set -u
pip install -q --disable-pip-version-check --root-user-action=ignore --require-hashes -r /salida/req.txt
B="--batch --level=5 --risk=1 --flush-session --output-dir=/salida/out --disable-coloring --host=app.localhost --timeout=15 --retries=1"
echo "### POST /solicitudes/nueva/RET (rrhh), segundo orden en /solicitudes"
timeout 2400 sqlmap -u "http://web:8000/solicitudes/nueva/RET" \
  --data="fecha_efectiva=2026-12-01&documento_del_colaborador=81000001&subtipo_elegido=fin_de_contrato&motivo=prueba&justificacion=prueba&csrfmiddlewaretoken=x" \
  --csrf-token=csrfmiddlewaretoken --cookie="sessionid=$RRHH; csrftoken=$CSRF" \
  --second-url="http://web:8000/solicitudes" \$B 2>&1 | grep -E "is vulnerable|injectable|all tested|identified the following|CRITICAL|parameter '" | sort | uniq -c
SH
echo "== sqlmap nivel 5, segundo orden, contra web:8000 (directo)"
docker run --rm --network jml_app -v "$S:/salida" "$PY" sh /salida/run.sh
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
bash auditoria/scripts/neutralizar.sh post
rm -rf "$S"
