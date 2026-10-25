# language: es
@T4 @A05-2025 @RS-05 @RS-13 @CWE-89 @WSTG-INPV
Característica: Las cabeceras HTTP son input no confiable

  Esquema del escenario: Cabecera hostil que llega a la aplicación
    Dado la base de datos con sus filas contadas
    Cuando se envía una petición válida con la cabecera "<cabecera>" y el valor "<valor>"
    Entonces la aplicación responde con una redirección o una página normal, nunca con un error de servidor
    Y la base de datos conserva las mismas filas

    Ejemplos:
      | cabecera        | valor                         |
      | User-Agent      | ' OR 1=1 --                   |
      | Referer         | x'); DROP TABLE auditoria;--  |
      | Accept-Language | es'; SELECT pg_sleep(5)--     |
      | Cookie          | a=b'; SELECT pg_sleep(5)--    |

  Escenario: Adversarial — un Host que no es el nuestro se rechaza
    Cuando se envía una petición con "Host: evil.example"
    Entonces la respuesta es 400

  Escenario: Adversarial — X-Forwarded-For desde un origen que no es BunkerWeb se descarta
    Cuando una petición llega desde "203.0.113.9" declarando "X-Forwarded-For: 10.1.1.1"
    Entonces la dirección del cliente sigue siendo "203.0.113.9"
    Y la cabecera reenviada ya no está en la petición

  Escenario: Borde con control positivo — desde BunkerWeb sí se toma la dirección reenviada
    Cuando una petición llega desde "10.20.40.2" declarando "X-Forwarded-For: 198.51.100.7"
    Entonces la dirección del cliente es "198.51.100.7"
