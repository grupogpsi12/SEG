# language: es
@T11 @T12 @T13 @A10-2025 @RNF-01 @RNF-02 @RF-18 @RF-38 @CA-01 @CA-07 @CA-11 @N-3
Característica: Resiliencia ante la caída de GLPI, de la base y de Supabase

  Escenario: Camino feliz — con GLPI caído se sigue aprobando y al volver no hay duplicados
    Dado que GLPI está caído
    Cuando RRHH emite un ingreso y el worker lo intenta varias veces
    Entonces la solicitud sigue aprobada y no se creó nada en GLPI
    Cuando GLPI se recupera y el worker procesa la bandeja
    Entonces existe exactamente un ticket por cada clave

  Escenario: Borde — tras diez fallos la solicitud pasa a error y el Administrador la reintenta
    Dado que GLPI está caído
    Cuando RRHH emite unas vacaciones y el worker agota los diez intentos
    Entonces la solicitud queda en error
    Cuando GLPI se recupera y el Administrador reintenta la emisión
    Entonces la solicitud llega a en ejecución sin tickets duplicados

  Escenario: Adversarial — el tiempo de espera después de crear no duplica el ticket
    Dado que GLPI crea el ticket pero la respuesta se pierde
    Cuando el worker reintenta la creación
    Entonces existe exactamente un ticket por cada clave

  Escenario: Borde — con la base caída el chequeo de salud responde 503 sin detalles
    Cuando la base de datos no responde
    Entonces el chequeo de salud responde 503 con un cuerpo genérico

  Escenario: Borde — un reinicio del proceso web pierde los desafíos en curso pero no abre acceso
    Dado una persona que ya pasó la contraseña y espera su código
    Cuando el proceso web se reinicia y presenta su código
    Entonces el desafío ya no existe y no entra
