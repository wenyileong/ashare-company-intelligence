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
migrations = collect_data_files("ashare", subdir="migrations", include_py_files=True)
# v2.1: the offline topology viewer's page, script, style sheet and bundled libraries (with their licences)
viewer = collect_data_files("ashare", subdir="viz/viewer")
# v2.1: the interface catalogues (English and Simplified Chinese)
viewer += collect_data_files("ashare", subdir="i18n")
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
