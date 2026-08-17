"""Self-test for Helm Chess.

Drives the real application through real key events -- chords included --
and checks what it says and what it does. Speech is captured instead of
spoken, so running this is silent.

    python selftest.py
"""

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


def main():
    print("Helm Chess self-test")
    print("=" * 60)
    test_describe()
    test_engine()
    test_updater()
    test_real_key_delivery()
    test_navigation()
    test_selection_and_movement()
    test_knight_chords()
    test_illegal_moves_are_blocked()
    test_promotion()
    test_shift_preview()
    test_extras()
    test_black_orientation()
    shutdown()

    print("=" * 60)
    print("%d passed, %d failed" % (len(PASSED), len(FAILED)))
    for name, detail in FAILED:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
