"""Presentation adapters. Renderers never discover or reclassify capabilities."""

from .human_html import (
    CanonicalIndexHtmlRenderer,
    HumanHtmlRenderer,
    render_index,
    render_report,
)

__all__ = [
    "CanonicalIndexHtmlRenderer",
    "HumanHtmlRenderer",
    "render_index",
    "render_report",
]
