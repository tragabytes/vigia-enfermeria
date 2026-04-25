"""
Tests de la fuente CODEM con múltiples feeds RSS.

Verifica que CODEMSource consulta tanto el feed de empleo público como
el de actualidad, y que cada item lleva en `extra["feed"]` la etiqueta
del feed de origen para facilitar la depuración.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from vigia.sources.codem import CODEMSource, CODEM_RSS_FEEDS


# RSS mínimo válido con un solo item por feed, etiquetando cuál es para
# poder verificar después que no se confundieron.
def _rss_xml(label: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>CODEM - {label}</title>
    <item>
      <title>Convocatoria de Enfermería del Trabajo desde feed {label}</title>
      <link>https://www.codem.es/item/{label}-1</link>
      <pubDate>Thu, 24 Apr 2026 10:00:00 GMT</pubDate>
      <description>Texto irrelevante del item del feed {label}</description>
    </item>
  </channel>
</rss>""".encode("utf-8")


class TestCODEMMultipleFeeds:
    def test_lista_de_feeds_correcta(self):
        """Sanity check: hay al menos los dos feeds esperados, con etiqueta única."""
        labels = [label for label, _ in CODEM_RSS_FEEDS]
        assert "empleo" in labels
        assert "actualidad" in labels
        assert len(labels) == len(set(labels)), "Etiquetas duplicadas en CODEM_RSS_FEEDS"

    def test_fetch_consume_todos_los_feeds(self, monkeypatch):
        """fetch() llama a requests.get una vez por cada feed configurado."""
        urls_solicitadas = []

        def fake_get(url, *args, **kwargs):
            urls_solicitadas.append(url)
            label = "empleo" if "e0fed1d6" in url else "actualidad"
            resp = MagicMock()
            resp.status_code = 200
            resp.content = _rss_xml(label)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("vigia.sources.codem.requests.get", fake_get)

        source = CODEMSource()
        items = source.fetch(date(2026, 4, 1))

        assert len(urls_solicitadas) == len(CODEM_RSS_FEEDS)
        assert len(items) == 2  # uno por feed

    def test_items_etiquetados_con_su_feed(self, monkeypatch):
        """Cada RawItem lleva en extra['feed'] el feed del que provino."""
        def fake_get(url, *args, **kwargs):
            label = "empleo" if "e0fed1d6" in url else "actualidad"
            resp = MagicMock()
            resp.status_code = 200
            resp.content = _rss_xml(label)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("vigia.sources.codem.requests.get", fake_get)

        source = CODEMSource()
        items = source.fetch(date(2026, 4, 1))

        feeds_encontrados = {item.extra["feed"] for item in items}
        assert feeds_encontrados == {"empleo", "actualidad"}

    def test_fallo_de_un_feed_no_corta_el_otro(self, monkeypatch):
        """Si un feed da error, el otro debe seguir procesándose."""
        def fake_get(url, *args, **kwargs):
            if "e0fed1d6" in url:
                raise ConnectionError("simulated 500")
            resp = MagicMock()
            resp.status_code = 200
            resp.content = _rss_xml("actualidad")
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("vigia.sources.codem.requests.get", fake_get)

        source = CODEMSource()
        items = source.fetch(date(2026, 4, 1))

        assert len(items) == 1
        assert items[0].extra["feed"] == "actualidad"
        # El error del feed roto debe haberse registrado en last_errors
        assert any("empleo" in err for err in source.last_errors)
