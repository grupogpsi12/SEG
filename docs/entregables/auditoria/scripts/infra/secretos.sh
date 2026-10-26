#!/usr/bin/env bash
# Secretos compartidos del equipo, cifrados en el repositorio con SOPS + age (ADR-029, item 5.7).
#
#   infra/scripts/secretos.sh llave                         # crea su llave age (una vez) y muestra la publica
#   infra/scripts/secretos.sh estado                        # grupos, si usted los descifra y que nombres tienen
#   infra/scripts/secretos.sh descifrar [--forzar] [grupo]  # escribe en secrets/ lo que falte
#   infra/scripts/secretos.sh cifrar <grupo> <nombre>...    # toma secrets/<nombre> y lo cifra en el grupo
#   infra/scripts/secretos.sh agregar <grupo> <clave-publica> <persona>
#   infra/scripts/secretos.sh quitar <grupo> <clave-publica>
#
# Grupos (minimo privilegio): `equipo` (URL, clave publicable y CA de Supabase, lo que pide el modo
# local) y `administracion` (service_role y las claves del Supabase de desarrollo). Un archivo
# infra/secretos/<grupo>.sops.yaml por grupo de destinatarios de .sops.yaml
# Cada clave del archivo es el nombre de un archivo de secrets/.
#
# Reglas (ADR-029):
# - Nada se imprime: los valores van de secrets/ al archivo cifrado y de vuelta, sin pasar por la
#   pantalla ni por la linea de comandos (se entregan a sops por stdin).
# - `descifrar` nunca pisa un archivo distinto que ya este en secrets/ (salvo --forzar).
# - Solo secretos de desarrollo y del equipo. Los de produccion siguen en Key Vault (ADR-009).
# - Quitar a alguien exige ROTAR los valores en su origen: conserva su llave y el historial de Git.
#
# Requiere `sops` 3.13+ y `age` 1.3+ (docs/probar-localmente.md). En Git Bash de Windows no se usa
# MSYS_NO_PATHCONV: sops y age son ejecutables de Windows y necesitan las rutas traducidas.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETOS="${JML_SECRETOS:-$RAIZ/secrets}"
CIFRADOS="${JML_CIFRADOS:-$RAIZ/infra/secretos}"
CONFIG="${JML_SOPS_CONFIG:-$RAIZ/.sops.yaml}"
NOMBRE_VALIDO='^[a-z0-9_]+$'          # tambien es el nombre del archivo en secrets/: sin rutas
CLAVE_VALIDA='^age1[02-9ac-hj-np-z]{58}$'

falla() { echo "secretos.sh: $*" >&2; exit 1; }

for herramienta in sops age-keygen; do
  command -v "$herramienta" > /dev/null || falla "falta '$herramienta' (instalacion: docs/probar-localmente.md)"
done

# La llave de cada persona vive fuera del repositorio, donde sops la busca por defecto.
if [ -z "${SOPS_AGE_KEY_FILE:-}" ]; then
  if [ -n "${APPDATA:-}" ]; then
    base="$(cygpath -u "$APPDATA" 2> /dev/null || printf '%s' "$APPDATA")"
  elif [ "$(uname -s)" = "Darwin" ]; then
    base="$HOME/Library/Application Support"
  else
    base="${XDG_CONFIG_HOME:-$HOME/.config}"
  fi
  SOPS_AGE_KEY_FILE="$base/sops/age/keys.txt"
fi
export SOPS_AGE_KEY_FILE

umask 077
mkdir -p "$SECRETOS"

grupos() {  # los grupos de .sops.yaml, de las lineas `path_regex: ...secretos[/\\]<grupo>\.sops\.yaml$`
  sed -nE 's/.*path_regex:.*\]([a-z0-9_]+)\\\.sops\\\.yaml\$.*/\1/p' "$CONFIG"
}

archivo_de() {  # grupo -> ruta del archivo cifrado (el grupo debe existir en .sops.yaml)
  [[ "$1" =~ $NOMBRE_VALIDO ]] || falla "grupo invalido: $1"
  grupos | grep -qx "$1" || falla "el grupo '$1' no esta en $CONFIG"
  printf '%s/%s.sops.yaml' "$CIFRADOS" "$1"
}

nombres_de() {  # claves de primer nivel de un archivo cifrado (los nombres no se cifran)
  grep -E '^[a-z0-9_]+:' "$1" | cut -d: -f1 | grep -vx sops || true
}

sin_fin() {  # contenido sin \r ni saltos finales, para comparar sin mostrar nada
  tr -d '\r' < "$1" | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
}

json() {  # el contenido de un archivo como cadena JSON (lo que espera `sops set`)
  printf '"'
  tr -d '\r' < "$1" | awk 'BEGIN { ORS = "" }
    { gsub(/\\/, "\\\\"); gsub(/"/, "\\\""); gsub(/\t/, "\\t"); if (NR > 1) printf "\\n"; printf "%s", $0 }'
  printf '"'
}

puedo_descifrar() {
  sops --config "$CONFIG" decrypt "$1" > /dev/null 2>&1
}

volver_a_cifrar() {  # tras cambiar destinatarios: updatekeys + nueva llave de datos
  local archivo="$1"
  [ -f "$archivo" ] || return 0
  sops --config "$CONFIG" updatekeys -y "$archivo" > /dev/null 2>&1 \
    || falla "no pude actualizar $archivo: ¿usted puede descifrarlo? (secretos.sh estado)"
  sops --config "$CONFIG" rotate -i "$archivo" > /dev/null 2>&1 || falla "no pude rotar $archivo"
}

orden="${1:-}"
[ $# -gt 0 ] && shift
case "$orden" in
  llave)
    if [ -s "$SOPS_AGE_KEY_FILE" ]; then
      echo "Ya tiene una llave en $SOPS_AGE_KEY_FILE"
    else
      mkdir -p "$(dirname "$SOPS_AGE_KEY_FILE")"
      age-keygen -o "$SOPS_AGE_KEY_FILE" 2> /dev/null
      echo "Llave creada en $SOPS_AGE_KEY_FILE. Respaldela en un lugar seguro y NUNCA la comparta."
    fi
    echo "Su clave publica (esta si se comparte, para que lo agreguen):"
    age-keygen -y "$SOPS_AGE_KEY_FILE"
    ;;

  estado)
    for g in $(grupos); do
      a="$CIFRADOS/$g.sops.yaml"
      if [ ! -f "$a" ]; then
        echo "$g: sin archivo todavia"
      elif puedo_descifrar "$a"; then
        echo "$g: lo descifra · $(nombres_de "$a" | tr '\n' ' ')"
      else
        echo "$g: NO lo descifra (pida que lo agreguen con su clave publica)"
      fi
    done
    ;;

  descifrar)
    forzar=no
    if [ "${1:-}" = "--forzar" ]; then forzar=si; shift; fi
    lista="${*:-$(grupos)}"
    for g in $lista; do
      a="$(archivo_de "$g")"
      [ -f "$a" ] || { echo "$g: sin archivo, nada que descifrar"; continue; }
      puedo_descifrar "$a" || { echo "$g: no lo descifra con su llave; se omite"; continue; }
      for n in $(nombres_de "$a"); do
        tmp="$SECRETOS/.$n.descifrado"
        sops --config "$CONFIG" decrypt --extract "[\"$n\"]" "$a" > "$tmp"
        destino="$SECRETOS/$n"
        if [ -s "$destino" ] && cmp -s <(sin_fin "$destino") <(sin_fin "$tmp"); then
          rm -f "$tmp"; echo "  $n: igual"
        elif [ -s "$destino" ] && [ "$forzar" != si ]; then
          rm -f "$tmp"; echo "  $n: DISTINTO al de secrets/; no se toca (use --forzar para reemplazarlo)"
        else
          mv -f "$tmp" "$destino"; echo "  $n: escrito"
        fi
      done
    done
    ;;

  cifrar)
    [ $# -ge 2 ] || falla "uso: secretos.sh cifrar <grupo> <nombre>..."
    a="$(archivo_de "$1")"; shift
    for n in "$@"; do
      [[ "$n" =~ $NOMBRE_VALIDO ]] || falla "nombre invalido: $n"
      [ -s "$SECRETOS/$n" ] || falla "no existe o esta vacio: $SECRETOS/$n"
    done
    mkdir -p "$CIFRADOS"
    if [ -f "$a" ]; then
      puedo_descifrar "$a" || falla "no puede modificar $a: su llave no lo descifra"
      for n in "$@"; do
        json "$SECRETOS/$n" | sops --config "$CONFIG" set --value-stdin "$a" "[\"$n\"]"
        echo "  $n: cifrado"
      done
    else
      # Archivo nuevo: el texto plano solo existe un instante, dentro de secrets/ (no versionado).
      plano="$SECRETOS/.nuevo.sops-plano.yaml"
      trap 'rm -f "$plano"' EXIT
      for n in "$@"; do printf '%s: %s\n' "$n" "$(json "$SECRETOS/$n")"; done > "$plano"
      sops --config "$CONFIG" encrypt --filename-override "$a" --input-type yaml --output-type yaml \
        "$plano" > "$a.nuevo"
      mv -f "$a.nuevo" "$a"
      rm -f "$plano"
      echo "  creado $a con: $*"
    fi
    ;;

  agregar)
    [ $# -eq 3 ] || falla "uso: secretos.sh agregar <grupo> <clave-publica> <persona>"
    g="$1"; clave="$2"; persona="$3"
    a="$(archivo_de "$g")"
    [[ "$clave" =~ $CLAVE_VALIDA ]] || falla "no es una clave publica de age: $clave"
    [[ "$persona" =~ ^[[:alnum:][:space:]._áéíóúñÁÉÍÓÚÑ-]+$ ]] || falla "nombre de persona invalido"
    if awk -v g="$g" -v c="$clave" '
        /path_regex:/ { dentro = index($0, "]" g "\\.sops") > 0 }
        dentro && index($0, c) { hallada = 1 }
        END { exit hallada ? 0 : 1 }' "$CONFIG"; then
      echo "$persona ya esta en el grupo $g"; exit 0
    fi
    awk -v g="$g" -v c="$clave" -v p="$persona" '
      /path_regex:/ { dentro = index($0, "]" g "\\.sops") > 0 }
      { print }
      dentro && /- age:/ && !hecho { print "          - " c "  # " p; hecho = 1 }' \
      "$CONFIG" > "$CONFIG.nuevo"
    mv -f "$CONFIG.nuevo" "$CONFIG"
    volver_a_cifrar "$a"
    echo "$persona agregada al grupo $g. Haga commit de .sops.yaml y de $a."
    ;;

  quitar)
    [ $# -eq 2 ] || falla "uso: secretos.sh quitar <grupo> <clave-publica>"
    g="$1"; clave="$2"
    a="$(archivo_de "$g")"
    [[ "$clave" =~ $CLAVE_VALIDA ]] || falla "no es una clave publica de age: $clave"
    awk -v g="$g" -v c="$clave" '
      /path_regex:/ { dentro = index($0, "]" g "\\.sops") > 0 }
      !(dentro && index($0, c)) { print }' "$CONFIG" > "$CONFIG.nuevo"
    if cmp -s "$CONFIG" "$CONFIG.nuevo"; then rm -f "$CONFIG.nuevo"; falla "esa clave no esta en el grupo $g"; fi
    mv -f "$CONFIG.nuevo" "$CONFIG"
    volver_a_cifrar "$a"
    echo "Quitada del grupo $g. IMPORTANTE: esa persona conserva el historial de Git y su llave."
    echo "Rote en su origen cada secreto de $g y vuelva a cifrarlo (ADR-029):"
    nombres_de "$a" | sed 's/^/  - /'
    ;;

  *)
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
