"""Hosted public-demo scaffolding (deploy only).

Not part of a real court deployment — these modules let the single public demo
give every browser session its own isolated, seeded sandbox. Gated behind
settings.demo_isolated_sessions so they never affect the core app or its tests.
"""
