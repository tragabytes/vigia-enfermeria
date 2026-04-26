"""
Tests del parser CIEMAT.

Cubre el flujo:
  1. Listar ofertas activas (HTML server-side, links a `/oferta/<id>` con
     fecha en bloque padre).
  2. Para cada oferta, descargar detalle (texto plano) + extraer PDFs
     anexos del propio dominio ciemat.es.
  3. Parsear los PDFs (mockeados con pdfplumber) y combinar con el HTML.
  4. Filtrar items que no contengan keyword tras detalle + PDFs.
  5. Whitelist anti-SSRF — solo PDFs en ciemat.es.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from vigia.sources.ciemat import CIEMATSource


def _resp(text: str, status: int = 200, content: bytes = None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.url = "https://www.ciemat.es/x"
    r.raise_for_status = lambda: None
    if content is not None:
        r.iter_content = lambda chunk_size: [content]
        r.headers = {"content-type": "application/pdf"}
        r.close = lambda: None
    return r


LISTING_HTML = """
<html><body>
  <ul>
    <li>
      <a href="/ofertas-de-empleo/-/ofertas/oferta/2380?_es_param=foo">
        CONCURSO ESPECIFICO I - 2026 PERSONAL FUNCIONARIO DEL CIEMAT
      </a>
      <span>24/04/2026</span>
    </li>
    <li>
      <a href="/ofertas-de-empleo/-/ofertas/oferta/2292?_es_param=bar">
        ESCALA TECNICOS ESPECIALIZADOS DE OPIS
      </a>
      <span>10/03/2026</span>
    </li>
    <li>
      <a href="/ofertas-de-empleo/-/ofertas/oferta/2100?_es_param=old">
        OFERTA HISTÓRICA YA CERRADA
      </a>
      <span>05/02/2025</span>
    </li>
  </ul>
</body></html>
"""

DETAIL_2380_HTML = """
<html><body>
  <h1>CONCURSO ESPECIFICO I - 2026 PERSONAL FUNCIONARIO DEL CIEMAT</h1>
  <h2>Hitos</h2>
  <p>24/04/2026 — Apertura plazo</p>
  <h2>Descargas</h2>
  <a href="https://www.ciemat.es/doc/ficheros_oe/2380Perfiles.pdf">
    Catálogo perfiles formativos por materias
  </a>
  <a href="https://attacker.example.com/leaked.pdf">malicious</a>
  <a href="https://www.ciemat.es/doc/otra/2380Bases.pdf">Bases técnicas</a>
</body></html>
"""

DETAIL_2292_HTML = """
<html><body>
  <h1>ESCALA TECNICOS ESPECIALIZADOS DE OPIS</h1>
  <h2>Descargas</h2>
  <a href="https://www.ciemat.es/doc/2292Bases.pdf">Bases</a>
</body></html>
"""


class TestCiematListing:
    def test_extrae_ofertas_filtrando_por_fecha(self):
        with patch("vigia.sources.ciemat.requests.get") as fake_get, \
             patch.object(CIEMATSource, "_fetch_offer_detail",
                          return_value=("texto genérico irrelevante", [])) as detail:
            fake_get.return_value = _resp(LISTING_HTML)
            items = CIEMATSource().fetch(since_date=date(2026, 1, 1))

        # Las ofertas 2380 y 2292 son posteriores a 2026-01-01; la 2100 (2025) se filtra.
        # Con detalle sin keywords del filtro fast, ningún item pasa,
        # pero `_fetch_offer_detail` SÍ se invocó 2 veces (las dos ofertas vivas).
        assert items == []
        assert detail.call_count == 2
        called_urls = [c.args[0] for c in detail.call_args_list]
        assert any("2380" in u for u in called_urls)
        assert any("2292" in u for u in called_urls)
        assert not any("2100" in u for u in called_urls)

    def test_listado_sin_ofertas_no_falla(self):
        with patch("vigia.sources.ciemat.requests.get",
                   return_value=_resp("<html><body>Mantenimiento</body></html>")):
            items = CIEMATSource().fetch(since_date=date(2026, 1, 1))
        assert items == []

    def test_listado_caido_devuelve_lista_vacia_con_error(self):
        src = CIEMATSource()
        with patch("vigia.sources.ciemat.requests.get",
                   side_effect=ConnectionError("DNS fallo")):
            items = src.fetch(since_date=date(2026, 1, 1))
        assert items == []
        assert any("DNS fallo" in e for e in src.last_errors)


class TestCiematDetailAndPdfs:
    def test_match_en_pdf_anexo_genera_raw_item(self):
        """Caso real: el HTML del detalle es genérico, pero el PDF anexo
        contiene "Especialidad de Enfermería del trabajo"."""
        listing_resp = _resp(LISTING_HTML)
        detail_resp = _resp(DETAIL_2380_HTML)

        def fake_get(url, **kw):
            if "ofertas-de-empleo" in url and "oferta/" not in url:
                return listing_resp
            if "oferta/2380" in url or "oferta/2292" in url:
                return detail_resp
            raise AssertionError(f"GET inesperado a {url}")

        with patch("vigia.sources.ciemat.requests.get", side_effect=fake_get), \
             patch.object(CIEMATSource, "_fetch_pdf_text") as fake_pdf:
            # El primer PDF (perfiles) tiene match; los siguientes no se piden.
            fake_pdf.side_effect = [
                "Especialidad de Enfermería del trabajo. Perfil formativo.",
                "irrelevante",
                "irrelevante",
            ]
            items = CIEMATSource().fetch(since_date=date(2026, 1, 1))

        assert len(items) >= 1
        # Localizar el item 2380
        item_2380 = next((it for it in items if "2380" in it.url), None)
        assert item_2380 is not None
        assert "Enfermería del trabajo" in item_2380.text
        assert "[ANEXO PDF" in item_2380.text
        assert item_2380.date == date(2026, 4, 24)

    def test_pdf_fuera_de_whitelist_se_ignora(self):
        """Anti-SSRF: el link a attacker.example.com NO se descarga."""
        listing_resp = _resp(LISTING_HTML)
        detail_resp = _resp(DETAIL_2380_HTML)

        called_pdfs = []
        def fake_get(url, **kw):
            if "ofertas-de-empleo" in url and "oferta/" not in url:
                return listing_resp
            if "oferta/" in url:
                return detail_resp
            raise AssertionError(f"GET inesperado a {url}")

        def track_pdf(url):
            called_pdfs.append(url)
            return "irrelevante"

        with patch("vigia.sources.ciemat.requests.get", side_effect=fake_get), \
             patch.object(CIEMATSource, "_fetch_pdf_text", side_effect=track_pdf):
            CIEMATSource().fetch(since_date=date(2026, 1, 1))

        # Solo se intentaron PDFs en ciemat.es; el de attacker.example.com nunca.
        assert all("ciemat.es" in u for u in called_pdfs)
        assert not any("attacker" in u for u in called_pdfs)

    def test_se_para_en_primer_pdf_con_match(self):
        """Optimización: si el primer PDF ya matchea, los siguientes
        no se descargan."""
        listing_resp = _resp(LISTING_HTML)
        detail_resp = _resp(DETAIL_2380_HTML)

        with patch("vigia.sources.ciemat.requests.get",
                   side_effect=lambda url, **kw: listing_resp if "oferta/" not in url else detail_resp), \
             patch.object(CIEMATSource, "_fetch_pdf_text") as fake_pdf:
            # Primer PDF de cada oferta tiene match → solo se descarga 1 por oferta
            fake_pdf.return_value = "Especialidad de Enfermería del trabajo"
            CIEMATSource().fetch(since_date=date(2026, 1, 1))

        # El detalle 2380 tiene 2 PDFs en whitelist (perfiles + bases). Solo
        # debería pedirse el primero porque ya matchea. La oferta 2292 tiene 1.
        # Total: 1 + 1 = 2 invocaciones.
        assert fake_pdf.call_count == 2

    def test_oferta_sin_match_no_genera_raw_item(self):
        """Si tras detalle + todos los PDFs no aparece keyword, se descarta."""
        listing_resp = _resp(LISTING_HTML)
        detail_resp = _resp(DETAIL_2292_HTML)

        with patch("vigia.sources.ciemat.requests.get",
                   side_effect=lambda url, **kw: listing_resp if "oferta/" not in url else detail_resp), \
             patch.object(CIEMATSource, "_fetch_pdf_text",
                          return_value="Bases técnicas para informática y química."):
            items = CIEMATSource().fetch(since_date=date(2026, 1, 1))

        assert items == []


class TestProbe:
    def test_probe_url_es_listado(self):
        assert CIEMATSource.probe_url == "https://www.ciemat.es/ofertas-de-empleo"
