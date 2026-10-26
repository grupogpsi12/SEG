"""Documento 5: Pruebas manuales complementarias (bandit, ZAP activo, Docker Bench, Wireshark, anti-DoS)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, Spacer

import comun as c

RAIZ = Path(__file__).resolve().parents[1]
SAL = RAIZ / "Documento-5-Pruebas-manuales-complementarias.pdf"


def main() -> None:
    est = c.estilos()
    h: list = c.portada(est, "5", "Pruebas manuales complementarias",
                        "Análisis estático, escaneo activo, endurecimiento de contenedores y verificación del control anti-DoS")

    h.append(Paragraph("1. Resumen", est["h1"]))
    h.append(Paragraph(
        "Este documento complementa las pruebas automatizadas y los escáneres de los Documentos 1 a 3 "
        "con cinco técnicas manuales ejecutadas a mano contra el despliegue local: análisis estático "
        "del código (bandit), escaneo dinámico activo con inyección de cargas reales (OWASP ZAP), "
        "auditoría de endurecimiento de los contenedores (Docker Bench), inspección del tráfico "
        "capturado (Wireshark) y verificación del control de disponibilidad del WAF (límite de "
        "peticiones y baneo). Juntas cubren las tres perspectivas: caja blanca (código), caja negra "
        "(ataque desde fuera) y configuración (contenedores y host).", est["cuerpo"]))
    h.append(c.tabla([
        ["Técnica", "Tipo", "Resultado", "Requisito"],
        ["bandit", "Estático (caja blanca)", "0 hallazgos en 8509 líneas", "RS-05, RS-11"],
        ["OWASP ZAP activo", "Dinámico con cargas reales", "0 FAIL · 110 reglas PASS", "RS-13, T4"],
        ["Docker Bench", "Config. de contenedores", "105 chequeos; aislamiento OK", "RS-14"],
        ["Wireshark", "Inspección de tráfico", "TLS externo; restringido no sale a GLPI", "RS-01, T7"],
        ["Verificación anti-DoS", "Control de disponibilidad", "429 y baneo responden", "RS-08, T13/T21"],
    ], [3.8 * cm, 4.5 * cm, 5.4 * cm, 3.3 * cm], est))

    h.append(Paragraph("2. Alcance y advertencia", est["h2"]))
    h.append(Paragraph(
        "Todo se ejecutó contra el stack local (Docker Compose), sobre el propio sistema, como "
        "laboratorio autorizado. <b>No se escaneó Supabase</b> (servicio de terceros). El escaneo "
        "activo de ZAP y la verificación anti-DoS envían peticiones de ataque, por lo que se "
        "dirigieron al entorno local desechable, nunca a datos que importe conservar. La frontera "
        "entre verificar un control y ejecutar un ataque destructivo se respeta explícitamente en la "
        "sección 6. Evidencia cruda: <font face='Courier'>evidencias/vulnerabilidades/</font> "
        "(<font face='Courier'>bandit.html</font>, <font face='Courier'>zap-activo-sin-waf.*</font>, "
        "<font face='Courier'>docker-bench-completo.txt</font>) y "
        "<font face='Courier'>evidencias/trafico/</font> (capturas .pcap). Guía reproducible: "
        "<font face='Courier'>docs/probar-seguridad.md</font>.", est["cuerpo"]))
    h.append(PageBreak())

    h.append(Paragraph("3. Análisis estático del código (bandit)", est["h1"]))
    h.append(Paragraph(
        "bandit recorre el código Python en busca de patrones inseguros (SQL con f-strings, "
        "<font face='Courier'>shell=True</font>, deserialización peligrosa, secretos embebidos). Es "
        "la cara de caja blanca que complementa a ZAP y sqlmap. Corre en la CI y a mano con el mismo "
        "comando.", est["cuerpo"]))
    h.append(c.bloque_mono(est, "bandit sobre src (igual que la CI)", """
$ uvx bandit==1.9.4 -r src -x '*/migrations/*'

Test results:  No issues identified.
Code scanned:  Total lines of code: 8509
Run metrics (by severity):  Undefined 0 · Low 0 · Medium 0 · High 0
Total issues skipped (#nosec, justificados): 3
"""))
    h.append(Paragraph(
        "Los 3 avisos deshabilitados con <font face='Courier'>#nosec</font> son usos revisados, no "
        "hallazgos: <font face='Courier'>B108</font> en <font face='Courier'>settings.py</font> (una "
        "ruta de latido bajo <font face='Courier'>/tmp</font>, no un archivo temporal inseguro) y "
        "<font face='Courier'>B308/B703</font> en <font face='Courier'>graficos.py</font> (el único "
        "<font face='Courier'>mark_safe</font> permitido, para el SVG que genera el servidor a partir "
        "de números, con etiquetas escapadas). Un hallazgo nuevo de severidad media o alta hace fallar "
        "la CI. Evidencia: <font face='Courier'>bandit.html</font>.", est["pie_tabla"]))

    h.append(Paragraph("4. Escaneo dinámico activo (OWASP ZAP)", est["h1"]))
    h.append(Paragraph(
        "El escaneo <b>activo</b> va más allá del baseline (pasivo) del Documento 2: inyecta cargas de "
        "ataque reales contra cada parámetro. Se ejecutó autenticado y <b>contra Django directamente</b> "
        "(red interna), no a través del WAF, para medir el código sin el borde —atravesar el WAF con un "
        "escaneo activo solo provoca el baneo, como se vio en el Documento 2—.", est["cuerpo"]))
    h.append(c.tabla([
        ["Resultado del escaneo activo", "Valor"],
        ["Reglas que fallaron (FAIL)", "0"],
        ["Reglas superadas (PASS)", "110"],
        ["Avisos (WARN)", "3 (bajo riesgo, por probar sin WAF)"],
    ], [10 * cm, 7 * cm], est))
    h.append(Paragraph(
        "Las reglas de inyección con cargas reales pasaron todas. Una muestra representativa:", est["cuerpo"]))
    h.append(c.tabla([
        ["Familia de ataque probada (activa)", "Regla ZAP"],
        ["Inyección SQL (genérica y por tiempo: PostgreSQL, MySQL, Oracle, MsSQL)", "40018–40027"],
        ["Inyección de comandos del SO (directa y por tiempo)", "90020, 90037"],
        ["Inyección de plantilla del servidor (SSTI, incluida ciega)", "90035, 90036"],
        ["Recorrido de rutas (Path Traversal)", "6"],
        ["Ejecución remota de código (Shell Shock, CVE-2012-1823)", "10048, 20018"],
        ["Entidad externa XML (XXE) y Padding Oracle", "90023, 90024"],
    ], [11.5 * cm, 5.5 * cm], est))
    h.append(Paragraph(
        "Los 3 WARN son los mismos de bajo riesgo del baseline y se explican por probar sin el WAF: "
        "<font face='Courier'>X-Content-Type-Options</font> ausente (lo añade BunkerWeb, RS-07), "
        "<font face='Courier'>ACAO:*</font> en el CSS estático, y «HTTP Only Site» (la prueba fue por "
        "HTTP directo; en producción todo es HTTPS). El borde los resuelve. Evidencia: "
        "<font face='Courier'>zap-activo-sin-waf.html</font> y <font face='Courier'>.json</font>.",
        est["pie_tabla"]))
    h.append(PageBreak())

    h.append(Paragraph("5. Endurecimiento de los contenedores (Docker Bench)", est["h1"]))
    h.append(Paragraph(
        "Docker Bench audita el stack contra el CIS Docker Benchmark (105 chequeos). Da evidencia "
        "directa de RS-14: contenedores sin privilegios, aislamiento del host, imágenes por digest y "
        "límites. Lo relevante del stack:", est["cuerpo"]))
    h.append(c.tabla([
        ["Chequeo", "Resultado", "Lectura"],
        ["5.3 Capacidades restringidas", "PASS", "cap_drop: ALL en el compose"],
        ["5.4 Sin contenedores privilegiados", "PASS", "Ninguno es --privileged"],
        ["5.5 Sin directorios sensibles del host montados", "PASS", "—"],
        ["5.6 Sin SSH dentro de contenedores", "PASS", "—"],
        ["5.15–5.21 Namespaces, seccomp", "PASS", "Aislamiento del host correcto"],
        ["5.31 Socket de Docker no montado", "PASS", "Ningún contenedor lo monta"],
        ["5.1 AppArmor", "WARN", "Limitación de Docker Desktop; activar en la VM Linux de Azure"],
        ["5.7 Puertos privilegiados (80/443)", "WARN", "Por diseño: solo el WAF los publica"],
        ["5.11 Límite de CPU", "WARN", "Hay mem_limit; falta cpus (endurece T13)"],
        ["5.12 rootfs de solo lectura", "WARN parcial", "web y worker sí (read_only); bases y reportería no pueden"],
        ["Ejecución como root (postgres, mariadb)", "WARN", "Sus imágenes arrancan root para el chown y bajan de usuario"],
    ], [6.4 * cm, 2.6 * cm, 8 * cm], est))
    h.append(Paragraph(
        "Resumen: 15 PASS y 11 WARN en la sección de contenedores (5.x); los PASS cubren el "
        "aislamiento y la restricción de privilegios, y los WARN son limitaciones del entorno de "
        "desarrollo (Docker Desktop/Windows) o endurecimientos adicionales para Azure, no fallos de "
        "diseño. Evidencia: <font face='Courier'>docker-bench-completo.txt</font>.", est["pie_tabla"]))

    h.append(Paragraph("6. Verificación del control anti-DoS", est["h1"]))
    h.append(Paragraph(
        "Un pentest de este sistema no busca tumbar el servicio, sino comprobar que sus protecciones "
        "de disponibilidad responden. El sistema las tiene explícitas (RS-08; amenazas T13 y T21; "
        "criterio CA-14 «el sexto intento en un minuto se bloquea»): límite general de 2 peticiones "
        "por segundo por IP, 5 por minuto en <font face='Courier'>/ingreso</font> y TOTP, y baneo de "
        "una hora por mal comportamiento. Una ráfaga <b>acotada</b> (una docena de peticiones) "
        "confirma el control sin causar caída.", est["cuerpo"]))
    h.append(c.bloque_mono(est, "Verificación acotada del límite de peticiones (RS-08, CA-14)", """
$ for i in $(seq 1 12); do
    curl -sk -o /dev/null -w "%{http_code} " --resolve app.localhost:443:127.0.0.1 \\
      https://app.localhost/ingreso
  done
200 200 200 302 429 429 429 429 429 429 429 429     # el límite de 5/min dispara 429

$ docker compose -f infra/compose.yaml exec bw-scheduler bwcli bans
  10.20.40.1  Service: app.localhost  Reason: bad behavior   (baneo de 1 h)

$ docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban 10.20.40.1
"""))
    h.append(Paragraph(
        "Que aparezca el 429 y que la IP quede baneada <b>es</b> la evidencia de que el control "
        "funciona. Durante el pentest del Documento 2, nmap, ZAP, sqlmap y Nikto dispararon este mismo "
        "baneo de forma espontánea.", est["cuerpo"]))
    h.append(Paragraph(
        "<b>Frontera.</b> Lo defensivo es esta verificación acotada del límite y el baneo. Queda fuera "
        "un ataque volumétrico real (flooding, agotamiento de recursos, amplificación) cuyo objetivo "
        "sea dejar el servicio caído: aun contra la propia máquina no aporta evidencia que la prueba "
        "acotada no dé ya, y el objetivo del laboratorio —probar que el límite de peticiones y el "
        "baneo responden— se cumple sin provocar la caída.", est["pie_tabla"]))
    h.append(PageBreak())

    h.append(Paragraph("7. Inspección del tráfico (Wireshark)", est["h1"]))
    h.append(Paragraph(
        "Wireshark es la cara gráfica del análisis con tshark del Documento 3. No hace falta volver a "
        "capturar: los <font face='Courier'>.pcap</font> ya están en "
        "<font face='Courier'>evidencias/trafico/</font> y se abren con filtros de visualización. Es "
        "observación pasiva del propio tráfico. Tres experimentos confirman las propiedades clave:",
        est["cuerpo"]))
    h.append(c.tabla([
        ["Experimento", "Filtro / acción", "Qué se ve"],
        ["Confidencialidad externa", "Follow → TLS Stream en bunkerweb.pcap", "Contenido ilegible (cifrado, RS-01)"],
        ["El restringido no sale a GLPI", "frame contains \"CENTINELA\" en glpi.pcap", "Cero paquetes (invariante 5, T7)"],
        ["…pero sí se almacena", "mismo filtro en postgres.pcap", "Aparece: vive solo en PostgreSQL"],
        ["Consultas parametrizadas", "pgsql.query en postgres.pcap", "Identificadores citados, sin concatenar input (T4)"],
    ], [4.3 * cm, 6.7 * cm, 6 * cm], est))
    h.append(Paragraph(
        "El detalle y los recuentos están en el Documento 3. Aquí se recogen como procedimiento manual "
        "reproducible con una herramienta gráfica.", est["pie_tabla"]))

    h.append(Paragraph("8. Conclusión", est["h1"]))
    h.append(Paragraph(
        "Las cinco técnicas manuales confirman, desde ángulos distintos, los mismos resultados que las "
        "pruebas automatizadas: el código no tiene patrones inseguros (bandit) ni es inyectable con "
        "cargas reales (ZAP activo, 0 FAIL / 110 PASS); los contenedores corren aislados y sin "
        "privilegios (Docker Bench); el tráfico externo viaja cifrado y el campo restringido no sale a "
        "GLPI (Wireshark); y el control de disponibilidad del WAF responde con 429 y baneo "
        "(verificación anti-DoS). Ningún hallazgo nuevo de severidad alta. Los puntos abiertos son los "
        "ya recogidos en el Documento 2 (mantenimiento de imágenes, endurecimiento adicional) y los "
        "propios de la fase de despliegue en Azure (AppArmor, límites de CPU, Lynis sobre la VM).",
        est["cuerpo"]))
    c.construir(str(SAL), "Pruebas manuales complementarias", h)


if __name__ == "__main__":
    main()
