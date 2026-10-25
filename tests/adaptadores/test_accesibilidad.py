"""RI-01 (Anexo A, Tabla XVIII): páginas en español, adaptables, sin JavaScript de terceros y con WCAG 2.1 nivel AA
en contraste y navegación por teclado.

Qué mide y qué no: calcula las razones de contraste de la hoja de estilos con la fórmula de WCAG (criterios 1.4.3 y
1.4.11) y revisa la estructura de cada página generada (idioma, etiquetas de formulario, encabezados, orden de
tabulación, recursos externos). NO sustituye una evaluación con tecnología de asistencia ni una auditoría manual
completa: cubre lo que se puede comprobar de forma mecánica y repetible.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.test import Client

from jml.adaptadores.entrada.web import composicion
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from tests.fabricas import AHORA
from tests.mundo import Mundo, cambio_de_departamento, ingreso, retiro, vacaciones

pytestmark = pytest.mark.django_db

CSS = (
    Path(__file__).resolve().parents[2] / "src/jml/adaptadores/entrada/web/static/web/estilo.css"
).read_text(encoding="utf-8")


# --- contraste (WCAG 1.4.3 texto 4,5:1 · 1.4.11 componentes y gráficos 3:1) -----------------------


def _luminancia(color: str) -> float:
    r, g, b = (int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lineal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lineal(r) + 0.7152 * lineal(g) + 0.0722 * lineal(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


VARIABLES = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", CSS))
BLANCO = "#ffffff"


def test_el_contraste_de_la_formula_coincide_con_valores_conocidos() -> None:
    """Control positivo: negro sobre blanco es 21:1 y un gris medio sobre blanco queda bajo 4,5:1."""
    assert contraste("#000000", BLANCO) == pytest.approx(21.0)
    assert contraste("#777777", BLANCO) < 4.5
    assert contraste("#767676", BLANCO) >= 4.5  # el gris más claro que cumple AA sobre blanco


@pytest.mark.parametrize(
    ("texto", "fondo"),
    [
        (VARIABLES["texto"], VARIABLES["fondo"]),  # cuerpo
        (VARIABLES["acento"], BLANCO),  # enlaces del encabezado
        (BLANCO, VARIABLES["acento"]),  # botón principal
        (VARIABLES["error"], BLANCO),  # mensajes de error
        (VARIABLES["ok"], BLANCO),
        ("#52606d", VARIABLES["fondo"]),  # texto de aviso
        (VARIABLES["texto"], "#e8eefb"),  # fila resaltada
    ],
)
def test_wcag_1_4_3_el_texto_tiene_al_menos_4_5_a_1(texto: str, fondo: str) -> None:
    assert contraste(texto, fondo) >= 4.5, f"{texto} sobre {fondo}: {contraste(texto, fondo):.2f}:1"


def test_wcag_1_4_11_el_borde_de_los_campos_tiene_al_menos_3_a_1() -> None:
    """S-40 (B-34): estaba en 1,39:1; el borde de los campos se oscurecio hasta 3,74:1."""
    assert contraste(VARIABLES["borde-campo"], BLANCO) >= 3.0


def test_wcag_1_4_11_las_barras_del_grafico_tienen_al_menos_3_a_1() -> None:
    """S-40 (B-34): estaban en 2,07:1; el relleno de las barras es ahora de 3,40:1."""
    barra = re.search(r"\.grafico \.barra \{ fill: (#[0-9a-fA-F]{6})", CSS)
    assert barra is not None
    assert contraste(barra.group(1), BLANCO) >= 3.0


def test_wcag_2_4_7_la_hoja_de_estilos_no_quita_el_indicador_de_foco() -> None:
    assert not re.search(r"outline\s*:\s*(none|0)", CSS)
    assert "tabindex" not in CSS


# --- estructura de las páginas generadas --------------------------------------------------------


class Revisor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.etiquetas: list[str] = []
        self.atributos: list[tuple[str, dict[str, str | None]]] = []
        self.etiquetas_for: set[str] = set()
        self.titulo = ""
        self._en_titulo = False
        self._en_label = 0
        self.dentro_de_label: list[bool] = []  # por cada elemento, si esta dentro de un <label>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self.etiquetas.append(tag)
        self.atributos.append((tag, a))
        self.dentro_de_label.append(self._en_label > 0)
        if tag == "label":
            self._en_label += 1
        if tag == "label" and a.get("for"):
            self.etiquetas_for.add(a["for"] or "")
        self._en_titulo = tag == "title"

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._en_titulo = False
        if tag == "label":
            self._en_label -= 1

    def handle_data(self, data: str) -> None:
        if self._en_titulo:
            self.titulo += data


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mundo:
    m = Mundo.nuevo(repositorios=RepositoriosDjango)
    monkeypatch.setattr(composicion, "reloj", lambda: m.reloj)
    monkeypatch.setattr(composicion, "directorio_de_soportes", lambda: tmp_path)
    m.registrar(vacaciones())
    m.emitir(ingreso())
    m.emitir(retiro("u-rrhh", "col-9"))
    m.registrar(cambio_de_departamento("u-jefe"))
    return m


PAGINAS = [
    ("/ingreso", None),
    ("/solicitudes", "u-col"),
    ("/solicitudes/nueva", "u-col"),
    ("/solicitudes/nueva/VAC", "u-col"),
    ("/solicitudes/nueva/ING", "u-rrhh"),
    ("/solicitudes/nueva/RET", "u-rrhh"),
    ("/bandeja", "u-rrhh"),
    ("/dashboard", "u-tec-ad"),
    ("/cuentas", "u-tec-ad"),
    ("/auditoria", "u-aud"),
    ("/administracion/perfiles", "u-admin"),
    ("/administracion/usuarios", "u-admin"),
    ("/errores", "u-admin"),
]


def _pagina(ruta: str, usuario: str | None) -> Revisor:
    cliente = Client()
    if usuario:
        sesion = cliente.session
        sesion["usuario_id"] = usuario
        sesion["inicio"] = AHORA.timestamp()
        sesion.save()
    r = cliente.get(ruta)
    assert r.status_code == 200, f"{ruta} respondió {r.status_code}"
    revisor = Revisor()
    revisor.feed(bytes(r.content).decode())
    return revisor


@pytest.mark.parametrize(("ruta", "usuario"), PAGINAS)
def test_ri_01_cada_pagina_cumple_la_estructura_accesible(
    mundo: Mundo, ruta: str, usuario: str | None
) -> None:
    p = _pagina(ruta, usuario)
    html = next(a for t, a in p.atributos if t == "html")
    assert html.get("lang") == "es", "WCAG 3.1.1: idioma de la página"
    meta = [a for t, a in p.atributos if t == "meta" and a.get("name") == "viewport"]
    assert meta
    assert "width=device-width" in str(meta[0]["content"]), "adaptable a distintos tamaños"
    assert p.titulo.strip(), "WCAG 2.4.2: título de la página"
    assert p.etiquetas.count("h1") >= 1, "WCAG 2.4.6: la página tiene un encabezado principal"
    assert "main" in p.etiquetas, "WCAG 1.3.1: región principal"
    # sin JavaScript de ningún tipo (de terceros o propio) y sin recursos externos (RI-01, invariante 11)
    assert "script" not in p.etiquetas
    for tag, a in p.atributos:
        for atributo in ("src", "href", "action"):
            valor = a.get(atributo) or ""
            assert not re.match(r"(https?:)?//", valor), (
                f"<{tag} {atributo}={valor}> es un recurso externo"
            )
        assert not any(k.startswith("on") for k in a), f"<{tag}> con manejador de eventos en línea"
        assert (
            not (a.get("tabindex") or "0").lstrip("-").isdigit() or int(a.get("tabindex") or 0) <= 0
        ), "WCAG 2.4.3: sin tabindex positivo (el orden de tabulación es el del documento)"


@pytest.mark.parametrize(("ruta", "usuario"), PAGINAS)
def test_ri_01_todo_campo_de_formulario_tiene_etiqueta(
    mundo: Mundo, ruta: str, usuario: str | None
) -> None:
    p = _pagina(ruta, usuario)
    for (tag, a), anidado in zip(p.atributos, p.dentro_de_label, strict=True):
        if tag not in ("input", "select", "textarea"):
            continue
        if tag == "input" and a.get("type") in ("hidden", "submit", "button"):
            continue
        etiquetado = (
            anidado
            or (a.get("id") in p.etiquetas_for)
            or a.get("aria-label")
            or a.get("aria-labelledby")
        )
        assert etiquetado, f"WCAG 3.3.2/4.1.2: <{tag} name={a.get('name')}> sin etiqueta en {ruta}"


@pytest.mark.parametrize(("ruta", "usuario"), PAGINAS)
def test_ri_01_imagenes_y_graficos_tienen_alternativa_y_las_tablas_encabezados(
    mundo: Mundo, ruta: str, usuario: str | None
) -> None:
    p = _pagina(ruta, usuario)
    for tag, a in p.atributos:
        if tag == "img":
            assert a.get("alt") is not None, "WCAG 1.1.1: imagen sin alt"
        if tag == "svg":
            assert (
                a.get("role") == "img" or a.get("aria-hidden") == "true" or a.get("aria-label")
            ), "WCAG 1.1.1: gráfico SVG sin rol ni nombre accesible"
    if "table" in p.etiquetas:
        assert "th" in p.etiquetas, "WCAG 1.3.1: tabla sin celdas de encabezado"
