"""Tests de los helpers compartidos `_pdf` y `_html`.

Antes la lógica vivía replicada en boe/bocm/ciemat/enricher (PDF) y en
isciii/cm_ficha_enfermeria/enricher (HTML). Estos tests cubren los
helpers extraídos en el refactor para garantizar que el comportamiento
único sigue cubriendo los matices de cada caller (verify=False de
ciemat, max_pages=None de bocm, separador y colapso del enricher, etc.).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vigia.sources._html import extract_clean_text
from vigia.sources._pdf import (
    DEFAULT_MAX_BYTES,
    download_and_extract_pdf,
    extract_pdf_text,
)


class TestExtractCleanText:
    def test_quita_scripts_y_styles_por_defecto(self):
        html = (
            "<html><body><p>visible</p>"
            "<script>oculto1()</script><style>.x{}</style>"
            "</body></html>"
        )
        text = extract_clean_text(html)
        assert "visible" in text
        assert "oculto1" not in text
        assert ".x{}" not in text

    def test_quita_nav_header_footer_noscript(self):
        html = (
            "<html><body>"
            "<nav>nav</nav><header>head</header>"
            "<main>contenido</main>"
            "<footer>foot</footer><noscript>ns</noscript>"
            "</body></html>"
        )
        text = extract_clean_text(html)
        assert "contenido" in text
        for noise in ("nav", "head", "foot", "ns"):
            assert noise not in text

    def test_target_selectors_usa_el_primero_que_matchee(self):
        html = (
            "<html><body>"
            "<article class='x'>articulo</article>"
            "<main>main</main>"
            "</body></html>"
        )
        text = extract_clean_text(
            html, target_selectors=("article.x", "main", "body")
        )
        assert text.strip() == "articulo"

    def test_target_selectors_cae_al_siguiente_si_el_primero_no_matchea(self):
        html = "<html><body><main>solo main</main></body></html>"
        text = extract_clean_text(
            html, target_selectors=("article.no-existe", "main", "body")
        )
        assert text.strip() == "solo main"

    def test_extra_decompose_borra_selectores_adicionales(self):
        html = (
            "<html><body><div>util</div>"
            "<div class='lfr-nav-item'>ruido</div></body></html>"
        )
        text = extract_clean_text(
            html, extra_decompose=(".lfr-nav-item",)
        )
        assert "util" in text
        assert "ruido" not in text

    def test_separator_y_collapse_lines_modo_enricher(self):
        """El enricher quiere `\\n` como separador y colapso por línea
        (preserva pistas visuales para el LLM)."""
        html = (
            "<html><body>"
            "<p>linea uno</p><p>linea dos</p>"
            "<p>   </p><p>linea tres</p>"
            "</body></html>"
        )
        text = extract_clean_text(html, separator="\n", collapse_lines=True)
        # Sin líneas vacías y cada párrafo en su línea.
        lines = text.splitlines()
        assert lines == ["linea uno", "linea dos", "linea tres"]

    def test_acepta_bytes_y_string(self):
        html_str = "<html><body><p>txt</p></body></html>"
        html_bytes = html_str.encode("utf-8")
        assert "txt" in extract_clean_text(html_str)
        assert "txt" in extract_clean_text(html_bytes)

    def test_html_vacio_devuelve_string_vacio(self):
        assert extract_clean_text("").strip() == ""


class TestExtractPdfText:
    def test_pdf_corrupto_devuelve_vacio_no_lanza(self):
        # Bytes que no son un PDF válido.
        assert extract_pdf_text(b"esto no es un pdf") == ""

    def test_max_pages_recorta(self):
        """Construye un PDF mínimo via reportlab si está disponible.

        Si no, salta — no es razón para fallar el suite. El comportamiento
        clave (recortar a max_pages) ya está cubierto por los tests del
        flujo BOE/CIEMAT que monkeypatchen pdfplumber directamente.
        """
        try:
            from reportlab.pdfgen import canvas
            from io import BytesIO
        except ImportError:
            pytest.skip("reportlab no disponible")
        buf = BytesIO()
        c = canvas.Canvas(buf)
        for i in range(3):
            c.drawString(100, 100, f"pagina {i}")
            c.showPage()
        c.save()
        data = buf.getvalue()

        full = extract_pdf_text(data)
        recortado = extract_pdf_text(data, max_pages=1)
        assert "pagina 0" in full
        assert "pagina 2" in full
        assert "pagina 0" in recortado
        assert "pagina 2" not in recortado

    def test_max_pages_none_recorre_todas(self):
        """max_pages=None debe equivaler al recorrido completo."""
        try:
            from reportlab.pdfgen import canvas
            from io import BytesIO
        except ImportError:
            pytest.skip("reportlab no disponible")
        buf = BytesIO()
        c = canvas.Canvas(buf)
        for i in range(35):  # más que el default de 30
            c.drawString(100, 100, f"p{i}")
            c.showPage()
        c.save()
        data = buf.getvalue()

        completo = extract_pdf_text(data, max_pages=None)
        capado = extract_pdf_text(data)  # default 30
        assert "p34" in completo
        assert "p34" not in capado


class TestDownloadAndExtractPdf:
    def test_streaming_corta_al_alcanzar_max_bytes(self):
        """Bombas-zip / PDFs anormalmente grandes deben quedarse al tope."""
        # Stream artificialmente grande. El cap por defecto es 5 MB; pasamos
        # 6 MB en chunks para verificar que el helper para de leer.
        chunks_grandes = [b"a" * 1024] * (6 * 1024)  # 6 MB total
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.iter_content.return_value = iter(chunks_grandes)
        resp.close = lambda: None

        with patch("vigia.sources._pdf.requests.get", return_value=resp):
            # extract_pdf_text de ese contenido devolverá "" (no es PDF),
            # pero importa que no nos comamos toda la memoria.
            with patch(
                "vigia.sources._pdf.extract_pdf_text", return_value=""
            ) as mock_extract:
                download_and_extract_pdf(
                    "https://x/y.pdf", headers={}, timeout=10,
                )
                # El body que llega a extract_pdf_text debe tener exactamente
                # max_bytes (no más).
                assert mock_extract.call_count == 1
                bytes_passed = mock_extract.call_args[0][0]
                assert len(bytes_passed) == DEFAULT_MAX_BYTES

    def test_propaga_verify_false_a_requests(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.iter_content.return_value = iter([b""])
        resp.close = lambda: None

        with patch("vigia.sources._pdf.requests.get", return_value=resp) as get:
            download_and_extract_pdf(
                "https://ciemat.es/x.pdf",
                headers={"User-Agent": "x"},
                timeout=25,
                verify=False,
            )
            kwargs = get.call_args.kwargs
            assert kwargs["verify"] is False
            assert kwargs["stream"] is True
            assert kwargs["timeout"] == 25
