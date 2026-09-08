"""Observability module for OTEL tracing and Phoenix integration."""

from .observability import is_phoenix_running, setup

__all__ = ["setup", "is_phoenix_running"]
