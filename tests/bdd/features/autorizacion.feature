# language: es
@T10 @T13 @T15 @A01-2025 @RF-03 @RF-05 @RF-09 @RF-15 @WSTG-ATHZ
Característica: Autorización por rol en cada recurso

  Esquema del escenario: Cada celda de la matriz (auditoria/matriz-authz.csv)
    Dado un usuario con rol "<rol>" autenticado
    Cuando solicita "<metodo> <ruta>"
    Entonces la respuesta es "<resultado>"

    Ejemplos: denegaciones con evidencia previa
      | rol           | metodo | ruta           | resultado |
      | solicitante   | GET    | bandeja        | 403       |
      | solicitante   | GET    | dashboard      | 403       |
      | tecnico_ad    | GET    | auditoria      | 403       |
      | rrhh          | GET    | admin_perfiles | 403       |
      | auditor       | GET    | bandeja        | 403       |
      | administrador | GET    | dashboard      | 403       |

    Ejemplos: controles positivos, la misma operación permitida a quien le corresponde
      | rol           | metodo | ruta           | resultado |
      | rrhh          | GET    | bandeja        | 200       |
      | tecnico_ad    | GET    | dashboard      | 200       |
      | auditor       | GET    | auditoria      | 200       |
      | administrador | GET    | admin_perfiles | 200       |

  Escenario: Adversarial — cada denegación por rol deja un evento
    Dado un usuario con rol "solicitante" autenticado
    Cuando solicita "GET bandeja"
    Entonces la respuesta es "403"
    Y queda un evento "acceso.denegado" con su usuario y la ruta

  Escenario: Adversarial — objeto ajeno del mismo tipo (IDOR)
    Dado que "u-col" registró unas vacaciones
    Cuando "u-jefe" solicita su detalle
    Entonces la respuesta es idéntica a la de un identificador inexistente

  Escenario: Adversarial — autoaprobación
    Dado que RRHH intenta emitir una solicitud sobre su propia persona
    Entonces es rechazada con el motivo de autoaprobación

  Escenario: Borde — dos solicitudes iguales abiertas no conviven
    Dado que "u-col" registró unas vacaciones
    Cuando "u-col" registra otras vacaciones iguales mientras la primera sigue abierta
    Entonces la segunda se rechaza como duplicada y queda una sola abierta
