"""Standalone HTML renderer adapter."""

from __future__ import annotations

from ..report import render_report as _render_report


class HumanHtmlRenderer:
    """Render a validated report model into one offline-readable HTML file."""

    def render(self, report: dict[str, object]) -> str:
        return _render_report(report, variant="human")


class CanonicalIndexHtmlRenderer:
    """Render a deterministic index without project-name or feature-source modes."""

    def render(self, report: dict[str, object]) -> str:
        return _render_report(report, variant="canonical")


def render_report(report: dict[str, object]) -> str:
    """Render the validated human-report schema."""

    return HumanHtmlRenderer().render(report)


def render_index(report: dict[str, object]) -> str:
    """Render the canonical static-index schema."""

    return CanonicalIndexHtmlRenderer().render(report)
