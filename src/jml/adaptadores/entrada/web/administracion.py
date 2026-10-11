"""Area de administracion (RF-37): matriz de perfiles y roles. Las reglas viven en los casos de
uso; aqui solo se traduce el formulario (una linea por grupo, licencia o recurso)."""

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.mensajes import texto_del_error
from jml.adaptadores.entrada.web.vistas import _contexto, con_sesion
from jml.aplicacion.dtos import PerfilDeUsuario
from jml.dominio.errores import ErrorDeDominio, NoAutorizado
from jml.dominio.perfiles import PerfilDeAcceso, RecursoCompartido
from jml.dominio.tipos import PerfilDeRecurso, Rol, TipoDeEquipo

_RECURSO = "ruta | serie | Consulta o Edición | grupo"


def _lineas(texto: str) -> tuple[str, ...]:
    return tuple(linea.strip() for linea in texto.splitlines() if linea.strip())


class FormularioDePerfil(forms.Form):
    departamento = forms.CharField(max_length=100)
    sede = forms.CharField(max_length=100)
    grupos_ad = forms.CharField(
        label="Grupos de AD (uno por línea)",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )
    grupos_red = forms.CharField(
        label="Grupos de red (uno por línea)",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )
    grupos_m365 = forms.CharField(
        label="Grupos de M365 (uno por línea)",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    licencias = forms.CharField(
        label="Licencias (una por línea)", widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    tipo_equipo = forms.ChoiceField(
        label="Tipo de equipo", choices=[(t.value, t.value) for t in TipoDeEquipo]
    )
    recursos = forms.CharField(
        label=f"Recursos compartidos (uno por línea: {_RECURSO})",
        widget=forms.Textarea(attrs={"rows": 5}),
        required=False,
    )

    @classmethod
    def de_perfil(cls, p: PerfilDeAcceso) -> "FormularioDePerfil":
        return cls(
            initial={
                "departamento": p.departamento,
                "sede": p.sede,
                "grupos_ad": "\n".join(p.grupos_ad),
                "grupos_red": "\n".join(p.grupos_red),
                "grupos_m365": "\n".join(p.grupos_m365),
                "licencias": "\n".join(p.licencias),
                "tipo_equipo": p.tipo_equipo.value,
                "recursos": "\n".join(
                    f"{r.ruta} | {r.serie} | {r.perfil.value} | {r.grupo}" for r in p.recursos
                ),
            }
        )

    def clean_recursos(self) -> tuple[RecursoCompartido, ...]:
        recursos = []
        for n, linea in enumerate(_lineas(self.cleaned_data["recursos"]), start=1):
            partes = [p.strip() for p in linea.split("|")]
            if len(partes) != 4:
                raise forms.ValidationError(f"Línea {n}: se esperan 4 partes ({_RECURSO}).")
            ruta, serie, perfil, grupo = partes
            try:
                recursos.append(RecursoCompartido(ruta, serie, PerfilDeRecurso(perfil), grupo))
            except ValueError:
                raise forms.ValidationError(
                    f"Línea {n}: el perfil debe ser «Consulta» o «Edición»."
                ) from None
            except ErrorDeDominio as e:
                raise forms.ValidationError(f"Línea {n}: {texto_del_error(e)}") from None
        return tuple(recursos)

    def a_perfil(self) -> PerfilDeAcceso:
        c = self.cleaned_data
        return PerfilDeAcceso(
            departamento=c["departamento"],
            sede=c["sede"],
            grupos_ad=_lineas(c["grupos_ad"]),
            grupos_red=_lineas(c["grupos_red"]),
            grupos_m365=_lineas(c["grupos_m365"]),
            licencias=_lineas(c["licencias"]),
            tipo_equipo=TipoDeEquipo(c["tipo_equipo"]),
            recursos=c["recursos"],
        )


@require_GET
@con_sesion
def perfiles(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    try:
        matriz = composicion.casos().matriz.ejecutar(perfil.usuario_id)
    except NoAutorizado:
        raise PermissionDenied from None
    return render(request, "web/admin_perfiles.html", _contexto(perfil, matriz=matriz))


@require_http_methods(["GET", "POST"])
@con_sesion
def editar_perfil(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    casos = composicion.casos()
    try:
        matriz = casos.matriz.ejecutar(perfil.usuario_id)
    except NoAutorizado:
        raise PermissionDenied from None
    if request.method == "POST":
        formulario = FormularioDePerfil(request.POST)
        if formulario.is_valid():
            try:
                casos.guardar_perfil.ejecutar(perfil.usuario_id, formulario.a_perfil())
            except ErrorDeDominio as e:
                formulario.add_error(None, texto_del_error(e))
            else:
                messages.success(
                    request, "Perfil guardado. Aplica a los eventos que se emitan desde ahora."
                )
                return redirect("admin_perfiles")
    else:
        clave = (request.GET.get("departamento", ""), request.GET.get("sede", ""))
        actual = next((p for p in matriz if (p.departamento, p.sede) == clave), None)
        formulario = FormularioDePerfil.de_perfil(actual) if actual else FormularioDePerfil()
    return render(request, "web/admin_perfil.html", _contexto(perfil, formulario=formulario))


class FormularioDeRoles(forms.Form):
    roles = forms.MultipleChoiceField(
        choices=[(r.value, r.value.replace("_", " ")) for r in Rol],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )


@require_GET
@con_sesion
def usuarios(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    try:
        filas = composicion.casos().usuarios.ejecutar(perfil.usuario_id)
    except NoAutorizado:
        raise PermissionDenied from None
    return render(
        request, "web/admin_usuarios.html", _contexto(perfil, filas=filas, todos=list(Rol))
    )


@require_POST
@con_sesion
def cambiar_roles(request: HttpRequest, perfil: PerfilDeUsuario, usuario: str) -> HttpResponse:
    formulario = FormularioDeRoles(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Roles inválidos.")
    else:
        roles = frozenset(Rol(r) for r in formulario.cleaned_data["roles"])
        try:
            composicion.casos().cambiar_roles.ejecutar(perfil.usuario_id, usuario, roles)
        except ErrorDeDominio as e:
            messages.error(request, texto_del_error(e))
        else:
            messages.success(request, "Roles actualizados.")
    # lecciones n.30: quien no es Administrador no vuelve a una pagina que tambien le niega
    return redirect("admin_usuarios" if Rol.ADMINISTRADOR in perfil.roles else "solicitudes")
