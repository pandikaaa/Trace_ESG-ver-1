"""Tiruan (fake) minimal modul `streamlit` untuk uji asap (smoke test) app.py TANPA Streamlit terpasang.

Yang diuji: seluruh jalur kode halaman berjalan tanpa exception Python terhadap data nyata.
Yang TIDAK diuji: tampilan visual, kompatibilitas versi API Streamlit, interaksi browser.
Untuk pengujian UI sebenarnya gunakan `streamlit run app.py` atau `streamlit.testing.v1.AppTest`.
"""
from __future__ import annotations

import types


class _Stop(BaseException):
    pass


class _Rerun(BaseException):
    pass


class _Dict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class _Ctx:
    def __init__(self, mod):
        self._m = mod

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._m, name)

    def __bool__(self):
        return True


def make_streamlit(page: str, submit_labels=(), button_labels=(), session=None, uploads=None):
    m = types.ModuleType("streamlit")
    m.session_state = session if session is not None else _Dict()
    m.calls = []

    def rec(name):
        def f(*a, **k):
            m.calls.append((name, a, k))
        return f

    for n in ["set_page_config", "markdown", "title", "caption", "info", "warning", "error", "success", "subheader",
              "write", "dataframe", "bar_chart", "metric", "divider", "code", "header", "table", "line_chart"]:
        setattr(m, n, rec(n))

    def columns(spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(m) for _ in range(n)]
    m.columns = columns
    m.tabs = lambda labels: [_Ctx(m) for _ in labels]
    m.expander = lambda *a, **k: _Ctx(m)
    m.container = lambda *a, **k: _Ctx(m)
    m.form = lambda *a, **k: _Ctx(m)
    m.spinner = lambda *a, **k: _Ctx(m)
    pending = {"submit": set(submit_labels), "button": set(button_labels)}

    def _once(kind):  # tombol hanya "ditekan" pada eksekusi pertama, seperti klik sungguhan
        def f(label="", **k):
            if label in pending[kind]:
                pending[kind].discard(label)
                return True
            return False
        return f
    m.form_submit_button = _once("submit")
    m.button = _once("button")
    m.download_button = lambda label="", data=None, **k: m.calls.append(("download", label, len(data or b"")))
    uploads = uploads or {}

    def file_uploader(label, *a, **k):
        for prefix, obj in uploads.items():
            if label.startswith(prefix):
                return obj
        return None
    m.file_uploader = file_uploader
    m.text_input = lambda label, value="", **k: value
    m.number_input = lambda label, min_value=None, max_value=None, value=0, step=None, **k: value
    m.checkbox = lambda label, value=False, **k: value
    m.date_input = lambda label, value=None, **k: value
    m.multiselect = lambda label, options, default=None, **k: list(default if default is not None else [])
    m.selectbox = lambda label, options, index=0, **k: list(options)[index]
    m.radio = lambda label, options, key=None, **k: page

    def stop():
        raise _Stop()

    def rerun():
        raise _Rerun()
    m.stop, m.rerun = stop, rerun
    m.sidebar = _Ctx(m)
    m.column_config = types.SimpleNamespace(NumberColumn=lambda *a, **k: {"fmt": k.get("format")})
    return m


class FakeUpload(__import__("io").BytesIO):
    """Mirip UploadedFile Streamlit: dapat di-read(), punya name, size, getvalue()."""

    def __init__(self, name: str, data: bytes):
        super().__init__(data)
        self.name, self.size = name, len(data)
