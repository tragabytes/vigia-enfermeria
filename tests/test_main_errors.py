"""
Tests para la propagación de errores no bloqueantes desde las fuentes
hasta el notifier (bug #1 del BACKLOG).

Antes de este fix, una fuente que capturaba un HTTP 4xx/5xx con
`logger.warning(...)` no llegaba al notifier y el run quedaba "silencioso":
sin novedades y sin aviso de la caída. Ahora cada fuente acumula sus
errores en `self.last_errors` y main.py los recoge y los pasa al notifier.
"""
from __future__ import annotations

from datetime import date

import pytest

from vigia.sources.base import RawItem, Source


class _OkSource(Source):
    """Fuente que devuelve 1 ítem sin errores."""
    name = "ok_source"

    def fetch(self, since_date: date) -> list[RawItem]:
        return [
            RawItem(
                source=self.name,
                url="http://example.com/1",
                title="convocatoria enfermería del trabajo prueba",
                date=date.today(),
                text="",
            )
        ]


class _FailingSource(Source):
    """Fuente que captura un fallo internamente y lo registra en last_errors."""
    name = "failing_source"

    def fetch(self, since_date: date) -> list[RawItem]:
        # Simulamos un fallo HTTP capturado dentro de la fuente.
        try:
            raise ConnectionError("simulated 403 Forbidden")
        except Exception as exc:
            self.last_errors.append(str(exc))
        return []


class _MultipleFailureSource(Source):
    """Fuente que falla múltiples veces (p.ej. BOE iterando varios días)."""
    name = "multi_fail"

    def fetch(self, since_date: date) -> list[RawItem]:
        for day in ["2026-04-22", "2026-04-23", "2026-04-24"]:
            self.last_errors.append(f"{day}: 404 Not Found")
        return []


# ---------------------------------------------------------------------------
# Tests del comportamiento de Source.last_errors
# ---------------------------------------------------------------------------

class TestSourceErrors:
    def test_source_inicializa_last_errors_vacio(self):
        s = _OkSource()
        assert s.last_errors == []

    def test_source_acumula_errores_durante_fetch(self):
        s = _FailingSource()
        items = s.fetch(date.today())
        assert items == []
        assert s.last_errors == ["simulated 403 Forbidden"]

    def test_source_puede_acumular_varios_errores(self):
        s = _MultipleFailureSource()
        s.fetch(date.today())
        assert len(s.last_errors) == 3
        assert all("404" in e for e in s.last_errors)

    def test_dos_instancias_no_comparten_estado(self):
        """Sanity check: last_errors es de instancia, no de clase."""
        a = _FailingSource()
        b = _FailingSource()
        a.fetch(date.today())
        assert a.last_errors == ["simulated 403 Forbidden"]
        assert b.last_errors == []


# ---------------------------------------------------------------------------
# Tests de _run_source y la integración con main()
# ---------------------------------------------------------------------------

class TestRunSourceTuple:
    def test_run_source_devuelve_tres_elementos(self):
        from vigia.main import _run_source
        name, items, errors = _run_source(_OkSource, date.today())
        assert name == "ok_source"
        assert len(items) == 1
        assert errors == []

    def test_run_source_propaga_errores_de_fetch(self):
        from vigia.main import _run_source
        name, items, errors = _run_source(_FailingSource, date.today())
        assert name == "failing_source"
        assert items == []
        assert errors == ["simulated 403 Forbidden"]

    def test_run_source_devuelve_lista_independiente(self):
        """La lista devuelta debe ser una copia, no referencia al objeto."""
        from vigia.main import _run_source
        _, _, errors = _run_source(_FailingSource, date.today())
        errors.append("modificación externa")
        # Una nueva instancia debería seguir sin errores externos.
        from vigia.sources.base import Source
        assert "modificación externa" not in _FailingSource().last_errors


class TestMainPropagaErrores:
    def test_pipeline_envia_telegram_con_errores_aunque_no_haya_novedades(
        self, monkeypatch, tmp_path
    ):
        """
        Con 0 matches pero con errores en una fuente, el notifier DEBE
        ser invocado (antes del fix se omitía el envío).
        """
        from vigia import main as main_module

        # Registry mock con una fuente que falla
        monkeypatch.setattr(
            main_module, "SOURCE_REGISTRY", {"failing_source": _FailingSource}
        )
        monkeypatch.setattr(main_module, "SOURCES_ENABLED", ["failing_source"])

        # BD temporal para no contaminar state/seen.db real
        from vigia import storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "seen.db")
        # Dashboard temporal para no escribir en docs/data/ del repo
        monkeypatch.setattr(
            main_module, "DASHBOARD_OUT_DIR", str(tmp_path / "dashboard"),
        )

        # Capturamos lo que llega al notifier
        capturado = {}

        def fake_send(items, errors, run_date=None):
            capturado["items"] = items
            capturado["errors"] = errors

        monkeypatch.setattr(main_module, "send", fake_send)

        # Argumentos vacíos → comportamiento por defecto
        monkeypatch.setattr("sys.argv", ["main.py"])

        main_module.main()

        # Debe haberse llamado al notifier con el error de la fuente
        assert capturado.get("items") == []
        assert capturado.get("errors") == [
            ("failing_source", "simulated 403 Forbidden")
        ]

    def test_pipeline_no_envia_telegram_si_todo_va_bien_y_sin_novedades(
        self, monkeypatch, tmp_path
    ):
        """
        Caso normal: 0 matches y 0 errores → silencio, sin spam diario.
        """
        from vigia import main as main_module

        class _SilentSource(Source):
            name = "silent"
            def fetch(self, since_date):
                return []

        monkeypatch.setattr(
            main_module, "SOURCE_REGISTRY", {"silent": _SilentSource}
        )
        monkeypatch.setattr(main_module, "SOURCES_ENABLED", ["silent"])

        from vigia import storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "seen.db")
        monkeypatch.setattr(
            main_module, "DASHBOARD_OUT_DIR", str(tmp_path / "dashboard"),
        )

        llamadas = []

        def fake_send(items, errors, run_date=None):
            llamadas.append((items, errors))

        monkeypatch.setattr(main_module, "send", fake_send)
        monkeypatch.setattr("sys.argv", ["main.py"])

        main_module.main()

        assert llamadas == []  # nadie ha llamado al notifier
