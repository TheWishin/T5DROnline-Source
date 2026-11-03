"""Advisory before BUILD GAME, using local display-adapter names only.

An adapter name cannot prove that a working Direct3D 12 device can be
created. In particular, a second adapter can be selected by Windows or the
renderer. Warn about the known old Intel classes; never block the build or
declare an unknown card supported. No game, shader, subprocess, or network
request is needed for this check.
"""
import re


def N_(text):
    return text


TITLE = N_("Graphics compatibility warning")
MESSAGE = N_(
    "This PC lists older Intel graphics ({gpus}). Intel HD 4400-class graphics may lack a working "
    "Direct3D 12 driver and may not run the game. Building the game does not add graphics support. "
    "If this PC has another graphics card, select it in Windows Graphics settings. Continue building?")

# A deliberately narrow name check, not a claim about all integrated GPUs.
# HD 5000 and Iris 5100/5200 are also Haswell; UHD, Iris Xe, HD 4xx/5xx/6xx
# (three digits), and e.g. HD 44000 must not match these four-digit names.
_OLD_INTEL = re.compile(
    r"\bintel\b.*?\b(?:hd\s+graphics(?:\s+(?:2000|2500|3000|4000|4200|4400|4600|5000))?"
    r"|iris(?:\s+pro)?\s+graphics\s+(?:5100|5200))\b", re.I)
_NUMBER_AFTER_HD = re.compile(r"\bhd\s+graphics\s+(\d+)\b", re.I)


def caution_names(adapters):
    """Names deserving a warning, from problem_report.gpu_info() tuples.

    The generic historical name ``Intel HD Graphics`` also deserves caution,
    but a model number outside our explicit list is unknown, not unsupported.
    Invalid rows and duplicate names have no effect.
    """
    names = []
    seen = set()
    for adapter in adapters or ():
        if not isinstance(adapter, (tuple, list)) or not adapter or not isinstance(adapter[0], str):
            continue
        name = " ".join(adapter[0].split())
        # Registry descriptions commonly contain Intel(R) / HD Graphics;
        # normalizing only these decorations keeps unrelated model names out.
        normalized = re.sub(r"\((?:R|TM)\)", "", name, flags=re.I)
        if not _OLD_INTEL.search(normalized):
            continue
        numbered = _NUMBER_AFTER_HD.search(normalized)
        if numbered and numbered.group(1) not in {
                "2000", "2500", "3000", "4000", "4200", "4400", "4600", "5000"}:
            continue
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names


def build_warning(adapters=None):
    """Return a translatable warning dict, or None when no caution is known.

    ``adapters`` permits an offline fixture. Without it, the existing read-only
    Windows registry collector is used; unavailable detection is inconclusive.
    The UI presents this warning before it starts the build worker, and the
    player can continue. It must translate message with the supplied values.
    """
    if adapters is None:
        try:
            import problem_report
            adapters = problem_report.gpu_info()
        except (ImportError, OSError, ValueError):
            return None
    names = caution_names(adapters)
    return {"title": TITLE, "message": MESSAGE, "values": {"gpus": ", ".join(names)}} if names else None
