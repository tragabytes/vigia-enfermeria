"""Base class for hash-watcher sources.

Tres fuentes emiten alertas por SNAPSHOT — descargan una URL fija,
extraen el cuerpo limpio, lo hashean, e incorporan ese hash al título
del RawItem como `[snapshot <hash>]`. Cuando el cuerpo cambia, cambia
el hash, cambia el título, cambia el `id_hash`, y `filter_new` trata
el item como nuevo. Cuando el cuerpo es idéntico, `filter_new` lo
descarta. Sin tabla de estado adicional — la dedup natural lo maneja.

Esta clase factoriza el patrón. Cada subclass declara su URL,
selectores de cuerpo, template de título, etiqueta de error, y opcionalmente
sobrescribe `extract_pub_date()` para usar una señal específica del
dominio (cascada de fechas en assets, regex "fecha publicación", etc.).

El GET HTTP, manejo de excepciones, y registro en `last_errors` viven
en cada subclass — no en la base. Esto es deliberado: los tests
existentes patchan `requests.get` en cada módulo subclass; centralizarlo
rompería esos patches sin aportar mucho. Lo que SÍ vive en la base es
la lógica post-GET: limpieza del HTML, hashing, construcción del título
y emisión del RawItem.

Coste mantenibilidad: cada subclass conserva ~8-10 líneas de boilerplate
HTTP, pero la lógica de hashing/título/fecha/empaquetado está en un
único sitio (~50 líneas) en lugar de duplicada tres veces.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

from vigia.sources._html import extract_clean_text
from vigia.sources.base import RawItem, Source


class HashWatcherSource(Source):
    """Plantilla para fuentes hash-watcher.

    Atributos de clase que cada subclass debe definir:

    - `url`: URL única que se vigila.
    - `title_template`: f-string con placeholder `{hash}`. P. ej.
      `"ISCIII Bolsa de empleo — Proceso Selectivo [snapshot {hash}]"`.
    - `error_label`: prefijo para los mensajes en `last_errors`. P. ej.
      `"ISCIII proceso-selectivo"`.
    - `body_selectors`: cascada de selectores CSS para `extract_clean_text`.
      P. ej. `("main", "#main-content", "body")`.
    - `noise_selectors` (opcional): selectores adicionales a descomponer
      antes del hashing. Útil cuando un menú custom (`.lfr-nav-item`) no
      lo cubren los `nav/header/footer/script/style` por defecto.
    - `probe_url`: por defecto se enlaza a `url` vía `__init_subclass__`,
      no hace falta declararlo en la subclase salvo que sea distinto.

    Método overridable:

    - `extract_pub_date(html, body_text) -> date`: devuelve la fecha de
      publicación. La subclase es responsable del fallback a
      `date.today()` (mantenido en su módulo para que los tests que
      patchean `<subclass_module>.date.today` sigan funcionando).
    """

    url: str = ""
    title_template: str = ""
    error_label: str = ""
    body_selectors: tuple = ("body",)
    noise_selectors: tuple = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Auto-enlaza probe_url a url si la subclase no lo ha redefinido.
        # Cubre el caso normal sin obligar a duplicar la constante.
        if not cls.__dict__.get("probe_url") and cls.url:
            cls.probe_url = cls.url

    def extract_pub_date(self, html: str, body_text: str) -> date:
        """Override en subclases. La subclase debe garantizar siempre
        una fecha (incluyendo `date.today()` como último recurso)."""
        return date.today()

    def _build_snapshot_raw_item(self, html: str) -> Optional[RawItem]:
        """Lógica post-GET compartida: limpia, hashea, construye el RawItem.

        Si el cuerpo queda vacío tras limpieza, registra `last_errors` y
        devuelve `None`. La subclase decide qué hacer con el `None`
        (típicamente devuelve `[]`).
        """
        body_text = extract_clean_text(
            html,
            target_selectors=self.body_selectors,
            extra_decompose=self.noise_selectors,
        )
        if not body_text.strip():
            msg = f"{self.error_label}: cuerpo principal vacío tras limpieza"
            self.logger.warning(msg)
            self.last_errors.append(msg)
            return None

        snapshot_hash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:10]
        title = self.title_template.format(hash=snapshot_hash)
        pub_date = self.extract_pub_date(html, body_text)

        return RawItem(
            source=self.name,
            url=self.url,
            title=title,
            date=pub_date,
            text=body_text,
        )
