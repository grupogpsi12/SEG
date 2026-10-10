import jml.aplicacion
import jml.dominio


def test_el_nucleo_se_importa() -> None:
    assert jml.dominio.__doc__
    assert jml.aplicacion.__doc__
