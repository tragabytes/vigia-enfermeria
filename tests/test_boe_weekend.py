"""
Regresión del bug detectado el 2026-05-24 durante el backfill EGOA: BOE
source descartaba sábados además de domingos, perdiendo silenciosamente
publicaciones reales como BOE-A-2025-26156 (convocatoria EGOA Sanidad y
Consumo del Ministerio de Sanidad, publicada el sábado 20/12/2025).

El comentario original decía "no hay BOE los sábados y domingos normalmente"
pero esto solo es cierto para los domingos: BOE publica de lunes a sábado
según el Real Decreto 181/2008.
"""
from __future__ import annotations

from datetime import date

import pytest

from vigia.sources import boe
from vigia.sources.boe import BOESource


class _FakeDateFactory:
    """Factory que produce una subclass de `date` con `today()` fijado.

    boe.py importa `date` a nivel de módulo; monkeypatching `boe.date` con
    una subclass que override `today()` permite controlar el rango de
    iteración en el test sin tocar el reloj del sistema.
    """
    @staticmethod
    def fixed(today: date):
        class _FixedDate(date):
            @classmethod
            def today(cls):  # type: ignore[override]
                return today
        return _FixedDate


class TestBOEWeekend:
    def _setup_capture(self, monkeypatch):
        """Reemplaza `_fetch_day` para capturar qué fechas se consultarían
        y devuelve la lista de targets vistos."""
        seen: list[date] = []

        def fake_fetch_day(self, target):
            seen.append(target)
            return []

        monkeypatch.setattr(BOESource, "_fetch_day", fake_fetch_day)
        return seen

    def test_sabado_se_procesa_no_se_descarta(self, monkeypatch):
        """20/12/2025 fue sábado y BOE publicó la convocatoria EGOA. El
        parser DEBE consultarlo (no descartarlo por weekday)."""
        seen = self._setup_capture(monkeypatch)
        monkeypatch.setattr(
            boe, "date", _FakeDateFactory.fixed(date(2025, 12, 20)),
        )

        BOESource().fetch(since_date=date(2025, 12, 20))
        assert seen == [date(2025, 12, 20)]

    def test_domingo_si_se_descarta(self, monkeypatch):
        """21/12/2025 fue domingo. BOE no publica domingos — sí debe
        saltarse para no gastar requests inútiles."""
        seen = self._setup_capture(monkeypatch)
        monkeypatch.setattr(
            boe, "date", _FakeDateFactory.fixed(date(2025, 12, 21)),
        )

        BOESource().fetch(since_date=date(2025, 12, 21))
        assert seen == []  # domingo descartado

    def test_rango_sabado_y_domingo_solo_sabado_se_consulta(self, monkeypatch):
        """Sábado 20/12 + domingo 21/12: solo el sábado entra."""
        seen = self._setup_capture(monkeypatch)
        monkeypatch.setattr(
            boe, "date", _FakeDateFactory.fixed(date(2025, 12, 21)),
        )

        BOESource().fetch(since_date=date(2025, 12, 20))
        assert seen == [date(2025, 12, 20)]

    def test_semana_completa_lunes_sabado_todos_se_consultan(self, monkeypatch):
        """Lunes 15 a sábado 20 de diciembre 2025: los 6 días se consultan."""
        seen = self._setup_capture(monkeypatch)
        monkeypatch.setattr(
            boe, "date", _FakeDateFactory.fixed(date(2025, 12, 20)),
        )

        BOESource().fetch(since_date=date(2025, 12, 15))
        assert seen == [date(2025, 12, d) for d in range(15, 21)]
