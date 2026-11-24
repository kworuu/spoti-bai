"""One place to read secrets, so BackEnd works both inside Streamlit and in plain scripts/tests.

Order: st.secrets (when running under `streamlit run`) -> environment variables -> .streamlit/secrets.toml
"""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"
_file_cache: dict | None = None


def _from_file() -> dict:
    global _file_cache
    if _file_cache is None:
        try:
            with open(SECRETS_FILE, "rb") as f:
                _file_cache = tomllib.load(f)
        except FileNotFoundError:
            _file_cache = {}
    return _file_cache


def _from_streamlit(name: str):
    try:
        from streamlit import runtime
        if not runtime.exists():          # plain `python` / pytest: skip st.secrets
            return None
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None


def get_secret(name: str, default=None):
    for value in (_from_streamlit(name), os.environ.get(name), _from_file().get(name)):
        if value not in (None, ""):
            return value
    return default