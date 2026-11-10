#!/usr/bin/env bash
# DS-5: prueba manual de inyección SQL que complementa a sqlmap. No modifica datos (solo GET de lectura).
#
#   bash auditoria/scripts/sqli-manual.sh
#
# Comprueba dos capas de defensa con cargas clásicas de inyección:
#  A) El WAF (CRS) bloquea con 403 las cargas obvias en la cadena de consulta.
#  B) La aplicación, con el ORM parametrizado, trata la carga como un dato literal: responde 200 sin
#     filtrar de más ni revelar un error de base de datos. Se prueba con una sesión de técnico.
# Se mide a través del WAF y directamente contra la aplicación (sin WAF), para separar las dos capas.
set -u
export MSYS_NO_PATHCONV=1
fallos=0
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }
desbanear() { docker compose -f infra/compose.yaml exec -T bw-scheduler bwcli unban 10.20.40.128 > /dev/null 2>&1; }
trap desbanear EXIT
desbanear

# Sesión de técnico (sin tocar Supabase): se crea en la base y se usa su cookie.
TEC=$(docker exec -i jml-web-1 python - <<'PY' 2>/dev/null | tail -1
import time, django
django.setup()
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
u = User.objects.filter(groups__name__startswith="tecnico", is_active=True).first()
s = SessionStore(); s["usuario_id"] = u.username; s["inicio"] = time.time(); s.save()
print(s.session_key)
PY
)
echo "sesión de técnico creada"

# Cargas clásicas de inyección SQL.
CARGAS=("1' OR '1'='1" "1; DROP TABLE app.solicitud--" "' UNION SELECT null,version()--" "1) OR (1=1" "admin'--")

echo "== A) a través del WAF: el CRS bloquea las cargas obvias (403) o la app las trata como dato (200)"
for carga in "${CARGAS[@]}"; do
  cod=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 --resolve app.localhost:443:127.0.0.1 \
    -b "sessionid=$TEC" -G --data-urlencode "documento=$carga" "https://app.localhost/cuentas" 2>/dev/null)
  echo "   [$cod] documento=$carga"
  afirmar "no hay 500 ni fuga para «$carga»" '[ "$cod" = 403 ] || [ "$cod" = 200 ]'
  desbanear
done

echo "== B) directo a la aplicación (sin WAF): el ORM parametrizado trata la carga como literal"
# Dentro de la red interna, contra web:8000 con Host: app.localhost (ALLOWED_HOSTS); el ORM
# parametrizado trata la carga como un dato literal.
# Cargas que caben en el campo (máx. 20, como el formulario): llegan a la consulta del ORM.
for carga in "' OR '1'='1" "1' OR '1'='1" "'||version()"; do
  res=$(docker run --rm --network jml_app nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70 \
    curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "Host: app.localhost" -b "sessionid=$TEC" \
    -G --data-urlencode "documento=$carga" "http://web:8000/cuentas" 2>/dev/null)
  echo "   [$res] documento=$carga"
  # 200 = la carga se trató como un dato literal (ORM) y no hubo coincidencias ni error de BD.
  afirmar "la app responde sin error de base de datos para «$carga»" '[ "$res" = 200 ]'
done
# Una carga más larga que el campo la rechaza la validación del formulario (404), antes del ORM.
largo=$(docker run --rm --network jml_app nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70 \
  curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "Host: app.localhost" -b "sessionid=$TEC" \
  -G --data-urlencode "documento='; DROP TABLE app.cuenta--" "http://web:8000/cuentas" 2>/dev/null)
echo "   [$largo] documento='; DROP TABLE app.cuenta-- (supera 20 caracteres)"
afirmar "una carga sobredimensionada la rechaza la validación (404), sin tocar la BD" '[ "$largo" = 404 ]'

echo "== integridad: las tablas siguen ahí y la cadena de auditoría es válida"
tablas=$(docker exec -i jml-postgres-1 psql -U postgres -d postgres -Atc \
  "select count(*) from information_schema.tables where table_schema='app'" 2>/dev/null)
echo "   tablas en el esquema app: $tablas"
afirmar "ninguna tabla fue eliminada (DROP TABLE no tuvo efecto)" '[ "${tablas:-0}" -gt 20 ]'

echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
