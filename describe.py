"""Turning chess positions and moves into sentences worth listening to."""

import chess

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

COLOR_NAMES = {chess.WHITE: "white", chess.BLACK: "black"}

# Spoken one letter at a time, because "b4" and "before" collide badly and
# some synthesisers swallow a bare letter next to a digit.
PHONETIC = {
    "a": "alpha", "b": "bravo", "c": "charlie", "d": "delta",
    "e": "echo", "f": "foxtrot", "g": "golf", "h": "hotel",
}


def square_name(square, phonetic=False):
    name = chess.square_name(square)
    if phonetic:
        return "%s %s" % (PHONETIC[name[0]], name[1])
    return name


def piece_name(piece, with_color=True):
    if piece is None:
        return "empty"
    name = PIECE_NAMES[piece.piece_type]
    if with_color:
        return "%s %s" % (COLOR_NAMES[piece.color], name)
    return name


def describe_square(board, square, phonetic=False):
    """"e4, white pawn" or "e4, empty"."""
    piece = board.piece_at(square)
    return "%s, %s" % (square_name(square, phonetic), piece_name(piece))


def describe_move(board, move, phonetic=False):
    """Describe `move` in the position *before* it is played."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        return move.uci()

    if board.is_kingside_castling(move):
        text = "%s castles kingside" % COLOR_NAMES[piece.color]
    elif board.is_queenside_castling(move):
        text = "%s castles queenside" % COLOR_NAMES[piece.color]
    else:
        text = "%s %s to %s" % (
            piece_name(piece),
            square_name(move.from_square, phonetic),
            square_name(move.to_square, phonetic),
        )
        if board.is_en_passant(move):
            text += ", captures pawn en passant"
        else:
            captured = board.piece_at(move.to_square)
            if captured is not None:
                text += ", captures %s" % piece_name(captured)
        if move.promotion:
            text += ", promotes to %s" % PIECE_NAMES[move.promotion]

    if board.gives_check(move):
        # Play it out to tell check apart from mate.
        board.push(move)
        try:
            if board.is_checkmate():
                text += ", checkmate"
            else:
                text += ", check"
        finally:
            board.pop()
    return text


def describe_destination(board, move, phonetic=False):
    """Short announcement for a landing square while steering a piece."""
    parts = [square_name(move.to_square, phonetic)]
    if board.is_en_passant(move):
        parts.append("captures pawn en passant")
    else:
        captured = board.piece_at(move.to_square)
        parts.append("captures %s" % piece_name(captured) if captured else "empty")
    if board.is_kingside_castling(move):
        parts = [square_name(move.to_square, phonetic), "castles kingside"]
    elif board.is_queenside_castling(move):
        parts = [square_name(move.to_square, phonetic), "castles queenside"]
    # python-chess hands back a concrete promotion move, but while you are
    # still steering, the piece has not been chosen yet -- so say so either way.
    if _is_promotion_square(board, move):
        parts.append("promotion")
    if board.gives_check(move):
        board.push(move)
        try:
            parts.append("checkmate" if board.is_checkmate() else "check")
        finally:
            board.pop()
    return ", ".join(parts)


def _is_promotion_square(board, move):
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return False
    rank = chess.square_rank(move.to_square)
    return rank == 7 if piece.color == chess.WHITE else rank == 0


def describe_status(board):
    """Whose move it is, plus any check or game-over state."""
    outcome = board.outcome(claim_draw=True)
    if outcome is not None:
        if outcome.winner is None:
            return "Draw by %s" % outcome.termination.name.lower().replace("_", " ")
        return "Checkmate, %s wins" % COLOR_NAMES[outcome.winner]
    text = "%s to move" % COLOR_NAMES[board.turn]
    if board.is_check():
        text += ", check"
    return text


def list_pieces(board, color, phonetic=False):
    """Read out one side's material, heaviest first."""
    order = [chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
    chunks = []
    for piece_type in order:
        squares = sorted(board.pieces(piece_type, color))
        if not squares:
            continue
        names = ", ".join(square_name(s, phonetic) for s in squares)
        label = PIECE_NAMES[piece_type]
        if len(squares) > 1:
            label += "s"
        chunks.append("%s on %s" % (label, names))
    if not chunks:
        return "%s has no pieces" % COLOR_NAMES[color]
    return "%s: %s" % (COLOR_NAMES[color], ". ".join(chunks))


def material_balance(board):
    """Point count for each side, phrased as an advantage."""
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    totals = {}
    for color in (chess.WHITE, chess.BLACK):
        totals[color] = sum(
            len(board.pieces(pt, color)) * val for pt, val in values.items()
        )
    white, black = totals[chess.WHITE], totals[chess.BLACK]
    if white == black:
        return "Material level, %d points each" % white
    leader = chess.WHITE if white > black else chess.BLACK
    return "White %d, black %d. %s is up %d" % (
        white, black, COLOR_NAMES[leader].capitalize(), abs(white - black),
    )


def move_history(board, phonetic=False, limit=None):
    """Replay the game so far as spoken moves."""
    if not board.move_stack:
        return "No moves yet"
    replay = chess.Board()
    lines = []
    for i, move in enumerate(board.move_stack):
        text = describe_move(replay, move, phonetic)
        if replay.turn == chess.WHITE:
            lines.append("%d. %s" % (i // 2 + 1, text))
        else:
            lines.append(text)
        replay.push(move)
    if limit:
        lines = lines[-limit:]
    return ". ".join(lines)


def render_board(board, cursor=None, selected=None, ghost=None):
    """Plain-text board for the window, mostly for anyone watching over a shoulder."""
    lines = []
    for rank in range(7, -1, -1):
        cells = []
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            symbol = piece.symbol() if piece else "."
            if square == ghost and ghost != selected:
                cell = "[%s]" % symbol
            elif square == selected:
                cell = "<%s>" % symbol
            elif square == cursor:
                cell = "(%s)" % symbol
            else:
                cell = " %s " % symbol
            cells.append(cell)
        lines.append("%d %s" % (rank + 1, "".join(cells)))
    lines.append("   " + "  ".join("abcdefgh"))
    return "\n".join(lines)
