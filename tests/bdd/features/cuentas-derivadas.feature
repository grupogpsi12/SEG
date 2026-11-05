# language: es
@T5 @A08-2025 @CA-05 @CA-08 @RF-24 @RF-25 @RF-26
Característica: El estado de las cuentas sale solo de los tickets resueltos

  Escenario: Camino feliz — con todos los tickets resueltos con solución la solicitud cierra y las cuentas se activan
    Dado un ingreso con sus tickets creados en GLPI
    Cuando los técnicos resuelven todos los tickets con solución y acta, y se sincroniza
    Entonces la solicitud queda cerrada
    Y las cuentas de AD, RED y M365 quedan activas

  Escenario: Adversarial — un ticket resuelto sin solución no cierra ni cambia la cuenta
    Dado un ingreso con sus tickets creados en GLPI
    Cuando el técnico de AD resuelve su ticket sin escribir la solución y se sincroniza
    Entonces la solicitud sigue en ejecución
    Y la cuenta de AD no se activa y queda marcada como cierre sin solución

  Escenario: Adversarial con control positivo — al registrar la solución sí cierra
    Dado un ingreso con sus tickets creados en GLPI
    Y que el técnico de AD resolvió sin solución y se sincronizó
    Cuando el técnico registra la solución y se sincroniza otra vez
    Entonces la solicitud queda cerrada
    Y la cuenta de AD queda activa

  Escenario: Borde — Inventario sin acta no cierra la solicitud
    Dado un ingreso con sus tickets creados en GLPI
    Cuando los técnicos resuelven todos los tickets con solución pero sin el acta de Inventario, y se sincroniza
    Entonces la solicitud sigue en ejecución

  Escenario: Borde — un ticket reabierto se refleja sin reabrir la solicitud
    Dado un ingreso con sus tickets creados en GLPI
    Y que todo se resolvió y la solicitud cerró
    Cuando el ticket de Licencias se reabre en GLPI y se sincroniza
    Entonces la solicitud sigue cerrada
    Y la cuenta de M365 vuelve a pendiente con la marca de reabierto
