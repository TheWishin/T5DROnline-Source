"""Display the server's legacy `region` field as a game edition, never a location."""
from .i18n import t


def edition_note(player, viewer):
    """Only flag a known edition that differs from the viewer's known edition."""
    edition = (player or {}).get("region")
    own = (viewer or {}).get("region")
    if own not in ("US", "EU") or edition == own:
        return ""
    if edition == "EU":
        return t("EU edition")
    if edition == "US":
        return t("US edition")
    return ""
