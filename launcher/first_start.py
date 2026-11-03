"""One-time launcher hints, independent of Tk and of the game process."""

try:
    from t5lobby.i18n import N_, t
except ImportError:       # the launcher can also run without the lobby files
    def N_(text):
        return text

    def t(text):
        return text


CONTROLS_HINT_KEY = "controls_hint_shown"
CONTROLS_HINT = N_(
    "Launcher button bindings and macros take priority over the game's Controller Setup. "
    "Set them in Settings > Set up controllers… in the launcher.")
_MISSING = object()


def show_controls_hint(settings, show, save, *, readonly=False):
    """Show once, after the first real launcher window is ready, then persist.

    Missing markers in an older settings file get this explanation once too.
    ``show(text)`` owns the dialog; ``save()`` persists the supplied settings.
    A failed dialog or save leaves the hint pending for a later attempt. The
    read-only launcher used by UI checks never shows or consumes the hint.
    """
    if readonly or settings.get(CONTROLS_HINT_KEY) is True:
        return False
    previous = settings.get(CONTROLS_HINT_KEY, _MISSING)
    # Mark before entering the modal dialog, which can process more Tk callbacks.
    settings[CONTROLS_HINT_KEY] = True
    try:
        show(t(CONTROLS_HINT))
        save()
    except Exception:
        if previous is _MISSING:
            settings.pop(CONTROLS_HINT_KEY, None)
        else:
            settings[CONTROLS_HINT_KEY] = previous
        raise
    return True
