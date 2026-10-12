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

25. **Duplicar una cabecera de seguridad en Django y en BunkerWeb**, o «arreglar» los avisos de `check --deploy` activando lo que ya hace el borde.
    → Una sola fuente por cabecera (RS-07). Los avisos que cubre BunkerWeb se silencian con su motivo en `SILENCED_SYSTEM_CHECKS`, y una prueba fija la lista exacta, de modo que cualquier aviso nuevo de `check --deploy` falla la CI.

26. **`monkeypatch` sobre una conexión de Django en una prueba sin `django_db`.** Al restaurar, `monkeypatch` deja fijado en la instancia el método bloqueante de pytest-django y todas las pruebas siguientes fallan con «Database access not allowed», pero solo según el orden de ejecución.
    → Parchear la referencia que usa el código bajo prueba (p. ej. `vistas.connections`), nunca el objeto conexión compartido.
    → Detectar: correr la suite completa en distinto orden (`tests/adaptadores tests/contratos` frente a la inversa).

27. **Pruebas de contrato con datos huérfanos.** El doble aceptaba un soporte sin solicitud o una entrada de bandeja sin ticket; la base, con claves foráneas, no. Las expectativas no estaban mal, los datos de partida sí.
    → Las pruebas de contrato siembran los datos padre como lo harían los casos de uso. Cambiar los datos de partida no es cambiar el contrato; cambiar una expectativa sí lo sería.
    → Además: pytest-django no prepara la base si la pide un fixture parametrizado con `getfixturevalue`; se marca `django_db` en la colección (`tests/conftest.py`).

28. **Comparar con el oráculo solo en instantes «normales».** La comparación ORM ↔ oráculo pasaba con un `<` cambiado por `<=` porque ningún dato caía justo en el borde.
    → Barrer instantes que incluyan los bordes exactos de cada ticket (emisión, activación, vencimiento, ±1 s, y −7 días para la ventana del indicador g) y los límites de mes. Validar la prueba introduciendo esos cambios a propósito.

29. **Escribir archivos con heredocs de bash que contienen comillas.** Un comando largo con varios heredocs y apóstrofes falló antes de ejecutarse («unexpected EOF») y no se aplicó nada.
    → Para crear o editar archivos usar Write/Edit; reservar Bash para ejecutar. Tras un fallo así, comprobar qué se aplicó antes de repetir.

30. **Redirigir tras una acción denegada a una página que también la deniega.** Un POST de aprobación hecho por un colaborador mostraba «sin permiso» pero redirigía a la bandeja de RRHH, que respondía 403 y ocultaba el mensaje.
    → El destino de la redirección depende del rol de quien actúa; probar el flujo con el rol que NO debe poder.


31. **Usar `motivo` como clave de datos de auditoría.** `motivo` está en las claves prohibidas (RD-05: es el campo restringido del retiro) y el evento lo rechaza o lo filtra.
    → Para la razón técnica de un rechazo usar `causa`. Antes de nombrar una clave de auditoría o de log, revisar `CLAVES_PROHIBIDAS` (`dominio/auditoria.py`).

32. **Agregar un supuesto S-nn sin actualizar sus pruebas de control.** `tests/dominio/test_supuestos.py` exige que el registro no tenga huecos, que cada ID esté nombrado en una prueba y que la columna «Prueba» cite funciones que existen.
    → Al agregar S-nn: subir el rango esperado, nombrar el ID en el docstring de la prueba y citar la función entre comillas invertidas en la fila.

33. **Instalar Docker Desktop desde una sesión sin privilegios.** `winget install Docker.DockerDesktop` falla (código 4294967291) si nadie acepta la elevación, y además Docker necesita WSL2, que exige reiniciar.
    → Pedírselo al equipo: PowerShell como administrador → `wsl --install` → reiniciar → `winget install -e --id Docker.DockerDesktop` → abrir Docker Desktop una vez.

34. **Una corrida contra Supabase cortada por la red deja una transacción huérfana.** La sesión quedó «idle in transaction» con bloqueos sobre `app_test`, y la corrida siguiente falló entera con `statement timeout` (187 errores que no eran del código).
    → Las conexiones llevan `idle_in_transaction_session_timeout=60000` (pruebas y producción): el servidor corta solo al huérfano.
    → Si vuelve a pasar: listar `pg_stat_activity` del rol `app_backend` y `pg_terminate_backend` solo de las sesiones propias en «idle in transaction» cuando no corre ninguna otra suite.

35. **Editar el código mientras una suite larga corre en segundo plano.** La suite importa módulos a medida que los necesita: 14 pruebas fallaron con `AttributeError` por una vista agregada a mitad de corrida.
    → Mientras corre una suite en segundo plano, solo se edita documentación. Los resultados de esa corrida valen para el commit en el que empezó.

36. **Probar un GRANT denegado esperando un error.** En PostgreSQL, un `GRANT` de alguien sin la opción de concesión no falla: solo avisa «no privileges were granted». La prueba no lanzaba la excepción y parecía que el permiso se concedía.
    → Probar el efecto (que la operación protegida siga negada), no el código de retorno del `GRANT`.

37. **Cambiar de dueño una secuencia ligada a una columna.** `ALTER SEQUENCE … OWNER` falla si la secuencia pertenece a una columna identity o serial: se mueve sola con su tabla.
    → Al reasignar dueños, recorrer solo tablas, vistas y funciones.

38. **Quitarle a `app_backend` la propiedad de tablas con RLS sin políticas.** El dueño se salta RLS; un rol que no es dueño no ve ninguna fila. Corregir H1 sin `BYPASSRLS` habría dejado la aplicación sin datos.
    → Cada vez que cambie quién es dueño de una tabla con RLS, revisar quién queda sin acceso (ADR-028).

39. **Una prueba que lee secretos de `JML_SECRETOS_DIR` bajo pytest-django.** `tests/adaptadores/ajustes.py` redefine esa variable a una carpeta temporal al importarse, así que la prueba de integración creyó que faltaba `supabase_service_role` y se omitió en silencio (aparecía «7 passed, 1 skipped»).
    → Las pruebas de integración ubican los secretos desde la raíz del repositorio, y se revisa siempre la línea de «skipped» (`-rs`).

40. **La CI de integración no debe correr `tests/adaptadores` con los ajustes de PostgreSQL.** Dos pruebas de configuración (`check_deploy`, `/salud` 503) asumen SQLite; con PostgreSQL fallan sin que haya un error real. Esa carpeta ya corre en el job `compuertas`.

41. **Scripts de `infra/` que llaman a `python3`.** En Git Bash de Windows `python3` es el atajo de la Microsoft Store y falla; con `set -e` el script se detiene a mitad y deja archivos de secreto vacíos.
    → Los scripts de infraestructura no dependen de Python (usar `/dev/urandom`, `openssl`, `base64`). Al reintentar, `asegurar` recrea los secretos vacíos.


42. **Archivos de datos fuera del paquete.** La imagen instala el proyecto con `pip install .` y setuptools solo empaqueta `.py`: en el contenedor faltaban las plantillas y el CSS y `/ingreso` daba 500, aunque las 1570 pruebas pasaban (corren desde el código fuente). Además, una prueba de empaquetado hecha sobre mi carpeta pasaba sin merecerlo, porque `src/jml.egg-info/SOURCES.txt` (residuo de la instalación editable) hace que setuptools incluya archivos.
    → Los datos del paquete se declaran en `pyproject.toml` (`package-data`). `test_empaquetado.py` construye desde una **copia limpia**, sin `*.egg-info`, y se comprobó que falla sin el arreglo.
    → Regla general: una prueba nueva se prueba también contra el defecto que dice vigilar.

43. **Probar un WAF con ráfagas.** El límite de peticiones (429) y el CRS (403) bloquean ambos; sin pausa entre peticiones, los ataques reciben 429 y la prueba «pasa» sin demostrar nada del CRS. Además el baneo es por sitio, y `curl -I` (HEAD) a una ruta que no lo acepta devuelve la página de error de BunkerWeb con su propia CSP.
    → `pruebas.sh` espera 1 s entre peticiones. Para revisar cabeceras usar `curl -D - -o /dev/null`, no `-I`.

44. **Montar de solo lectura un directorio que el servicio también escribe.** `bw-scheduler` crea subcarpetas en `/data/configs` y se reiniciaba en bucle con `Read-only file system`.
    → Se montan de solo lectura solo las subcarpetas que la configuración controla (`modsec-crs/`, `modsec/`).

45. **Heredocs de bash con comillas, otra vez.** Un comando largo con varios heredocs falló al analizarse y no se aplicó nada (lección 29).
    → Los scripts de edición de más de unas pocas líneas se escriben con la herramienta de archivos y se ejecutan aparte.


46. **Escribir un adaptador sin probarlo contra el sistema real.** El adaptador de GLPI pasaba 17 pruebas contra un simulador y, contra GLPI real, descubrimos cinco cosas que el simulador no podía saber: GLPI ignora `priority` y `time_to_resolve` al crear; responde 200 con una lista a `Ticket/no-existe`; acepta vincular a un documento 0; guarda los tokens cifrados; y trabaja en UTC.
    → Un simulador solo refleja lo que su autor creyó. Mientras no exista la suite contra el sistema real, el adaptador es provisional. Después, el simulador se actualiza con lo aprendido para que siga siendo útil.

47. **Probar contra un sistema con estado.** GLPI conserva los tickets entre pruebas y la suite esperaba empezar vacía: fallaban pruebas por residuos de corridas anteriores, no por el código.
    → El ayudante real limpia lo suyo al empezar (`limpiar()`), y solo si se declara que es un GLPI de pruebas (`JML_GLPI_DE_PRUEBAS=si`), porque las claves de prueba (`SOL-2026-000001`) podrían chocar con las de datos reales.

48. **Derechos de GLPI que no avisan.** Sin el bit 256 del derecho `slm`, GLPI ignora en silencio el vencimiento que se le envía (responde 200). Se halló por bisección automática sobre los 100 derechos que diferían del Super-Admin.
    → Ante un valor que «no se guarda» sin error, comparar contra una cuenta con todos los derechos y bisectar.

49. **Límites en cadena.** El WAF (21 MB), Django (20 MB) y GLPI (PHP con unos pocos MB) deben coincidir: GLPI respondía 413 al subir el soporte de 20 MB aunque todo lo anterior lo aceptaba.
    → Los límites de subida se declaran juntos (BunkerWeb, Django, `infra/glpi/php-jml.ini` y `document_max_size`) y se prueban con el archivo del tamaño máximo.

50. **Código que depende de la hora del servidor.** Se enviaba el vencimiento en hora de Bogotá a un GLPI que guarda UTC: quedaba 5 horas corrido. → Enviar siempre en la zona del servidor receptor (UTC) y documentar la conversión para quien lo lee (S-35).

51. **Una restricción por IP que incluye al proxy no restringe nada.** El cliente de API de GLPI admitía `10.20.40.0/24`, y BunkerWeb (`10.20.40.2`) está en ese rango: cualquiera que llegara por el WAF con los tokens entraba. Además, la API aceptaba usuario y contraseña, un inicio de sesión sin el doble factor de la interfaz.
    → Todo servicio detrás del WAF debe revisarse ruta por ruta: lo que solo usa la red interna se bloquea en el WAF y, además, en el propio servicio. Se prueba desde fuera (`pruebas.sh`) y desde la IP del WAF.

52. **Idempotente no significa seguro ante la concurrencia.** `configurar-glpi` busca y crea si no encuentra: dos corridas a la vez duplicaron grupos, reglas y SLA sin avisar. Pasó porque una tarea detenida siguió viva en segundo plano.
    → Un comando que crea objetos detecta duplicados y se detiene nombrándolos. Al detener una tarea, comprobar que sus procesos hijos (`docker run`) también terminaron.

53. **Una guía para otros solo está probada si se siguió desde cero.** Desde un clon limpio aparecieron tres fallos invisibles en la máquina del autor: las cuentas compartidas no servían con otra base, el WAF tapaba los 403 de la aplicación y la configuración concurrente de GLPI duplicaba.
    → Antes de entregar instrucciones, seguirlas en una carpeta nueva con un proyecto de Compose aparte (`-p`), sin los secretos del autor.

54. **Una prueba de concurrencia que exige un ganador concreto falla de forma intermitente.** H3 esperaba que ganara siempre la cancelación; la CI quedaba en rojo según el orden de los hilos y, como la imagen solo se publica con la CI en verde, el equipo siguió descargando una imagen rota durante dos commits.
    → En una carrera se verifica la invariante (gana exactamente una) y no quién gana. Revisar que lo publicado (`ultima`) corresponda al último commit.

55. **El WAF también reescribe respuestas legítimas.** BunkerWeb intercepta por defecto los 4xx y 5xx del upstream y pone su página: el «Su cuenta no tiene acceso» de la aplicación se veía como un bloqueo del WAF.
    → En sitios cuya aplicación genera sus propios errores con contenido, interceptar solo 502, 503 y 504 (`INTERCEPTED_ERROR_CODES`), y verificar a través del WAF los mensajes de error, no solo los códigos.
