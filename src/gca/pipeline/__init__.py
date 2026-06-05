import importlib

from . import cache, normalize, runs

__all__ = ["runs", "normalize", "cache", "feature_extractor", "embedder"]

# embedder (sentence-transformers) and feature_extractor (openai) pull heavy
# deps not bundled in the API lambda; import them lazily so the API can use
# normalize without them.
_LAZY = ("embedder", "feature_extractor")


def __getattr__(name: str):
    if name in _LAZY:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
