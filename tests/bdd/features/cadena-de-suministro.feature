# language: es
@T16 @A03-2025 @RS-11 @N-5
Característica: La cadena de suministro es verificable

  Escenario: Camino feliz — cada dependencia está fijada con su hash
    Cuando se lee el archivo de dependencias de la imagen
    Entonces toda dependencia tiene versión exacta y al menos un hash

  Escenario: Borde — las imágenes de terceros y las acciones de CI se fijan por resumen
    Cuando se leen los compose, el Dockerfile y los flujos de CI
    Entonces cada imagen de terceros lleva un resumen sha256
    Y cada acción de GitHub se fija a un commit completo

  @requiere-red
  Escenario: Adversarial con control positivo — pip-audit no encuentra vulnerabilidades y sí ve las sembradas
    Cuando se audita el archivo de dependencias de la imagen
    Entonces no hay vulnerabilidades conocidas
    Y una dependencia vieja sembrada sí se reporta

  Escenario: Adversarial — ningún documento declara algo con un hueco sin llenar
    Cuando se buscan marcadores sin reemplazar en la documentación
    Entonces no hay ninguno
