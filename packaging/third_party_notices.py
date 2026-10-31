"""Write THIRD_PARTY_NOTICES.txt for the Windows build.

    python packaging/third_party_notices.py BUILD_DIR OUT_FILE

BUILD_DIR is PyInstaller's work folder for the spec (``build/ashare``). The
script reads the tables of contents PyInstaller wrote there (PYZ-00.toc and
COLLECT-00.toc), so the notices list exactly the components that were
bundled, maps every bundled file to the installed distribution it came from,
and copies each distribution's licence files. It must run with the Python
that ran PyInstaller, so that the versions match the build.

Also included: the licence of the Python runtime itself (which covers the
software it incorporates), the Tcl/Tk licence when Tk is bundled, the
PyInstaller bootloader licence, and a note on the Microsoft Visual C++
runtime. The script exits with an error if a bundled distribution ships no
licence text and none is supplied in EXTRA_TEXTS, so that a build never goes
out with a notice missing.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from importlib import metadata
from pathlib import Path

# A licence file: one named LICENSE/LICENCE/COPYING/NOTICE/COPYRIGHT anywhere, or any file in a
# distribution's licence folder (PEP 639 ``.dist-info/licenses/``, or a LICENSES/ folder).
LICENCE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)[^/]*$|\.dist-info/licen[cs]es/|(^|/)LICEN[CS]ES/",
                          re.I)
SKIP_FILE = re.compile(r"\.(py|pyc|pyi|so|pyd|dll)$", re.I)
OWN_PACKAGES = {"ashare"}
# Distributions that ship no licence file of their own; their licence text is supplied here.
EXTRA_TEXTS: dict[str, str] = {}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def _toc(path: Path):
    return ast.literal_eval(path.read_text(encoding="utf-8"))


def bundled_sources(build_dir: Path) -> list[str]:
    srcs: list[str] = []
    pyz = _toc(build_dir / "PYZ-00.toc")
    srcs += [e[1] for e in pyz[1] if e[1]]
    collect = _toc(build_dir / "COLLECT-00.toc")
    entries = collect[0] if isinstance(collect, tuple) else collect
    srcs += [e[1] for e in entries if isinstance(e, tuple) and len(e) >= 2 and e[1]]
    return srcs


def file_owners() -> dict[str, metadata.Distribution]:
    owners: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        for f in dist.files or []:
            try:
                owners[_norm(str(dist.locate_file(f)))] = dist
            except Exception:
                continue
    return owners


def licence_of(dist: metadata.Distribution) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic + (f" ({', '.join(classifiers)})" if classifiers and lic not in classifiers else "")
    return ", ".join(classifiers) or (lic.splitlines()[0][:80] if lic else "see licence text")


def licence_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in dist.files or []:
        name = str(f).replace("\\", "/")
        if LICENCE_FILE.search(name) and not SKIP_FILE.search(name):
            try:
                out.append((name, Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return out


def homepage(dist: metadata.Distribution) -> str:
    md = dist.metadata
    if md.get("Home-page"):
        return md["Home-page"]
    for url in md.get_all("Project-URL") or []:
        label, _, link = url.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return link.strip()
    return ""


def main(build_dir: str, out_file: str) -> int:
    build = Path(build_dir)
    owners = file_owners()
    base = _norm(sys.base_prefix)
    dists: dict[str, metadata.Distribution] = {}
    python_runtime = tk = False
    for src in bundled_sources(build):
        key = _norm(src)
        dist = owners.get(key)
        if dist is not None:
            name = dist.metadata["Name"]
            if name.lower() not in OWN_PACKAGES:
                dists[name.lower()] = dist
        elif key.startswith(base):
            python_runtime = True
            if "tcl" in key.lower() or "tk" in Path(key).name.lower():
                tk = True
    missing = []
    parts = []
    summary = []
    for _, dist in sorted(dists.items()):
        name, version = dist.metadata["Name"], dist.version
        lic = licence_of(dist)
        summary.append(f"  {name} {version}  ({lic})")
        texts = licence_texts(dist) or ([("supplied", EXTRA_TEXTS[name.lower()])] if name.lower() in EXTRA_TEXTS else [])
        if not texts:
            missing.append(name)
        block = [f"{name} {version}", f"Licence: {lic}"]
        if homepage(dist):
            block.append(f"Home page: {homepage(dist)}")
        for fname, text in texts:
            label = re.sub(r"^.*?\.dist-info/licen[cs]es/", "", fname)
            block += ["", f"--- {label} ---", text.strip()]
        parts.append("\n".join(block))
    if python_runtime:
        py = Path(sys.base_prefix) / "LICENSE.txt"
        text = py.read_text(encoding="utf-8", errors="replace") if py.exists() else "See https://docs.python.org/3/license.html"
        summary.insert(0, f"  Python {sys.version.split()[0]} runtime  (Python Software Foundation License, with the "
                          "licences of the software it incorporates)")
        major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
        inc = Path(__file__).resolve().parent / "notices" / f"python-{major_minor}-incorporated.txt"
        if not inc.exists():
            print(f"Missing {inc.name}: copy the section 'Licenses and Acknowledgements for Incorporated Software' "
                  f"of CPython's Doc/license.rst for Python {major_minor} into packaging/notices/.", file=sys.stderr)
            return 1
        parts.insert(0, "\n".join([f"Python {sys.version.split()[0]} runtime", "Licence: PSF-2.0 and others (below)",
                                   "", "--- LICENSE.txt ---", text.strip(), "",
                                   f"--- {inc.name} ---", inc.read_text(encoding="utf-8").strip()]))
    if tk:
        terms = [c for c in (Path(sys.base_prefix) / "tcl" / "tcl8.6" / "license.terms",
                             Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms") if c.exists()]
        if terms:
            summary.append("  Tcl/Tk 8.6  (Tcl/Tk licence, BSD-style)")
            parts.append("\n".join(["Tcl/Tk 8.6 (used by the desktop window)",
                                    "Licence: Tcl/Tk licence (BSD-style); Tcl and Tk are distributed under the same "
                                    "terms", ""] + [f"--- {c.parent.name}/license.terms ---\n"
                                                   f"{c.read_text(encoding='utf-8', errors='replace').strip()}"
                                                   for c in terms]))
    try:
        pi = metadata.distribution("pyinstaller")
        summary.append(f"  PyInstaller {pi.version} bootloader  (GPL-2.0-or-later with the bootloader exception)")
        parts.append("\n".join([
            f"PyInstaller {pi.version} bootloader",
            "Licence: GPL-2.0-or-later with a special exception for the bootloader",
            "The executables start through PyInstaller's bootloader. Its licence includes an exception that "
            "permits it to be distributed with programs under any licence; the exception is reproduced in the "
            "PyInstaller licence text below.", ""] + [f"--- {Path(f).name} ---\n{t.strip()}" for f, t in licence_texts(pi)]))
    except metadata.PackageNotFoundError:
        pass
    # v2.1: the JavaScript libraries bundled in the offline topology viewer (ashare/viz/viewer/vendor)
    js = Path(__file__).resolve().parents[1] / "ashare" / "viz" / "viewer" / "vendor" / "LICENSES.txt"
    if js.exists():
        summary.append("  3d-force-graph 1.80.1, force-graph 1.52.0, Chart.js 4.4.8 and the modules they bundle "
                       "(three.js, d3)  (MIT and ISC), in the topology viewer")
        parts.append("\n".join(["JavaScript libraries of the topology viewer (written into topology.html)",
                                "Licence: MIT and ISC (below)", "", js.read_text(encoding="utf-8").strip()]))
    summary.append("  Microsoft Visual C++ runtime (VCRUNTIME140.dll)  (Microsoft redistributable)")
    parts.append("Microsoft Visual C++ runtime (VCRUNTIME140.dll)\nLicence: redistributed with the Python runtime "
                 "under the Microsoft Visual Studio redistributable terms; it remains Microsoft's property.")
    if missing:
        print("No licence text found for: " + ", ".join(missing) + ". Add it to EXTRA_TEXTS.", file=sys.stderr)
        return 1
    header = [
        "THIRD-PARTY NOTICES",
        "",
        "A-share Company Intelligence is licensed under the PolyForm Strict License 1.0.0 (LICENSE.md). It",
        "bundles the third-party components listed below. Bundled components keep their own licences, reproduced",
        "in full in this file; the PolyForm Strict licence does not apply to them, and nothing in it changes the",
        "terms on which they are licensed. The copyright notices and licence texts are included as their",
        "licences require.",
        "",
        "Source code: each component's source code is available from the home page given below, and from the",
        "Python Package Index (https://pypi.org) for the version shown. certifi is distributed under the Mozilla",
        "Public License 2.0; its source code, including the unmodified certificate bundle shipped here, is",
        "available at https://github.com/certifi/python-certifi and https://pypi.org/project/certifi/.",
        "",
        f"Generated from the build ({len(summary)} components):",
        "",
    ]
    sep = "\n\n" + "=" * 78 + "\n\n"
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    Path(out_file).write_text("\n".join(header + summary) + sep + sep.join(parts) + "\n", encoding="utf-8")
    print(f"Wrote {out_file}: {len(summary)} components")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
