"""Graphics-loss evidence from runtime diagnostics, without probing this PC or starting anything."""
import re


def N_(text):
    return text


HD4400_ADVICE = N_(
    "Intel HD Graphics 4400 lost the graphics device (exit code 12). "
    "Try the latest graphics driver offered by your PC maker, close GPU-heavy programs and overlays, "
    "and choose Lowest (0.5x) Internal resolution. If this PC has another GPU, select it for t5dr.exe "
    "in Windows Graphics settings. These steps may not fix it. If it still fails, click Report a problem "
    "and send the report to the maintainer.")

# Use the selected adapter's own diagnostic, never a stray mention of a model in a crash or dialog.
RE_ADAPTER = re.compile(r"^\[gpu\] adapter: (.+?) \(vendor [0-9A-Fa-f]+,")
RE_HD4400 = re.compile(r"\bIntel(?:\(R\))?\s+HD(?:\s+Graphics)?\s+4400\b", re.I)


def adapter_name(line):
    match = RE_ADAPTER.match(line)
    return match.group(1).strip() if match else None


def is_hd4400(adapter):
    return bool(RE_HD4400.search(adapter or ""))


def device_lost(line):
    """Only the runtime's fatal loss paths, rather than a test switch or an arbitrary HRESULT mention."""
    return line.startswith("[gpu] device lost at ") or line.startswith("[gpu] FATAL (exit code 12):")
