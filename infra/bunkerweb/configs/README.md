# Exclusiones de ModSecurity (RS-18, invariante 14)

Nunca se desactiva el CRS ni ModSecurity para que algo funcione. Cada falso positivo se resuelve con
**un archivo por exclusión**, con la ruta exacta, el ID de la regla y el motivo, y se prueba el
flujo completo a través del WAF (`infra/waf/pruebas.sh` y CA-20).

El scheduler de BunkerWeb monta esta carpeta en `/data/configs` (solo lectura). Estructura que
espera BunkerWeb 1.6 (confirmar en el spike 0.6):

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

Todavía no hay exclusiones: se agregan en el spike 0.6, a medida que el modo `detect` muestre
reglas disparadas por tráfico legítimo de la aplicación o de GLPI.
