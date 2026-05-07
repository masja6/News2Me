"""AI Brief source adapters.

Each adapter exposes a ``fetch_*() -> list[Article]`` function that the
pipeline dispatcher calls alongside the existing RSS fetcher.
"""
