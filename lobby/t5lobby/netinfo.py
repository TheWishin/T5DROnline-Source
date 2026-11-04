"""What the launcher tells the lobby about this PC for the search options (docs/ONLINE.md "Search options, areas and
languages"): does it play over Wi-Fi, and which language does the player speak.

Wi-Fi: the network adapter Windows sends internet traffic through (the default route's interface, GetBestInterface
towards a public address -- nothing is sent) and its type (GetAdaptersAddresses: IF_TYPE_IEEE80211 = Wi-Fi). Not
Windows, or anything unclear (no route, a VPN's virtual adapter): None = not known, which no search option holds
against anybody.
"""
import ctypes
import os
import socket
import struct

IF_TYPE_IEEE80211 = 71
_PROBE = "8.8.8.8"          # only the routing table is asked about it; nothing is sent


def _best_interface(addr=_PROBE):
    """Index of the interface the default route uses (Windows), or None."""
    try:
        iphlp = ctypes.windll.iphlpapi
    except (AttributeError, OSError):
        return None
    dest = struct.unpack("<I", socket.inet_aton(addr))[0]
    index = ctypes.c_ulong(0)
    try:
        if iphlp.GetBestInterface(ctypes.c_ulong(dest), ctypes.byref(index)) != 0:
            return None
    except OSError:
        return None
    return index.value


class _SOCKADDR(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class _IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


# The head of IP_ADAPTER_ADDRESSES_LH up to IfType (the fields read here; the rest is not declared).
_IP_ADAPTER_ADDRESSES._fields_ = [
    ("Length", ctypes.c_ulong), ("IfIndex", ctypes.c_ulong),
    ("Next", ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.c_void_p), ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p), ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p), ("Description", ctypes.c_wchar_p), ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * 8), ("PhysicalAddressLength", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong), ("Mtu", ctypes.c_ulong), ("IfType", ctypes.c_ulong),
]


def _adapter_types():
    """{interface index: IfType} of every adapter (Windows), or {}."""
    try:
        iphlp = ctypes.windll.iphlpapi
    except (AttributeError, OSError):
        return {}
    size = ctypes.c_ulong(16384)
    for _ in range(3):
        buf = ctypes.create_string_buffer(size.value)
        # AF_UNSPEC, GAA_FLAG_SKIP_UNICAST | ANYCAST | MULTICAST | DNS_SERVER (0x0F): only the adapters themselves
        rc = iphlp.GetAdaptersAddresses(0, 0x0F, None, buf, ctypes.byref(size))
        if rc == 111:          # ERROR_BUFFER_OVERFLOW: size has the size needed
            continue
        if rc != 0:
            return {}
        out = {}
        p = ctypes.cast(buf, ctypes.POINTER(_IP_ADAPTER_ADDRESSES))
        while p:
            a = p.contents
            out[a.IfIndex] = a.IfType
            p = a.Next
        return out
    return {}


def on_wifi(best_interface=_best_interface, adapter_types=_adapter_types):
    """True / False: this PC reaches the internet over Wi-Fi; None when that cannot be told."""
    if os.name != "nt" and best_interface is _best_interface:
        return None
    try:
        idx = best_interface()
        if idx is None:
            return None
        kind = adapter_types().get(idx)
    except (OSError, ValueError, AttributeError):
        return None
    if kind is None:
        return None
    return kind == IF_TYPE_IEEE80211


# The areas a player can pick (server/mmfilters.py AREAS): code -> what the launcher shows (translated there).
AREAS = (("na", "North America"), ("sa", "South America"), ("eu", "Europe"), ("af", "Africa"), ("as", "Asia"),
         ("oc", "Oceania"))
AREA_NAMES = dict(AREAS)
# The languages a player can say they speak: the launcher's seven, then more that players of the game speak.
LANGS = (("en", "English"), ("de", "Deutsch"), ("es", "Español"), ("fr", "Français"), ("pt-BR", "Português (Brasil)"),
         ("ko", "한국어"), ("ja", "日本語"), ("it", "Italiano"), ("pl", "Polski"), ("ru", "Русский"), ("tr", "Türkçe"),
         ("nl", "Nederlands"))
LANG_NAMES = dict(LANGS)
MAX_PINGS = (None, 60, 100, 150)
