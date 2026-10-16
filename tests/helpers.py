"""Shared bits for the tests: paths, importing tools/*.py, fake keys.

Nothing here is real key material. The fake keys are derived from hashes of
fixed labels at run time, so no key-shaped literal exists in the repository
(tools/check_no_game_data.py would rightly flag one).
"""
import hashlib
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
PY = sys.executable


def load_tool(name):
    """Import tools/<name>.py as a module (the tools are scripts, not a package)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_bytes(label, n=16):
    out = b""
    i = 0
    while len(out) < n:
        out += hashlib.sha256(f"t5dr-ci fake {label} {i}".encode()).digest()
        i += 1
    return out[:n]


def fake_keys(revision=1):
    """A complete key set in the shape tools/unself.py expects -- all fake."""
    pbox = bytes(sorted(range(16), key=lambda i: hashlib.sha256(f"pbox {i}".encode()).digest()))
    rev = f"NPDRM_{revision:04X}"
    return {
        "NP_KLIC_KEY": fake_bytes("klic"),
        "RAP_KEY": fake_bytes("rap"),
        "RAP_PBOX": pbox,
        "RAP_E1": fake_bytes("e1"),
        "RAP_E2": fake_bytes("e2"),
        rev + "_ERK": fake_bytes(f"erk {revision}", 32),
        rev + "_RIV": fake_bytes(f"riv {revision}"),
    }


def put(path, data):
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as f:
        f.write(data)


def get(path):
    with open(path, "rb") as f:
        return f.read()


def write_keys(path, keys):
    with open(path, "w") as f:
        f.write("# fake keys written by the tests\n")
        for name, val in keys.items():
            f.write(f"{name}={val.hex().upper()}\n")
