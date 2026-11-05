# Anclas DREAD de la auditoría

Para que el DREAD no sea una opinión con decimales (plan §3), cada eje tiene aquí lo que significa
un 1, un 5 y un 10 **en este sistema**. Quien puntúa cita el ancla más cercana en el hallazgo.

**Fórmula.** `DREAD = (D + R + E + A + D) / 5`, cada eje de 1 a 10.
**Bandas de severidad** (se asignan con el DREAD, sin el factor): 0–3 Bajo · 4–6 Medio · 7–8 Alto · 9–10 Crítico. La severidad «Informativa» es para lo que no es una vulnerabilidad (deriva documental, endurecimiento sin ataque asociado).
**Prioridad.** Para ordenar la remediación, `score = DREAD × factor`: exploit público ×1,5 · requiere sesión autenticada ×0,7 · requiere acceso al host o a la red interna ×0,5. El factor ordena, no cambia la banda.

## Los cinco ejes

| Eje | 1–3 | 5 | 8–10 |
|---|---|---|---|
| **D — Daño** | Molestia o dato no sensible; se corrige sin pérdida (un mensaje de error, una cabecera) | Datos personales de **una** persona, o una función no crítica caída; recuperable con el respaldo (RPO 24 h) | Datos personales o **campos restringidos** de muchas personas; modificar solicitudes aprobadas o la cadena de auditoría; control de la API de GLPI, de `service_role` o del proyecto de Supabase |
| **R — Reproducibilidad** | Una carrera rara o un orden de eventos que no se controla | Hace falta una condición concreta (un rol, un orden de arranque, una sesión válida), pero con ella ocurre siempre | Ocurre siempre, con un comando o un clic, sin condiciones |
| **E — Explotabilidad** | Acceso al host, o a la red interna **y** conocimiento del sistema | Usuario autenticado con un rol y herramientas públicas | Anónimo y remoto, con un navegador o `curl` |
| **A — Usuarios afectados** | Una cuenta | Un rol o un grupo (p. ej. todo RRHH) | Todos los usuarios o todos los colaboradores |
| **D — Descubribilidad** | Exige el código fuente y análisis | Se ve con herramientas estándar estando autenticado | Se ve en una página pública o con un escaneo básico |

## Reglas

1. **Inherente y residual.** Se puntúa primero **sin** el control (inherente). El residual (con el control) **solo baja si existe una prueba que se rompe al quitar el control** (plan §3, regla iv). Un control declarado por diseño no baja nada.
2. **Cuatro ojos.** Un hallazgo Alto o Crítico lo puntúan dos contextos independientes por separado y se promedia (plan §9.2.2). A la fecha no hay ninguno.
3. **Cita obligatoria.** Cada eje del hallazgo termina con la frase «ancla: …» que lo justifica.
4. **Disidencia.** Si el equipo puntúa distinto, se respeta y la diferencia se anota en `docs/decisiones.md`.

## Ejemplo resuelto — B-01 (IP de confianza de bunkerweb)

| Eje | Puntaje | Ancla |
|---|---|---|
| D | 6 | Sin el WAF la aplicación queda inalcanzable desde fuera (no hay pérdida de datos): equivale a «una función crítica caída», entre 5 y 8 |
| R | 5 | Depende del orden de arranque tras un reinicio; con el orden forzado ocurre siempre |
| E | 2 | Exige poder reiniciar o iniciar contenedores en el host |
| A | 8 | Afecta a todos los usuarios mientras dura |
| D | 4 | No se ve desde fuera; se ve al reiniciar |
| **DREAD** | **5,0 (Medio)** | Factor ×0,5 (acceso al host): score de prioridad 2,5 |
