# language: es
@T8 @A01-2025 @CA-13 @RD-10 @RS-14 @N-4
Característica: Los datos de Supabase solo se alcanzan por el servidor

  Escenario: Camino feliz — la aplicación solo se conecta a la base por el rol acotado
    Dado la configuración de producción de la base de datos
    Entonces se conecta con el usuario "app_backend", con TLS verify-full y en el esquema "app"

  Escenario: Adversarial — el código nunca usa la API de datos de Supabase
    Cuando se busca en el código la API REST de datos de Supabase
    Entonces no hay ninguna referencia a "rest/v1", "postgrest" ni a la clave anon

  Escenario: Adversarial — el aprovisionamiento le quita todo a anon, authenticated y service_role
    Cuando se lee el script que deja al dueño separado
    Entonces revoca todo sobre el esquema de la aplicación a PUBLIC, anon, authenticated y service_role

  Escenario: Borde — el catálogo local y el de Supabase coinciden salvo lo declarado
    Dado las instantáneas de catálogo de F3-PAR
    Cuando se comparan sección por sección
    Entonces solo difieren las extensiones de la plataforma y los roles propios de Supabase

  @pendiente-F7
  Escenario: Adversarial — la API de datos de Supabase con la clave pública no devuelve nada
    Cuando se pide una tabla del esquema "app" a la API de datos con la clave pública
    Entonces la respuesta no contiene filas
