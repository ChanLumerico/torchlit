from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Support `streamlit run .../torchlit/web/Home.py` without package install.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torchlit.web.ui import apply_sidebar_brand, load_text_asset


def main() -> None:
    st.set_page_config(page_title="TorchLit", layout="wide")
    apply_sidebar_brand()

    st.title("TorchLit")
    st.caption("Local visualization toolkit for PyTorch training and inspection")
    st.markdown(load_text_asset("home_intro.md"))


if __name__ == "__main__":
    main()
