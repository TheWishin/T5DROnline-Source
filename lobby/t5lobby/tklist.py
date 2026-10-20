"""Lists that update in place.

The Online tab's lists (players, rooms, friends, the leaderboard, tournaments) used to be emptied and filled again on
every lobby update (about once a second while anything moves): the list jumped back to its top while it was being
scrolled, the row under the mouse flickered, and a long list cost its full rebuild each time. sync() changes only the
rows that changed, so the scroll position, the selection and the focus stay where they are.
"""


def sync(tv, rows):
    """Make Treeview `tv` show `rows` in that order: [(iid, values, image or None, tags)]. Rows that are gone are
    deleted, new ones inserted, changed ones updated; unchanged rows are not touched."""
    cache = getattr(tv, "_t5_rows", None)
    if cache is None:
        cache = tv._t5_rows = {}
    have = tv.get_children()
    have_set = set(have)
    want = [r[0] for r in rows]
    want_set = set(want)
    gone = [i for i in have if i not in want_set]
    if gone:
        tv.delete(*gone)
    for k in [k for k in cache if k not in want_set or k not in have_set]:
        del cache[k]
    for idx, (iid, values, image, tags) in enumerate(rows):
        values = tuple(values)
        tags = tuple(tags or ())
        img = image if image is not None else ""
        sig = (values, str(img), tags)
        if iid in have_set:
            if cache.get(iid) != sig:
                tv.item(iid, values=values, image=img, tags=tags)
                cache[iid] = sig
        else:
            tv.insert("", idx, iid=iid, values=values, image=img, tags=tags)
            cache[iid] = sig
    if list(tv.get_children()) != want:
        for idx, iid in enumerate(want):
            tv.move(iid, "", idx)
