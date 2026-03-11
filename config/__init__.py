"""Configuration package.

This package groups small helper files that read environment settings and build
clients for services like the LLM, email provider, proxy provider, and database.
Other parts of the codebase import from this package instead of hardcoding
service setup in many places.
"""
