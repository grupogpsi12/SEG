#!/usr/bin/env bash
# F7-06: `local_infile` y el tramo GLPI↔MariaDB (V-04). Solo lectura de variables globales, con el usuario `glpi`.
# La clave se lee DENTRO del contenedor desde /run/secrets: no sale ni se imprime.
set -u
export MSYS_NO_PATHCONV=1
q() { docker exec jml-mariadb-1 sh -c 'mariadb -uglpi -p"$(cat /run/secrets/glpi_db_password)" -N -e "$0"' "$1" 2>&1 | grep -v "Warning"; }
echo "## variables de MariaDB"
q "SHOW GLOBAL VARIABLES WHERE Variable_name IN ('local_infile','have_ssl','require_secure_transport','ssl_cert','skip_name_resolve','secure_file_priv','bind_address','version')"
echo "## privilegios del usuario glpi (FILE permitiria leer o escribir archivos del servidor)"
q "SHOW GRANTS FOR CURRENT_USER()" | sed -E "s/IDENTIFIED BY PASSWORD '[^']+'/IDENTIFIED BY PASSWORD '<oculto>'/"
echo "## la sesion actual de esta consulta (por socket local): cifrado en uso"
q "SHOW SESSION STATUS LIKE 'Ssl_cipher'"
echo "## como se conecta GLPI a la base (config_db.php; sin la clave)"
docker exec jml-glpi-1 sh -c 'cat /var/glpi/config/config_db.php' | sed -E "s/(dbpassword *= *).*/<oculto>/"
echo "   (sin opciones de TLS: GLPI abre la conexion en claro hacia mariadb:3306 por la red interna db_net)"
echo "## hosts desde los que MariaDB ve conexiones (el tramo viaja por la red interna db_net)"
q "SELECT SUBSTRING_INDEX(HOST, ':', 1) AS origen, COUNT(*) AS conexiones FROM information_schema.PROCESSLIST GROUP BY origen"
