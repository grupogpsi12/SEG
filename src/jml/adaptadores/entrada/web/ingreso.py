"""Ingreso en dos pasos (RF-01, RF-02, RF-04; ADR-017; invariante 9).

1. `/ingreso`: correo y contrasena. La sesion guarda solo un `desafio_id` opaco y aleatorio, nunca
   un token de Supabase. Se rota el id de sesion (fijacion de sesion).
2. `/ingreso/segundo-factor`: en el primer ingreso muestra la clave para inscribir el TOTP; luego
   pide el codigo. Solo si el nucleo acepta la identidad AAL2 se crea la sesion de usuario, con
   otro id rotado.

Los errores son genericos (RS-08) y estas paginas no se guardan en cache: la de inscripcion
muestra el secreto TOTP.
"""

import logging
from urllib.parse import parse_qs, urlparse

from django import forms
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.vistas import SESION_INICIO, SESION_USUARIO
from jml.aplicacion.puertos import CredencialesInvalidas, IdentidadNoDisponible
from jml.dominio.errores import NoAutorizado

registro = logging.getLogger(__name__)

SESION_DESAFIO = "desafio"
SESION_INSCRIBIR = "inscribir"
SESION_CANDIDATO = "candidato"  # id de Supabase tras la contrasena: solo para auditar fallos

ERROR_CREDENCIALES = "Correo o contraseña incorrectos."
ERROR_CODIGO = "Código incorrecto o vencido. Si persiste, vuelva a ingresar."
ERROR_ACCESO = "Su cuenta no tiene acceso a la aplicación. Contacte al administrador."
ERROR_SERVICIO = "El servicio de ingreso no está disponible. Intente de nuevo en unos minutos."


class FormularioDeIngreso(forms.Form):
    correo = forms.EmailField(
        max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "username"})
    )
    contrasena = forms.CharField(
        label="Contraseña",
        max_length=128,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class FormularioDeCodigo(forms.Form):
    codigo = forms.CharField(
        label="Código de 6 dígitos",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "pattern": "[0-9]{6}"}
        ),
    )


def _secreto(uri: str) -> str:
    """La clave para escribir a mano en la app autenticadora (sin QR: sin JS ni dependencias)."""
    return parse_qs(urlparse(uri).query).get("secret", [""])[0]


@never_cache
@require_http_methods(["GET", "POST"])
def ingreso(request: HttpRequest) -> HttpResponse:
    if request.session.get(SESION_USUARIO):
        return redirect("inicio")
    formulario = FormularioDeIngreso(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            primer = composicion.casos().iniciar_ingreso.ejecutar(
                formulario.cleaned_data["correo"], formulario.cleaned_data["contrasena"]
            )
        except CredencialesInvalidas:
            formulario.add_error(None, ERROR_CREDENCIALES)
        except IdentidadNoDisponible:
            registro.exception("Supabase Auth no respondio al autenticar")
            formulario.add_error(None, ERROR_SERVICIO)
        else:
            request.session.cycle_key()
            request.session[SESION_DESAFIO] = primer.desafio_id
            request.session[SESION_INSCRIBIR] = primer.requiere_inscripcion
            request.session[SESION_CANDIDATO] = primer.usuario_id
            return redirect("segundo_factor")
    return render(request, "web/ingreso.html", {"formulario": formulario})


@never_cache
@require_http_methods(["GET", "POST"])
def segundo_factor(request: HttpRequest) -> HttpResponse:
    desafio = request.session.get(SESION_DESAFIO)
    if not isinstance(desafio, str):
        return redirect("ingreso")
    casos = composicion.casos()
    formulario = FormularioDeCodigo(request.POST or None)
    secreto = None
    if request.method == "POST" and formulario.is_valid():
        try:
            usuario_id = casos.completar_ingreso.ejecutar(
                desafio,
                formulario.cleaned_data["codigo"],
                str(request.session.get(SESION_CANDIDATO, "-")),
            )
        except CredencialesInvalidas:
            formulario.add_error(None, ERROR_CODIGO)
        except NoAutorizado:
            request.session.flush()
            return render(
                request,
                "web/ingreso.html",
                {"formulario": FormularioDeIngreso(), "error": ERROR_ACCESO},
                status=403,
            )
        except IdentidadNoDisponible:
            registro.exception("Supabase Auth no respondio al verificar el TOTP")
            formulario.add_error(None, ERROR_SERVICIO)
        else:
            request.session.cycle_key()
            for clave in (SESION_DESAFIO, SESION_INSCRIBIR, SESION_CANDIDATO):
                request.session.pop(clave, None)
            request.session[SESION_USUARIO] = usuario_id
            request.session[SESION_INICIO] = composicion.reloj().ahora().timestamp()
            return redirect("inicio")
    elif request.method == "GET" and request.session.get(SESION_INSCRIBIR):
        try:
            secreto = _secreto(casos.inscribir_totp.ejecutar(desafio))
        except CredencialesInvalidas:  # desafio vencido: se empieza de nuevo
            request.session.flush()
            return redirect("ingreso")
        except IdentidadNoDisponible:
            registro.exception("Supabase Auth no respondio al inscribir el TOTP")
            formulario.add_error(None, ERROR_SERVICIO)
    return render(
        request,
        "web/segundo_factor.html",
        {
            "formulario": formulario,
            "secreto": secreto,
            "inscribir": bool(request.session.get(SESION_INSCRIBIR)),
        },
    )


@require_POST
def salir(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect("ingreso")
