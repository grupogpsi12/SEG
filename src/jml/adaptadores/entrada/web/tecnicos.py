"""Vistas para los roles tecnicos: dashboard, busqueda de cuentas, CSV y ficha (RF-29 a RF-34).

Sin tiempo real (ADR-020, invariante 11): el boton «Actualizar» es un enlace que vuelve a pedir
la pagina. Los permisos los verifica el caso de uso; aqui solo se traduce `NoAutorizado` a 403.
"""

import csv
from collections import defaultdict

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.entrada.web.graficos import barras
from jml.adaptadores.entrada.web.vistas import _contexto, con_sesion
from jml.aplicacion.dtos import FiltroDeCuentas, PerfilDeUsuario
from jml.dominio.errores import DatoInvalido, NoAutorizado, NoEncontrado
from jml.dominio.tipos import EstadoDeCuenta, SistemaDeCuenta

# Una celda que empieza con estos caracteres se ejecuta como formula en Excel o LibreOffice
# (inyeccion CSV, OWASP): se antepone un apostrofo.
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


class FormularioDeBusqueda(forms.Form):
    nombre = forms.CharField(required=False, max_length=100)
    documento = forms.CharField(required=False, max_length=20)
    usuario = forms.CharField(required=False, max_length=40)
    departamento = forms.CharField(required=False, max_length=100)
    sede = forms.CharField(required=False, max_length=100)
    sistema = forms.ChoiceField(
        required=False, choices=[("", "Todos"), *[(s.value, s.value) for s in SistemaDeCuenta]]
    )
    estado_de_cuenta = forms.ChoiceField(
        label="Estado de la cuenta",
        required=False,
        choices=[("", "Todos"), *[(e.value, e.value.replace("_", " ")) for e in EstadoDeCuenta]],
    )
    pagina = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)

    def filtro(self) -> FiltroDeCuentas:
        c = self.cleaned_data
        return FiltroDeCuentas(
            nombre=c["nombre"] or None,
            documento=c["documento"] or None,
            usuario=c["usuario"] or None,
            departamento=c["departamento"] or None,
            sede=c["sede"] or None,
            sistema=SistemaDeCuenta(c["sistema"]) if c["sistema"] else None,
            estado_de_cuenta=EstadoDeCuenta(c["estado_de_cuenta"])
            if c["estado_de_cuenta"]
            else None,
            pagina=c["pagina"] or 1,
        )


@require_GET
@con_sesion
def dashboard(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    try:
        ind = composicion.casos().dashboard.ejecutar(perfil.usuario_id)
    except NoAutorizado:
        raise PermissionDenied from None
    por_cola: dict[str, int] = defaultdict(int)
    for f in ind.pendientes:
        por_cola[f.cola.value] += f.cantidad
    resaltada = ind.cola_resaltada.value if ind.cola_resaltada else None
    graficos = {
        "pendientes": barras("Tickets pendientes por cola", sorted(por_cola.items()), resaltada),
        "cuentas": barras(
            "Cuentas por sistema y estado",
            [
                (f"{f.sistema.value} · {f.estado.value.replace('_', ' ')}", f.cantidad)
                for f in ind.cuentas
            ],
        ),
    }
    return render(
        request,
        "web/dashboard.html",
        _contexto(perfil, ind=ind, graficos=graficos, resaltada=resaltada),
    )


def _buscar(request: HttpRequest) -> FormularioDeBusqueda:
    formulario = FormularioDeBusqueda(request.GET or None)
    if request.GET and not formulario.is_valid():
        raise Http404  # parametros manipulados: no hay pagina que mostrar
    return formulario


@require_GET
@con_sesion
def cuentas(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    formulario = _buscar(request)
    filtro = formulario.filtro() if request.GET else FiltroDeCuentas()
    try:
        pagina = composicion.casos().buscar_cuentas.ejecutar(perfil.usuario_id, filtro)
    except NoAutorizado:
        raise PermissionDenied from None
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    ultima = max(1, -(-pagina.total // pagina.tamano))
    return render(
        request,
        "web/cuentas.html",
        _contexto(
            perfil,
            formulario=formulario,
            pagina=pagina,
            ultima=ultima,
            consulta=parametros.urlencode(),
        ),
    )


def _celda(valor: object) -> str:
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto.startswith(_FORMULA) else texto


@require_GET
@con_sesion
def cuentas_csv(request: HttpRequest, perfil: PerfilDeUsuario) -> HttpResponse:
    formulario = _buscar(request)
    filtro = formulario.filtro() if request.GET else FiltroDeCuentas()
    try:
        filas = composicion.casos().exportar_cuentas.ejecutar(perfil.usuario_id, filtro)
    except NoAutorizado:
        raise PermissionDenied from None
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="cuentas.csv"'
    respuesta["Cache-Control"] = "no-store"
    respuesta.write("﻿")  # BOM: Excel abre bien las tildes
    escritor = csv.writer(respuesta)
    escritor.writerow(
        [
            "Colaborador",
            "Documento",
            "Usuario",
            "Departamento",
            "Sede",
            "Estado",
            "Sistema",
            "Estado de la cuenta",
            "Desde",
        ]
    )
    for f in filas:
        base = [f.nombre_completo, f.documento, f.usuario, f.departamento, f.sede, f.estado.value]
        for c in f.cuentas or (None,):
            extra = (
                ["", "", ""]
                if c is None
                else [c.sistema.value, c.estado.value, c.desde.date().isoformat()]
            )
            escritor.writerow([_celda(v) for v in base + extra])
    return respuesta


@require_GET
@con_sesion
def ficha(request: HttpRequest, perfil: PerfilDeUsuario, colaborador: str) -> HttpResponse:
    try:
        f = composicion.casos().ficha.ejecutar(perfil.usuario_id, colaborador)
    except NoAutorizado:
        raise PermissionDenied from None
    except (NoEncontrado, DatoInvalido):
        raise Http404 from None
    return render(
        request,
        "web/ficha.html",
        _contexto(perfil, f=f, glpi=settings.JML_GLPI_URL.rstrip("/")),
    )
