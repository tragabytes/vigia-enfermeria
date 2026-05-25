"""
Tests del DetailWatcher genérico.

Cubre:
  1. Query "items vivos" del Storage filtra por deadline + excluded_sources
     + escoge el title más reciente cuando hay varios snapshots por URL.
  2. Seed mode implícito: primera vez que se ve una URL, guarda sin emitir.
  3. Cambio detectado: emite RawItem con source original y `[snapshot]`.
  4. Sin cambio: no emite.
  5. Build de title limpia `[snapshot XXX]` previo y trunca a 150 chars.
  6. HTTP error en una URL no detiene el resto, queda en last_errors.
  7. Body cap a 16 KB defensivo (test sintético con body grande).
  8. Source excluido no se procesa.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from vigia.storage import Item, Storage
from vigia.watchers.detail_watcher import (
    DetailWatcher,
    EXCLUDED_SOURCES,
    MAX_BODY_BYTES,
)


def _resp(html: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = html
    if status >= 400:
        r.raise_for_status = MagicMock(side_effect=Exception(f"HTTP {status}"))
    else:
        r.raise_for_status = lambda: None
    return r


def _persist_item(storage, **kw):
    """Crea, persiste y enriquece (sólo deadline) un item de test."""
    item = Item(
        source=kw.get("source", "canal_isabel_ii"),
        url=kw.get("url", "https://canal.example.com/x"),
        titulo=kw.get("titulo", "Proceso de prueba"),
        fecha=kw.get("fecha", date(2026, 4, 10)),
        categoria=kw.get("categoria", "oposicion"),
        first_seen_at=kw.get("first_seen_at"),
    )
    storage.save(item)
    deadline = kw.get("deadline_inscripcion")
    if deadline is not None:
        storage._conn.execute(
            "UPDATE items SET deadline_inscripcion = ? WHERE id_hash = ?",
            (deadline, item.id_hash),
        )
        storage._conn.commit()
    if "first_seen_at" in kw:
        # Re-escribimos first_seen_at (save() escribe el del dataclass al
        # insertar, que podría no coincidir con el del kw).
        storage._conn.execute(
            "UPDATE items SET first_seen_at = ? WHERE id_hash = ?",
            (kw["first_seen_at"].isoformat(), item.id_hash),
        )
        storage._conn.commit()
    return item


HTML_BASE = """
<html><body>
<header>cabecera</header>
<main>
  <h1>Convocatoria viva — Enfermería del Trabajo</h1>
  <p>Información del proceso, fechas, plazos, etc.</p>
</main>
<footer>pie</footer>
</body></html>
"""

HTML_MODIFICADO = """
<html><body>
<main>
  <h1>Convocatoria viva — Enfermería del Trabajo</h1>
  <p>NUEVO: Lista provisional de admitidos publicada.</p>
</main>
</body></html>
"""


# --------------------------------------------------------------------------
# Storage.iter_live_items_for_detail_watch
# --------------------------------------------------------------------------


class TestQueryItemsVivos:
    def test_excluye_sources_de_lista_negra(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="boe", url="https://boe.es/a",
                      deadline_inscripcion="2099-01-01")
        _persist_item(s, source="canal_isabel_ii", url="https://canal/x",
                      deadline_inscripcion="2099-01-01")
        rows = s.iter_live_items_for_detail_watch(
            excluded_sources={"boe", "bocm"},
        )
        urls = [r[1] for r in rows]
        s.close()
        assert "https://canal/x" in urls
        assert "https://boe.es/a" not in urls

    def test_deadline_pasado_excluido(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="ciemat", url="https://ciemat/old",
                      deadline_inscripcion="2020-01-01")
        _persist_item(s, source="ciemat", url="https://ciemat/new",
                      deadline_inscripcion="2099-01-01")
        rows = s.iter_live_items_for_detail_watch(
            excluded_sources=set(), today=date(2026, 5, 25),
        )
        urls = [r[1] for r in rows]
        s.close()
        assert "https://ciemat/new" in urls
        assert "https://ciemat/old" not in urls

    def test_sin_deadline_y_first_seen_reciente_incluido(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="ciemat", url="https://ciemat/sin_deadline_reciente",
                      first_seen_at=datetime(2026, 5, 20, 10, 0))
        rows = s.iter_live_items_for_detail_watch(
            excluded_sources=set(),
            days_without_deadline=90,
            today=date(2026, 5, 25),
        )
        urls = [r[1] for r in rows]
        s.close()
        assert "https://ciemat/sin_deadline_reciente" in urls

    def test_sin_deadline_y_first_seen_antiguo_excluido(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="ciemat", url="https://ciemat/antiguo",
                      first_seen_at=datetime(2025, 1, 1, 10, 0))
        rows = s.iter_live_items_for_detail_watch(
            excluded_sources=set(),
            days_without_deadline=90,
            today=date(2026, 5, 25),
        )
        urls = [r[1] for r in rows]
        s.close()
        assert "https://ciemat/antiguo" not in urls

    def test_url_duplicada_devuelve_titulo_mas_reciente(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        url = "https://canal/mismo"
        _persist_item(s, source="canal_isabel_ii", url=url,
                      titulo="Snapshot viejo",
                      first_seen_at=datetime(2026, 5, 1, 10, 0),
                      deadline_inscripcion="2099-01-01")
        _persist_item(s, source="canal_isabel_ii", url=url,
                      titulo="Snapshot nuevo",
                      first_seen_at=datetime(2026, 5, 20, 10, 0),
                      deadline_inscripcion="2099-01-01")
        rows = s.iter_live_items_for_detail_watch(
            excluded_sources=set(), today=date(2026, 5, 25),
        )
        s.close()
        # Una sola fila para la URL, con el título más reciente
        assert len(rows) == 1
        assert rows[0][2] == "Snapshot nuevo"


# --------------------------------------------------------------------------
# DetailWatcher.run + _process_one
# --------------------------------------------------------------------------

class TestDetailWatcher:
    def test_seed_implicito_primera_vez_no_emite_pero_persiste(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="canal_isabel_ii",
                      url="https://canal/seed",
                      titulo="Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        dw = DetailWatcher(s, excluded_sources=frozenset())
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(HTML_BASE),
        ):
            raws = dw.run()
        snap = s.get_detail_snapshot("https://canal/seed")
        s.close()
        assert raws == []  # seed: no emite
        assert snap is not None
        assert len(snap[0]) == 10  # hash sha1[:10]

    def test_cambio_detectado_emite_raw_item_con_source_original(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="canal_isabel_ii",
                      url="https://canal/change",
                      titulo="Convocatoria Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        # Primera pasada: seed (no emite)
        dw = DetailWatcher(s, excluded_sources=frozenset())
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(HTML_BASE),
        ):
            dw.run()
        # Segunda pasada con HTML modificado: emite snapshot
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(HTML_MODIFICADO),
        ):
            raws = dw.run()
        s.close()
        assert len(raws) == 1
        raw = raws[0]
        assert raw.source == "canal_isabel_ii"  # source ORIGINAL
        assert raw.url == "https://canal/change"
        assert "[snapshot " in raw.title
        assert "Convocatoria Enfermería del Trabajo" in raw.title
        assert raw.extra.get("detected_by") == "detail_watcher"
        assert raw.extra.get("previous_hash")  # truthy

    def test_sin_cambio_no_emite(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="canal_isabel_ii",
                      url="https://canal/same",
                      titulo="Algo Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        dw = DetailWatcher(s, excluded_sources=frozenset())
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(HTML_BASE),
        ):
            dw.run()  # seed
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(HTML_BASE),
        ):
            raws = dw.run()  # idéntico
        s.close()
        assert raws == []

    def test_http_error_no_detiene_y_queda_en_last_errors(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="canal_isabel_ii",
                      url="https://canal/ok",
                      titulo="OK Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        _persist_item(s, source="ciemat",
                      url="https://ciemat/down",
                      titulo="Down Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")

        def fake_get(url, **kw):
            if "down" in url:
                return _resp("", status=500)
            return _resp(HTML_BASE)

        dw = DetailWatcher(s, excluded_sources=frozenset())
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            side_effect=fake_get,
        ):
            dw.run()  # seed
            # Cambiamos HTML para el de OK, dejamos roto el otro
            def fake_get_2(url, **kw):
                if "down" in url:
                    return _resp("", status=500)
                return _resp(HTML_MODIFICADO)
            with patch(
                "vigia.watchers.detail_watcher.requests.get",
                side_effect=fake_get_2,
            ):
                raws = dw.run()
        s.close()
        # El URL OK genera snapshot pese al fallo del down
        urls_emitidas = [r.url for r in raws]
        assert "https://canal/ok" in urls_emitidas
        assert any("down" in e for e in dw.last_errors)

    def test_excluded_sources_no_se_consultan(self, tmp_path):
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="boe", url="https://boe.es/a",
                      titulo="BOE Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        # BOE está en EXCLUDED_SOURCES por defecto
        dw = DetailWatcher(s)
        # patcheamos requests.get para detectar si se invoca
        with patch(
            "vigia.watchers.detail_watcher.requests.get"
        ) as mock_get:
            dw.run()
        s.close()
        assert mock_get.call_count == 0

    def test_body_grande_se_trunca_a_max_body_bytes(self, tmp_path):
        """Body > 16 KB se trunca defensivamente al persistir."""
        s = Storage(db_path=tmp_path / "seen.db")
        _persist_item(s, source="canal_isabel_ii",
                      url="https://canal/big",
                      titulo="Big Enfermería del Trabajo",
                      deadline_inscripcion="2099-01-01")
        # 50 KB de texto repetido dentro de <main>
        big_html = f"<html><body><main>{'A' * 50_000}</main></body></html>"
        dw = DetailWatcher(s, excluded_sources=frozenset())
        with patch(
            "vigia.watchers.detail_watcher.requests.get",
            return_value=_resp(big_html),
        ):
            dw.run()  # seed con body truncado
        snap = s.get_detail_snapshot("https://canal/big")
        s.close()
        assert snap is not None
        assert len(snap[1].encode("utf-8")) <= MAX_BODY_BYTES

    def test_titulo_largo_se_trunca_a_150_chars(self):
        long_title = "X" * 300
        result = DetailWatcher._build_snapshot_title(long_title, "abc1234567")
        assert len(result) <= 150 + len(" [snapshot abc1234567]") + 2
        assert result.endswith("[snapshot abc1234567]")

    def test_titulo_con_snapshot_previo_se_limpia(self):
        original = "Convocatoria X [snapshot abcd123456]"
        result = DetailWatcher._build_snapshot_title(original, "newhash999")
        assert "[snapshot abcd123456]" not in result
        assert result == "Convocatoria X [snapshot newhash999]"
