"""Modelos de Django (SRS 5.1). NO son el dominio: los repositorios mapean modelo <-> entidad.

Las reglas que la base de datos debe garantizar por si misma estan aqui como restricciones
(RD-01, RD-09); las que el ORM no expresa (disparador de RF-14, REVOKE de RD-02, RLS de RD-10)
estan en la migracion 0002, solo para PostgreSQL.
"""

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q

from jml.dominio.tipos import ESTADOS_ABIERTOS, EstadoColaborador

_ABIERTOS = sorted(e.value for e in ESTADOS_ABIERTOS)


class Colaborador(models.Model):
    id = models.CharField(primary_key=True, max_length=64)
    documento = models.CharField(max_length=15)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    vinculacion = models.CharField(max_length=20)
    departamento = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100)
    sede = models.CharField(max_length=100)
    jefe_id = models.CharField(max_length=64, null=True)
    fecha_ingreso = models.DateField()
    fecha_fin = models.DateField(null=True)
    estado = models.CharField(max_length=20)
    usuario = models.CharField(max_length=20, null=True)
    id_usuario_glpi = models.CharField(max_length=64, null=True)

    class Meta:
        db_table = "colaborador"
        constraints = [
            # RD-09: el documento es unico entre los colaboradores que no estan retirados (S-26)
            models.UniqueConstraint(
                fields=["documento"],
                condition=~Q(estado=EstadoColaborador.RETIRADO.value),
                name="colaborador_documento_unico_no_retirado",
            ),
        ]


class PerfilDeUsuario(models.Model):
    """Datos propios del usuario de Django: el colaborador al que corresponde.

    El usuario es el `User` de Django, con el id de Supabase como `username`, sin contrasena
    local (RF-06, ADR-017). Los roles son sus grupos de Django (SRS 3.3).
    """

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    colaborador_id = models.CharField(max_length=64, null=True)

    class Meta:
        db_table = "usuario_perfil"


class PerfilDeAcceso(models.Model):
    departamento = models.CharField(max_length=100)
    sede = models.CharField(max_length=100)
    grupos_ad = models.JSONField(default=list)
    grupos_red = models.JSONField(default=list)
    grupos_m365 = models.JSONField(default=list)
    licencias = models.JSONField(default=list)
    tipo_equipo = models.CharField(max_length=20)

    class Meta:
        db_table = "perfil_acceso"
        constraints = [
            models.UniqueConstraint(fields=["departamento", "sede"], name="perfil_unico_por_sede")
        ]


class RecursoPerfil(models.Model):
    perfil = models.ForeignKey(PerfilDeAcceso, on_delete=models.CASCADE, related_name="recursos")
    ruta = models.CharField(max_length=300)
    serie = models.CharField(max_length=300)
    perfil_de_recurso = models.CharField(max_length=30)
    grupo = models.CharField(max_length=300)

    class Meta:
        db_table = "recurso_perfil"
        constraints = [
            models.UniqueConstraint(fields=["perfil", "ruta"], name="recurso_ruta_unica_por_perfil")
        ]


class Consecutivo(models.Model):
    """Consecutivos por anio (SOL-AAAA-NNNNNN) y fila candado de la auditoria."""

    clave = models.CharField(primary_key=True, max_length=32)
    ultimo = models.BigIntegerField(default=0)

    class Meta:
        db_table = "consecutivo"


class Solicitud(models.Model):
    id = models.CharField(primary_key=True, max_length=15)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=3)
    subtipo = models.CharField(max_length=30, null=True)
    fecha_efectiva = models.DateField()
    datos = models.JSONField()
    solicitante_id = models.CharField(max_length=64)
    estado = models.CharField(max_length=25)
    creada_en = models.DateTimeField()
    solicitud_origen = models.ForeignKey("self", on_delete=models.PROTECT, null=True)
    tickets = models.JSONField(default=list)
    para_revision = models.BooleanField(default=False)

    class Meta:
        db_table = "solicitud"
        constraints = [
            # RD-01 / ADR-006: la deduplicacion la garantiza la base, tambien ante carreras (CA-01)
            models.UniqueConstraint(
                fields=["colaborador", "tipo"],
                condition=Q(estado__in=_ABIERTOS),
                name="solicitud_abierta_unica",
            ),
        ]


class SolicitudRestringida(models.Model):
    """RD-05: motivo de retiro o descripcion de emergencia. Solo RRHH lo lee."""

    solicitud = models.OneToOneField(Solicitud, on_delete=models.CASCADE, primary_key=True)
    contenido = models.TextField()

    class Meta:
        db_table = "solicitud_restringida"


class Decision(models.Model):
    """Solo insercion (RD-02)."""

    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=25)
    justificacion = models.TextField(null=True)
    usuario_id = models.CharField(max_length=64)
    fecha = models.DateTimeField()

    class Meta:
        db_table = "decision"


class Soporte(models.Model):
    solicitud = models.OneToOneField(Solicitud, on_delete=models.PROTECT, primary_key=True)
    nombre_original = models.CharField(max_length=100)
    tamano = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    nombre_almacenado = models.CharField(max_length=128)
    estado = models.CharField(max_length=15)
    id_documento_glpi = models.CharField(max_length=64, null=True)

    class Meta:
        db_table = "soporte"


class Ticket(models.Model):
    clave = models.CharField(primary_key=True, max_length=80)
    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT)
    # Lo que el dashboard filtra y agrupa son columnas reales (RF-30); el resto, en `definicion`.
    cola = models.CharField(max_length=20)
    clase = models.CharField(max_length=20)
    accion = models.CharField(max_length=15)
    prioridad = models.CharField(max_length=10)
    emitido_en = models.DateTimeField()
    vence_en = models.DateTimeField()
    activo_desde = models.DateTimeField()
    definicion = models.JSONField()  # el TicketDeCola completo, tal como se genero
    id_externo = models.CharField(max_length=64, null=True)
    estado_glpi = models.IntegerField(null=True)
    tiene_solucion = models.BooleanField(default=False)
    documentos = models.IntegerField(default=0)
    observado_en = models.DateTimeField(null=True)
    reabierto = models.BooleanField(default=False)

    class Meta:
        db_table = "ticket"
        indexes = [models.Index(fields=["id_externo"], name="ticket_creados")]


class Cuenta(models.Model):
    colaborador_id = models.CharField(max_length=64)
    sistema = models.CharField(max_length=10)
    estado = models.CharField(max_length=25)
    ticket_origen = models.CharField(max_length=80)
    origen_emitido_en = models.DateTimeField()
    origen_vence_en = models.DateTimeField()
    desde = models.DateTimeField()
    marca = models.CharField(max_length=25, null=True)

    class Meta:
        db_table = "cuenta"
        constraints = [
            models.UniqueConstraint(fields=["colaborador_id", "sistema"], name="cuenta_unica")
        ]


class CuentaHistorial(models.Model):
    """Solo insercion (RD-02)."""

    colaborador_id = models.CharField(max_length=64)
    sistema = models.CharField(max_length=10)
    estado_anterior = models.CharField(max_length=25, null=True)
    estado_nuevo = models.CharField(max_length=25)
    marca_nueva = models.CharField(max_length=25, null=True)
    ticket = models.CharField(max_length=80)
    fecha = models.DateTimeField()

    class Meta:
        db_table = "cuenta_historial"


class EntradaDeBandeja(models.Model):
    """Outbox (RF-18). La definicion del ticket esta en `ticket`."""

    ticket = models.OneToOneField(Ticket, on_delete=models.PROTECT, primary_key=True)
    estado = models.CharField(max_length=15)
    intentos = models.IntegerField(default=0)
    proximo_intento = models.DateTimeField()
    ultimo_error = models.CharField(max_length=40, null=True)

    class Meta:
        db_table = "outbox"
        indexes = [models.Index(fields=["estado", "proximo_intento"], name="outbox_vencidas")]


class ActivoAsignado(models.Model):
    colaborador_id = models.CharField(max_length=64)
    id_glpi = models.CharField(max_length=64)
    tipo = models.CharField(max_length=100)
    serie = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    asignado_desde = models.DateField()
    tiene_acta = models.BooleanField()

    class Meta:
        db_table = "activo_asignado"


class LicenciaAsignada(models.Model):
    colaborador_id = models.CharField(max_length=64)
    id_glpi = models.CharField(max_length=64)
    software = models.CharField(max_length=100)
    licencia = models.CharField(max_length=100)

    class Meta:
        db_table = "licencia_asignada"


class Sincronizacion(models.Model):
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    resultado = models.CharField(max_length=10)
    tickets_leidos = models.IntegerField()
    errores = models.IntegerField()

    class Meta:
        db_table = "sincronizacion"


class RegistroDeAuditoria(models.Model):
    """Solo insercion, con cadena de hashes (RD-02, RD-03). Se escribe solo por el puerto."""

    secuencia = models.BigIntegerField(primary_key=True)
    fecha = models.DateTimeField()
    actor = models.CharField(max_length=64)
    accion = models.CharField(max_length=80)
    objeto = models.CharField(max_length=80)
    datos = models.JSONField()
    hash_anterior = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "auditoria"
