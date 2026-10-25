#!/usr/bin/env bash
# F6 (plan §6): neutralizar efectos ANTES y DESPUES de un escaner o fuzzer, en el stack LOCAL de pruebas.
#   auditoria/scripts/neutralizar.sh pre     # copia de la base, worker detenido, baneos levantados
#   auditoria/scripts/neutralizar.sh unban   # solo levanta los baneos (no toca la copia)
#   auditoria/scripts/neutralizar.sh post    # restaura la copia, reanuda el worker, verifica que todo volvio
# La copia vive dentro del contenedor de PostgreSQL local (/tmp/f6.dump); nada sale al repositorio.
set -u
export MSYS_NO_PATHCONV=1
C="-f infra/compose.yaml -f infra/compose.local.yaml"
unban() {
  for ip in 10.20.40.128 127.0.0.1; do
    docker compose $C exec -T bw-scheduler bwcli unban "$ip" > /dev/null 2>&1
  done
  true
}
filas() { docker exec jml-postgres-1 psql -U postgres -tAc "select (select count(*) from app.auditoria)||'/'||(select count(*) from app.solicitud)||'/'||(select count(*) from app.ticket)||'/'||(select count(*) from app.colaborador)"; }

case "${1:-}" in
  pre)
    unban
    docker exec jml-postgres-1 sh -c 'pg_dump -U postgres -Fc postgres > /tmp/f6.dump' || exit 1
    echo "filas antes (auditoria/solicitud/ticket/colaborador): $(filas)"
    docker stop jml-worker-1 > /dev/null && echo "worker detenido: los POST del escaner no crean tickets en GLPI"
    echo "correlation_id de laboratorio: usar el prefijo lab-f6- en X-Request-ID"
    ;;
  unban)
    unban
    ;;
  post)
    docker stop jml-web-1 jml-worker-1 > /dev/null 2>&1
    docker exec jml-postgres-1 sh -c 'pg_restore -U postgres -d postgres --clean --if-exists /tmp/f6.dump' > /dev/null 2>&1
    docker start jml-web-1 jml-worker-1 > /dev/null
    for _ in $(seq 1 30); do
      [ "$(docker inspect -f '{{.State.Health.Status}}' jml-web-1 2>/dev/null)" = healthy ] && break
      sleep 3
    done
    unban
    echo "filas despues (auditoria/solicitud/ticket/colaborador): $(filas)"
    echo "web: $(docker inspect -f '{{.State.Health.Status}}' jml-web-1) · worker: $(docker inspect -f '{{.State.Status}}' jml-worker-1)"
    ;;
  *) echo "uso: $0 pre|unban|post" >&2; exit 2 ;;
esac
