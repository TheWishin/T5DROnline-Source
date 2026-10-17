"""The smoke tests. Each is a function taking a Ctx; ctx.boot() starts the
game (fresh gamedata unless told otherwise) and returns a Game. Register a
test with @test(name, suites, description). See docs/SMOKE.md, "Adding a test".

Main menu order on the title screen (cursor starts on ARCADE BATTLE):
  0 ARCADE  1 GHOST  2 VS  3 ONLINE  4 SURVIVAL  5 PRACTICE  6 GALLERY  7 OPTIONS
Buttons (Tekken names): SQUARE=1/LP  TRIANGLE=2/RP  CROSS=3/LK  CIRCLE=4/RK.
The menu flows below were recorded by the QA agent (build/qa/scripts) on
2026-10-16 and re-checked by the smoke agent.
"""
import re

TESTS = {}

ARCADE, GHOST, VS, ONLINE, SURVIVAL, PRACTICE, GALLERY, OPTIONS = range(8)


def test(name, suites, desc, budget=120):
    def deco(fn):
        TESTS[name] = {"name": name, "suites": tuple(suites), "desc": desc, "fn": fn, "budget": budget}
        return fn
    return deco


def tests_for(suite):
    return [t for t in TESTS.values() if suite in t["suites"]]


# ------------------------------------------------------------ helpers
def to_title(g, name="title"):
    """Boot, skip the intro movie, land on the title menu (cursor on ARCADE)."""
    ok = g.wait_title()
    g.expect("title", ok, "intro skipped, title menu reached" if ok else "title menu not reached in 90 s")
    g.phase(name, "title")
    return ok


def is_title(f):
    """The title menu: mostly black around the logo and the menu."""
    return f["black"] >= 0.5 and 8 < f["mean"] < 45


def back_to_title(g, timeout=15.0):
    f = g.wait_frame(is_title, timeout=timeout, need=2)
    g.expect("back-to-title", f is not None, "title menu again" if f else f"no title screen within {timeout:.0f}s",
             evidence=(f or g.latest_frame() or {}).get("file"))
    g.phase("title-again", "title")
    g.wait(6)
    g.shot("title-again")


def pick_mode(g, index, wait=2.5):
    for _ in range(index):
        g.press("DOWN", gap=450)
    g.press("CROSS")
    g.wait(wait)


def start_fight(g, taps=(("CROSS", 1),), timeout=60.0, skip=True):
    """Confirm everything until the fight HUD is up: CROSS picks the fighter,
    GAME START and the stage; with skip, START skips the VS splash and the
    intros (CROSS does not skip arcade intros). Tapping stops at the first
    frame with the HUD; if a last START still opened the pause/practice menu
    (no HUD on the next frames), one more START closes it. Practice uses
    skip=False: START there opens the practice menu and CROSS is enough."""
    g.phase("to-fight", "load")
    t = g.until_fight(timeout=timeout, taps=tuple(taps) + ((("START", 1),) if skip else ()), need=1)
    if t is not None and skip:
        f = g.wait_frame(lambda f: True, timeout=4, need=2)
        if f is not None and not f.get("fight", {}).get("is_fight"):
            g.event("unpause", "no HUD right after the fight started: START once to close the menu")
            g.press("START", gap=800)
    g.expect("fight", t is not None, f"fight HUD after {t - g.phases[-1][2]:.0f}s" if t else
             f"no fight HUD within {timeout:.0f}s", evidence=(g.latest_frame() or {}).get("file"))
    return t is not None


def fight(g, seconds, name="fight", two_pads=False, shots=2):
    """Play for `seconds`: P1 walks in and attacks; with two_pads P2 does the
    same from the other side. Shots at the start and at the end."""
    g.phase(name, "fight")
    g.shot(f"{name}-start", expect="fight")
    t_end = g.now() + seconds
    i = 0
    while g.now() < t_end:
        g.hold("RIGHT")
        if two_pads:
            g.hold("LEFT", pad=2)
        g.wait(0.4)
        g.release()
        if two_pads:
            g.release(pad=2)
        for b in ("SQUARE", "TRIANGLE", "CROSS") if i % 2 == 0 else ("CIRCLE", "SQUARE"):
            g.press(b, gap=150)
            if two_pads:
                g.press2(b, gap=150)
        g.wait(0.8)
        i += 1
        if shots > 2 and i % max(1, int(seconds / 3 / 2.5)) == 0:
            g.shot(f"{name}-{i}", expect="any")
    g.shot(f"{name}-end", expect="fight")


# ------------------------------------------------------------ quick suite
@test("boot_menu", ("quick", "full"), "boot -> intro skipped -> title menu; cursor down and back up", budget=45)
def boot_menu(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.shot("title")
    g.wait(6)
    for _ in range(3):
        g.press("DOWN", gap=600)
    g.shot("menu-down3")
    for _ in range(3):
        g.press("UP", gap=600)
    g.wait(2)
    g.shot("menu-back")


@test("arcade_fight", ("quick", "full"), "ARCADE -> character select -> GAME START -> round 1, 15 s of fighting", budget=65)
def arcade_fight(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("arcade-select", "menu")
    pick_mode(g, ARCADE, wait=3.0)
    g.shot("charsel")
    if start_fight(g):
        fight(g, 15)


@test("vs_two_pads", ("quick", "full"), "VS with both pads scripted: P1 and P2 pick, stage select, 15 s fight", budget=75)
def vs_two_pads(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("vs-charsel", "menu")
    pick_mode(g, VS, wait=3.0)
    g.shot("charsel")
    g.press("CROSS", gap=1200)                   # P1: the cursor's fighter
    g.press2("RIGHT", gap=400)
    g.press2("CROSS", gap=600)                   # P2: one to the right
    g.wait(10)                                   # a full 5-s fps/audio window on the menu
    g.shot("both-picked")
    if start_fight(g, taps=(("CROSS", 1), ("CROSS", 2))):
        fight(g, 15, two_pads=True)


@test("practice", ("quick", "full"), "PRACTICE -> pick both fighters and the stage -> 12 s practice fight", budget=65)
def practice(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("practice-select", "menu")
    pick_mode(g, PRACTICE, wait=3.0)
    g.shot("charsel")
    if start_fight(g, skip=False):
        fight(g, 12)


@test("title_twice", ("quick", "full"),
      "title -> attract demo -> START -> title -> attract -> START -> title: the third scene load "
      "(QA issue 1, sys_memory never reuses freed ranges)", budget=95)
def title_twice(ctx):
    g = ctx.boot()
    if not to_title(g, "title1"):
        return
    g.shot("title1")
    for n in (1, 2):
        # The title falls into the attract demo after ~20 s idle. The title is
        # mostly black; the demo is a full-screen fight.
        f = g.wait_frame(is_attract, timeout=60, need=2)
        g.expect(f"attract{n}", f is not None, "attract demo started" if f else "no attract demo within 60 s")
        g.phase(f"attract{n}", "attract")
        g.wait(2)
        g.shot(f"attract{n}", expect="any")
        g.press("START")
        g.phase(f"title{n + 1}", "title")
        g.wait(4)
        g.shot(f"title{n + 1}")
    g.wait(6)
    g.shot("title3-10s")


def is_attract(f):
    return f["black"] < 0.3 and f["mean"] > 35 and f["std"] > 10


# ------------------------------------------------------------ full suite only
@test("ghost", ("full",), "GHOST BATTLE -> character -> 15 s fight against a ghost", budget=60)
def ghost(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("ghost-select", "menu")
    pick_mode(g, GHOST, wait=3.0)
    g.shot("charsel")
    if start_fight(g):
        fight(g, 15)


@test("survival_loop", ("full",), "SURVIVAL: 80 s of fights back to back, RETRY on the results screen", budget=140)
def survival_loop(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("survival-select", "menu")
    pick_mode(g, SURVIVAL, wait=3.0)
    g.shot("charsel")
    if not start_fight(g):
        return
    g.phase("survival", "fight")
    g.shot("survival-start", expect="fight")
    t_end = g.now() + 80
    k = 0
    while g.now() < t_end:
        g.press("CIRCLE", gap=2900)              # a kick in the fight, RETRY on the results screen
        k += 1
        if k % 10 == 0:
            g.shot(f"survival-{k * 3:03d}s", expect="any")
    g.shot("survival-end", expect="any")


@test("options", ("full",), "OPTIONS: game, sound (BGM volume changed) and controller pages, EXIT back to the title",
      budget=60)
def options(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("options", "menu")
    options_round_trip(g)
    back_to_title(g)


def options_round_trip(g):
    """OPTIONS menu: GAME OPTIONS, SOUND OPTIONS, CONTROLLER SETUP,
    ONLINE MANUAL, DELETE SAVE DATA, EXIT. Visits the first three pages,
    turns the BGM volume up one step (so there is a setting to save) and
    leaves through EXIT. The game and sound pages go back with CIRCLE; the
    controller page only through its own EXIT item."""
    pick_mode(g, OPTIONS, wait=2.5)
    g.shot("options")
    g.press("CROSS", gap=1500)                   # GAME OPTIONS
    g.shot("options-game")
    g.wait(1.0)                                  # pages ignore CIRCLE while they slide in
    g.press("CIRCLE", gap=1500)
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)                   # SOUND OPTIONS
    g.press("DOWN", gap=400)                     # SPEAKER OUTPUT -> BGM VOLUME
    g.press("RIGHT", gap=600)
    g.shot("options-sound")
    g.press("CIRCLE", gap=1500)
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)                   # CONTROLLER SETUP
    g.shot("options-controller")
    g.wait(1.0)
    g.press("DOWN", gap=400)                     # SETTINGS -> DEFAULT -> EXIT
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)
    for _ in range(3):
        g.press("DOWN", gap=400)                 # CONTROLLER SETUP -> EXIT
    g.press("CROSS")


@test("gallery_offline", ("full",), "GALLERY with no network: the update fails cleanly, back to the title", budget=60)
def gallery_offline(ctx):
    g = ctx.boot()
    if not to_title(g):
        return
    g.phase("gallery", "menu")
    pick_mode(g, GALLERY, wait=3.0)
    g.wait(3)
    g.shot("gallery-retry")                      # "Unable to update content list. Retry update?"
    g.press("RIGHT", gap=500)                    # NO
    g.press("CROSS", gap=2500)
    g.shot("gallery-return")                     # "Content list must be updated ... Return to Title Screen?"
    g.press("CROSS")                             # YES
    back_to_title(g)


@test("save_reload", ("full",),
      "fresh profile: change a setting in OPTIONS so the game saves, quit, boot again on the same gamedata: "
      "the save loads (QA issue 4: the first save into a new folder failed); then OPTIONS > DELETE SAVE DATA "
      "deletes one of the two saves through the system list", budget=180)
def save_reload(ctx):
    g = ctx.boot(label="boot1")
    if to_title(g):
        g.phase("options", "menu")
        options_round_trip(g)                    # leaving OPTIONS with a changed setting saves the profile
        g.wait_log(r"\[cellSaveData\] SAVE complete", timeout=20)
        g.wait(4)
    log = g.log_bytes()
    saves, fails = log.count(b"[cellSaveData] SAVE complete"), log.count(b"Unable to save")
    g.expect("saved", saves > 0 and fails == 0, f"{saves} 'SAVE complete', {fails} 'Unable to save' dialog(s)",
             evidence="game.log")
    ctx.stop(g)
    g2 = ctx.boot(label="boot2", keep_gamedata=True)
    to_title(g2)
    log = g2.log_bytes()
    loads = len(re.findall(rb"\[cellSaveData\] LOAD dir='[^']+' \(new=0\)", log))
    bad = log.count(b"Unable to load")
    g2.expect("loaded", loads > 0 and bad == 0,
              f"{loads} existing save(s) loaded, {bad} 'Unable to load' dialog(s)", evidence="game.log")
    g2.wait(3)
    g2.shot("title-after-reload")
    # OPTIONS > DELETE SAVE DATA opens the system's save data list (ps3_sysui,
    # patch 0033): second save, "Delete this saved data?" Yes, back to the game.
    g2.phase("delete-save", "menu")
    pick_mode(g2, OPTIONS, wait=2.5)
    for _ in range(4):
        g2.press("DOWN", gap=450)                # DELETE SAVE DATA
    g2.press("CROSS", gap=1500)
    listed = g2.wait_log(r"\[sysui\] list .*: 2 item", timeout=10)
    g2.press("DOWN", gap=600)
    g2.press("CROSS", gap=900)                   # "Delete this saved data?" (cursor on No)
    g2.press("LEFT", gap=600)                    # Yes
    g2.press("CROSS", gap=2500)                  # deleted -> "Deleted." -> the list again
    left = g2.wait_log(r"\[sysui\] list .*: 1 item", timeout=10)
    g2.press("CIRCLE", gap=1500)                 # back to the game's OPTIONS menu
    gone = g2.wait_log(r"Delete2: 1 save\(s\) deleted", timeout=10)
    g2.expect("deleted", listed and left and gone,
              "the list showed 2 saves, one was deleted, 1 left" if listed and left and gone else
              f"list with 2 saves: {listed}, 1 left after deleting: {left}, Delete2 reported it: {gone}",
              evidence="game.log")
    g2.wait(2)
    g2.shot("options-after-delete")


@test("idle_attract", ("full",), "10 minutes with no input: title <-> attract demo cycling by itself", budget=610)
def idle_attract(ctx):
    g = ctx.boot()
    g.phase("idle", "idle")
    k = 0
    while g.now() < 600:
        g.wait(10)
        k += 1
        if k % 6 == 0:
            g.shot(f"idle-{int(g.now()):03d}s", expect="any")
