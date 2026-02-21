import streamlit as st

from torchlit.web.pages.inspector import render as render_inspector
from torchlit.web.pages.training import render as render_training


def main() -> None:
    st.set_page_config(page_title="Torchlit", layout="wide")

    st.sidebar.title("Torchlit")
    page = st.sidebar.radio("Page", options=["Training", "Inspector"], index=0)

    if page == "Training":
        render_training()
    else:
        render_inspector()


if __name__ == "__main__":
    main()
