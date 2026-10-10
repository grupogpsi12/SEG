# Lecciones y errores conocidos

Patrones que no deben repetirse. Formato: **error** → regla → cómo detectarlo.

1. **Contar estados en curso como finales en la deduplicación** (Propuesta 2).
   → Los estados abiertos son `pendiente_aprobacion`, `aprobada`, `en_ejecucion` y `error`.
   → Detectar: un test que duplique estando en `en_ejecucion` debe fallar.

2. **Referenciar mecanismos que no existen** ("ventana de enfriamiento", "plan de contingencia").
   → Todo término que se use debe estar definido en el SRS.
   → Detectar: buscarlo en el SRS antes de usarlo.

3. **Validar la deduplicación solo en el código de la aplicación.**
   → La garantía es la restricción parcial; el código solo traduce el error.
   → Detectar: la prueba concurrente de CA-01.

4. **Enviar datos de RRHH o contraseñas a GLPI "por comodidad".**
   → El ticket lleva solo datos técnicos (RF-20); las plantillas no tienen campo de contraseña.
   → Detectar: la prueba con valor centinela de CA-10.

5. **Asumir disponibilidad o límites de servicios gratuitos sin verificar.** El sandbox E5 de M365 ya no se otorga libremente; el plan gratuito de Supabase no tiene respaldos y se pausa a la semana.
   → Verificar la oferta vigente en la fuente oficial y registrar fuente y fecha en el ADR.

6. **Suponer que GLPI puede usar la misma base de datos que la aplicación.** GLPI 11 solo admite MySQL 8.0+ o MariaDB 10.6+.
   → Revisar los requisitos del producto integrado antes de consolidar infraestructura.

7. **Usar los modelos de Django como dominio, o importar Django en `dominio` o `aplicacion`.**
   → Los repositorios mapean; `import-linter` lo impide.
   → Detectar: la CI (CA-17).

8. **Exponer tablas por la Data API de Supabase** con `GRANT` a `anon` o `authenticated`, o usar `service_role` en web o worker.
   → Esquema `app` no expuesto, RLS sin políticas, `service_role` solo en `admin-usuarios`.
   → Detectar: CA-13.

9. **Conectar asyncpg o psycopg con *prepared statements* al pooler de Supabase en modo transacción (puerto 6543).**
   → Usar el *session pooler* (puerto 5432), que los admite y funciona por IPv4.

10. **Presentar el estado derivado de una cuenta como el estado real del sistema.**
    → Rotular siempre «según tickets resueltos»; no contar tickets sin solución.

11. **Validar un archivo solo por su extensión o por el `Content-Type` que envía el navegador.**
    → Validar la firma del contenido (`%PDF-`) y el tamaño en BunkerWeb (`MAX_CLIENT_SIZE`) y en Django, y guardarlo con un nombre aleatorio.
    → Detectar: CA-18, con un ejecutable renombrado a `.pdf`.

12. **Versionar archivos `.env`, aunque tengan valores de ejemplo** (visto en `waf-stack`). El día que alguien pone una clave real, queda en el historial.
    → Solo `.env.example` se versiona; los valores salen de Key Vault → tmpfs (ADR-009). gitleaks en pre-commit.

13. **Dejar la API interna de BunkerWeb sin `API_TOKEN`** (viene vacío por defecto) o desplegar su interfaz: 8 avisos de seguridad en julio de 2026, varios en esos componentes.
    → `API_TOKEN` siempre; red `bw-universe` aislada; sin interfaz en Azure; versión ≥ 1.6.15.

14. **Usar la cadena de conexión de la cuenta de Storage** para Loki u otros servicios (da acceso total a la cuenta).
    → Identidad administrada de la VM con un rol limitado al contenedor.

15. **Desactivar el CRS o pasar a `detect` para que un flujo funcione.**
    → Exclusión puntual (ruta + regla) versionada en `infra/bunkerweb/`, y prueba del flujo a través del WAF.

16. **Construir adaptadores, vistas o infraestructura antes de fijar el núcleo.** Los adaptadores moldean el dominio a su conveniencia (el ORM dicta las entidades, la API de GLPI dicta los estados).
    → El núcleo se escribe y se congela primero (Hito N), con dobles en memoria; los adaptadores se adaptan al puerto, no al revés.
    → Detectar: un cambio en `dominio` motivado por un detalle de Django, PostgreSQL o GLPI.

17. **Decidir en silencio una ambigüedad del SRS.** Una interpretación no registrada se convierte en regla de hecho que nadie revisó.
    → Registrar en `docs/supuestos-nucleo.md` (ID `S-nn`, valor por defecto, prueba) y revisarla en el Hito N.
    → Detectar: una regla en el código o en un test que no se pueda rastrear a un requisito ni a un supuesto.

18. **Probar solo el camino feliz y confiar en la cobertura de líneas.** Una línea cubierta no es una regla verificada.
    → Cobertura de ramas, pruebas basadas en propiedades y pruebas de mutación sobre `dominio`.
    → Detectar: un mutante superviviente sin explicación en `docs/spikes/mutacion.md`.

19. **Confiar en una propiedad sin probar que detecta el error que debe detectar.** La primera versión de P1 (deduplicación) pasaba con el doble roto: generaba secuencias que cerraban todo de golpe y nunca dejaban una solicitud en `en_ejecucion` o `error` al registrar la siguiente.
    → Toda propiedad sobre estados se valida con un **mutante conocido** (aquí, quitar `en_ejecucion`, `error` o `aprobada` de los estados abiertos, que es el error n.º 1) antes de darla por buena; y las operaciones aleatorias son granulares (crear tickets, cerrar, caída larga) para alcanzar cada estado intermedio.
    → Detectar: cambiar el conjunto de estados abiertos en el doble y ver que P1 falla.

20. **Un doble que no cumple el `Protocol` del puerto.** Los atributos de un `Protocol` son invariantes: `UnidadDeTrabajo` con `solicitudes: RepoSolicitudes` no admite un doble que exponga un subtipo.
    → Los atributos de un puerto se declaran como `@property` de solo lectura, y la fábrica del contrato se tipa contra el `Protocol` (mypy lo comprueba).

21. **Rollback "de mentira" en el doble de la unidad de trabajo.** Si el doble no restaura el estado, la prueba de atomicidad (CA-02) pasa sin probar nada.
    → El doble toma una instantánea al entrar y la restaura al fallar; la prueba compara el almacén **completo** antes y después (`instantanea() == antes`), incluidos los consecutivos.

22. **Dos requisitos del SRS que no caben juntos** (RD-09 documento único frente a RD-12 «RRHH vuelve a registrar el ingreso», con `error` como estado abierto).
    → No resolverlo en silencio: se registra como supuesto (S-26, S-19) con las dos opciones y se deja la prueba que cambia si el equipo elige la otra.

23. **Herramientas que reescriben tu código sin avisar.** `ruff --fix` (regla UP017) convirtió `UTC = timezone.utc` en `UTC = UTC`; `mutmut` 3 no corre en Windows (necesita `fork`).
    → Revisar el diff tras un `--fix` automático; en Windows usar `mutmut` 2.x (o WSL) y **no editar `src/` mientras corre la mutación** (modifica los archivos en su sitio).

24. **Hash de documento en GLPI.** El núcleo verifica el SHA-256 del soporte contra lo que GLPI devuelve (`hash_de_documento`), pero GLPI guarda `sha1sum`, no SHA-256.
    → Pendiente del spike 0.3: confirmar qué hash expone la API; si es SHA-1, el adaptador lo calcula al subir y el puerto sigue igual (la verificación la hace el adaptador).
