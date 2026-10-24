"""Item 5.7 / ADR-029: secretos compartidos del equipo con SOPS + age.

Las pruebas estáticas corren siempre: ningún valor de `infra/secretos/` queda sin cifrar. Las de
`infra/scripts/secretos.sh` necesitan `sops`, `age-keygen` y `bash`; sin ellos se omiten (S-28).
Usan una carpeta temporal y llaves desechables: nunca tocan `secrets/` ni la llave de nadie.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
CIFRADOS = RAIZ / "infra" / "secretos"
SCRIPT = RAIZ / "infra" / "scripts" / "secretos.sh"
CONFIG: dict[str, Any] = yaml.safe_load((RAIZ / ".sops.yaml").read_text(encoding="utf-8"))


def _hojas(nodo: Any) -> list[Any]:
    if isinstance(nodo, dict):
        return [h for k, v in nodo.items() if k != "sops" for h in _hojas(v)]
    if isinstance(nodo, list):
        return [h for v in nodo for h in _hojas(v)]
    return [nodo]


def test_ADR_029_ningun_valor_de_infra_secretos_esta_en_claro() -> None:
    for archivo in CIFRADOS.glob("*"):
        assert archivo.name.endswith(".sops.yaml"), (
            f"{archivo.name}: aqui solo van archivos cifrados"
        )
        datos = yaml.safe_load(archivo.read_text(encoding="utf-8"))
        assert datos["sops"]["age"], archivo.name  # cifrado para alguien
        for valor in _hojas(datos):
            assert isinstance(valor, str), archivo.name
            assert valor.startswith("ENC[AES256_GCM,"), f"{archivo.name}: un valor sin cifrar"


def test_ADR_029_cada_grupo_tiene_su_regla_y_solo_claves_publicas() -> None:
    reglas = CONFIG["creation_rules"]
    grupos = {r["path_regex"].split("]")[-1].split("\\.")[0] for r in reglas}
    assert grupos == {"equipo", "administracion"}
    for r in reglas:
        assert r["path_regex"].startswith("infra[/\\\\]secretos[/\\\\]"), r["path_regex"]
        for clave in r["key_groups"][0]["age"] or []:
            assert clave.startswith("age1"), "solo claves publicas de age"
    texto = (RAIZ / ".sops.yaml").read_text(encoding="utf-8")
    assert "AGE-SECRET-KEY" not in texto


def test_ADR_029_secrets_sigue_ignorado_e_infra_secretos_no() -> None:
    ignorados = subprocess.run(
        ["git", "check-ignore", "secrets/x", "infra/secretos/equipo.sops.yaml"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    assert "secrets/x" in ignorados
    assert "infra/secretos" not in ignorados


# --- infra/scripts/secretos.sh -----------------------------------------------------------------

BASH = shutil.which("bash")
SIN_SOPS = not (shutil.which("sops") and shutil.which("age-keygen") and BASH)
VALORES = {
    "db_password": 'clave-"con"-comillas-y-\\barra-CENTINELA7d1',
    "supabase_ca_crt": "-----BEGIN CERTIFICATE-----\nMIIBfalsoCENTINELA7d1\nX\n-----END CERTIFICATE-----\n",
}


class Entorno:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.secretos = base / "secrets"
        self.cifrados = base / "infra" / "secretos"  # la ruta que exigen las reglas
        self.config = base / ".sops.yaml"
        self.secretos.mkdir()
        # Las mismas reglas del repositorio, sin sus destinatarios reales (prueba hermética).
        reglas = (RAIZ / ".sops.yaml").read_text(encoding="utf-8").splitlines(keepends=True)
        self.config.write_text("".join(x for x in reglas if "age1" not in x), encoding="utf-8")

    def correr(self, *args: str, llave: str = "a", ok: bool = True) -> str:
        env = {
            **os.environ,
            "JML_SECRETOS": str(self.secretos),
            "JML_CIFRADOS": str(self.cifrados),
            "JML_SOPS_CONFIG": str(self.config),
            "SOPS_AGE_KEY_FILE": str(self.base / f"llave-{llave}.txt"),
        }
        r = subprocess.run(
            [str(BASH), str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
        )
        salida = r.stdout + r.stderr
        assert (r.returncode == 0) is ok, salida
        assert "CENTINELA7d1" not in salida, "el script imprimio un valor"
        return salida

    def publica(self, llave: str) -> str:
        return self.correr("llave", llave=llave).strip().splitlines()[-1]


@pytest.fixture
def entorno(tmp_path: Path) -> Entorno:
    return Entorno(tmp_path)


@pytest.mark.skipif(SIN_SOPS, reason="S-28: sin sops, age-keygen o bash")
def test_cifrar_y_descifrar_conserva_los_valores_sin_mostrarlos(entorno: Entorno) -> None:
    entorno.correr("agregar", "equipo", entorno.publica("a"), "Persona A")
    for nombre, valor in VALORES.items():
        (entorno.secretos / nombre).write_text(valor, encoding="utf-8", newline="")
    entorno.correr("cifrar", "equipo", "db_password")
    entorno.correr("cifrar", "equipo", "supabase_ca_crt")  # el segundo, sobre el archivo existente
    cifrado = (entorno.cifrados / "equipo.sops.yaml").read_text(encoding="utf-8")
    assert "CENTINELA7d1" not in cifrado
    assert "db_password: ENC[" in cifrado  # los nombres se ven; los valores no
    for nombre in VALORES:
        (entorno.secretos / nombre).unlink()
    assert "escrito" in entorno.correr("descifrar", "equipo")
    for nombre, valor in VALORES.items():
        leido = (entorno.secretos / nombre).read_text(encoding="utf-8")
        assert leido.rstrip("\n") == valor.rstrip("\n"), nombre


@pytest.mark.skipif(SIN_SOPS, reason="S-28: sin sops, age-keygen o bash")
def test_descifrar_no_pisa_un_secreto_distinto_salvo_con_forzar(entorno: Entorno) -> None:
    entorno.correr("agregar", "equipo", entorno.publica("a"), "Persona A")
    (entorno.secretos / "db_password").write_text(VALORES["db_password"], encoding="utf-8")
    entorno.correr("cifrar", "equipo", "db_password")
    (entorno.secretos / "db_password").write_text("local-propia", encoding="utf-8")
    assert "DISTINTO" in entorno.correr("descifrar", "equipo")
    assert (entorno.secretos / "db_password").read_text(encoding="utf-8") == "local-propia"
    entorno.correr("descifrar", "--forzar", "equipo")
    assert (entorno.secretos / "db_password").read_text(encoding="utf-8") == VALORES["db_password"]


@pytest.mark.skipif(SIN_SOPS, reason="S-28: sin sops, age-keygen o bash")
def test_agregar_y_quitar_personas_vuelve_a_cifrar(entorno: Entorno) -> None:
    a, b = entorno.publica("a"), entorno.publica("b")
    entorno.correr("agregar", "equipo", a, "Persona A")
    (entorno.secretos / "db_password").write_text(VALORES["db_password"], encoding="utf-8")
    entorno.correr("cifrar", "equipo", "db_password")
    assert "NO lo descifra" in entorno.correr("estado", llave="b")
    entorno.correr("agregar", "equipo", b, "Persona B")  # lo agrega quien ya descifra
    assert "equipo: lo descifra" in entorno.correr("estado", llave="b")
    salida = entorno.correr("quitar", "equipo", a, llave="b")
    assert "Rote en su origen" in salida
    assert "NO lo descifra" in entorno.correr("estado", llave="a")
    assert a not in entorno.config.read_text(encoding="utf-8")


@pytest.mark.skipif(SIN_SOPS, reason="S-28: sin sops, age-keygen o bash")
def test_rechaza_nombres_con_rutas_y_grupos_desconocidos(entorno: Entorno) -> None:
    entorno.correr("agregar", "equipo", entorno.publica("a"), "Persona A")
    (entorno.secretos / "x").write_text("y", encoding="utf-8")
    assert "invalido" in entorno.correr("cifrar", "equipo", "../x", ok=False)
    assert "no esta" in entorno.correr("cifrar", "otro", "x", ok=False)
    assert "no es una clave publica" in entorno.correr(
        "agregar", "equipo", "AGE-SECRET-KEY-1X", "Z", ok=False
    )
    # nadie se agrega solo: sin poder descifrar, no hay updatekeys
    entorno.correr("cifrar", "equipo", "x")
    assert "no pude actualizar" in entorno.correr(
        "agregar", "equipo", entorno.publica("b"), "Persona B", llave="b", ok=False
    )
