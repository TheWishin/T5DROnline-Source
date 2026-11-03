# Controller Setup hint

The first real launcher window shows a one-time explanation that launcher
bindings and macros take priority over the game's Controller Setup. Use
Settings > Set up controllers in the launcher to configure them.

The `controls_hint_shown` launcher setting is the once-only marker. It defaults
to false; older settings files without the marker get the hint once after
upgrading. A successful display saves true. The read-only launcher used for
UI checks does not show or consume the hint. Resetting this marker to false
shows the explanation again on the next launcher start. The Controls window
also keeps the explanation visible beside its existing setup instructions.

`tests/test_first_start.py` covers persistence across restarts, old and malformed
settings, read-only mode, modal reentry, failed display/save and translation at
display time. These tests were added and remain unexecuted here. The
maintainer still needs to check the first-start dialog and Controls layout in
all languages in a real launcher session. This changes launcher text and hint
state only; the game's input handling and simulation are unchanged.
