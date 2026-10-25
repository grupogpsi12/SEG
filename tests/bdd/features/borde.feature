# language: es
@requiere-stack @T19 @T20 @T21 @N-1 @N-2 @A02-2025 @RS-02 @RS-08 @RS-19 @CA-20
Característica: El borde es la única superficie

  Escenario: Solo el WAF publica puertos hacia fuera del equipo
    Cuando se listan los puertos publicados por los contenedores del stack
    Entonces bunkerweb publica solo el 80 y el 443
    Y ningún otro contenedor publica puertos fuera de 127.0.0.1

  Escenario: Adversarial — la API interna del WAF desde la red de la aplicación
    Cuando la aplicación pide "http://bunkerweb:5000/instances" sin token y con un token incorrecto
    Entonces ninguna respuesta es 200

  Escenario: Adversarial con control positivo — un ataque se bloquea y lo legítimo sigue pasando
    Dado que no hay ninguna IP baneada
    Cuando se envía un ataque de inyección SQL por el User-Agent
    Entonces el WAF responde 403
    Cuando se levanta el baneo y se envía una petición normal
    Entonces la aplicación responde con una redirección al ingreso

  Escenario: Borde — el ritmo humano no recibe 429
    Dado que no hay ninguna IP baneada
    Cuando se piden seis páginas legítimas a un ritmo de una por segundo y medio
    Entonces ninguna respuesta es 429

  @pendiente-F7
  Escenario: Adversarial — los tokens de GLPI no viajan en claro entre el worker y GLPI
    Cuando se captura el tráfico entre el worker y glpi durante una sincronización
    Entonces ninguna trama contiene las cabeceras App-Token ni Session-Token en claro
