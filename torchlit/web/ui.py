from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=32)
def load_text_asset(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8").strip()


def apply_sidebar_brand() -> None:
    css = load_text_asset("sidebar_brand.css")
    st.markdown(
        f"<style>\n{css}\n</style>",
        unsafe_allow_html=True,
    )
