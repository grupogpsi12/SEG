# Exclusiones de ModSecurity (RS-18, invariante 14)

Nunca se desactiva el CRS ni ModSecurity para que algo funcione. Cada falso positivo se resuelve con
**un archivo por exclusión**, con la ruta exacta, el ID de la regla y el motivo, y se prueba el
flujo completo a través del WAF (`infra/waf/pruebas.sh` y CA-20).

El scheduler de BunkerWeb monta esta carpeta en `/data/configs` (solo lectura). Estructura que
espera BunkerWeb 1.6 (confirmado el 26/10/2026 con la primera exclusión):

```
configs/
  modsec-crs/<sitio>/<nombre>.conf   # antes del CRS (ctl:ruleRemoveById por ruta)
  modsec/<sitio>/<nombre>.conf       # después del CRS
```

Plantilla de una exclusión (`configs/modsec-crs/app.localhost/subida-soporte-920420.conf`):

```apache
# Ruta: POST /solicitudes/nueva/ING
# Regla: 920420 (tipo de contenido no permitido)
# Motivo: <qué dispara la regla y por qué es legítimo>; probado con un PDF de 20 MB (CA-20).
SecRule REQUEST_URI "@streq /solicitudes/nueva/ING" \
  "id:1000001,phase:1,pass,nolog,ctl:ruleRemoveById=920420"
```

## Exclusiones vigentes

| Archivo | Sitio y ruta | Regla | Motivo |
|---|---|---|---|
| `modsec-crs/glpi.localhost/locale-953100.conf` | `glpi.localhost` · `GET /front/locale.php` | 953100 (PHP Information Leakage, salida) | El catálogo de traducciones de GLPI contiene frases como las de los errores de PHP; la regla cortaba la respuesta y el navegador recibía 500 (B-39). Probado con `auditoria/scripts/verificar-w01.sh` y `infra/waf/pruebas.sh glpi.localhost` |

Los ID propios empiezan en 1000101 para GLPI y en 1000001 para la aplicación.
