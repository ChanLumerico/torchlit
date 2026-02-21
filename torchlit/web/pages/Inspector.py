from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Support running as Streamlit page script without package install.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torchlit.web.ui import apply_sidebar_brand


def render() -> None:
    apply_sidebar_brand()
    st.title("Inspector")
    st.info("Inspector page is planned for Phase 2 (manifest-based inference inspection).")


if __name__ == "__main__":
    render()
