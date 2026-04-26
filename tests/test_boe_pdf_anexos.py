"""
Tests del flujo de extracción de PDFs anexos del BOE.

Cuando el HTML del ítem BOE no contiene "enfermer" pero el departamento es
relevante (Ministerio de Ciencia, Defensa, Interior…), el flujo entra a
los PDFs anexos enlazados en el HTML y aplica el matcher al texto
extraído. Cubre el caso real de OPIs conjuntas (CIEMAT, IAC, INIA…)
donde la lista de plazas vive en un PDF separado.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from vigia.sources.boe import BOESource


def _html_response(body_html: str, url: str = "https://www.boe.es/x"):
    resp = MagicMock()
    resp.status_code = 200
    resp.url = url
    resp.text = body_html
    resp.raise_for_status = lambda: None
    return resp


class TestPdfLinkExtraction:
    def test_extrae_link_pdf_anexo_de_dominio_boe(self):
        html = """
        <html><body><div id="textoxslt">
            Texto del item.
            <a href="https://www.boe.es/boe/dias/2026/04/01/pdfs/BOE-A-2026-9999-anexo.pdf">
              Anexo I — Lista de plazas
            </a>
        </div></body></html>
        """
        with patch.object(
            BOESource, "_default_headers", return_value={}
        ), patch("vigia.sources.boe.requests.get", return_value=_html_response(html)):
            text, pdfs = BOESource()._fetch_html_with_pdf_links(
                "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1234"
            )
        assert "Lista de plazas" in text
        assert pdfs == [
            "https://www.boe.es/boe/dias/2026/04/01/pdfs/BOE-A-2026-9999-anexo.pdf"
        ]

    def test_excluye_pdf_propio_del_mismo_item(self):
        """El "Versión PDF" del propio item es idéntico al HTML — no debe
        aparecer en la lista de anexos a descargar."""
        html = """
        <html><body><div id="textoxslt">
            <a href="https://www.boe.es/boe/dias/2026/04/01/pdfs/BOE-A-2026-1234.pdf">
              Versión PDF
            </a>
            <a href="https://www.boe.es/boe/dias/2026/04/01/pdfs/anexo-bases.pdf">
              Bases técnicas
            </a>
        </div></body></html>
        """
        with patch.object(
            BOESource, "_default_headers", return_value={}
        ), patch("vigia.sources.boe.requests.get", return_value=_html_response(html)):
            _, pdfs = BOESource()._fetch_html_with_pdf_links(
                "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1234"
            )
        assert pdfs == [
            "https://www.boe.es/boe/dias/2026/04/01/pdfs/anexo-bases.pdf"
        ]

    def test_descarta_links_fuera_de_whitelist(self):
        """Anti-SSRF: solo dominio boe.es. Otros se ignoran."""
        html = """
        <html><body><div id="textoxslt">
            <a href="https://attacker.example.com/secret.pdf">malicious</a>
            <a href="https://otro-dominio.es/bases.pdf">otro</a>
            <a href="https://www.boe.es/anexo.pdf">anexo legítimo</a>
        </div></body></html>
        """
        with patch.object(
            BOESource, "_default_headers", return_value={}
        ), patch("vigia.sources.boe.requests.get", return_value=_html_response(html)):
            _, pdfs = BOESource()._fetch_html_with_pdf_links(
                "https://www.boe.es/x?id=BOE-A-2026-555"
            )
        assert pdfs == ["https://www.boe.es/anexo.pdf"]

    def test_prioriza_anexo_sobre_otros(self):
        html = """
        <html><body><div id="textoxslt">
            <a href="https://www.boe.es/otro.pdf">otro link</a>
            <a href="https://www.boe.es/anexo-i-plazas.pdf">anexo I</a>
            <a href="https://www.boe.es/bases-tecnicas.pdf">bases</a>
        </div></body></html>
        """
        with patch.object(
            BOESource, "_default_headers", return_value={}
        ), patch("vigia.sources.boe.requests.get", return_value=_html_response(html)):
            _, pdfs = BOESource()._fetch_html_with_pdf_links(
                "https://www.boe.es/x?id=BOE-A-2026-777"
            )
        assert pdfs == [
            "https://www.boe.es/anexo-i-plazas.pdf",
            "https://www.boe.es/bases-tecnicas.pdf",
            "https://www.boe.es/otro.pdf",
        ]


class TestBuildRawItemConPdfAnexo:
    def _patch_html_and_pdf(self, html_text: str, pdf_text: str):
        """Mockea las dos descargas: HTML del item y PDF del anexo."""
        return (
            patch.object(
                BOESource,
                "_fetch_html_with_pdf_links",
                return_value=(html_text, ["https://www.boe.es/anexo-plazas.pdf"]),
            ),
            patch.object(BOESource, "_fetch_pdf_text", return_value=pdf_text),
        )

    def test_match_en_anexo_pdf_genera_raw_item(self):
        """OPIs Ministerio de Ciencia: HTML genérico, plazas en anexo PDF."""
        html_generico = (
            "Resolución de la Subsecretaría del Ministerio de Ciencia, "
            "por la que se aprueba la oferta de empleo público 2026 de los "
            "Organismos Públicos de Investigación. Anexo I disponible."
        )
        pdf_con_match = (
            "ANEXO I — DISTRIBUCIÓN DE PLAZAS\n"
            "Centro: CIEMAT\n"
            "Categoría: Diplomado en Enfermería del Trabajo\n"
            "Plazas: 1"
        )
        p1, p2 = self._patch_html_and_pdf(html_generico, pdf_con_match)
        with p1, p2:
            item = BOESource()._build_raw_item(
                titulo="Oferta de empleo público de los OPIs 2026",
                url_html="https://www.boe.es/x?id=BOE-A-2026-1111",
                target=date(2026, 4, 1),
                sec_code="2A",
                dept_name="Ministerio de Ciencia, Innovación y Universidades",
            )
        assert item is not None
        assert "Enfermería del Trabajo" in item.text
        # El anexo PDF se concatena al body con un marcador
        assert "[ANEXO PDF" in item.text

    def test_no_match_anexo_no_genera_raw_item(self):
        """Si ni el HTML ni el PDF anexo contienen match, se descarta."""
        p1, p2 = self._patch_html_and_pdf(
            "Resolución sin contenido relevante.",
            "Anexo de mantenimiento de instalaciones eléctricas.",
        )
        with p1, p2:
            item = BOESource()._build_raw_item(
                titulo="Mantenimiento de instalaciones",
                url_html="https://www.boe.es/x?id=BOE-A-2026-2222",
                target=date(2026, 4, 1),
                sec_code="2A",
                dept_name="Ministerio de Ciencia",
            )
        assert item is None

    def test_no_se_consulta_pdf_si_html_ya_matchea(self):
        """Optimización: si el HTML contiene match, los anexos PDF se saltan."""
        html_con_match = (
            "Convocatoria SERMAS — plaza de Enfermería del Trabajo. Oferta 2026."
        )
        pdf_caro_no_invocado = MagicMock()
        with patch.object(
            BOESource,
            "_fetch_html_with_pdf_links",
            return_value=(html_con_match, ["https://www.boe.es/anexo.pdf"]),
        ), patch.object(BOESource, "_fetch_pdf_text", new=pdf_caro_no_invocado):
            item = BOESource()._build_raw_item(
                titulo="Convocatoria personal estatutario fijo",
                url_html="https://www.boe.es/x?id=BOE-A-2026-3333",
                target=date(2026, 4, 1),
                sec_code="2B",
                dept_name="Comunidad de Madrid — Consejería de Sanidad",
            )
        assert item is not None
        pdf_caro_no_invocado.assert_not_called()

    def test_se_para_en_primer_anexo_que_matchea(self):
        """Si descargo 3 anexos pero el primero ya tiene match, no toco los otros."""
        html_generico = "Resolución del Ministerio de Defensa..."
        pdfs = [
            "https://www.boe.es/anexo-1.pdf",
            "https://www.boe.es/anexo-2.pdf",
            "https://www.boe.es/anexo-3.pdf",
        ]
        # Solo el primer PDF contiene match; los otros no deberían descargarse
        call_count = {"n": 0}
        def fake_pdf(self, url):
            call_count["n"] += 1
            return "Plaza de Enfermería del Trabajo" if call_count["n"] == 1 else "irrelevante"

        with patch.object(
            BOESource,
            "_fetch_html_with_pdf_links",
            return_value=(html_generico, pdfs),
        ), patch.object(BOESource, "_fetch_pdf_text", autospec=True, side_effect=fake_pdf):
            item = BOESource()._build_raw_item(
                titulo="Resolución de la Subsecretaría",
                url_html="https://www.boe.es/x?id=BOE-A-2026-4444",
                target=date(2026, 4, 1),
                sec_code="2A",
                dept_name="Ministerio de Defensa",
            )
        assert item is not None
        assert call_count["n"] == 1   # solo se descargó el primero

    def test_dept_no_relevante_no_dispara_pdf_fetch(self):
        """Si el departamento no está en la whitelist, ni siquiera se mira
        el HTML — y por tanto tampoco los PDFs."""
        with patch.object(
            BOESource, "_fetch_html_with_pdf_links"
        ) as fake_html, patch.object(BOESource, "_fetch_pdf_text") as fake_pdf:
            item = BOESource()._build_raw_item(
                titulo="Convocatoria genérica de un dept no sanitario",
                url_html="https://www.boe.es/x?id=BOE-A-2026-5555",
                target=date(2026, 4, 1),
                sec_code="2A",
                dept_name="Universidad de Zaragoza",   # no en whitelist
            )
        assert item is None
        fake_html.assert_not_called()
        fake_pdf.assert_not_called()
