# language: es
@T17 @T18 @A06-2025 @CA-18 @RF-39 @RF-40 @RS-13
Característica: Soporte de vinculación en PDF

  Escenario: Camino feliz — se sube una vez, se vincula solo a AD y Licencias y se borra la copia
    Dado un ingreso emitido por RRHH con un PDF válido
    Cuando el worker crea los tickets en GLPI
    Entonces el documento queda vinculado solo a los tickets de AD y de Licencias
    Y la copia local se borra después de verificar el hash

  Escenario: Borde — veinte megabytes exactos se aceptan y uno más no
    Cuando RRHH sube un PDF de 20 MiB exactos
    Entonces el soporte se acepta
    Cuando RRHH sube un PDF de 20 MiB más un byte
    Entonces el soporte se rechaza antes de tocar el disco

  Escenario: Adversarial — un archivo que no es un PDF disfrazado de PDF
    Cuando RRHH sube un ejecutable llamado "acta.pdf"
    Entonces el soporte se rechaza antes de tocar el disco

  Escenario: Adversarial — nombres con recorrido de ruta o caracteres de control
    Cuando RRHH sube un PDF llamado "../../etc/passwd.pdf"
    Entonces el nombre guardado no conserva rutas ni caracteres de control

  Escenario: Adversarial — el hash del documento en GLPI no coincide
    Dado un ingreso emitido por RRHH con un PDF válido
    Cuando GLPI corrompe el documento al recibirlo y el worker intenta crear los tickets
    Entonces la copia local se conserva y el intento cuenta como fallo
