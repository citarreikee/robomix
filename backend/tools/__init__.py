import importlib
from pathlib import Path

from .base import Tool
from .registry import register_tool, registry


for file in Path(__file__).parent.glob("*.py"):
    if file.stem.startswith("_") or file.stem in {"base", "registry"}:
        continue
    importlib.import_module(f".{file.stem}", package=__package__)


__all__ = ["Tool", "registry", "register_tool"]
