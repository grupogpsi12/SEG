# language: es
@T2 @T9 @T14 @A09-2025 @A04-2025 @RS-06 @RS-09 @RS-15 @RD-05
Característica: Los secretos y los datos sensibles no salen de donde viven

  Escenario: Camino feliz — la clave service_role solo está en el contenedor de administración
    Cuando se revisa qué servicios del compose montan el secreto "supabase_service_role"
    Entonces solo lo monta "admin-usuarios"

  Escenario: Borde — los secretos y el entorno generado no se versionan
    Cuando se lista lo que git versiona
    Entonces no hay nada bajo "secrets/" salvo el aviso y los cifrados, ni un infra/.env

  Escenario: Adversarial — un valor bajo una clave prohibida no llega al registro
    Cuando se registra un evento con la contraseña, el token, el motivo y la descripción de una persona
    Entonces ninguno de esos valores aparece en el registro JSON
    Y el registro conserva el correlation_id

  Escenario: Adversarial — las plantillas de tickets no tienen campo de contraseña
    Cuando se generan los tickets de un ingreso
    Entonces ningún título ni contenido menciona contraseñas ni claves
