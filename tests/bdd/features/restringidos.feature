# language: es
@T7 @A01-2025 @CA-10 @RD-05 @RF-20 @RS-09
Característica: Los campos restringidos no salen de su tabla

  Escenario: Camino feliz — RRHH ve el motivo y queda auditado el acceso
    Dado un retiro con el motivo "CENTINELA-7f3a" emitido por RRHH
    Cuando RRHH abre el detalle de la solicitud
    Entonces ve el motivo
    Y el acceso queda en la auditoría

  Escenario: Adversarial — el centinela no llega a ningún destino no autorizado
    Dado un retiro con el motivo "CENTINELA-7f3a" emitido por RRHH
    Cuando se crean los tickets, los técnicos los resuelven y se sincroniza
    Entonces el valor no aparece en GLPI, auditoría, logs, dashboard, ficha ni CSV
    Y la cadena de auditoría sigue íntegra

  Escenario: Adversarial — quien registró la renuncia no ve el motivo y un técnico ni siquiera la ve
    Dado una renuncia registrada por el propio colaborador con el motivo "CENTINELA-7f3a"
    Cuando el colaborador y un técnico piden el detalle de la solicitud
    Entonces el colaborador ve la solicitud sin el motivo
    Y al técnico se le responde que no existe
