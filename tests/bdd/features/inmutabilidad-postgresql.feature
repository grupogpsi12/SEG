# language: es
@integracion @T3 @T6 @T13 @T8 @A08-2025 @RF-14 @RD-02 @RD-10 @CA-01 @CA-13 @N-4
Característica: Inmutabilidad y permisos en PostgreSQL real

  Escenario: Adversarial — modificar una solicitud aprobada saltándose el repositorio
    Dado una solicitud aprobada en la base
    Cuando se intenta cambiar su fecha efectiva con el rol de la aplicación
    Entonces el disparador la rechaza y el contenido no cambia

  Escenario: Adversarial — modificar o borrar el campo restringido de una aprobada
    Cuando se intenta cambiar o borrar su campo restringido con el rol de la aplicación
    Entonces el disparador lo rechaza en los dos casos

  Escenario: Adversarial — borrar o modificar las tablas de solo inserción
    Cuando el rol de la aplicación ejecuta UPDATE, DELETE y TRUNCATE sobre auditoria, decision y cuenta_historial
    Entonces las tres sentencias fallan por falta de privilegio

  Escenario: Adversarial — el rol de la aplicación no apaga disparadores ni asume otros roles
    Cuando el rol de la aplicación intenta deshabilitar el disparador de solicitud y asumir anon
    Entonces ambas cosas fallan

  Escenario: Borde — anon, authenticated y PUBLIC no tienen nada en el esquema
    Cuando se consultan los privilegios de anon, authenticated, service_role y PUBLIC
    Entonces ninguno tiene acceso al esquema ni a sus tablas
    Y todas las tablas tienen RLS activo y ninguna política

  Escenario: Adversarial — dos altas simultáneas, una gana
    Cuando dos conexiones registran la misma solicitud a la vez
    Entonces una queda abierta y la otra se rechaza como duplicada
