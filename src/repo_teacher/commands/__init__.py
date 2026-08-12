"""Application command handlers.

The CLI parses arguments and composes these handlers with provider-specific
ports. Command modules own stage ordering, consistency and publication.
"""

from .inventory import InventoryCommandPorts, run_inventory
from .report import ReportCommandPorts, run_report

__all__ = [
    "InventoryCommandPorts",
    "ReportCommandPorts",
    "run_inventory",
    "run_report",
]
