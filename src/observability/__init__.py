"""Observability module for OTEL tracing and Phoenix integration."""

from .observability import setup, is_phoenix_running

__all__ = ["setup", "is_phoenix_running"]
