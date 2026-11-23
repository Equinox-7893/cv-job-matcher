"""Privacy step: remove personal details before scoring."""

from .redactor import REDACTOR_VERSION, RedactionResult, redact

__all__ = ["REDACTOR_VERSION", "RedactionResult", "redact"]
