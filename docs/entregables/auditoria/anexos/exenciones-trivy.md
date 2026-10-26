# Exenciones escritas de Trivy (F7-03)

Meta del plan: «0 críticas sin exención escrita». Trivy 0.67.2 sobre las cinco imágenes, priorizado con CISA KEV y EPSS del 25/10/2026. **Ninguna vulnerabilidad está en el catálogo KEV** (1756 CVE explotadas activamente; 139 distintas en nuestras imágenes). Cada CRÍTICA queda corregida o exenta por escrito, con motivo, dueño y fecha de revisión. Dueño de todas: el equipo (Administrador del sistema). Revisión: en cada refresco de imágenes y, a más tardar, el **25/11/2026**.

| Imagen | Vulnerabilidad | Paquete | Parche | Decisión | Motivo |
|---|---|---|---|---|---|
| `jml-app` | GHSA-6q48-6c7w-9gw2 (CA raíz emSign) | certifi 2026.7.22 | 2026.10.19 | **Corregida en el código (B-15); falta reconstruir la imagen** | El lock ya lleva 2026.10.19; la imagen local es anterior. Se reconstruye y se vuelve a escanear en F9. |
| `bunkerweb` 1.6.15 | GHSA-6q48-6c7w-9gw2 | certifi 2026.7.22 | 2026.10.19 | **Exenta hasta el próximo refresco** | Imagen de terceros fijada por digest (ADR-023). Afecta solo a certificados de emSign en conexiones SALIENTES de BunkerWeb (listas de reputación, Let's Encrypt); la aplicación no depende de ninguna CA emSign. |
| `bunkerweb-scheduler` 1.6.15 | GHSA-6q48-6c7w-9gw2 (×2) | certifi 2026.6.17 | 2026.10.19 | **Exenta hasta el próximo refresco** | Igual que la anterior. |
| `glpi` 11.0.11 | CVE-2026-44172 y CVE-2026-49261 (inyección SQL por importación y ejecución de código por `wsrep` en el **servidor** MariaDB) | libmariadb3, mariadb-client, -compat, -core, -common | sin parche | **Exentas** | Son paquetes del **cliente**; el contenedor no ejecuta un servidor MariaDB (el de verdad está en el contenedor `mariadb`). No alcanzable. |
| `glpi` | CVE-2026-6653 (denegación de servicio por XML) | libxml2, libxml2-dev | sin parche | **Exenta** | Denegación de servicio, no ejecución. Sin parche upstream; un reinicio del contenedor la absorbe (healthcheck). |
| `glpi` | CVE-2026-93221 | linux-libc-dev | sin parche | **Exenta** | Son cabeceras del núcleo para compilar; el núcleo que corre es el del anfitrión, no este paquete. No explotable desde el contenedor. |
| `mariadb` 11.4 | CVE-2025-68121 (validación de certificados en `crypto/tls`) | stdlib de Go dentro de `gosu` | 1.24.13 / 1.25.7 | **Exenta; se corrige al refrescar** | `gosu` solo baja privilegios al arrancar el contenedor y no abre conexiones TLS. |

**HIGH con EPSS ≥ 10 %**: CVE-2026-111497 (`brotli` y `brotli-libs`, EPSS 0,328, con parche 1.2.1-r0) en `bunkerweb` y su planificador, sin parche en la imagen fijada. BunkerWeb usa brotli para comprimir respuestas, no para decodificar entrada no confiable; riesgo aceptado hasta el refresco, y es el primero que se aplica.

**Qué cambia la decisión.** Que una de estas entre en KEV, que su EPSS pase del 10 % o que exista una imagen nueva con el parche: entonces se refresca antes de la fecha. El refresco de imágenes por digest se propone como ADR (F8-04).
