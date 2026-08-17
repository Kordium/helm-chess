"""Helm Chess -- a keyboard chess client for screen reader users.

Movement works the way the Monarch's chess app works. With nothing
selected the arrow keys walk a cursor around the board and every square is
announced. Press enter on one of your pieces to pick it up, and from then
on the arrow keys steer that piece. Anything that is not a legal move is
simply refused, with a reason.

Moving in two directions at once means pressing both arrows at once: up and
right together takes a bishop up-right one square. Hold shift with the
arrows to hear what a direction has to offer without committing to it.

The window is only there to receive keystrokes; everything that matters is
spoken.
"""

import argparse
import json
import os
import sys
import threading
import tkinter as tk

import chess
import chess.pgn

import describe
import engine as engine_module
import speech
import updater
from version import __version__

try:
    import winsound
except ImportError:
    winsound = None


APP_NAME = "Helm Chess"

ARROWS = {
    "Up": (0, 1),
    "Down": (0, -1),
    "Left": (-1, 0),
    "Right": (1, 0),
}
ARROW_WORDS = {(0, 1): "up", (0, -1): "down", (-1, 0): "left", (1, 0): "right"}

PROMOTION_KEYS = {
    "q": chess.QUEEN,
    "r": chess.ROOK,
    "b": chess.BISHOP,
    "n": chess.KNIGHT,
}

DEFAULT_SETTINGS = {
    "chord_ms": 90,          # how long to wait for a second arrow
    "level": 3,              # opponent strength, 1 to 8
    "play_as": "white",
    "phonetic_files": False,  # say "echo 4" instead of "e4"
    "flip_for_black": True,   # up means forward when you play black
    "prefer_stockfish": True,
    "stockfish_path": "",
    "check_updates_on_start": True,
    "sounds": True,
}


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "HelmChess")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def load_settings():
    values = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as handle:
            values.update(json.load(handle))
    except (OSError, ValueError):
        pass
    return values


def save_settings(values):
    try:
        with open(settings_path(), "w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2)
    except OSError:
        pass


class HelmChess(tk.Tk):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.title(APP_NAME)
        self.geometry("520x360")

        self.board = chess.Board()
        self.human_color = chess.BLACK if settings["play_as"] == "black" else chess.WHITE
        self.cursor = chess.E1 if self.human_color == chess.WHITE else chess.E8
        self.selected = None
        self.ghost = None

        self.thinking = False
        self._think_ply = 0
        self._knight_pending = {}
        self._promotion_pending = None
        self._jump_buffer = None

        # Chord tracking. `_held` stops key auto-repeat from firing a chord
        # over and over; `_chord` is what actually gets resolved.
        self._held = set()
        self._chord = set()
        self._chord_shift = False
        self._chord_job = None

        self.opponent, reason = engine_module.create_opponent(
            level=settings["level"],
            prefer_stockfish=settings["prefer_stockfish"],
            stockfish_path=settings["stockfish_path"] or None,
        )
        self._engine_reason = reason

        self._build_window()
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        # Alt-tabbing away while an arrow is down means its release never
        # arrives. Without this the game would think that key is still held
        # and quietly ignore it forever after.
        self.bind("<FocusOut>", self._on_focus_out)
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        self._timers = [self.after(300, self._greet)]
        if settings["check_updates_on_start"]:
            self._timers.append(
                self.after(1500, lambda: self.check_updates(quiet=True)))

    # -- window ------------------------------------------------------------

    def _build_window(self):
        self.display = tk.Label(
            self, font=("Consolas", 12), justify="left", anchor="nw", padx=10, pady=10,
        )
        self.display.pack(fill="both", expand=True)
        self.status = tk.Label(self, anchor="w", padx=10, pady=4)
        self.status.pack(fill="x")
        self._refresh()

    def _refresh(self):
        self.display.config(text=describe.render_board(
            self.board, self.cursor, self.selected, self.ghost,
        ))
        self.status.config(text="%s  |  %s  |  F1 for help" % (
            describe.describe_status(self.board), self.opponent.describe(),
        ))

    def _greet(self):
        self.say(
            "%s version %s. %s. You play %s. %s. "
            "Arrow keys to explore, enter to pick up a piece, F1 for help."
            % (APP_NAME, __version__, self.opponent.describe(),
               describe.COLOR_NAMES[self.human_color],
               describe.describe_square(self.board, self.cursor, self._phonetic()))
        )

    # -- helpers -----------------------------------------------------------

    def _phonetic(self):
        return self.settings["phonetic_files"]

    def say(self, text, interrupt=True):
        speech.speak(text, interrupt=interrupt)

    def refuse(self, text):
        """Say why something did not happen, with the system's own error sound."""
        if self.settings["sounds"] and winsound is not None:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass
        self.say(text)

    def _orient(self, vector):
        """Flip the arrows when you play black, so up is always forward."""
        if self.human_color == chess.BLACK and self.settings["flip_for_black"]:
            return (-vector[0], -vector[1])
        return vector

    def _human_to_move(self):
        return self.board.turn == self.human_color and not self.board.is_game_over()

    # -- key handling ------------------------------------------------------

    def _on_key_press(self, event):
        keysym = event.keysym

        if keysym in ARROWS:
            if keysym in self._held:
                return "break"          # auto-repeat while held, ignore
            self._held.add(keysym)
            self._chord.add(keysym)
            if event.state & 0x0001:
                self._chord_shift = True
            if self._chord_job is None:
                self._chord_job = self.after(
                    max(20, int(self.settings["chord_ms"])), self._resolve_chord,
                )
            return "break"

        self._handle_command(event)
        return "break"

    def _on_key_release(self, event):
        self._held.discard(event.keysym)

    def _on_focus_out(self, _event=None):
        self._held.clear()

    def _resolve_chord(self):
        keys, shift = set(self._chord), self._chord_shift
        self._chord.clear()
        self._chord_shift = False
        self._chord_job = None
        if not keys:
            return

        df = sum(ARROWS[key][0] for key in keys)
        dr = sum(ARROWS[key][1] for key in keys)
        if (df, dr) == (0, 0):
            self.refuse("Opposite directions at once. Nothing to do.")
            return
        # Three arrows at once can add up past one square; keep it to a step.
        vector = (max(-1, min(1, df)), max(-1, min(1, dr)))

        if shift:
            self._preview(vector)
        else:
            self._step(vector)

    # -- moving around -----------------------------------------------------

    def _offset(self, square, vector):
        file = chess.square_file(square) + vector[0]
        rank = chess.square_rank(square) + vector[1]
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None

    def _step(self, vector):
        if self._promotion_pending:
            self.refuse("Choose a promotion piece first: q, r, b, or n.")
            return
        if self.thinking:
            self.refuse("The opponent is still thinking.")
            return

        vector = self._orient(vector)

        if self._knight_pending:
            self._resolve_knight(vector)
            return

        if self.selected is None:
            self._move_cursor(vector)
        else:
            self._steer(vector)

    def _move_cursor(self, vector):
        target = self._offset(self.cursor, vector)
        if target is None:
            self.refuse("Edge of the board.")
            return
        self.cursor = target
        self._refresh()
        self.say(describe.describe_square(self.board, target, self._phonetic()))

    def _steer(self, vector):
        """Walk the held piece one square in `vector`, or explain the refusal."""
        piece = self.board.piece_at(self.selected)
        if piece is None:
            self._deselect(quiet=True)
            return

        if piece.piece_type == chess.KNIGHT:
            self._steer_knight(vector)
            return

        target = self._offset(self.ghost, vector)
        if target is None:
            self.refuse("Edge of the board.")
            return

        move = self._legal_move(self.selected, target)
        if move is None:
            self.refuse(self._why_not(target, piece))
            return

        self.ghost = target
        self._refresh()
        self.say(describe.describe_destination(self.board, move, self._phonetic()))

    def _steer_knight(self, vector):
        """A knight cannot be walked, so a diagonal chord picks its L instead."""
        if vector[0] == 0 or vector[1] == 0:
            self.refuse(
                "A knight moves in an L. Press two arrows together for the "
                "corner you want, like up and right."
            )
            return

        candidates = []
        for move in self.board.legal_moves:
            if move.from_square != self.selected:
                continue
            file_delta = chess.square_file(move.to_square) - chess.square_file(self.selected)
            rank_delta = chess.square_rank(move.to_square) - chess.square_rank(self.selected)
            if (file_delta > 0) == (vector[0] > 0) and (rank_delta > 0) == (vector[1] > 0):
                candidates.append((move, file_delta, rank_delta))

        if not candidates:
            self.refuse("No legal knight move that way.")
            return

        if len(candidates) == 1:
            move = candidates[0][0]
            self.ghost = move.to_square
            self._refresh()
            self.say("%s. Enter to move." % describe.describe_destination(
                self.board, move, self._phonetic()))
            return

        # Two of them share a corner. The long leg tells them apart.
        # The keys are board directions, because that is what _step hands
        # back; the words spoken are the arrows the player actually presses,
        # which differ from the board when black is flipped.
        self._knight_pending = {}
        spoken = []
        for move, file_delta, rank_delta in candidates:
            if abs(file_delta) == 2:
                leg = (1 if file_delta > 0 else -1, 0)
            else:
                leg = (0, 1 if rank_delta > 0 else -1)
            self._knight_pending[leg] = move
            spoken.append("%s for %s" % (
                ARROW_WORDS[self._orient(leg)],
                describe.describe_destination(self.board, move, self._phonetic()),
            ))
        self.say("Two knight moves. %s. Escape to cancel." % ". ".join(spoken))

    def _resolve_knight(self, vector):
        move = self._knight_pending.get(vector)
        self._knight_pending = {}
        if move is None:
            self.say("Cancelled.")
            return
        self.ghost = move.to_square
        self._refresh()
        self.say("%s. Enter to move." % describe.describe_destination(
            self.board, move, self._phonetic()))

    def _legal_move(self, from_square, to_square):
        """The legal move between two squares, ignoring which promotion piece."""
        for move in self.board.legal_moves:
            if move.from_square == from_square and move.to_square == to_square:
                return move
        return None

    def _why_not(self, target, piece):
        """Say something more useful than 'illegal move'."""
        name = describe.square_name(target, self._phonetic())
        occupant = self.board.piece_at(target)

        if occupant is not None and occupant.color == piece.color:
            return "Blocked by your own %s on %s." % (
                describe.piece_name(occupant, with_color=False), name)

        # Legal shape, but it would hang the king.
        candidate = chess.Move(self.selected, target)
        promotion = chess.Move(self.selected, target, promotion=chess.QUEEN)
        if candidate in self.board.pseudo_legal_moves or promotion in self.board.pseudo_legal_moves:
            if self.board.is_check():
                return "No. That does not get you out of check."
            return "No. That would leave your king in check."

        if self.ghost != self.selected:
            return "The %s cannot go on to %s from there." % (
                describe.piece_name(piece, with_color=False), name)
        return "A %s cannot move to %s." % (
            describe.piece_name(piece, with_color=False), name)

    def _preview(self, vector):
        """Shift plus arrows: what is available that way, without moving."""
        vector = self._orient(vector)
        origin = self.selected if self.selected is not None else self.cursor

        if self.selected is None:
            # Nothing held: peek at the neighbouring square, leave the cursor put.
            target = self._offset(self.cursor, vector)
            if target is None:
                self.refuse("Edge of the board.")
                return
            self.say(describe.describe_square(self.board, target, self._phonetic()))
            return

        piece = self.board.piece_at(origin)
        found = []
        for move in self.board.legal_moves:
            if move.from_square != origin:
                continue
            file_delta = chess.square_file(move.to_square) - chess.square_file(origin)
            rank_delta = chess.square_rank(move.to_square) - chess.square_rank(origin)
            if not self._matches_direction(file_delta, rank_delta, vector,
                                           piece.piece_type == chess.KNIGHT):
                continue
            found.append(move)

        if not found:
            self.say("Nothing that way.")
            return
        found.sort(key=lambda m: abs(chess.square_file(m.to_square) - chess.square_file(origin))
                   + abs(chess.square_rank(m.to_square) - chess.square_rank(origin)))
        seen, parts = set(), []
        for move in found:
            if move.to_square in seen:
                continue
            seen.add(move.to_square)
            parts.append(describe.describe_destination(self.board, move, self._phonetic()))
        self.say("%d that way. %s" % (len(parts), ". ".join(parts)))

    @staticmethod
    def _matches_direction(file_delta, rank_delta, vector, knight):
        if knight:
            return ((file_delta > 0) == (vector[0] > 0) or vector[0] == 0) and \
                   ((rank_delta > 0) == (vector[1] > 0) or vector[1] == 0) and \
                   (vector[0] == 0 or file_delta != 0) and \
                   (vector[1] == 0 or rank_delta != 0)
        if vector[0] == 0:
            return file_delta == 0 and (rank_delta > 0) == (vector[1] > 0)
        if vector[1] == 0:
            return rank_delta == 0 and (file_delta > 0) == (vector[0] > 0)
        return (abs(file_delta) == abs(rank_delta) and file_delta != 0
                and (file_delta > 0) == (vector[0] > 0)
                and (rank_delta > 0) == (vector[1] > 0))

    # -- selecting and committing -----------------------------------------

    def _select(self):
        if not self._human_to_move():
            self.refuse("Not your move." if not self.board.is_game_over()
                        else describe.describe_status(self.board))
            return
        piece = self.board.piece_at(self.cursor)
        if piece is None:
            self.refuse("%s is empty." % describe.square_name(self.cursor, self._phonetic()))
            return
        if piece.color != self.human_color:
            self.refuse("That is not your piece.")
            return
        moves = [m for m in self.board.legal_moves if m.from_square == self.cursor]
        if not moves:
            self.refuse("That %s has no legal moves." %
                        describe.piece_name(piece, with_color=False))
            return

        self.selected = self.cursor
        self.ghost = self.cursor
        self._refresh()
        self.say("%s selected on %s. %d moves. Arrows to steer, escape to put it back." % (
            describe.piece_name(piece, with_color=False),
            describe.square_name(self.cursor, self._phonetic()),
            len(moves),
        ))

    def _deselect(self, quiet=False):
        self.selected = None
        self.ghost = None
        self._knight_pending = {}
        self._refresh()
        if not quiet:
            self.say("Put back. %s" % describe.describe_square(
                self.board, self.cursor, self._phonetic()))

    def _commit(self):
        if self.selected is None:
            self._select()
            return
        if self.ghost == self.selected:
            self.refuse("The piece has not moved yet. Steer it with the arrow keys.")
            return

        move = self._legal_move(self.selected, self.ghost)
        if move is None:
            self.refuse("That is not a legal move.")
            return

        if move.promotion is not None:
            self._promotion_pending = (self.selected, self.ghost)
            self.say("Promotion. Press q for queen, r for rook, b for bishop, "
                     "or n for knight.")
            return

        self._play(move)

    def _finish_promotion(self, piece_type):
        from_square, to_square = self._promotion_pending
        self._promotion_pending = None
        move = chess.Move(from_square, to_square, promotion=piece_type)
        if move not in self.board.legal_moves:
            self.refuse("That promotion is not legal.")
            return
        self._play(move)

    def _play(self, move):
        text = describe.describe_move(self.board, move, self._phonetic())
        self.board.push(move)
        self.selected = None
        self.ghost = None
        self.cursor = move.to_square
        self._refresh()

        if self.board.is_game_over(claim_draw=True):
            self.say("%s. %s" % (text, describe.describe_status(self.board)))
            return
        self.say(text)
        self.after(150, self._start_thinking)

    # -- the opponent ------------------------------------------------------

    def _start_thinking(self):
        if self.board.is_game_over(claim_draw=True) or self.board.turn == self.human_color:
            return
        self.thinking = True
        self.status.config(text="Thinking...")
        # If the position changes underneath us -- a new game, a takeback --
        # the reply we are waiting on belongs to a game that no longer exists.
        self._think_ply = self.board.ply()
        snapshot = self.board.copy()
        result = {}

        def work():
            try:
                result["move"] = self.opponent.play(snapshot)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        self.after(50, self._collect_move, thread, result)

    def _collect_move(self, thread, result):
        if thread.is_alive():
            self.after(50, self._collect_move, thread, result)
            return

        self.thinking = False
        if self.board.ply() != self._think_ply:
            self._refresh()     # the game moved on; drop the stale reply
            return
        if "error" in result:
            self._refresh()
            self.refuse("The engine failed: %s" % result["error"])
            return

        move = result.get("move")
        if move is None or move not in self.board.legal_moves:
            self._refresh()
            self.refuse("The engine had no legal move.")
            return

        text = describe.describe_move(self.board, move, self._phonetic())
        self.board.push(move)
        self.cursor = move.to_square
        self._refresh()
        if self.board.is_game_over(claim_draw=True):
            self.say("%s. %s" % (text, describe.describe_status(self.board)))
        else:
            self.say("%s. Your move." % text)

    # -- commands ----------------------------------------------------------

    def _handle_command(self, event):
        keysym = event.keysym
        key = keysym.lower()
        control = bool(event.state & 0x0004)

        if self._promotion_pending is not None:
            if key in PROMOTION_KEYS:
                self._finish_promotion(PROMOTION_KEYS[key])
            elif key == "escape":
                self._promotion_pending = None
                self.say("Promotion cancelled.")
            else:
                self.refuse("Press q, r, b, or n.")
            return

        if self._jump_buffer is not None:
            self._handle_jump(key)
            return

        if control:
            actions = {
                "n": self.new_game,
                "u": lambda: self.check_updates(quiet=False),
                "s": self.save_game,
                "q": self.quit_app,
            }
            if key in actions:
                actions[key]()
                return

        if keysym in ("Return", "KP_Enter", "space"):
            self._commit()
        elif keysym == "Escape":
            if self._knight_pending:
                self._knight_pending = {}
                self.say("Cancelled.")
            elif self.selected is not None:
                self._deselect()
            else:
                self.say(describe.describe_status(self.board))
        elif keysym in ("F1", "question", "slash"):
            self.say(HELP_TEXT)
        elif key == "c":
            self.say(describe.describe_square(self.board, self.cursor, self._phonetic()))
        elif key == "s":
            self.say(describe.describe_status(self.board))
        elif key == "v":
            self.say(describe.material_balance(self.board))
        elif key == "w":
            self.say(describe.list_pieces(self.board, chess.WHITE, self._phonetic()))
        elif key == "b":
            self.say(describe.list_pieces(self.board, chess.BLACK, self._phonetic()))
        elif key == "l":
            self._say_last_move()
        elif key == "m":
            self.say(describe.move_history(self.board, self._phonetic()))
        elif key == "f":
            self.say(self.board.fen())
        elif key == "j":
            self._jump_buffer = ""
            self.say("Jump to. Type a file letter then a rank number.")
        elif key == "k":
            self._jump_to_king()
        elif key == "h":
            self._hint()
        elif key == "u":
            self.take_back()
        elif keysym in ("plus", "equal", "KP_Add"):
            self._change_level(+1)
        elif keysym in ("minus", "KP_Subtract"):
            self._change_level(-1)
        elif keysym == "Home":
            self.cursor = chess.A1 if self.human_color == chess.WHITE else chess.H8
            self._refresh()
            self.say(describe.describe_square(self.board, self.cursor, self._phonetic()))

    def _say_last_move(self):
        if not self.board.move_stack:
            self.say("No moves yet.")
            return
        move = self.board.move_stack[-1]
        self.board.pop()
        try:
            text = describe.describe_move(self.board, move, self._phonetic())
        finally:
            self.board.push(move)
        self.say("Last move, %s" % text)

    def _handle_jump(self, key):
        if key == "escape":
            self._jump_buffer = None
            self.say("Cancelled.")
            return
        if not self._jump_buffer:
            if key in "abcdefgh":
                self._jump_buffer = key
            else:
                self._jump_buffer = None
                self.refuse("Not a file letter. Cancelled.")
            return
        if key in "12345678":
            square = chess.parse_square(self._jump_buffer + key)
            self._jump_buffer = None
            self.cursor = square
            self._refresh()
            self.say(describe.describe_square(self.board, square, self._phonetic()))
        else:
            self._jump_buffer = None
            self.refuse("Not a rank number. Cancelled.")

    def _jump_to_king(self):
        square = self.board.king(self.human_color)
        if square is None:
            self.refuse("No king on the board.")
            return
        self.cursor = square
        self._refresh()
        self.say("Your king. %s" % describe.describe_square(
            self.board, square, self._phonetic()))

    def _hint(self):
        """Ask the engine what it would play in your shoes. Opt in, on request."""
        if not self._human_to_move():
            self.refuse("Not your move.")
            return
        if self.thinking:
            self.refuse("Busy.")
            return
        self.say("Thinking about a hint.")
        self.thinking = True
        snapshot = self.board.copy()
        result = {}

        def work():
            try:
                result["move"] = self.opponent.play(snapshot)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def collect():
            if thread.is_alive():
                self.after(50, collect)
                return
            self.thinking = False
            self._refresh()
            if "move" in result and result["move"] is not None:
                self.say("Hint. %s" % describe.describe_move(
                    self.board, result["move"], self._phonetic()))
            else:
                self.refuse("No hint available.")

        self.after(50, collect)

    def take_back(self):
        """Undo your move and the reply, so a blunder is a lesson not a loss."""
        if self.thinking:
            self.refuse("Wait for the opponent to finish.")
            return
        if not self.board.move_stack:
            self.refuse("Nothing to take back.")
            return
        self.board.pop()
        if self.board.move_stack and self.board.turn != self.human_color:
            self.board.pop()
        self.selected = None
        self.ghost = None
        self._refresh()
        self.say("Taken back. %s" % describe.describe_status(self.board))

    def _change_level(self, delta):
        level = max(1, min(8, self.opponent.level + delta))
        self.opponent.set_level(level)
        self.settings["level"] = level
        save_settings(self.settings)
        self._refresh()
        self.say(self.opponent.describe())

    def new_game(self):
        self.board.reset()
        self.selected = None
        self.ghost = None
        self.cursor = chess.E1 if self.human_color == chess.WHITE else chess.E8
        self._refresh()
        self.say("New game. You play %s." % describe.COLOR_NAMES[self.human_color])
        if self.human_color == chess.BLACK:
            self.after(300, self._start_thinking)

    def save_game(self):
        game = chess.pgn.Game.from_board(self.board)
        game.headers["Event"] = "Helm Chess practice"
        white = "You" if self.human_color == chess.WHITE else self.opponent.name
        black = self.opponent.name if self.human_color == chess.WHITE else "You"
        game.headers["White"] = white
        game.headers["Black"] = black
        folder = os.path.dirname(settings_path())
        path = os.path.join(folder, "games.pgn")
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(str(game) + "\n\n")
            self.say("Game saved to %s" % path)
        except OSError as exc:
            self.refuse("Could not save: %s" % exc)

    # -- updates -----------------------------------------------------------

    def check_updates(self, quiet=True):
        """Ask GitHub whether there is a newer version. Never installs silently."""
        if not quiet:
            self.say("Checking for updates.")
        result = {}

        def work():
            try:
                result["value"] = updater.check_for_update()
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def collect():
            if thread.is_alive():
                self.after(200, collect)
                return
            if "error" in result:
                if not quiet:
                    self.refuse("Update check failed: %s" % result["error"])
                return
            available = result["value"]
            if available is None:
                if not quiet:
                    self.say("You are on the latest version, %s." % __version__)
                return
            latest, url, notes = available
            self._offer_update(latest, url, notes)

        self.after(200, collect)

    def _offer_update(self, latest, url, notes):
        self.say("Version %s is available. You have %s. Press y to install it, "
                 "or any other key to skip. %s" % (latest, __version__, notes[:200]))

        def on_answer(event):
            self.unbind("<KeyPress>", binding)
            self.bind("<KeyPress>", self._on_key_press)
            if event.keysym.lower() == "y":
                self._install_update(url)
            else:
                self.say("Update skipped.")
            return "break"

        self.unbind("<KeyPress>")
        binding = self.bind("<KeyPress>", on_answer)

    def _install_update(self, url):
        self.say("Downloading the update.")
        result = {}

        def work():
            try:
                result["files"] = updater.download_and_install(url)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def collect():
            if thread.is_alive():
                self.after(200, collect)
                return
            if "error" in result:
                self.refuse("Update failed: %s" % result["error"])
                return
            self.say("Update installed, %d files replaced. Close and reopen "
                     "Helm Chess to use the new version."
                     % len(result["files"]))

        self.after(200, collect)

    # -- shutdown ----------------------------------------------------------

    def quit_app(self):
        for timer in self._timers:
            try:
                self.after_cancel(timer)
            except Exception:
                pass
        self._timers = []
        try:
            self.opponent.close()
        except Exception:
            pass
        save_settings(self.settings)
        self.destroy()


HELP_TEXT = (
    "Helm Chess keys. "
    "Arrow keys move the cursor around the board when nothing is selected. "
    "Two arrows at the same time move diagonally. "
    "Enter picks up the piece under the cursor. "
    "Once a piece is held, the arrows steer it, and two arrows together move it "
    "diagonally. A knight needs two arrows together for the corner you want. "
    "Enter again makes the move. Escape puts the piece back. "
    "Shift with the arrows says what lies that way without moving. "
    "C says the current square. S says whose move it is. "
    "W and B read the white and black pieces. V gives the material count. "
    "L repeats the last move. M reads the whole game. F gives the position code. "
    "J jumps to a square you type. K jumps to your king. "
    "H asks for a hint. U takes back your last move. "
    "Plus and minus change the opponent's strength. "
    "Control N starts a new game. Control S saves the game. "
    "Control U checks for updates. Control Q quits."
)


def main():
    parser = argparse.ArgumentParser(description="Helm Chess, a keyboard chess client.")
    parser.add_argument("--black", action="store_true", help="play as black")
    parser.add_argument("--white", action="store_true", help="play as white")
    parser.add_argument("--level", type=int, help="opponent strength, 1 to 8")
    parser.add_argument("--no-stockfish", action="store_true",
                        help="always use the built-in engine")
    parser.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    args = parser.parse_args()

    settings = load_settings()
    if args.black:
        settings["play_as"] = "black"
    if args.white:
        settings["play_as"] = "white"
    if args.level:
        settings["level"] = max(1, min(8, args.level))
    if args.no_stockfish:
        settings["prefer_stockfish"] = False

    app = HelmChess(settings)
    if app.human_color == chess.BLACK:
        app.after(1200, app._start_thinking)
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
