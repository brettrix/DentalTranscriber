"""Small custom page components (Streamlit v2 components: trusted, fixed JavaScript; visit data is passed as data)."""
from __future__ import annotations

import streamlit as st

_COPY_HTML = '<button type="button" class="copy"></button>'
_COPY_CSS = """
.copy { font: inherit; color: inherit; background: transparent; cursor: pointer; white-space: nowrap;
  border: 1px solid rgba(128, 128, 128, .45); border-radius: .5rem; padding: .36rem .8rem; min-height: 2.5rem; }
.copy:hover { border-color: #ff4b4b; color: #ff4b4b; }
.copy.done { border-color: #1f8a3b; color: #1f8a3b; }
"""
_COPY_JS = """
export default function (component) {
  const { parentElement, data } = component;
  const btn = parentElement.querySelector("button");
  btn.textContent = data.label;
  btn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(data.text);
    } catch (err) {  // older browsers, or a page that isn't served over https
      const ta = document.createElement("textarea");
      ta.value = data.text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    btn.textContent = "Copied \\u2713";
    btn.classList.add("done");
    setTimeout(() => { btn.textContent = data.label; btn.classList.remove("done"); }, 1800);
  };
}
"""
_copy = st.components.v2.component("scribe_copy_text", html=_COPY_HTML, css=_COPY_CSS, js=_COPY_JS)


def copy_button(text: str, key: str, label: str = "Copy as text") -> None:
    """One click copies `text` to the clipboard (for pasting into charting software)."""
    _copy(data={"text": text, "label": label}, key=key)
