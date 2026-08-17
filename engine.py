"""The opponent.

Two implementations, same interface:

* `StockfishOpponent` drives a Stockfish binary over UCI, if one is found.
* `BuiltinOpponent` is a small alpha-beta searcher in pure Python, so the
  game always has an opponent even on a machine with nothing installed.

Neither one ever sees anything you don't: they get the same `chess.Board`,
they play legal moves, and they do not take moves back or look at the clock.
Strength is lowered by thinking less, never by being fed secrets or by
deliberately hanging pieces.
"""

import os
import shutil
import time

import chess

try:
    import chess.engine as uci_engine
except Exception:  # pragma: no cover - only if python-chess is trimmed down
    uci_engine = None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Square bonuses from white's point of view, index 0 = a1.
_PAWN_TABLE = [
      0,  0,  0,  0,  0,  0,  0,  0,
      5, 10, 10,-20,-20, 10, 10,  5,
      5, -5,-10,  0,  0,-10, -5,  5,
      0,  0,  0, 20, 20,  0,  0,  0,
      5,  5, 10, 25, 25, 10,  5,  5,
     10, 10, 20, 30, 30, 20, 10, 10,
     50, 50, 50, 50, 50, 50, 50, 50,
      0,  0,  0,  0,  0,  0,  0,  0,
]
_KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
_BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
_ROOK_TABLE = [
      0,  0,  5, 10, 10,  5,  0,  0,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
      5, 10, 10, 10, 10, 10, 10,  5,
      0,  0,  0,  0,  0,  0,  0,  0,
]
_QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -10,  5,  5,  5,  5,  5,  0,-10,
      0,  0,  5,  5,  5,  5,  0, -5,
     -5,  0,  5,  5,  5,  5,  0, -5,
    -10,  0,  5,  5,  5,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
_KING_TABLE = [
     20, 30, 10,  0,  0, 10, 30, 20,
     20, 20,  0,  0,  0,  0, 20, 20,
    -10,-20,-20,-20,-20,-20,-20,-10,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
]

_TABLES = {
    chess.PAWN: _PAWN_TABLE,
    chess.KNIGHT: _KNIGHT_TABLE,
    chess.BISHOP: _BISHOP_TABLE,
    chess.ROOK: _ROOK_TABLE,
    chess.QUEEN: _QUEEN_TABLE,
    chess.KING: _KING_TABLE,
}

MATE_SCORE = 100000


def evaluate(board):
    """Score the position in centipawns, positive meaning good for the side to move."""
    if board.is_checkmate():
        return -MATE_SCORE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    for square, piece in board.piece_map().items():
        table = _TABLES[piece.piece_type]
        index = square if piece.color == chess.WHITE else chess.square_mirror(square)
        value = PIECE_VALUES[piece.piece_type] + table[index]
        score += value if piece.color == chess.WHITE else -value

    # A small nudge towards having options, which keeps the weak levels from
    # shuffling the same piece back and forth.
    score += 5 * (len(board.attacks(board.king(chess.WHITE))) -
                  len(board.attacks(board.king(chess.BLACK))))

    return score if board.turn == chess.WHITE else -score


class SearchTimeout(Exception):
    pass


class BuiltinOpponent:
    """Alpha-beta with quiescence and iterative deepening, in pure Python.

    Level 1-8 maps to how deep and how long it is allowed to think. Nothing
    else changes, so a higher level is genuinely a better player rather than
    the same player told to blunder less.
    """

    LEVELS = {
        1: (1, 0.10),
        2: (2, 0.25),
        3: (2, 0.60),
        4: (3, 1.00),
        5: (3, 2.00),
        6: (4, 3.00),
        7: (4, 5.00),
        8: (5, 8.00),
    }

    name = "built-in engine"

    def __init__(self, level=3):
        self.set_level(level)
        self.nodes = 0
        self._deadline = 0.0

    def set_level(self, level):
        self.level = max(1, min(8, int(level)))
        self.max_depth, self.time_budget = self.LEVELS[self.level]

    def describe(self):
        return "built-in engine, level %d of 8" % self.level

    def close(self):
        pass

    # -- search ------------------------------------------------------------

    def play(self, board):
        self.nodes = 0
        self._deadline = time.monotonic() + self.time_budget

        legal = list(board.legal_moves)
        if not legal:
            return None
        if len(legal) == 1:
            return legal[0]

        best = legal[0]
        for depth in range(1, self.max_depth + 1):
            try:
                move = self._search_root(board, depth, best)
            except SearchTimeout:
                break
            if move is not None:
                best = move
        return best

    def _search_root(self, board, depth, previous_best):
        alpha, beta = -MATE_SCORE * 2, MATE_SCORE * 2
        best_move = None
        for move in self._ordered_moves(board, previous_best):
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha)
            finally:
                board.pop()
            if score > alpha:
                alpha = score
                best_move = move
        return best_move

    def _negamax(self, board, depth, alpha, beta):
        if self.nodes % 512 == 0 and time.monotonic() > self._deadline:
            raise SearchTimeout()
        self.nodes += 1

        if board.is_checkmate():
            return -MATE_SCORE + board.ply()
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        if board.can_claim_fifty_moves() or board.is_repetition(3):
            return 0
        if depth <= 0:
            return self._quiescence(board, alpha, beta)

        for move in self._ordered_moves(board):
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha)
            finally:
                board.pop()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _quiescence(self, board, alpha, beta):
        """Keep looking while captures are still flying, so we don't stop mid-trade."""
        if self.nodes % 512 == 0 and time.monotonic() > self._deadline:
            raise SearchTimeout()
        self.nodes += 1

        stand_pat = evaluate(board)
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        for move in self._ordered_moves(board, captures_only=True):
            board.push(move)
            try:
                score = -self._quiescence(board, -beta, -alpha)
            finally:
                board.pop()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _ordered_moves(self, board, first=None, captures_only=False):
        """Try the promising moves first so alpha-beta can prune more."""
        moves = []
        for move in board.legal_moves:
            capture = board.is_capture(move)
            if captures_only and not capture and not move.promotion:
                continue
            score = 0
            if move == first:
                score = 10000
            elif capture:
                victim = board.piece_at(move.to_square)
                attacker = board.piece_at(move.from_square)
                victim_value = PIECE_VALUES[victim.piece_type] if victim else 100
                attacker_value = PIECE_VALUES[attacker.piece_type] if attacker else 0
                score = 1000 + victim_value - attacker_value // 10
            if move.promotion:
                score += 900
            moves.append((score, move))
        moves.sort(key=lambda pair: pair[0], reverse=True)
        return [move for _, move in moves]


class StockfishOpponent:
    """A Stockfish process, kept small: one thread, 16 MB of hash."""

    name = "Stockfish"

    def __init__(self, path, level=3):
        if uci_engine is None:
            raise RuntimeError("python-chess UCI support is unavailable")
        self.path = path
        self.engine = uci_engine.SimpleEngine.popen_uci(path)
        try:
            self.engine.configure({"Threads": 1, "Hash": 16})
        except Exception:
            pass
        self.set_level(level)

    def set_level(self, level):
        self.level = max(1, min(8, int(level)))
        # 1320 is the lowest rating Stockfish will admit to.
        self.elo = 1320 + (self.level - 1) * 240
        self.think_time = min(0.1 + 0.15 * self.level, 1.5)
        try:
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": self.elo})
        except Exception:
            # Older builds use Skill Level instead.
            try:
                self.engine.configure({"Skill Level": max(0, self.level * 2 - 2)})
            except Exception:
                pass

    def describe(self):
        return "Stockfish, level %d of 8, about %d elo" % (self.level, self.elo)

    def play(self, board):
        result = self.engine.play(board, uci_engine.Limit(time=self.think_time))
        return result.move

    def close(self):
        try:
            self.engine.quit()
        except Exception:
            pass


def find_stockfish(extra_paths=()):
    """Look for a Stockfish binary next to the app, then on PATH."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = list(extra_paths)
    candidates += [
        os.path.join(here, "engines", "stockfish.exe"),
        os.path.join(here, "engines", "stockfish"),
        os.path.join(here, "stockfish.exe"),
        os.path.join(here, "stockfish"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return shutil.which("stockfish")


def create_opponent(level=3, prefer_stockfish=True, stockfish_path=None):
    """Best available opponent, with the reason we picked it."""
    if prefer_stockfish:
        path = find_stockfish([stockfish_path] if stockfish_path else ())
        if path:
            try:
                return StockfishOpponent(path, level), "Stockfish found at %s" % path
            except Exception as exc:
                return (
                    BuiltinOpponent(level),
                    "Stockfish failed to start (%s), using the built-in engine" % exc,
                )
    return BuiltinOpponent(level), "using the built-in engine"
