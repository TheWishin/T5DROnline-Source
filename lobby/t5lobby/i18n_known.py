"""English texts that reach a player from outside the launcher, so the launcher can put them into the
player's language.

The lobby server, the lobby client library and the build tools write their messages in English. The texts
here are the ones the launcher knows: i18n.translate_message(text) finds a message in this list (a text with
{placeholders} is a pattern: the values in the message go into the translated text) and shows the translated
one; a message that is not in the list is shown as it came. The translations are in the catalogs (i18n_de.py,
i18n_es.py, ...), like all others.

Adding a message to the server, the client or the build tool means adding it here: tests/test_i18n.py reads
their source and fails for a message that no entry covers (messages for programmers, not players, are listed
in DEV_ONLY of that test).
"""
from .i18n import N_

# lobby/t5lobby/server/lobby.py: errors answering a request ({"t": "error", "msg": ...}), notices, kick reasons
SERVER = (
    # login, accounts
    N_("login timeout"),
    N_("idle timeout"),
    N_("banned from this server"),
    N_("too many connections"),
    N_("server full"),
    N_("slow down"),
    N_("bad request"),
    N_("the server is busy; try again in a few seconds"),
    N_("the chat is busy; try again in a moment"),
    N_("that name looks too much like the account {other}"),
    N_("that name looks too much like {name}, who is online"),
    N_("flooding: disconnected"),
    N_("this server speaks lobby protocol {version}; update the launcher"),
    N_("build {build} is not accepted by this server; update the launcher and rebuild the game"),
    N_("already logged in"),
    N_("this server has no accounts"),
    N_("this server has no guest logins"),
    N_("too many failed logins; wait a few minutes"),
    N_("too many failed attempts; wait a few minutes"),
    N_("too many password changes; wait a minute"),
    N_("too many requests for new codes; wait a minute"),
    N_("too many new accounts from this address"),
    N_("the saved login has expired; log in with your password"),
    N_("session expired; log in again"),
    N_("names are 2-16 letters, digits, spaces or _-.[]()!?"),
    N_("that name is reserved"),
    N_("that name is not allowed here"),
    N_("that name belongs to an account"),
    N_("that name is taken"),
    N_("someone with that name is online"),
    N_("wrong name or password"),
    N_("wrong password"),
    N_("the current password is wrong"),
    N_("passwords are 6-128 characters"),
    N_("guests have no password"),
    N_("guests have no account"),
    N_("wrong name or recovery code (each code works once)"),
    N_("logged in from another place"),
    N_("this account is banned for good"),
    N_("this account is banned for good: {reason}"),
    N_("this account is banned until {time}"),
    N_("this account is banned until {time}: {reason}"),
    # lobby
    N_("you are {status}"),
    N_("ranked needs an account"),
    N_("ranked matches come from the ranked queue on this server"),
    N_("your character is locked until this ranked set ends"),
    N_("the ranked set goes on by itself"),
    N_("you are in a ranked set ({mine}-{theirs}); leave it first (that counts as a loss)"),
    N_("that player is in a ranked set"),
    N_("you are not in a ranked set"),
    N_("finish your running match with the same game build first"),
    N_("this PC ran its last match at {fps} fps; ranked needs at least {min_fps} (both games run at the slower "
       "PC's speed). Close other programs or lower the resolution scale, then play a casual match to measure again"),
    N_("chat: slow down"),
    N_("history is kept for accounts only"),
    N_("no such player"),
    N_("no such room"),
    N_("room is full"),
    N_("you cannot join this room"),
    N_("not in a room"),
    N_("no opponent in the room"),
    N_("that player runs a different build of the game"),
    N_("finish the match first"),
    N_("finish or leave the running match first"),
    N_("that match is over; find a new opponent"),
    N_("your opponent is no longer available"),
    N_("that player is not available"),
    N_("busy"),
    N_("one challenge at a time"),
    N_("that player has challenges pending"),
    N_("no such challenge"),
    N_("challenge no longer possible"),
    N_("no such match"),
    N_("match is {state}"),
    N_("you cannot block yourself"),
    N_("the block list is full ({max})"),
    N_("that player is not on your block list"),
    N_("you are not in a set"),
    N_("no such finished match"),
    # friends and invites
    N_("guests cannot have friends; create an account (free)"),
    N_("there is no account with that name"),
    N_("you cannot add yourself"),
    N_("you blocked that player; unblock them first"),
    N_("your friends list is full ({max})"),
    N_("you can send {count} friend requests a day; try again tomorrow"),
    N_("your last invite to that friend ended a moment ago; try again in {seconds} s"),
    N_("your last challenge to that player ended a moment ago; try again in {seconds} s"),
    N_("too many friend requests from this internet address today; try again tomorrow"),
    N_("{count} of your friend requests are waiting for an answer; cancel some first"),
    N_("{name} declined your last request; you can ask again in {days} day(s)"),
    N_("that player has too many friend requests waiting"),
    N_("that player's friends list is full"),
    N_("no friend request from that player"),
    N_("no friend request to that player"),
    N_("that player is not on your friends list"),
    N_("that friend is not online"),
    N_("that friend's launcher is too old for invites (it needs 1.1.2 or newer)"),
    N_("create a room first, then invite"),
    N_("that friend is busy right now"),
    N_("one invite at a time"),
    N_("wait a moment before inviting again"),
    N_("that player has invites pending"),
    N_("that invite is over"),
    N_("the invite is no longer possible"),
    # notices during a match
    N_("{name} is back in the lobby"),
    N_("{name} lost the lobby connection; waiting {seconds} s for them to return"),
    N_("your PC ran its last match at {fps} fps"),
    N_("your opponent's PC ran its last match at {fps} fps"),
    N_("{name}'s PC ran its last match at {fps} fps"),
    N_("{parts} -- this match runs at the slower PC's speed"),
    N_("you two played {count} ranked matches in the last 24 hours; this one is unranked (limit {max})"),
    N_("your PC's UDP packets did not reach the lobby server; check the firewall"),
    N_("your opponent reported the result; please report yours"),
    N_("opponent runs a different build"),
    # spectating (server/spectating.py)
    N_("this launcher cannot watch matches; update it"),
    N_("that match is not being played right now"),
    N_("you are playing in that match"),
    N_("you are in a match yourself"),
    N_("only friends of a player can watch this match"),
    N_("the players do not allow spectators"),
    N_("neither player can send the match right now"),
    N_("this match cannot be watched any more"),
    N_("this match has {count} spectators already"),
    N_("the server cannot show more matches right now"),
    N_("too many matches are watched from your network; stop watching one first"),
    N_("the places for guests at this match are taken; log in with an account to watch"),
    N_("the server cannot show guests more matches right now; log in with an account to watch"),
    # private and community rooms (server/rooms.py, 1.1.3: docs/ONLINE.md "Rooms")
    N_("private rooms need a newer launcher; update it"),
    N_("only the room's host can do that"),
    N_("too many wrong room passwords; try again in {seconds} s"),
    N_("wrong room password"),
    N_("the room's password changed; try again"),
    N_("no room has that invite code"),
    N_("rooms hold 2 to {count} players"),
    N_("room passwords are 4-64 characters, no space at either end"),
    N_("private and community rooms are casual (unranked)"),
    N_("you are in that room"),
    N_("the room's host removed you from this room"),
    N_("the room's host turned away password guesses from your network; ask the host for an invite"),
    N_("only a room with a password counts wrong guesses"),
    N_("that player is not in your room"),
    N_("you cannot remove yourself; leave the room instead"),
    N_("you can remove that player after their match"),
    N_("only rooms for 3 or more players take turns"),
    N_("you sit out in the room; press Back in line to play again"),
    N_("the room picks the next match by itself"),
    N_("the room's host removed that player from this room"),
    N_("only the room's players can watch its match"),
    # training rooms and the health handicap (server/matchrules.py, 1.1.5)
    N_("training rooms need a newer launcher; update it"),
    N_("training rooms are casual (unranked)"),
    N_("the health handicap needs a newer launcher; update it"),
    N_("life is 30 to 100 in steps of 10"),
)

# lobby/t5lobby/server/tournaments.py: errors answering a tournament request (docs/TOURNAMENTS.md)
TOURNAMENTS = (
    N_("tournaments need an account"),
    N_("no such tournament"),
    N_("only the server's organizers can create tournaments here"),
    N_("a tournament name is 3-40 characters"),
    N_("the format is single or double elimination"),
    N_("a set is first to 2 or first to 3 games"),
    N_("the player limit is 8, 16, 32 or 64"),
    N_("the check-in window is 0, 5, 10, 15, 30 or 60 minutes"),
    N_("seeding is random or by rating"),
    N_("that start time has passed"),
    N_("a tournament starts within {days} days"),
    N_("this server has as many tournaments as it takes; try again later"),
    N_("that tournament name is not allowed here"),
    N_("this internet address runs as many tournaments as one organizer may; finish or cancel one first"),
    N_("the organizer took you off this tournament"),
    N_("you play in that set yourself: a server tournament admin decides it (or cancel the tournament)"),
    N_("you already run {count} tournaments; finish or cancel one first"),
    N_("update the launcher to play in tournaments"),
    N_("sign-up for that tournament is closed"),
    N_("that tournament is played with another build of the game"),
    N_("that tournament is full"),
    N_("you are not in that tournament"),
    N_("that tournament is over"),
    N_("check-in is not open"),
    N_("that tournament is not running"),
    N_("that set is not yours to play"),
    N_("that set is not waiting for you"),
    N_("only the organizer can do that"),
    N_("that tournament has started already"),
    N_("a tournament needs at least 2 players"),
    N_("no such player in that tournament"),
    N_("that player is out already"),
    N_("no such set"),
    N_("that set is decided; override it instead"),
    N_("only a played set can be overridden"),
    N_("that set has not been played"),
    N_("that set was a walkover"),
    N_("set {set} was already played from this result; reset it first"),
    N_("finish your match first, then accept the tournament set"),
    N_("finish your set first, then accept the tournament set"),
    N_("you are in a tournament set; finish it first"),
    N_("that player is playing a tournament set"),
    N_("your tournament set is ready; accept it first"),
    N_("that player has a tournament set to play"),
)

# lobby/t5lobby/client.py: LobbyError texts and the reasons a connection ended
CLIENT = (
    N_("not connected to the lobby"),
    N_("the lobby server did not answer"),
    N_("no answer to {type}"),
    N_("cannot reach {host}:{port} ({error})"),
    N_("the server's certificate does not match the pinned one"),
    N_("this server has no encryption (TLS): a password would cross the internet readable. Play as a guest, or "
       "ask the server's host to set up TLS and give you its fingerprint."),
    N_("connection closed"),
    N_("message too long"),
    N_("closed"),
    N_("the server sent a malformed match id"),
    N_("this server has no private rooms"),     # (client.py create_room: a new launcher, an older server)
    N_("this server has no training rooms"),    # (client.py create_room / set_life: an older server)
    N_("this server has no health handicap"),
)

# tools/build_game.py: the sentence after "ERROR:" in the build log, shown in the Build tab
BUILD_TOOL = (
    N_("Choose your game package (.pkg) first."),
    N_("The package file does not exist: {file}"),
    N_("{file} is not a PS3 package (.pkg)."),
    N_("Choose your license file (.rap) first."),
    N_("{file} is not a PS3 license: a .rap file is exactly 16 bytes."),
    N_("This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or theme?). The port needs "
       "{game}."),
    N_("This package is \"{title}\" ({id}). The port needs {game}."),
    N_("This copy is a different version of the game: \"{title}\" version {version}, content ID {id} (program "
       "SHA-1 {sha}...). The port supports only {game}, content ID {supported}."),
    N_("This package is version {version} of the game (program content ID {id}). The port supports only version "
       "{supported}: {game}, content ID {cid}, {size} bytes. This version cannot be used, whatever the license "
       "(.rap)."),
    N_("The license (.rap) does not belong to this package. Use the .rap whose name matches the package's content "
       "ID ({id})."),
    N_("Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press BUILD GAME "
       "again; if it fails again, check that the package is {size} bytes."),
    N_("The package is {size} bytes, the supported one is {supported} bytes: the download is incomplete or it is "
       "a different file. Download it again."),
    N_("The ps3recomp copy in this folder does not match this version of the port. Download the release again and "
       "extract it into an empty folder."),
    N_("Git is needed to download ps3recomp (the recompiler). Install Git, or use a release zip, which already "
       "contains it."),
    N_("This package's Python is missing pycryptodome. Download the release again."),
    N_("Could not download the public PS3 key data from github.com (needed once, a few KB). Check the internet "
       "connection and press BUILD GAME again."),
    N_("The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not installed. Open the "
       "launcher's Build tab and click Install next to them."),
    N_("clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the release again."),
    N_("The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build tools."),
    N_("clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio component 'C++ Clang tools "
       "for Windows'."),
    N_("CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake tools for Windows'."),
    N_("CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross"),
    N_("glslang and spirv-cross were not found; the game's shaders need them. "
       "On macOS: brew install glslang spirv-cross"),
    N_("Building the game is supported on Windows and macOS only."),
    N_("This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: "
       "python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with "
       ".venv/bin/python."),
    N_("expected 1 SPU image, found {count}"),
    N_("step '{step}' failed: a tool exited with code {code} -- the lines above say why."),
    N_("cancelled"),
    N_("step '{step}' could not read or write a file: {reason} ({file}). The folder path is too long for Windows: "
       "move the folder to a short path such as C:\\Games\\T5DR."),
    N_("step '{step}' could not read or write a file: {reason} ({file}). Is the disk full, or does another "
       "program (antivirus, OneDrive) hold the file?"),
)

# tools/prereqs.py: what the "Build tools on this PC" list shows
PREREQS = (
    N_("Python 3.10+"),
    N_("pycryptodome (Python AES)"),
    N_("ps3recomp source"),
    N_("Game runtime (t5dr.exe)"),
    N_("clang-cl + lld-link"),
    N_("C++ build tools (MSVC x64)"),
    N_("Windows SDK (Direct3D 12)"),
    N_("clang-cl 16+ (LLVM)"),
    N_("CMake + Ninja"),
    N_("{version} at {path}"),
    N_("installed"),
    N_("missing -- pip install pycryptodome"),
    N_("included in this package"),
    N_("git checkout in deps/"),
    N_("not present -- will be downloaded with Git"),
    N_("not present and Git is missing"),
    N_("precompiled, included in this package"),
    N_("missing from toolchain\\llvm -- download the release again"),
    N_("not found"),
    N_("missing {tools}"),
)

# launcher/problem_report.py: the parts of the problem report the window lists (the report's own files stay English)
REPORT = (
    N_("System information and the settings you use"),
    N_("What happened (what you wrote)"),
    N_("Launcher log"),
    N_("Game log (the newest one)"),
    N_("Game log (the newest {count})"),
    N_("Build log"),
    N_("Build log (the last build went fine)"),
    N_("Online: the files of the last match"),
    N_("controls.ini (your button settings)"),
    N_("Desync dumps (game state numbers, binary)"),
    N_("The last replay (the inputs of the last online session, without names)"),
    N_("could not be cleaned of private data"),
    N_("no room left in the size limit"),
    N_("could not be read"),
)

# launcher/updater.py: problems the update check, the download and the swap step report (they also go into
# swap.log and result.json in English; the launcher shows them through translate_message())
UPDATER = (
    N_("The launcher cannot write next to its folder or into it, so it cannot update itself. Download the zip "
       "from the releases page instead."),
    N_("Refused to download from {host}: not this project's GitHub releases."),
    N_("The download came from {host}. Nothing was changed."),
    N_("GitHub did not return a published release."),
    N_("The latest release has an unexpected version ({tag})."),
    N_("Release {version} has no {name} with SHA256SUMS yet."),
    N_("The downloaded release does not say it is version {version}. Nothing was changed."),
    N_("The downloaded release has no launcher. Nothing was changed."),
    N_("This folder has no python\\pythonw.exe, so the launcher cannot update itself (a development checkout?). "
       "Download the zip from the releases page instead."),
    N_("The download was sent to {host}, which is not GitHub's storage for this project. Nothing was changed."),
    N_("Release {version}: {name} is not on this project's GitHub releases."),
    N_("Release {version}: {name} is still being uploaded."),
    N_("The download stopped early ({done} of {total} bytes). Try again."),
    N_("The download is not a readable zip ({error}). Nothing was changed."),
    N_("The download unpacks to far more than a release should. Nothing was changed."),
    N_("Not enough free disk space: the update needs about {need} MB next to the folder, {free} MB are free."),
    N_("SHA256SUMS of release {version} has no line for {name}. Nothing was changed."),
    N_("SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed."),
    N_("The download is damaged or not the published file: its SHA-256 is {got}..., SHA256SUMS says {want}.... "
       "Nothing was changed."),
    N_("The downloaded release has no python\\pythonw.exe. Nothing was changed."),
    N_("The download is far bigger than a release should be. Nothing was changed."),
    N_("The download contains an unexpected path ({name}: {why}). Nothing was changed."),
    N_("The download contains an unexpected path ({name}). Nothing was changed."),
    N_("Cancelled."),
    N_("Could not download or unpack the update ({error}). Nothing was changed."),
    N_("The download is damaged ({error}). Nothing was changed."),
    N_("the new release contains {names} (the player's files)"),
    N_("release.json does not say {version} after the swap"),
    N_("launcher\\t5dr_launcher.pyw is missing after the swap"),
    N_("python\\pythonw.exe is missing after the swap"),
    N_("the update plan is incomplete"),
    N_("the launcher did not close"),
    N_("programs from the folder were still running ({names}); close them and try again"),
    N_("the new launcher {version} did not start"),
    N_("could not replace the program files: {error}"),
    N_("unexpected error: {error}"),
    N_("GitHub asks to wait with update checks until {time}."),
    N_("GitHub limits update checks right now. Try again later."),
    N_("GitHub answered with error {code}. Try again later."),
    N_("No connection to GitHub. Check the internet connection and try again."),
    N_("A build is running. Update when it is finished."),
    N_("The game is running. Close it first, then update."),
    N_("'Host for friends' is running. Stop hosting first, then update."),
    N_("An online match was found. Update after the match."),
    N_("An online match is running. Update after the match."),
    N_("You are searching for or playing an online match. Update afterwards."),
    N_("Other programs from this folder are still running ({names}): another launcher window, the game or a "
       "lobby server. Close them, then update."),
    N_("not a plain relative path"),
    N_("'.', '..' or an empty part"),
    N_("outside the folder {folder}"),
    N_("named like the player's own files"),
    N_("a name Windows does not keep as written"),
    N_("Release {version} is a test version; it is not installed automatically."),
    N_("Release {version} is not signed with the project's release key (no SHA256SUMS.sig). It was not made by "
       "the project's release process; nothing was changed."),
    N_("Release {version} failed the signature check ({error}). It was not made by the project's release "
       "process; nothing was changed."),
)

# Words that are part of a message ("you are {status}": the server's player states), translated on their own.
WORDS = (
    N_("idle"),
    N_("room"),
    N_("queue"),
    N_("match"),
    N_("playing"),
)


GROUPS = (SERVER, TOURNAMENTS, CLIENT, BUILD_TOOL, PREREQS, REPORT, UPDATER)


def templates():
    """The known messages that have {placeholders}: patterns for i18n.translate_message()."""
    seen = []
    for group in GROUPS:
        for text in group:
            if "{" in text and text not in seen:
                seen.append(text)
    return seen


def exact():
    """The known messages without placeholders."""
    return {text for group in GROUPS for text in group if "{" not in text}
