# language: es
@T3 @T6 @A08-2025 @RF-14 @RF-35 @RF-36 @RD-03 @CA-09
Característica: Auditoría encadenada y detección de manipulación

  Escenario: Camino feliz — el Auditor verifica la cadena desde la interfaz
    Dado una cadena de auditoría con más de cincuenta eventos
    Cuando el Auditor ejecuta la verificación
    Entonces el resultado dice que la cadena es íntegra
    Y la verificación queda registrada en la propia cadena

  Escenario: Borde — una cadena vacía o de un solo evento también verifica
    Dado una cadena de auditoría con un solo evento
    Cuando el Auditor ejecuta la verificación
    Entonces el resultado dice que la cadena es íntegra

  Escenario: Adversarial con control positivo — manipulación detectada y reversible
    Dado una cadena de auditoría con más de cincuenta eventos
    Y que la verificación devuelve íntegra
    Cuando alguien altera el actor del evento diecisiete directamente en la base
    Entonces la verificación señala el evento diecisiete como el primero afectado
    Y al restaurar el valor la verificación vuelve a ser íntegra
