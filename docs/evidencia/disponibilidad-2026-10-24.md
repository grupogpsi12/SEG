# Evidencia de CA-11 — detección de fallos y restauración desde respaldos

Para quién: el equipo y quien evalúe el proyecto (ítem 5.3; RNF-01, RNF-04 y RD-06). **Fecha:** 24/10/2026, en el stack local (`compose.local.yaml`).

**CA-11:** el fallo simulado de GLPI y de Supabase se detecta en menos de 2 minutos, y la restauración completa desde los respaldos tarda menos de 4 horas.

## 1. Detección de fallos (RNF-01)

```bash
infra/scripts/deteccion.sh glpi     # detiene GLPI y mide hasta que el worker queda unhealthy
infra/scripts/deteccion.sh base     # detiene la base y mide hasta que web queda unhealthy
```

| Fallo | Antes | Después | Exigido |
|---|---|---|---|
| GLPI detenido | worker **sigue «healthy» a los 300 s** | worker unhealthy a los **63 s** | < 120 s |
| Base detenida (Supabase en Azure) | — | web unhealthy a los **56 s** | < 120 s |

**Causa del incumplimiento.** El chequeo del worker solo miraba el latido de la última sincronización. Ese latido envejece tras 3 ciclos de 5 minutos, así que GLPI caído pasaba inadvertido hasta 15 minutos.

**Corrección:**
- `worker --salud` también pregunta a la raíz de la API de GLPI, sin tokens: cualquier respuesta por debajo de 500 prueba que GLPI está arriba.
- Los chequeos de `web` y `worker` pasan a 30 s × 2 intentos.
- `tests/adaptadores/test_infra.py` impide subirlos por encima de 2 minutos en el peor caso.

## 2. Respaldo y restauración (RNF-04: RPO de 24 h y RTO de 4 h)

```bash
JML_MODO=local JML_RESPALDO_DESTINO=.contrato-tmp/respaldos infra/scripts/respaldo.sh
infra/scripts/restaurar-prueba.sh .contrato-tmp/respaldos
```

**Respaldo:**
- `pg_dump` del esquema `app` como `app_owner`: 96 KB.
- `mariadb-dump` de GLPI: 132 KB.

**Restauración en instancias nuevas y desechables:**
- PostgreSQL 17 con los roles de Supabase y el dueño separado (ADR-028).
- `pg_restore` del esquema `app` y `migrar`, como indica `docs/operacion.md` §6.
- MariaDB 11.4 con el volcado de GLPI.

Resultado:

```
filas por tabla: iguales en 24 tablas (sincronizacion y django_session las escribe el sistema solo)
cabeza de la cadena: igual (secuencia 92)
cadena de auditoria: VALIDA segun la aplicacion, leida como app_backend
app_backend no puede modificar la auditoria (RD-02, CA-13)
GLPI (tickets, categorias, grupos, reglas, usuarios, documentos): iguales (0 114 5 97 9 3)
RESTAURACION COMPLETA Y VERIFICADA: 21 s de restauracion, 23 s con las comprobaciones (RTO exigido: 4 h)
```

- La verificación de la cadena la hace la **propia aplicación**, conectada como `app_backend`.
- La cabeza de la cadena coincide con la del origen, así que no se perdió ni se alteró ningún registro.
- `app_backend` sigue sin poder modificar la auditoría tras restaurar: los permisos viajan en el respaldo.
- `sincronizacion` y `django_session` no se comparan, porque el origen siguió vivo después del respaldo y el worker escribió una sincronización nueva.

**Hallazgo al restaurar.** El volcado trae su propio `CREATE SCHEMA app`, pero el esquema ya existe, vacío y de `app_owner`, tras el aprovisionamiento. `pg_restore` fallaba en esa línea. El simulacro omite esa entrada con `pg_restore -l | grep -v ' SCHEMA - app '` y `-L`, y así puede usar `--exit-on-error`. `docs/operacion.md` §6 lo indica.

## 3. Límites de esta evidencia

- **Entorno.** Se hizo en local. Falta repetirlo en Azure (5.2):
  - restaurar el volcado en un **proyecto de Supabase nuevo**;
  - descargar los respaldos de Blob, con la identidad administrada.

  El procedimiento y los scripts son los mismos.
- **Volumen.** Los datos de la base local son pocos. Con la semilla de carga (300 colaboradores y 6586 registros de auditoría) el volcado crece, pero sigue lejos del RTO.
