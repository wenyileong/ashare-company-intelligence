# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build specification.
#
# Produces one folder, dist/AShareScraper/, containing two executables that
# share the same runtime:
#   AShareScraper.exe  - desktop interface (no console window)
#   ashare-cli.exe     - command line (console)
#
# Build on the target operating system (PyInstaller does not cross-compile):
#   pyinstaller --noconfirm --clean packaging/ashare.spec
import os
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
# v2.2.0: make the package importable for the hooks below even when it is not installed (GitHub's runners), and
# collect its data files from the source tree, so the build does not depend on how PyInstaller finds the package.
import sys
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _package_files(sub, include_py_files=False):
    base = os.path.join(ROOT, "ashare", *sub.split("/"))
    out = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith((".pyc", ".pyo")) or (name.endswith(".py") and not include_py_files):
                continue
            src = os.path.join(folder, name)
            out.append((src, os.path.dirname(os.path.relpath(src, ROOT))))
    if not out:
        raise SystemExit(f"no files found under {base}")
    return out
ICON = os.path.join(SPECPATH, "ashare.ico")
icon = ICON if os.path.exists(ICON) else None

hidden = (
    collect_submodules("ashare")
    + collect_submodules("rich")          # rich loads unicode tables lazily
    + ["sqlalchemy.dialects.sqlite", "lxml.etree", "lxml._elementpath"]
    + collect_submodules("pypdfium2") + collect_submodules("pypdfium2_raw")
)
# v1.5: pdfium renders source pages on the Review page and gives character
# positions to the layout-aware table extractor.
pdfium_bins = collect_dynamic_libs("pypdfium2_raw")
pdfium_data = collect_data_files("pypdfium2_raw") + collect_data_files("pypdfium2")
# v2.0: Alembic loads the migration scripts from files, so they ship as source.
migrations = _package_files("migrations", include_py_files=True)
# v2.1: the offline topology viewer's page, script, style sheet and bundled libraries (with their licences)
viewer = _package_files("viz/viewer")
# v2.1: the interface catalogues (English and Simplified Chinese)
viewer += _package_files("i18n")
hidden += collect_submodules("alembic", filter=lambda n: not n.startswith("alembic.testing")) + ["mako.template"]

# Size: rich needs pygments only for the Python lexer (help formatting).
# Excluding the rest keeps the download small. (v2.0: the SQLAlchemy
# dialects stay, because Alembic imports its DDL implementations for all of
# them; the database drivers other than sqlite3 are not bundled.)
import pkgutil
import pygments.lexers as _lexers
unused = [
    "sqlalchemy.testing", "alembic.testing",
    "pydoc_data", "unittest", "setuptools", "pkg_resources",
] + ["pygments.lexers." + m.name for m in pkgutil.iter_modules(_lexers.__path__)
     if m.name not in ("_mapping", "python")]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=pdfium_bins,
    datas=pdfium_data + migrations + viewer,
    hiddenimports=hidden,
    excludes=["pandas", "numpy", "matplotlib", "pytest", "reportlab", "IPython", "PIL"] + unused,
    noarchive=False,
)
# Tcl's time-zone database and clock translations are used only by Tcl's
# own clock command, which the interface does not use.
a.datas = [d for d in a.datas
           if not any(part in d[0].replace("\\", "/") for part in ("_tcl_data/tzdata/", "_tcl_data/msgs/"))]
pyz = PYZ(a.pure)

gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AShareScraper",
    console=False,
    icon=icon,
    upx=False,
)
cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ashare-cli",
    console=True,
    icon=icon,
    upx=False,
)
coll = COLLECT(gui, cli, a.binaries, a.datas, name="AShareScraper", upx=False)
