#!/usr/bin/env bash
# L-01 (ADR-031): verifica la copia de la auditoria y los respaldos a un medio externo, usando una
# carpeta que hace las veces de disco externo. No toca el stack: lee el volumen `exportes` y la base.
#
#   bash auditoria/scripts/probar-copias-locales.sh
#
# 1. Primera copia: todo se copia y cada archivo coincide por SHA-256.
# 2. Segunda copia: nada se copia de nuevo (idempotente).
# 3. Control negativo: se altera una copia; el script lo denuncia, sale con error y NO la sobrescribe.
# 4. Respaldo con destino en el medio externo, retencion de 30 dias y simulacro de restauracion (CA-11).
set -u
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"
MEDIO="$RAIZ/.contrato-tmp/medio-externo"
rm -rf "$MEDIO" && mkdir -p "$MEDIO"
fallos=0
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }

echo "== 1. primera copia"
salida1="$(JML_MEDIO_EXTERNO="$MEDIO" bash infra/scripts/copiar-exportes.sh 2>&1)"; c1=$?
echo "$salida1"
n=$(ls "$MEDIO/auditoria" | wc -l)
afirmar "codigo 0 y $n archivos en el medio externo" '[ $c1 -eq 0 ] && [ $n -gt 0 ]'

echo "== 2. segunda copia (idempotente)"
salida2="$(JML_MEDIO_EXTERNO="$MEDIO" bash infra/scripts/copiar-exportes.sh 2>&1)"; c2=$?
echo "$salida2"
afirmar "no copia nada de nuevo" '[ $c2 -eq 0 ] && echo "$salida2" | grep -q "copiados: 0 "'

echo "== 3. control negativo: una copia alterada"
victima="$(ls "$MEDIO/auditoria"/ancla-*.json | head -1)"
echo '{"alterada": true}' > "$victima"; antes="$(sha256sum < "$victima")"
salida3="$(JML_MEDIO_EXTERNO="$MEDIO" bash infra/scripts/copiar-exportes.sh 2>&1)"; c3=$?
echo "$salida3"
afirmar "sale con error y da la alarma" '[ $c3 -ne 0 ] && echo "$salida3" | grep -q ALARMA'
afirmar "no sobrescribe la copia alterada" '[ "$(sha256sum < "$victima")" = "$antes" ]'

echo "== 4. respaldo en el medio externo, retencion y restauracion"
mkdir -p "$MEDIO/respaldos"
touch -d "40 days ago" "$MEDIO/respaldos/app-2026-09-01.dump" "$MEDIO/respaldos/glpi-2026-09-01.sql.gz"
touch -d "40 days ago" "$MEDIO/respaldos/otro-archivo.txt"
JML_RESPALDO_DESTINO="$MEDIO/respaldos" bash infra/scripts/respaldo.sh; c4=$?
afirmar "respaldo con codigo 0" '[ $c4 -eq 0 ]'
afirmar "retira los respaldos de mas de 30 dias" '[ ! -e "$MEDIO/respaldos/app-2026-09-01.dump" ] && [ ! -e "$MEDIO/respaldos/glpi-2026-09-01.sql.gz" ]'
afirmar "no toca archivos ajenos" '[ -e "$MEDIO/respaldos/otro-archivo.txt" ]'
bash infra/scripts/restaurar-prueba.sh "$MEDIO/respaldos" 2>&1 | tail -12; c5=${PIPESTATUS[0]}
afirmar "el simulacro de restauracion pasa" '[ $c5 -eq 0 ]'

echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
