"""v2.0.4: THIRD_PARTY_NOTICES.txt lists what the build bundled, with full licence texts."""
import importlib.util
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("third_party_notices", ROOT / "packaging" / "third_party_notices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_build(tmp_path, files):
    build = tmp_path / "build"
    build.mkdir()
    (build / "PYZ-00.toc").write_text(repr(("x.pyz", [(f"m{i}", str(f), "PYMODULE") for i, f in enumerate(files)])),
                                      encoding="utf-8")
    (build / "COLLECT-00.toc").write_text(repr(([("x.exe", str(build / "x.exe"), "EXECUTABLE")],)), encoding="utf-8")
    return build


def test_notices_cover_bundled_distributions_and_python(tmp_path):
    mod = _load()
    httpx = metadata.distribution("httpx")
    httpx_file = next(Path(httpx.locate_file(f)) for f in httpx.files if str(f).endswith("__init__.py"))
    stdlib_file = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "json" \
        / "__init__.py"
    if not stdlib_file.exists():
        stdlib_file = Path(metadata.__file__)
    build = _fake_build(tmp_path, [httpx_file, stdlib_file])
    out = tmp_path / "THIRD_PARTY_NOTICES.txt"
    inc = ROOT / "packaging" / "notices" / f"python-{sys.version_info.major}.{sys.version_info.minor}-incorporated.txt"
    code = mod.main(str(build), str(out))
    if not inc.exists() and str(stdlib_file).startswith(sys.base_prefix):
        assert code == 1                                     # a Python version without its notices stops the build
        return
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert f"httpx {httpx.version}" in text and "BSD" in text
    assert "Bundled components keep their own licences" in text
    assert "ashare" not in text.split("Generated from the build")[1].split("=" * 78)[0]


def test_missing_licence_text_stops_the_build(tmp_path, monkeypatch):
    mod = _load()
    httpx = metadata.distribution("httpx")
    httpx_file = next(Path(httpx.locate_file(f)) for f in httpx.files if str(f).endswith("__init__.py"))
    build = _fake_build(tmp_path, [httpx_file])
    monkeypatch.setattr(mod, "licence_texts", lambda dist: [])
    assert mod.main(str(build), str(tmp_path / "n.txt")) == 1
    assert not (tmp_path / "n.txt").exists()


def test_python_312_incorporated_notices_are_present():
    text = (ROOT / "packaging" / "notices" / "python-3.12-incorporated.txt").read_text(encoding="utf-8")
    for name in ("OpenSSL", "Apache License", "expat", "libffi", "zlib", "libmpdec"):
        assert name in text


def test_licence_is_polyform_strict_unchanged():
    """LICENSE.md: licensor line, then the PolyForm Strict License 1.0.0 exactly as published."""
    import hashlib
    text = (ROOT / "LICENSE.md").read_text(encoding="utf-8")
    head, _, body = text.partition("---\n\n")
    assert "Licensor: Leong, Wen Yi" in head and "THIRD_PARTY_NOTICES.txt" in head
    assert body.startswith("# PolyForm Strict License 1.0.0")
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == "9eb48619fbc193ab7bb327b090cfcc703000265b83e670f81f231d0b1c43c56e"
    assert "license: PolyForm-Strict-1.0.0" in (ROOT / "CITATION.cff").read_text(encoding="utf-8")
