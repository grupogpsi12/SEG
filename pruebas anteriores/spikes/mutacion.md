# Pruebas de mutación del dominio (ítem 1.13)

Herramienta: **mutmut 2.5.1** sobre `src/jml/dominio/` (1340 mutantes). Se usa la versión 2.x porque **mutmut 3 no corre en Windows** (necesita `fork`) y el equipo trabaja en Windows. Con 2.x hubo que escribir `dominio` sin la sintaxis `type X = …` ni `def f[T]` de PEP 695 (el analizador `parso` no la entiende); se usa `TypeAlias` y `TypeVar`, y `ruff` ignora UP040/UP047 por eso.

Cómo repetirlo: `make mutacion` (lento, unos 25 minutos). **No editar `src/` ni correr pruebas mientras corre**: mutmut modifica los archivos en su sitio. Si se interrumpe, `git checkout src` y borrar los `.bak`.

## Resultados

| Corrida | Pruebas | Eliminados | Supervivientes | Sospechosos | Tasa |
|---|---|---|---|---|---|
| 1.ª (parcial, 1332 mutantes) | 839 | 800 + 1 timeout | 528 | 3 | 60,1 % |
| **2.ª (completa, 1340 mutantes)** | 1045 | **1253 + 1 timeout** | **86** | **0** | **93,6 %** |
| 3.ª | 1077 | *interrumpida a pedido del equipo, sin resultado* | | | |

**Meta del prompt: ≥ 85 %. Cumplida por la 2.ª corrida (93,6 %).**

Entre la 1.ª y la 2.ª se agregaron `test_pines.py`, `test_pines_validacion.py`, `test_tickets_golden.py` (prueba dorada del texto de los tickets) y `test_bordes.py`.

## Clasificación de los 86 supervivientes de la 2.ª corrida

### Equivalentes: 27 (no se pueden matar; no cambian el comportamiento observable)

| Mutantes | Dónde | Por qué es equivalente |
|---|---|---|
| 14, 16, 92, 295, 710, 711 | `Escalar`, `ValorAuditable`, `UsuarioId`, `Dato`, `T = TypeVar("T")` | Alias y variables de tipo: solo los ve `mypy`, que ya falla si se rompen |
| 239–241, 581–583 | `dict[str, str \| int \| bool \| None]` en eventos de cuenta y de solicitud | Anotaciones de variable local: no se evalúan en ejecución |
| 180 | `catalogo.validar_evento`: nombre de campo en `a_utc(ahora, "ahora")` | Código inalcanzable: `hoy_en_bogota(ahora)` ya rechazó antes un `ahora` sin zona, con el mismo campo |
| 448 | `permisos.validar_roles`: `ordenados[i - 1:]` | Revisa pares ya revisados; el primer par incompatible detectado es el mismo |
| 628, 652 | `_justificacion(…, "aprobar"/"cancelar", obligatoria=False)` | Con `obligatoria=False` la etiqueta de la acción nunca llega a un error |
| 756 | `"sin especificar"` en el ticket de equipo del ING | `DatosIngreso` ya prohíbe `requiere_equipo` sin `tipo_equipo` |
| 844 | `traslada_equipo = None` | `None` y `False` se comportan igual en el único `if` que lo lee |
| 1112, 1114 | `usuarios._primer_token`: `"".join(tokens[1:2])` | Solo se usa la inicial del segundo apellido; con una o con varias piezas da la misma |
| 1216, 1221, 1251 | límites de `SolicitudId.de` y `split("@", 2)` | El regex de `SolicitudId`/`CorreoUPN` rechaza lo mismo inmediatamente después |
| 1291, 1293 | `/` y `\` en `NombreDeSoporteSaneado` | El regex `_RE_NO_PERMITIDO` ya los rechaza (defensa en profundidad redundante a propósito) |
| 1311 | `len(base) > _MAX_NOMBRE` frente a `>=` | Con exactamente 100 caracteres el recorte devuelve la misma cadena |
| 1340 | `hash(("CampoRestringido", valor))` | Cambiar la etiqueta cambia el valor del hash, no su consistencia |

### Faltaba una prueba: 59 (corregidos en `tests/dominio/test_supervivientes.py`)

- Campo y motivo exactos de rechazos poco frecuentes: auditoría, colaborador, perfiles, generación de tickets, observaciones, `a_utc` con `ahora` sin zona (≈ 45).
- Claves prohibidas de la auditoría (`contrasena`, `contraseña`) y su destino (`auditoria`), uno por uno.
- `activos.py` sin comprobación de `frozen`/`slots` (la prueba genérica no lo veía porque el mutante dejaba de ser dataclass).
- `abierta` y `final` de `Solicitud` convertidas en métodos (un método siempre es verdadero).
- `cerrar(1)` debe rechazarse (`> 0` frente a `> 1`).
- La justificación de una cancelación de RRHH debe guardarse.
- `nombre_de_sede("San Andrés")` → `Sanandres` y mayúscula inicial.
- `rstrip(".")` del recorte del usuario no puede comerse letras (`x`), ni `strip(" .")` del saneado de nombres.
- `a_utc` con una zona cuyo `utcoffset()` es `None`; `ascii_minuscula` con caracteres no ASCII.
- Representación y mensajes del campo restringido (`repr`, `format`, destino `serializacion`).

## Lo que NO está verificado

La 3.ª corrida (con las 32 pruebas de `test_supervivientes.py`) se detuvo para priorizar el desarrollo del núcleo. **No se midió la tasa final tras las correcciones.** Lo esperable es ≥ 93,6 % (solo pueden subir los eliminados); queda como verificación pendiente antes de congelar el Hito N, o en la CI nocturna.

## Hallazgos de proceso

- Un mutante de `usuarios.py` (`if candidato in ocupados` en un `while True`) produce un **bucle infinito** y mutmut 2 no lo cortaba en Windows. Se agregó `pytest-timeout` (`--timeout=30`) al runner (`setup.cfg`).
- Perfil de hypothesis `mutacion` (determinista, 25 ejemplos) en `tests/conftest.py`, para que los resultados sean reproducibles.
- La cobertura de ramas no bastaba: con 98 % de cobertura la 1.ª corrida eliminó solo el 60 %. Ver lessons.md n.º 18 y 19.
