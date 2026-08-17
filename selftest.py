"""Self-test for Helm Chess.

Drives the real application through real key events -- chords included --
and checks what it says and what it does. Speech is captured instead of
spoken, so running this is silent.

    python selftest.py
"""

import os
import sys
import time

import chess

import speech

_spoken = []


def _capture(text, interrupt=True):
    _spoken.append(text or "")


speech.speak = _capture  # must happen before the app imports are used

import describe          # noqa: E402
import engine as engine_module  # noqa: E402
import helm_chess     # noqa: E402
import updater           # noqa: E402

helm_chess.speech.speak = _capture

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  pass  %s" % name)
    else:
        FAILED.append((name, detail))
        print("  FAIL  %s %s" % (name, ("-- " + detail) if detail else ""))


def last_speech():
    return _spoken[-1] if _spoken else ""


def all_speech_since(mark):
    return " ".join(_spoken[mark:])


# ---------------------------------------------------------------------------
# Pieces that need no window
# ---------------------------------------------------------------------------

def test_describe():
    print("\ndescribe.py")
    board = chess.Board()
    check("square with a piece",
          describe.describe_square(board, chess.E2) == "e2, white pawn",
          describe.describe_square(board, chess.E2))
    check("empty square",
          describe.describe_square(board, chess.E4) == "e4, empty")
    check("phonetic files",
          describe.describe_square(board, chess.E2, phonetic=True) == "echo 2, white pawn")

    move = chess.Move.from_uci("e2e4")
    check("plain move", describe.describe_move(board, move) == "white pawn e2 to e4",
          describe.describe_move(board, move))

    board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    move = chess.Move.from_uci("e4d5")
    check("capture is announced",
          "captures black pawn" in describe.describe_move(board, move),
          describe.describe_move(board, move))

    board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2")
    move = chess.Move.from_uci("d8h4")
    check("checkmate is announced",
          "checkmate" in describe.describe_move(board, move),
          describe.describe_move(board, move))

    board = chess.Board("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    move = chess.Move.from_uci("e1g1")
    check("castling is announced",
          describe.describe_move(board, move) == "white castles kingside",
          describe.describe_move(board, move))

    check("material balance", "level" in describe.material_balance(chess.Board()).lower())
    check("piece listing", "e1" in describe.list_pieces(chess.Board(), chess.WHITE))


def test_engine():
    print("\nengine.py")
    opponent = engine_module.BuiltinOpponent(level=2)
    board = chess.Board()
    move = opponent.play(board)
    check("engine returns a legal opening move", move in board.legal_moves, str(move))
    check("engine did not disturb the board", board.fen() == chess.Board().fen())

    # Mate in one: the engine must find it.
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R3K2R w KQ - 0 1")
    opponent.set_level(3)
    move = opponent.play(board)
    board.push(move)
    check("engine finds mate in one", board.is_checkmate(), str(move))

    # A hanging queen: any sane search takes it rather than shuffling.
    board = chess.Board("4k3/8/8/8/8/8/4q3/4K2R w K - 0 1")
    opponent.set_level(2)
    move = opponent.play(board)
    check("engine takes a free queen", move == chess.Move.from_uci("e1e2"), str(move))

    opponent.set_level(1)
    check("level 1 is shallow", opponent.max_depth == 1)
    opponent.set_level(99)
    check("level is clamped", opponent.level == 8)

    made, reason = engine_module.create_opponent(level=3, prefer_stockfish=True)
    check("an opponent is always available", made is not None, reason)
    made.close()


def test_updater():
    print("\nupdater.py")
    check("plain version", updater.parse_version("1.2.3") == (1, 2, 3))
    check("tagged version", updater.parse_version("v10.0.2") == (10, 0, 2))
    check("newer beats older", updater.parse_version("1.1.0") > updater.parse_version("1.0.9"))
    try:
        updater.parse_version("not a version")
        check("bad version rejected", False)
    except updater.UpdateError:
        check("bad version rejected", True)
    check("updatable suffixes include python",
          ".py" in updater.UPDATABLE_SUFFIXES)


# ---------------------------------------------------------------------------
# The real application, driven by real key events
# ---------------------------------------------------------------------------

class FakeEvent:
    """The two attributes the key handlers actually read."""

    def __init__(self, keysym, state=0):
        self.keysym = keysym
        self.state = state


class Driver:
    """Drives the app through its real key handlers.

    Tk's synthetic event queue turned out to drop and reorder events under a
    tight update() loop, which made the tests lie about the game. So these go
    straight into the handlers and the chord timer is fired on demand. The
    logic under test is identical; only the delivery is made deterministic.
    `test_real_key_delivery` covers the Tk wiring itself.
    """

    def __init__(self, app):
        self.app = app

    def pump(self, seconds=0.0):
        deadline = time.monotonic() + seconds
        while True:
            self.app.update()
            if time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        self.app.update()

    def arrows(self, *keysyms, shift=False):
        """Press the given arrows together, the way a chord actually arrives."""
        state = 1 if shift else 0
        for keysym in keysyms:
            self.app._on_key_press(FakeEvent(keysym, state))
        for keysym in keysyms:
            self.app._on_key_release(FakeEvent(keysym))
        self._fire_chord()

    def _fire_chord(self):
        if self.app._chord_job is not None:
            try:
                self.app.after_cancel(self.app._chord_job)
            except Exception:
                pass
            self.app._chord_job = None
        self.app._resolve_chord()
        self.app.update()

    def key(self, keysym, state=0):
        self.app._on_key_press(FakeEvent(keysym, state))
        self.app._on_key_release(FakeEvent(keysym))
        self.app.update()

    def wait_for_engine(self, timeout=20.0):
        # The reply is scheduled on a short timer, so give it a chance to
        # start before deciding that nothing is happening.
        self.pump(0.4)
        deadline = time.monotonic() + timeout
        while self.app.thinking and time.monotonic() < deadline:
            self.pump(0.05)
        self.pump(0.15)

    def setup(self, fen, cursor):
        """Drop a fresh position in, with nothing held over from before."""
        self.app.selected = None
        self.app.ghost = None
        self.app._knight_pending = {}
        self.app._promotion_pending = None
        self.app.board.set_fen(fen)
        self.app.cursor = cursor
        self.app._refresh()
        self.app.update()


_APP = None


def make_app(**overrides):
    """One shared application for every test.

    Tk only delivers synthetic key events to the first root of a process, so
    a fresh window per test would look broken while the game is fine. We
    build one and reset it between tests instead.
    """
    global _APP
    if _APP is None:
        settings = dict(helm_chess.DEFAULT_SETTINGS)
        settings.update({
            "level": 1,
            "check_updates_on_start": False,
            "prefer_stockfish": False,
            "sounds": False,
            "chord_ms": 60,
        })
        _APP = helm_chess.HelmChess(settings)
        _APP.withdraw()     # no window flashing up during the test
        Driver(_APP).pump(0.5)   # let the opening announcement get out of the way

    app = _APP
    app.settings.update(overrides)
    app.board.reset()
    app.selected = None
    app.ghost = None
    app.thinking = False
    app._knight_pending = {}
    app._promotion_pending = None
    app._jump_buffer = None
    app._held.clear()
    app._chord.clear()
    app._chord_shift = False
    app.human_color = (chess.BLACK if app.settings.get("play_as") == "black"
                       else chess.WHITE)
    app.cursor = chess.E1 if app.human_color == chess.WHITE else chess.E8
    app.opponent.set_level(1)
    app._refresh()
    app.update()
    return app


def release_app(app):
    """Tests call this instead of closing, since the instance is shared."""
    app.selected = None
    app.ghost = None
    app.settings["play_as"] = "white"
    app.update()


def shutdown():
    global _APP
    if _APP is not None:
        _APP.quit_app()
        _APP = None


def test_real_key_delivery():
    """The one test that goes through Tk itself, so the wiring is proven."""
    print("\nreal key delivery")
    app = make_app()
    driver = Driver(app)
    try:
        app.cursor = chess.E1
        _spoken.clear()

        app.event_generate("<KeyPress-Up>", when="now")
        app.event_generate("<KeyRelease-Up>", when="now")
        driver.pump(app.settings["chord_ms"] / 1000.0 + 0.25)
        check("a real arrow key reaches the board", app.cursor == chess.E2,
              chess.square_name(app.cursor))

        app.event_generate("<KeyPress-Return>", when="now")
        app.event_generate("<KeyRelease-Return>", when="now")
        driver.pump(0.1)
        check("a real enter key picks the piece up", app.selected == chess.E2,
              str(app.selected))

        app.event_generate("<KeyPress-Escape>", when="now")
        app.event_generate("<KeyRelease-Escape>", when="now")
        driver.pump(0.1)
        check("a real escape key puts it back", app.selected is None)

        # A key held down repeats; that must not count as a second press.
        app.cursor = chess.E1
        app._on_key_press(FakeEvent("Up"))
        app._on_key_press(FakeEvent("Up"))     # auto-repeat
        app._on_key_press(FakeEvent("Up"))
        driver._fire_chord()
        check("auto-repeat does not double-move", app.cursor == chess.E2,
              chess.square_name(app.cursor))

        # A release lost to alt-tab must not jam the key permanently.
        app._on_key_press(FakeEvent("Up"))     # no release follows
        app._on_focus_out()
        app._on_key_press(FakeEvent("Up"))
        driver._fire_chord()
        check("a lost key release does not jam the arrow", app.cursor == chess.E3,
              chess.square_name(app.cursor))
    finally:
        release_app(app)


def test_navigation():
    print("\nnavigation")
    app = make_app()
    driver = Driver(app)
    try:
        app.cursor = chess.E1
        _spoken.clear()

        driver.arrows("Up")
        check("up moves one rank", app.cursor == chess.E2,
              chess.square_name(app.cursor))
        check("the square is announced", "e2" in last_speech(), last_speech())

        driver.arrows("Up", "Right")
        check("a chord moves diagonally", app.cursor == chess.F3,
              chess.square_name(app.cursor))

        driver.arrows("Left", "Down")
        check("the other diagonal works", app.cursor == chess.E2,
              chess.square_name(app.cursor))

        app.cursor = chess.A1
        driver.arrows("Left")
        check("the board edge refuses", app.cursor == chess.A1)
        check("the edge is explained", "edge" in last_speech().lower(), last_speech())

        mark = len(_spoken)
        driver.arrows("Left", "Right")
        check("opposite arrows are rejected",
              "opposite" in all_speech_since(mark).lower(), all_speech_since(mark))

        app.cursor = chess.E1
        driver.key("j")
        driver.key("c")
        driver.key("5")
        check("jump to a typed square", app.cursor == chess.C5,
              chess.square_name(app.cursor))
    finally:
        release_app(app)


def test_selection_and_movement():
    print("\nselecting and steering")
    app = make_app()
    driver = Driver(app)
    try:
        app.cursor = chess.E2
        _spoken.clear()

        driver.key("Return")
        check("a pawn can be picked up", app.selected == chess.E2)
        check("selection is announced", "pawn" in last_speech().lower(), last_speech())

        driver.arrows("Up")
        check("the pawn steps to e3", app.ghost == chess.E3,
              chess.square_name(app.ghost) if app.ghost else "none")

        driver.arrows("Up")
        check("the pawn reaches e4", app.ghost == chess.E4,
              chess.square_name(app.ghost) if app.ghost else "none")

        mark = len(_spoken)
        driver.arrows("Up")
        check("a third step is refused", app.ghost == chess.E4)
        check("the refusal names the piece",
              "pawn" in all_speech_since(mark).lower(), all_speech_since(mark))

        mark = len(_spoken)
        driver.arrows("Right")
        check("sideways is refused for a pawn", app.ghost == chess.E4)

        driver.key("Escape")
        check("escape puts the piece back", app.selected is None)

        # A rook boxed in by its own pieces should say so.
        app.cursor = chess.A1
        driver.key("Return")
        check("a rook with no moves is refused", app.selected is None, last_speech())
        check("the refusal is explained",
              "no legal moves" in last_speech().lower(), last_speech())
    finally:
        release_app(app)


def test_knight_chords():
    print("\nknight chords")
    app = make_app()
    driver = Driver(app)
    try:
        app.cursor = chess.G1
        _spoken.clear()
        driver.key("Return")
        check("the knight is picked up", app.selected == chess.G1)

        mark = len(_spoken)
        driver.arrows("Up")
        check("a single arrow will not move a knight", app.ghost == chess.G1)
        check("the L shape is explained",
              "knight" in all_speech_since(mark).lower(), all_speech_since(mark))

        # From g1 only f3 lies up-and-left, because e2 is our own pawn.
        mark = len(_spoken)
        driver.arrows("Up", "Left")
        check("an unambiguous corner moves straight away", app.ghost == chess.F3,
              chess.square_name(app.ghost) if app.ghost else "none")
        check("own pawn on e2 is not offered", "e2" not in all_speech_since(mark),
              all_speech_since(mark))

        driver.key("Return")
        driver.pump(0.3)
        check("the knight move is played",
              app.board.piece_at(chess.F3) is not None
              and app.board.piece_at(chess.F3).piece_type == chess.KNIGHT)
        driver.wait_for_engine()
        check("the opponent replied", len(app.board.move_stack) == 2,
              str(app.board.move_stack))
        check("the opponent's move was legal", app.board.is_valid())

        # A knight in the open has two moves per corner, so it must ask which.
        driver.setup("4k2r/8/8/8/3N4/8/8/4K3 w - - 0 1", chess.D4)
        driver.key("Return")
        mark = len(_spoken)
        driver.arrows("Up", "Left")
        said = all_speech_since(mark).lower()
        check("two options are offered", "two knight moves" in said, said)
        check("both squares are named", "b5" in said and "c6" in said, said)
        check("nothing moved while it asks", app.ghost == chess.D4)

        driver.arrows("Up")
        check("the long leg picks c6", app.ghost == chess.C6,
              chess.square_name(app.ghost) if app.ghost else "none")

        driver.setup("4k2r/8/8/8/3N4/8/8/4K3 w - - 0 1", chess.D4)
        driver.key("Return")
        driver.arrows("Up", "Left")
        driver.arrows("Left")
        check("the other long leg picks b5", app.ghost == chess.B5,
              chess.square_name(app.ghost) if app.ghost else "none")

        driver.setup("4k2r/8/8/8/3N4/8/8/4K3 w - - 0 1", chess.D4)
        driver.key("Return")
        driver.arrows("Up", "Left")
        mark = len(_spoken)
        driver.key("Escape")
        check("escape cancels the question",
              "cancel" in all_speech_since(mark).lower(), all_speech_since(mark))
        check("the knight is still held", app.selected == chess.D4)
    finally:
        release_app(app)


def test_illegal_moves_are_blocked():
    print("\nillegal moves")
    app = make_app()
    driver = Driver(app)
    try:
        # A rook pinned down the e-file may slide along it but not off it.
        driver.setup("4r2k/8/8/8/8/8/4R3/4K3 w - - 0 1", chess.E2)
        _spoken.clear()

        driver.key("Return")
        check("the pinned rook can still be picked up", app.selected == chess.E2,
              last_speech())

        mark = len(_spoken)
        driver.arrows("Right")
        said = all_speech_since(mark).lower()
        check("the pin is enforced", app.ghost == chess.E2,
              chess.square_name(app.ghost) if app.ghost else "none")
        check("the reason given is the king", "king" in said, said)

        driver.arrows("Up")
        check("but along the pin is fine", app.ghost == chess.E3,
              chess.square_name(app.ghost) if app.ghost else "none")

        # Blocked by your own piece.
        driver.setup("4k3/8/8/8/8/8/4P3/4K2R w K - 0 1", chess.E1)
        mark = len(_spoken)
        driver.key("Return")
        driver.arrows("Up")
        said = all_speech_since(mark).lower()
        check("own piece blocks the king", app.ghost == chess.E1,
              chess.square_name(app.ghost) if app.ghost else "none")
        check("the blocker is named", "your own pawn" in said, said)

        # Castling falls out of walking the king two squares.
        mark = len(_spoken)
        driver.arrows("Right")
        check("king steps to f1", app.ghost == chess.F1,
              chess.square_name(app.ghost) if app.ghost else "none")
        driver.arrows("Right")
        check("king reaches g1", app.ghost == chess.G1,
              chess.square_name(app.ghost) if app.ghost else "none")
        check("it is announced as castling",
              "castles kingside" in all_speech_since(mark).lower(),
              all_speech_since(mark))

        driver.key("Return")
        driver.pump(0.3)
        check("castling was played", app.board.piece_at(chess.G1) is not None
              and app.board.piece_at(chess.G1).piece_type == chess.KING)
        check("the rook came too", app.board.piece_at(chess.F1) is not None
              and app.board.piece_at(chess.F1).piece_type == chess.ROOK)
        driver.wait_for_engine()
    finally:
        release_app(app)


def test_promotion():
    print("\npromotion")
    app = make_app()
    driver = Driver(app)
    try:
        driver.setup("8/4P3/8/8/8/8/8/4K1k1 w - - 0 1", chess.E7)
        _spoken.clear()

        driver.key("Return")
        driver.arrows("Up")
        check("the pawn reaches the last rank", app.ghost == chess.E8,
              chess.square_name(app.ghost) if app.ghost else "none")
        check("promotion is flagged", "promotion" in last_speech().lower(), last_speech())

        driver.key("Return")
        check("it asks which piece", app._promotion_pending is not None)
        check("the choices are spoken", "queen" in last_speech().lower(), last_speech())

        driver.key("r")
        driver.pump(0.3)
        piece = app.board.piece_at(chess.E8)
        check("it promoted to a rook", piece is not None and piece.piece_type == chess.ROOK,
              str(piece))
        driver.wait_for_engine()
    finally:
        release_app(app)


def test_shift_preview():
    print("\nshift preview")
    app = make_app()
    driver = Driver(app)
    try:
        driver.setup("4k3/8/8/8/8/8/8/R3K3 w Q - 0 1", chess.A1)
        _spoken.clear()

        driver.key("Return")
        mark = len(_spoken)
        driver.arrows("Up", shift=True)
        said = all_speech_since(mark).lower()
        check("preview lists squares up the file", "a2" in said and "a8" in said, said)
        check("preview did not move the piece", app.ghost == chess.A1)

        mark = len(_spoken)
        driver.arrows("Down", shift=True)
        check("nothing below a1", "nothing that way" in all_speech_since(mark).lower(),
              all_speech_since(mark))
    finally:
        release_app(app)


def test_extras():
    print("\nextras")
    app = make_app()
    driver = Driver(app)
    try:
        _spoken.clear()
        driver.key("s")
        check("status key", "white to move" in last_speech().lower(), last_speech())
        driver.key("v")
        check("material key", "material" in last_speech().lower(), last_speech())
        driver.key("w")
        check("white pieces key", "white" in last_speech().lower(), last_speech())
        driver.key("k")
        check("jump to king", app.cursor == chess.E1)
        driver.key("F1")
        check("help key", "arrow keys" in last_speech().lower(), last_speech()[:60])

        level_before = app.opponent.level
        driver.key("plus")
        check("strength goes up", app.opponent.level == level_before + 1)
        driver.key("minus")
        check("strength goes down", app.opponent.level == level_before)

        # Play a move, then take it back.
        app.cursor = chess.E2
        driver.key("Return")
        driver.arrows("Up")
        driver.arrows("Up")
        driver.key("Return")
        driver.wait_for_engine()
        plies = len(app.board.move_stack)
        check("a move and a reply happened", plies == 2, str(plies))
        driver.key("u")
        check("take back removes both", len(app.board.move_stack) == 0,
              str(len(app.board.move_stack)))
        check("it is your move again", app.board.turn == chess.WHITE)
    finally:
        release_app(app)


def test_black_orientation():
    print("\nplaying as black")
    app = make_app(play_as="black")
    driver = Driver(app)
    try:
        driver.setup("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                     chess.E7)
        _spoken.clear()

        driver.key("Return")
        check("black pawn picked up", app.selected == chess.E7)
        driver.arrows("Up")
        check("up means forward for black too", app.ghost == chess.E6,
              chess.square_name(app.ghost) if app.ghost else "none")
        driver.key("Escape")

        # The knight question used to store the answer in screen directions
        # while reading the reply in board directions, so as black neither
        # arrow ever matched and the knight could not be moved at all.
        driver.setup("rnbqkbnr/pppp1ppp/8/8/3PpP2/8/PPP1P1PP/RNBQKBNR b KQkq f3 0 3",
                     chess.G8)
        driver.key("Return")
        mark = len(_spoken)
        driver.arrows("Up", "Right")
        said = all_speech_since(mark).lower()
        check("black knight is asked about", "two knight moves" in said, said)
        check("the arrows named are the ones you press",
              "up for f6" in said and "right for e7" in said, said)

        driver.arrows("Up")
        check("black knight answers to the long leg", app.ghost == chess.F6,
              chess.square_name(app.ghost) if app.ghost else "none")

        driver.setup("rnbqkbnr/pppp1ppp/8/8/3PpP2/8/PPP1P1PP/RNBQKBNR b KQkq f3 0 3",
                     chess.G8)
        driver.key("Return")
        driver.arrows("Up", "Right")
        driver.arrows("Right")
        check("the other black knight leg works", app.ghost == chess.E7,
              chess.square_name(app.ghost) if app.ghost else "none")
    finally:
        release_app(app)


def test_updater_folder_replacement():
    """The sounds folder is replaced wholesale, and that must stay safe.

    Runs the real installer against fake release zips built in the shape
    GitHub produces, so none of this touches the network.
    """
    print("\nupdater folder replacement")
    import io
    import tempfile
    import zipfile

    padding = "x" * 40000   # clears the updater's minimum-size sanity check

    def make_zip(top_files, folders):
        buffer = io.BytesIO()
        top_files = dict(top_files)
        top_files["NOTES.txt"] = padding
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in top_files.items():
                archive.writestr("helm-chess-abc123/%s" % name, content)
            for folder, files in folders.items():
                for name, content in files.items():
                    archive.writestr("helm-chess-abc123/%s/%s" % (folder, name), content)
                if not files:
                    archive.writestr("helm-chess-abc123/%s/" % folder, "")
        return buffer.getvalue()

    def install_from(payload, install_dir):
        path = os.path.join(tempfile.mkdtemp(), "release.zip")
        with open(path, "wb") as handle:
            handle.write(payload)
        original = updater._open
        updater._open = lambda url: open(path, "rb")
        try:
            return updater.download_and_install("local", install_dir=install_dir)
        finally:
            updater._open = original

    def fresh_install():
        folder = tempfile.mkdtemp(prefix="helm-install-")
        with open(os.path.join(folder, "version.py"), "w") as handle:
            handle.write('__version__ = "1.0.0"\n')
        sounds = os.path.join(folder, "sounds")
        os.makedirs(sounds)
        for name in ("capture1.ogg", "capture2.ogg", "select.ogg"):
            with open(os.path.join(sounds, name), "wb") as handle:
                handle.write(b"OggS" + b"\0" * 2000)
        return folder

    def sound_files(folder):
        path = os.path.join(folder, "sounds")
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    untouched = ["capture1.ogg", "capture2.ogg", "select.ogg"]
    one_sound = {"sounds": {"capture.ogg": b"OggS" + b"\0" * 2000}}
    version_only = {"version.py": '__version__ = "1.0.1"\n'}

    install = fresh_install()
    install_from(make_zip(version_only, {
        "sounds": {"capture.ogg": b"OggS" + b"\0" * 2000,
                   "move1.ogg": b"OggS" + b"\0" * 2000,
                   "CREDITS.txt": "credits"}}), install)
    check("renamed sounds leave no orphans behind",
          sound_files(install) == ["CREDITS.txt", "capture.ogg", "move1.ogg"],
          str(sound_files(install)))

    install = fresh_install()
    install_from(make_zip(version_only, {}), install)
    check("a release without the folder leaves yours alone",
          sound_files(install) == untouched, str(sound_files(install)))

    install = fresh_install()
    install_from(make_zip(version_only, {"sounds": {}}), install)
    check("an empty folder is not read as a delete order",
          sound_files(install) == untouched, str(sound_files(install)))

    install = fresh_install()
    engines = os.path.join(install, "engines")
    os.makedirs(engines)
    with open(os.path.join(engines, "stockfish.exe"), "wb") as handle:
        handle.write(b"MZ" + b"\0" * 5000)
    install_from(make_zip(version_only, one_sound), install)
    check("a Stockfish you installed yourself survives",
          os.path.isfile(os.path.join(engines, "stockfish.exe")))

    install = fresh_install()
    install_from(make_zip(version_only, one_sound), install)
    backup = os.path.join(install, ".update-backup", "sounds")
    check("the replaced sounds are recoverable from the backup",
          os.path.isdir(backup) and sorted(os.listdir(backup)) == untouched,
          str(sorted(os.listdir(backup)) if os.path.isdir(backup) else "no backup"))

    install = fresh_install()
    try:
        install_from(make_zip({"something_else.py": "nope"}, {}), install)
        check("a download that is not Helm Chess is refused", False)
    except updater.UpdateError:
        check("a download that is not Helm Chess is refused", True)
    check("the refused download changed nothing",
          sound_files(install) == untouched, str(sound_files(install)))


def test_settings_menu():
    print("\nsettings menu")
    app = make_app()
    driver = Driver(app)
    try:
        _spoken.clear()
        driver.key("o")
        check("the menu opens", app._in_settings)
        said = last_speech().lower()
        check("inverted mode comes first", "inverted mode" in said, said)
        check("the description is read", "real chess board" in said, said)
        check("it says which way it is set", "inverted mode, off" in said, said)

        before = app.settings["inverted"]
        driver.key("Right")
        check("right toggles it", app.settings["inverted"] != before)
        check("the new value is announced", "inverted mode, on" in last_speech().lower(),
              last_speech())
        driver.key("Return")
        check("enter toggles it back", app.settings["inverted"] == before)

        driver.key("Down")
        check("down reaches opponent strength",
              "opponent strength" in last_speech().lower(), last_speech())
        level_before = app.settings["level"]
        driver.key("Right")
        check("right raises the level", app.settings["level"] == level_before + 1)
        check("the engine hears about it", app.opponent.level == level_before + 1)

        # Numbers must stop at their ends rather than wrapping to nonsense.
        for _ in range(12):
            driver.key("Right")
        check("the level stops at 8", app.settings["level"] == 8, str(app.settings["level"]))
        check("the ceiling is explained", "highest" in last_speech().lower(), last_speech())
        for _ in range(12):
            driver.key("Left")
        check("the level stops at 1", app.settings["level"] == 1, str(app.settings["level"]))

        driver.key("End")
        check("end reaches the last item",
              app._settings_index == len(helm_chess.SETTINGS_ITEMS) - 1)
        driver.key("Down")
        check("it wraps round to the first", app._settings_index == 0)

        driver.key("Escape")
        check("escape closes the menu", not app._in_settings)
        check("closing says whose move it is", "to move" in last_speech().lower(),
              last_speech())

        # Arrows must go back to steering the board once the menu is gone.
        app.cursor = chess.E1
        driver.arrows("Up")
        check("the arrows drive the board again", app.cursor == chess.E2,
              chess.square_name(app.cursor))

        app.opponent.set_level(1)
        app.settings["level"] = 1
    finally:
        release_app(app)


def test_inverted_mode():
    print("\ninverted mode")
    app = make_app(play_as="black")
    driver = Driver(app)
    try:
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

        app.settings["inverted"] = False
        driver.setup(fen, chess.E7)
        driver.key("Return")
        driver.arrows("Up")
        check("off: the board faces you, up is forward", app.ghost == chess.E6,
              chess.square_name(app.ghost) if app.ghost else "none")

        app.settings["inverted"] = True
        driver.setup(fen, chess.E7)
        driver.key("Return")
        driver.arrows("Up")
        check("on: the board stays white's way up, so up goes backwards",
              app.ghost is None or app.ghost == chess.E7,
              chess.square_name(app.ghost) if app.ghost else "none")
        driver.arrows("Down")
        check("on: down is forward for black", app.ghost == chess.E6,
              chess.square_name(app.ghost) if app.ghost else "none")

        app.settings["inverted"] = False
    finally:
        release_app(app)


def test_settings_migration():
    print("\nsettings migration")
    # The old name meant the opposite of the new one.
    check("old flip_for_black true becomes inverted false",
          _migrated({"flip_for_black": True})["inverted"] is False)
    check("old flip_for_black false becomes inverted true",
          _migrated({"flip_for_black": False})["inverted"] is True)
    check("the old key is not kept around",
          "flip_for_black" not in _migrated({"flip_for_black": True}))


def _migrated(stored):
    import json
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "settings.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(stored, handle)
    original = helm_chess.settings_path
    helm_chess.settings_path = lambda: path
    try:
        return helm_chess.load_settings()
    finally:
        helm_chess.settings_path = original


def main():
    print("Helm Chess self-test")
    print("=" * 60)
    test_describe()
    test_engine()
    test_updater()
    test_updater_folder_replacement()
    test_real_key_delivery()
    test_navigation()
    test_selection_and_movement()
    test_knight_chords()
    test_illegal_moves_are_blocked()
    test_promotion()
    test_shift_preview()
    test_extras()
    test_black_orientation()
    test_settings_menu()
    test_inverted_mode()
    test_settings_migration()
    shutdown()

    print("=" * 60)
    print("%d passed, %d failed" % (len(PASSED), len(FAILED)))
    for name, detail in FAILED:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
