"""Keep PyGWalker initialization safe across Streamlit sessions."""

from threading import Lock

from pygwalker.api.streamlit import StreamlitRenderer

# PyGWalker 0.5 uses DuckDB's shared default connection for field metadata.
# Concurrent register/query calls can deadlock while holding Python's GIL,
# freezing every Streamlit session, even those displaying another tab.
_renderer_lock = Lock()


def render_interactive(df):
    with _renderer_lock:
        # Browser-side calculations avoid subsequent shared-connection queries
        # from asynchronous PyGWalker callbacks outside this lock.
        renderer = StreamlitRenderer(df, kernel_computation=False)
        renderer.explorer()
