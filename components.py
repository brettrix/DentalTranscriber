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


# ---------------------------------------------------------------- pinned audio player

# The page renders an ordinary st.audio for the recording. This script adds a bar pinned to the bottom of the
# window that drives that same <audio> element, and makes every link of the form #t=<seconds> (transcript
# timestamps, quotes on review cards) jump there and play. It installs itself once per browser tab and keeps
# itself in step with the page: when a page without a recording is shown, the bar goes away. If the script
# can't run, the ordinary player stays visible and nothing else breaks.
_PLAYER_JS = """
function fmt(t) {
  if (!isFinite(t) || t < 0) t = 0;
  const s = Math.floor(t), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const two = (n) => String(n).padStart(2, "0");
  return h ? h + ":" + two(m) + ":" + two(r) : two(m) + ":" + two(r);
}

function install() {
  if (window.__scribePlayer) return window.__scribePlayer;
  const P = { bar: null, dragging: false };
  const audio = () => document.querySelector(".st-key-scribe_audio audio");

  const style = document.createElement("style");
  style.textContent = `
    #scribe-player { position: fixed; bottom: 0; right: 0; z-index: 1000; display: none; align-items: center;
      gap: .6rem; padding: .55rem 1.2rem; box-sizing: border-box; border-top: 1px solid rgba(128,128,128,.35);
      font: 14px/1.2 "Source Sans Pro", "Source Sans", system-ui, sans-serif; box-shadow: 0 -2px 10px rgba(0,0,0,.08); }
    #scribe-player button { font: inherit; color: inherit; background: transparent; cursor: pointer;
      border: 1px solid rgba(128,128,128,.45); border-radius: .5rem; padding: .3rem .65rem; white-space: nowrap; }
    #scribe-player button:hover { border-color: #ff4b4b; color: #ff4b4b; }
    #scribe-player button.main { min-width: 4.6rem; font-weight: 600; }
    #scribe-player input[type=range] { flex: 1; min-width: 6rem; accent-color: #ff4b4b; cursor: pointer; }
    #scribe-player .time { font-variant-numeric: tabular-nums; white-space: nowrap; opacity: .85; }
    html.scribe-player-on .st-key-scribe_audio { position: absolute; width: 1px; height: 1px; overflow: hidden;
      opacity: 0; pointer-events: none; }
    html.scribe-player-on [data-testid="stMainBlockContainer"] { padding-bottom: 6rem; }
    a[href^="#t="] { text-decoration: none; font-variant-numeric: tabular-nums; cursor: pointer; }
    a[href^="#t="]:hover { text-decoration: underline; }
    .scribe-now { background: rgba(255, 196, 0, .22); border-radius: .25rem; }
  `;
  document.head.appendChild(style);

  const bar = document.createElement("div");
  bar.id = "scribe-player";
  bar.setAttribute("role", "region");
  bar.setAttribute("aria-label", "Visit recording");
  bar.innerHTML = `
    <button type="button" data-act="back" title="Back 10 seconds" aria-label="Back 10 seconds">&#8722;10s</button>
    <button type="button" data-act="toggle" class="main" aria-label="Play">Play</button>
    <button type="button" data-act="fwd" title="Forward 10 seconds" aria-label="Forward 10 seconds">+10s</button>
    <span class="time" data-part="now">00:00</span>
    <input type="range" min="0" max="1000" value="0" step="1" aria-label="Position in the recording">
    <span class="time" data-part="total">00:00</span>`;
  document.body.appendChild(bar);
  P.bar = bar;
  const range = bar.querySelector("input");
  const nowEl = bar.querySelector('[data-part="now"]');
  const totalEl = bar.querySelector('[data-part="total"]');
  const toggle = bar.querySelector('[data-act="toggle"]');

  P.seek = (seconds, play) => {
    const a = audio();
    if (!a) return;
    const go = () => {
      const max = isFinite(a.duration) ? Math.max(0, a.duration - 0.05) : seconds;
      a.currentTime = Math.max(0, Math.min(seconds, max));
      if (play) a.play().catch(() => {});
    };
    if (a.readyState >= 1) go();
    else { a.addEventListener("loadedmetadata", go, { once: true }); a.load(); }
  };

  bar.addEventListener("click", (ev) => {
    const act = ev.target.closest("button") && ev.target.closest("button").dataset.act;
    const a = audio();
    if (!act || !a) return;
    if (act === "toggle") { if (a.paused) a.play().catch(() => {}); else a.pause(); }
    if (act === "back") P.seek(a.currentTime - 10, !a.paused);
    if (act === "fwd") P.seek(a.currentTime + 10, !a.paused);
  });
  range.addEventListener("input", () => {
    P.dragging = true;
    const a = audio();
    if (a && isFinite(a.duration)) nowEl.textContent = fmt((range.value / 1000) * a.duration);
  });
  range.addEventListener("change", () => {
    const a = audio();
    if (a && isFinite(a.duration)) P.seek((range.value / 1000) * a.duration, !a.paused);
    P.dragging = false;
  });

  // Timestamps and quotes: any link to #t=<seconds> jumps the recording there and plays.
  document.addEventListener("click", (ev) => {
    const link = ev.target.closest && ev.target.closest('a[href^="#t="]');
    if (!link || !audio()) return;
    ev.preventDefault();
    ev.stopPropagation();
    const seconds = parseFloat(link.getAttribute("href").slice(3));
    if (isFinite(seconds)) P.seek(seconds, true);
  }, true);

  P.sync = () => {
    const a = audio();
    const on = !!a;
    document.documentElement.classList.toggle("scribe-player-on", on);
    bar.style.display = on ? "flex" : "none";
    if (!on) return;
    const main = document.querySelector('[data-testid="stMain"]') || document.body;
    const app = document.querySelector('[data-testid="stApp"]') || document.body;
    const css = getComputedStyle(app);
    bar.style.left = Math.max(0, main.getBoundingClientRect().left) + "px";
    bar.style.background = css.backgroundColor;
    bar.style.color = css.color;
    const total = isFinite(a.duration) ? a.duration : 0;
    totalEl.textContent = fmt(total);
    if (!P.dragging) {
      nowEl.textContent = fmt(a.currentTime);
      range.value = total ? Math.round((a.currentTime / total) * 1000) : 0;
    }
    const label = a.paused ? "Play" : "Pause";
    if (toggle.textContent !== label) { toggle.textContent = label; toggle.setAttribute("aria-label", label); }
    // Mark the line being spoken: the last timestamp at or before the current time.
    let current = null;
    document.querySelectorAll('[data-testid="stMain"] p > a[href^="#t="]').forEach((link) => {
      if (parseFloat(link.getAttribute("href").slice(3)) <= a.currentTime + 0.05) current = link;
    });
    const row = current && !a.paused ? current : null;
    document.querySelectorAll(".scribe-now").forEach((el) => { if (el !== row) el.classList.remove("scribe-now"); });
    if (row) row.classList.add("scribe-now");
  };
  setInterval(P.sync, 250);
  window.__scribePlayer = P;
  return P;
}

export default function () {
  install().sync();
}
"""
_player = st.components.v2.component("scribe_audio_player", js=_PLAYER_JS)


def audio_player(path, mime: str, key: str = "scribe_player") -> None:
    """The visit recording, with a player pinned to the bottom of the page (play/pause, scrub bar, current time,
    10 seconds back and forward). Links to `#t=<seconds>` anywhere on the page jump the recording there."""
    with st.container(key="scribe_audio"):
        st.audio(str(path), format=mime)
    _player(key=key)


def seek_link(seconds: float, label: str, title: str = "Play from here") -> str:
    """HTML for something that jumps the recording to `seconds` when clicked (label must already be escaped)."""
    return f'<a href="#t={seconds:.2f}" title="{title}">{label}</a>'
