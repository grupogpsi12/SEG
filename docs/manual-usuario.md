# Manual de usuario — Sistema de eventos laborales (Andina Servicios)

Para quién: las personas que usan la aplicación (colaboradores, jefes, RRHH, TI, Auditor y Administrador). Todos los datos de ejemplo son ficticios.

## Ingresar

1. Abra la dirección de la aplicación (`https://app.<dominio>`) y escriba su correo y su contraseña.
2. **La primera vez** la aplicación le muestra una **clave**. Regístrela en su aplicación autenticadora (Google Authenticator, Microsoft Authenticator, Aegis u otra) como clave «basada en tiempo», y escriba el código de 6 dígitos que le muestra la app. Si recarga la página, se genera una clave nueva: use siempre la última.
3. **Las siguientes veces** solo se pide el código de 6 dígitos.

Tenga en cuenta:
- Si el correo o la contraseña no coinciden, el mensaje no dice cuál de los dos falló. Así nadie puede averiguar qué correos existen.
- Tras varios intentos fallidos en un minuto, su conexión queda bloqueada temporalmente.
- La sesión se cierra tras 30 minutos sin actividad y, en todo caso, a las 8 horas. Use **Salir** cuando termine.
- Su cuenta la crea el Administrador del sistema; no hay registro abierto. Si «no tiene acceso a la aplicación», pídale que revise sus roles.

## Colaborador (rol Solicitante)

| Quiere… | Haga esto |
|---|---|
| Pedir vacaciones | **Nueva solicitud → Vacaciones**. Indique la fecha de inicio y la de regreso. |
| Presentar su renuncia | **Nueva solicitud → Retiro**. Indique su último día y el motivo. El motivo **solo lo ve RRHH**. |
| Ver en qué van sus solicitudes | **Mis solicitudes**, de la más reciente a la más antigua, de 50 en 50 (enlaces **Más recientes** y **Más antiguas**). Haga clic en el número para ver el detalle. |
| Cancelar una solicitud | En **Mis solicitudes**, botón **Cancelar**. Solo se puede mientras siga *pendiente de aprobación*. |

No puede haber dos solicitudes abiertas del mismo tipo para la misma persona: la aplicación se lo indicará.

## Jefe directo (rol Solicitante con personas a cargo)

Además de lo anterior, en **Nueva solicitud** aparecen **Cambio de departamento** y **Cambio de sucursal**. Solo puede elegir a sus subordinados directos.

## RRHH

| Tarea | Dónde |
|---|---|
| Aprobar o rechazar lo que registraron colaboradores y jefes | **Bandeja de RRHH**. Para rechazar, escriba la justificación. Al aprobar, los tickets se envían a TI automáticamente. |
| Revisar el detalle, incluido el motivo de retiro o la descripción de una emergencia | Clic en el número de la solicitud. Solo RRHH ve ese campo, y cada consulta queda registrada. |
| Emitir directamente cualquier evento (ingreso, vacaciones, cambios, retiro, emergencia) | **Nueva solicitud**. Busque a la persona por su **número de documento** y escriba la justificación. Queda emitida sin pasar por la bandeja. |
| Registrar un ingreso | **Nueva solicitud → Ingreso**. Adjunte el **soporte de vinculación en PDF** (máximo 20 MB). Se rechaza cualquier archivo que no sea PDF, aunque se llame `.pdf`. |
| Emitir una emergencia (despido con justa causa o fuga) | **Nueva solicitud → Emergencia**. La fecha efectiva es la de hoy y la prioridad es máxima. |
| Ver contratos que vencen en 7 días | **Bandeja de RRHH**, sección «Contratos por vencer». |

RRHH no puede aprobar ni emitir solicitudes sobre su propia persona; esas las emite el Administrador.

## Técnicos de TI (AD, Comunicaciones, Licencias, Inventario)

El trabajo técnico se hace **en GLPI** (`https://glpi.<dominio>`). La aplicación crea los tickets por usted y los sincroniza cada 5 minutos.

| Pantalla | Para qué |
|---|---|
| **Dashboard** | Pendientes por cola (la suya aparece resaltada), vencidos, exposición de retiros y emergencias, solicitudes del mes, cuentas, equipos, programados de 7 días y cierres incompletos. No se actualiza solo: use **Actualizar**. |
| **Cuentas** | Busque por nombre, documento, usuario, departamento, sede, sistema o estado. **Exportar CSV** descarga el resultado completo (la exportación queda registrada). |
| **Ficha del colaborador** | Clic en un nombre. Muestra datos laborales, cuentas, equipos, licencias, solicitudes y tickets con enlace a GLPI. Cada consulta queda registrada. |

**Para cerrar bien un ticket en GLPI:** ponga el estado en *Resuelto* **y** escriba la **solución** con la plantilla de su cola. En Inventario adjunte además el **acta**. Sin eso, la aplicación no da por cerrado el trabajo ni cambia el estado de la cuenta.

## Auditor

**Auditoría**: muestra los registros del más reciente al más antiguo, de 50 en 50. El botón **Verificar la integridad de la cadena** recorre la cadena completa y, si alguien alteró un registro directamente en la base de datos, indica la posición del primero afectado. La verificación también queda registrada.

## Administrador del sistema

| Tarea | Dónde |
|---|---|
| Crear o desactivar una cuenta | Por línea de comandos: `docker compose -f infra/compose.yaml run --rm admin-usuarios crear --correo X --rol Y [--colaborador col-…]` o `… desactivar --usuario <id>`. La contraseña inicial **se muestra una sola vez**: entréguela por un canal seguro. |
| Cambiar los roles de una persona | **Administración → Usuarios y roles**. Las combinaciones incompatibles se rechazan; usted no puede cambiar sus propios roles. |
| Mantener la matriz de perfiles (grupos, licencias, equipo y recursos compartidos por departamento y sede) | **Administración → Matriz de perfiles**. Los cambios aplican a los eventos futuros. |
| Reintentar una solicitud cuya emisión a GLPI falló | **Solicitudes en error → Reintentar** (revise antes que GLPI esté disponible). |
| Emitir un evento sobre una persona de RRHH | **Nueva solicitud**, con su documento y una justificación (emisión por excepción). |
