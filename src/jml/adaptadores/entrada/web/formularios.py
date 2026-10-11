"""Formularios de Django: validan la forma del input y lo traducen a `NuevaSolicitud`.

Las reglas de negocio (fechas pasadas, subtipos, documentos duplicados, soporte PDF, permisos)
NO viven aqui: las aplica el dominio y la vista muestra su error (RF-07, RF-08, RF-39).
"""

from collections.abc import Sequence
from datetime import date
from typing import Any, ClassVar

from django import forms

from jml.aplicacion.dtos import ArchivoRecibido, NuevaSolicitud, OpcionDeColaborador
from jml.dominio.catalogo import (
    DatosCambioDepartamento,
    DatosCambioSucursal,
    DatosDelEvento,
    DatosEmergencia,
    DatosIngreso,
    DatosRetiro,
    DatosVacaciones,
)
from jml.dominio.tipos import Subtipo, TipoDeEquipo, TipoDeVinculacion, TipoEvento
from jml.dominio.valores import MAX_SOPORTE_BYTES, Documento

ETIQUETAS_DE_TIPO: dict[TipoEvento, str] = {
    TipoEvento.ING: "Ingreso",
    TipoEvento.VAC: "Vacaciones",
    TipoEvento.CDP: "Cambio de departamento",
    TipoEvento.CSU: "Cambio de sucursal",
    TipoEvento.RET: "Retiro",
    TipoEvento.EMG: "Emergencia",
}

_FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
_FECHA_HORA = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


def _fecha(etiqueta: str, requerida: bool = True) -> forms.DateField:
    return forms.DateField(label=etiqueta, required=requerida, widget=_FECHA)


class FormularioDeEvento(forms.Form):
    """Base: la fecha efectiva y, segun quien lo llena, a quien afecta y la justificacion."""

    TIPO: ClassVar[TipoEvento]
    SUBTIPO_FIJO: ClassVar[Subtipo | None] = None
    fecha_efectiva = _fecha("Fecha efectiva")

    def __init__(
        self,
        *args: Any,
        emision: bool = False,
        subordinados: Sequence[OpcionDeColaborador] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.emision = emision
        if emision:
            if (
                self.TIPO is not TipoEvento.ING
            ):  # el ingreso crea a la persona: no hay a quien buscar
                self.fields["documento_del_colaborador"] = forms.CharField(
                    label="Documento del colaborador", max_length=20
                )
            self.fields["justificacion"] = forms.CharField(
                label="Justificación", widget=forms.Textarea(attrs={"rows": 3}), max_length=500
            )
        elif self.TIPO in (TipoEvento.CDP, TipoEvento.CSU):
            self.fields["colaborador"] = forms.ChoiceField(
                label="Colaborador", choices=[(o.colaborador_id, o.nombre) for o in subordinados]
            )

    # --- traduccion a los DTO del nucleo ---------------------------------------------------------

    def datos(self) -> DatosDelEvento:
        raise NotImplementedError

    def subtipo(self) -> Subtipo | None:
        return self.SUBTIPO_FIJO

    def restringido(self) -> str | None:
        return None

    def soporte(self) -> ArchivoRecibido | None:
        return None

    def documento_buscado(self) -> str | None:
        return self.cleaned_data.get("documento_del_colaborador")

    def colaborador_elegido(self) -> str | None:
        return self.cleaned_data.get("colaborador")

    def a_nueva_solicitud(
        self, usuario_id: str, colaborador_id: str | None, fecha_efectiva: date | None = None
    ) -> NuevaSolicitud:
        return NuevaSolicitud(
            usuario_id=usuario_id,
            tipo=self.TIPO,
            fecha_efectiva=fecha_efectiva or self.cleaned_data["fecha_efectiva"],
            datos=self.datos(),
            colaborador_id=colaborador_id,
            subtipo=self.subtipo(),
            restringido=self.restringido(),
            soporte=self.soporte(),
            justificacion=self.cleaned_data.get("justificacion"),
        )


class FormularioDeVacaciones(FormularioDeEvento):
    TIPO = TipoEvento.VAC
    fecha_regreso = _fecha("Fecha de regreso")

    def datos(self) -> DatosDelEvento:
        return DatosVacaciones(self.cleaned_data["fecha_regreso"])


class FormularioDeRetiro(FormularioDeEvento):
    TIPO = TipoEvento.RET
    subtipo_elegido = forms.ChoiceField(
        label="Tipo de retiro",
        choices=[
            (Subtipo.RENUNCIA.value, "Renuncia"),
            (Subtipo.FIN_DE_CONTRATO.value, "Fin de contrato"),
        ],
    )
    motivo = forms.CharField(
        label="Motivo (solo lo ve RRHH)", widget=forms.Textarea(attrs={"rows": 3}), max_length=2000
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.emision:  # el colaborador solo registra su renuncia
            del self.fields["subtipo_elegido"]

    def datos(self) -> DatosDelEvento:
        return DatosRetiro()

    def subtipo(self) -> Subtipo | None:
        return Subtipo(self.cleaned_data.get("subtipo_elegido", Subtipo.RENUNCIA.value))

    def restringido(self) -> str | None:
        return str(self.cleaned_data["motivo"])


class FormularioDeCambioDeDepartamento(FormularioDeEvento):
    TIPO = TipoEvento.CDP
    departamento_nuevo = forms.CharField(label="Departamento nuevo", max_length=100)
    cargo_nuevo = forms.CharField(label="Cargo nuevo", max_length=100)
    jefe_nuevo_id = forms.CharField(label="Id del jefe nuevo (opcional)", required=False)

    def datos(self) -> DatosDelEvento:
        return DatosCambioDepartamento(
            self.cleaned_data["departamento_nuevo"],
            self.cleaned_data["cargo_nuevo"],
            self.cleaned_data["jefe_nuevo_id"] or None,
        )


class FormularioDeCambioDeSucursal(FormularioDeEvento):
    TIPO = TipoEvento.CSU
    sede_nueva = forms.CharField(label="Sede nueva", max_length=100)
    traslada_equipo = forms.BooleanField(label="Traslada el equipo", required=False)

    def datos(self) -> DatosDelEvento:
        return DatosCambioSucursal(
            self.cleaned_data["sede_nueva"], self.cleaned_data["traslada_equipo"]
        )


class FormularioDeEmergencia(FormularioDeEvento):
    """Una emergencia es efectiva el dia de la emision (S-03): la fecha la pone la vista."""

    TIPO = TipoEvento.EMG
    subtipo_elegido = forms.ChoiceField(
        label="Tipo de emergencia",
        choices=[
            (Subtipo.DESPIDO_CON_JUSTA_CAUSA.value, "Despido con justa causa"),
            (Subtipo.FUGA_DETECTADA.value, "Fuga detectada"),
        ],
    )
    reportado_por = forms.CharField(label="Reportado por", max_length=100)
    hora_del_hecho = forms.DateTimeField(label="Hora del hecho", widget=_FECHA_HORA)
    descripcion = forms.CharField(
        label="Descripción (solo la ve RRHH)",
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        del self.fields["fecha_efectiva"]

    def datos(self) -> DatosDelEvento:
        return DatosEmergencia(
            self.cleaned_data["reportado_por"], self.cleaned_data["hora_del_hecho"]
        )

    def subtipo(self) -> Subtipo | None:
        return Subtipo(self.cleaned_data["subtipo_elegido"])

    def restringido(self) -> str | None:
        return str(self.cleaned_data["descripcion"])


class FormularioDeIngreso(FormularioDeEvento):
    TIPO = TipoEvento.ING
    nombres = forms.CharField(max_length=100)
    apellidos = forms.CharField(max_length=100)
    documento = forms.CharField(max_length=20)
    vinculacion = forms.ChoiceField(
        label="Vinculación", choices=[(v.value, v.value.capitalize()) for v in TipoDeVinculacion]
    )
    departamento = forms.CharField(max_length=100)
    cargo = forms.CharField(max_length=100)
    sede = forms.CharField(max_length=100)
    jefe_id = forms.CharField(label="Id del jefe (opcional)", required=False)
    fecha_fin = _fecha("Fecha de fin del contrato (si no es empleado)", requerida=False)
    requiere_equipo = forms.BooleanField(label="Requiere equipo", required=False)
    tipo_equipo = forms.ChoiceField(
        label="Tipo de equipo",
        required=False,
        choices=[("", "—"), *[(t.value, t.value) for t in TipoDeEquipo]],
    )
    soporte_pdf = forms.FileField(label="Soporte de vinculación (PDF)", required=False)

    def clean_soporte_pdf(self) -> Any:
        archivo = self.cleaned_data.get("soporte_pdf")
        if archivo is not None and archivo.size > MAX_SOPORTE_BYTES:
            raise forms.ValidationError("El archivo supera los 20 MB.")
        return archivo

    def datos(self) -> DatosDelEvento:
        c = self.cleaned_data
        return DatosIngreso(
            nombres=c["nombres"],
            apellidos=c["apellidos"],
            documento=Documento(c["documento"]),
            vinculacion=TipoDeVinculacion(c["vinculacion"]),
            departamento=c["departamento"],
            cargo=c["cargo"],
            sede=c["sede"],
            jefe_id=c["jefe_id"] or None,
            fecha_fin=c["fecha_fin"],
            requiere_equipo=c["requiere_equipo"],
            tipo_equipo=TipoDeEquipo(c["tipo_equipo"]) if c["tipo_equipo"] else None,
        )

    def soporte(self) -> ArchivoRecibido | None:
        archivo = self.cleaned_data.get("soporte_pdf")
        # El contenido se valida por firma en el nucleo (RF-39); el nombre es solo informativo.
        return None if archivo is None else ArchivoRecibido(archivo.name, archivo.read())


FORMULARIOS: dict[TipoEvento, type[FormularioDeEvento]] = {
    TipoEvento.ING: FormularioDeIngreso,
    TipoEvento.VAC: FormularioDeVacaciones,
    TipoEvento.CDP: FormularioDeCambioDeDepartamento,
    TipoEvento.CSU: FormularioDeCambioDeSucursal,
    TipoEvento.RET: FormularioDeRetiro,
    TipoEvento.EMG: FormularioDeEmergencia,
}


class FormularioDeJustificacion(forms.Form):
    justificacion = forms.CharField(
        label="Justificación",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=500,
    )
