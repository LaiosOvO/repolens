"""Load packaged agent role contracts used by pipeline stages."""

from .catalog import AgentSpec, load_agent_spec

__all__ = ["AgentSpec", "load_agent_spec"]
