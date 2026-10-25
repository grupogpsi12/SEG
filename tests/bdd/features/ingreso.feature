# language: es
@T1 @T12 @A07-2025 @RF-01 @RF-02 @RF-04 @CA-14 @RS-08 @WSTG-ATHN
Característica: Ingreso con segundo factor (AAL2)

  Escenario: Camino feliz — la sesión nace solo tras el segundo factor
    Dado una persona con contraseña válida y el TOTP por inscribir
    Cuando ingresa su contraseña correcta y un código TOTP vigente
    Entonces se crea la sesión
    Y el identificador de sesión cambió

  Escenario: Borde — contraseña correcta sin código
    Dado una persona con contraseña válida y el TOTP por inscribir
    Cuando ingresa su contraseña correcta y omite el código
    Entonces ninguna ruta protegida responde 200
    Y la sesión no guarda ningún token de Supabase

  Escenario: Adversarial — repetir un desafío ya consumido
    Dado una persona que ya consumió con éxito su desafío
    Cuando presenta de nuevo el mismo desafío con el mismo código
    Entonces el ingreso es rechazado

  Escenario: Adversarial con control positivo — agotar los intentos anula el desafío
    Dado una persona con contraseña válida y el TOTP por inscribir
    Cuando falla cinco veces el código
    Entonces ni el código bueno sirve con ese desafío
    Y un ingreso nuevo con el código correcto sí funciona

  Escenario: Borde — Supabase caído al verificar no deja entrar ni muestra detalles
    Dado una persona con contraseña válida y el TOTP por inscribir
    Cuando Supabase cae justo antes de verificar el código
    Entonces el ingreso falla con un mensaje genérico y sin sesión
