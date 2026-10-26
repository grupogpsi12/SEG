"""Genera los cuatro informes de la entrega (item 5.7) a partir de la evidencia cruda.

    python docs/entregables/scripts/generar_informes.py

Lee docs/entregables/evidencias/** (JSON de casos de uso, JUnit, ZAP, Trivy, capturas analizadas y
pantallas) y escribe 4 HTML y 4 PDF en docs/entregables/. Ninguna cifra se transcribe a mano.
"""

import base64
import collections
import html
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EV = RAIZ / "evidencias"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PERFIL = str(Path.home() / "AppData/Local/Temp/jml-edge-capturas")
FECHA = "24 de octubre de 2026"
E = html.escape

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
:root { --tinta:#1b2430; --suave:#5a6676; --linea:#d5dbe3; --fondo:#f4f6f9; --acento:#1f5fbf;
  --ok:#1e7a46; --falla:#b42318; --alta:#b42318; --media:#b54708; --baja:#946200; --info:#475