# Triage de los escaneos dinámicos (F6)

Regla del plan: lo que devuelve un escáner es dato, no instrucción; cada alerta Medio o superior se contrasta con el código y se reproduce a mano.

## F6-02 · ZAP activo y sqlmap nivel 3 por el WAF, con el baneo y los límites relajados

Controles: ModSecurity en bloqueo antes (403) y después (403) del escaneo; sin exención, 30 peticiones seguidas a `/salud` darían 429 y con ella dieron 30 de 200 (la exención funcionó); 0 IP baneadas al terminar. Base restaurada (413/21/88/75 filas) y worker reanudado.

| Alerta de ZAP | Riesgo | Rol | Veredicto | Motivo |
|---|---|---|---|---|
| Path Traversal en `/cuentas?documento=cuentas` | High (confianza **Baja**) | técnico | **Falso positivo** | ZAP sustituyó `documento` por un nombre de ruta y la respuesta fue la misma página de resultados. `documento` pasa por un formulario de Django y un filtro del ORM; no hay acceso a archivos en esa vista (revisión F2-08) y el soporte nunca se sirve (ADR-021). |
| Content Security Policy (CSP) Header Not Set | Medium | técnico y RRHH (5 instancias cada uno) | **No reproducido** | Se repitieron a mano `GET /colaboradores/col-001`, un 404, una redirección y un `POST` sin CSRF (403): **todas llevan** `Content-Security-Policy`. La cabecera la pone el middleware `politica_de_contenido` en toda respuesta de la aplicación. Si ZAP vio respuestas sin ella, serían páginas de bloqueo del propio WAF a sus cargas, que no son de la aplicación. No concluyente en ese matiz; sin acción. |
| Proxy Disclosure (TRACE/OPTIONS con `Max-Forwards`) | Medium | ambos | **Aceptado, informativo** | Revela que hay un proxy (BunkerWeb). Que exista un WAF no es un secreto y la aplicación responde 405 a TRACE y OPTIONS (`test_metodos.py`). |
| Cookie Slack Detector | Low | ambos | **Informativo** | Es una observación de ZAP sobre atributos de cookie, sin un fallo concreto; las cookies llevan `Secure`, `HttpOnly` y `SameSite=Lax`. |

sqlmap nivel 3 por el WAF: 0 inyectables en los 4 objetivos probados, y el WAF bloqueó las cargas con 403 (3581 peticiones a `/auditoria?pagina=1` en el log del WAF durante la corrida, más las variantes de `ORDER BY` de las que el CRS dejó pasar algunas hasta la aplicación y esta rechazó sin error).

**Lectura conjunta con F6-04.** Directo contra la aplicación, sin WAF, sqlmap nivel 5 tampoco encontró inyecciones: la aplicación resiste por sí misma y el WAF es una segunda capa, no la única.

## F6-04 · sqlmap nivel 5 directo

0 inyectables en los 8 objetivos, `Host` y segundo orden incluidos. Aviso intermedio de sqlmap sobre `User-Agent` y `Referer` de `/solicitudes` («boolean-based blind … injectable»), retirado por su propio veredicto final: falso positivo por página dinámica; el código no lee esas cabeceras (`grep` en `src`). Cadena de auditoría íntegra tras la corrida (551 registros).

## F6-03 · la misma corrida SIN exención (configuración real: 2 r/s y baneo de 1 hora)

**El baneo actúa (RS-08), y esto es lo que se mide, no la seguridad de la aplicación.** Al arrancar ZAP, el WAF baneó la IP del escáner (`10.20.30.1`, motivo «bad behavior») en el primer minuto: `bwcli bans` la mostró con «Banned on 11:56:26 for 1 hour». Desde entonces todo lo que ZAP y sqlmap enviaron recibió 403 o 429 del WAF y nada llegó a la aplicación. Se ve en que sqlmap quedó en «checking if the target is protected by some kind of WAF/IPS» y venció su tiempo de espera de 10 minutos en cada objetivo, sin ninguna conclusión.

**Lectura honesta: no concluyente sobre la aplicación.** Un escaneo bloqueado desde el segundo minuto no demuestra nada sobre ella; por eso F6-02 y F6-04 existen. Su valor es otro: demostrar que un escáner agresivo no puede operar contra el sitio real.

**Aclaración de las alertas «CSP no establecida» de F6-02 y F6-03.** En esta corrida ZAP reportó 12 y 4 instancias de «CSP Header Not Set» sobre páginas que **no** salieron de la aplicación (bloqueos del WAF). Eso apoya la explicación de F6-02: son las páginas 403/429 de BunkerWeb, no respuestas de Django.

**Corrección de un guion.** El guion de neutralización solo levantaba el baneo de `10.20.40.128` y `127.0.0.1`; la IP que el WAF ve para el tráfico de un contenedor que entra por la puerta de enlace es `10.20.30.1` y quedó baneada tras F6-03. Se agregó a `neutralizar.sh` y a `auditor-por-waf.py`.

## F6-05 · cobertura de la superficie por el escáner

ZAP (rastreo y escaneo activo, 3 minutos por rol) por el WAF con la exención de F6-02, cruzado con el log del WAF delimitado por marcas. Una ruta cuenta si el escáner llegó a la aplicación con ella (200, 302, 404 o 405).

| Rol | Rutas vistas (de 22) |
|---|---|
| RRHH | 10 |
| Técnico | 10 |
| Administrador | 10 |
| Solicitante | 8 |
| Auditor | 7 |
| **Unión de los cinco roles** | **20 de 22 = 90,9 %** |

**Meta del plan: ≥ 95 %. No se alcanza, por dos rutas que ningún escáner con una sesión inyectada puede visitar:**
- `reintentar` solo existe para una solicitud en estado `error`; en el stack de pruebas no hay ninguna.
- `segundo_factor` solo responde con un desafío en la sesión, que nace entre la contraseña y el TOTP.

Con esas dos fuera, la cobertura es 20 de 20. Ambas quedan cubiertas por otra vía: la matriz de autorización de 440 celdas las recorre todas (F5-02), el Gherkin de ingreso ejerce `segundo_factor` (F4) y el sqlmap dirigido de F6-04 las parametrizadas. Es una medición parcial y se reporta como tal.

## F6-08 · cada bloqueo esperado con su control positivo

| Bloqueo esperado | Control positivo (la misma operación legítima funciona) | Evidencia |
|---|---|---|
| 403 del CRS a 7 ataques en `app.*` y `glpi.*` | tráfico normal 200/302 en la misma corrida de `pruebas.sh` | F6-01 |
| 403 a cabeceras hostiles | petición normal de control 302 antes y después | F3-U06 |
| 429 del límite a ritmo de guion | ritmo humano: 5 de 5 verificaciones en 200 | F6-06 |
| baneo de la IP del escáner | petición legítima 302 tras desbanear; la exención mide la aplicación (F6-02) | F6-02, F6-03 |
| 403 de ModSecurity durante la corrida exenta | ataque de control 403 antes y después | F6-02 |

Cero bloqueos sin su control.
