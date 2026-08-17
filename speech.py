"""Speech output for Helm Chess.

Talks to whatever screen reader is running (NVDA, JAWS, ...) through
accessible_output2, and falls back to SAPI or plain stdout if none is
available. Nothing here is chess-specific.
"""

import sys

_output = None
_kind = "none"

try:
    from accessible_output2.outputs.auto import Auto

    _output = Auto()
    _kind = type(_output.get_first_available_output()).__name__
except Exception:
    try:
        from accessible_output2.outputs.sapi5 import SAPI5

        _output = SAPI5()
        _kind = "SAPI5"
    except Exception:
        _output = None
        _kind = "stdout"


def backend():
    """Name of the speech backend in use, for the startup announcement."""
    return _kind


def speak(text, interrupt=True):
    """Say `text`. Interrupts whatever is being spoken unless told not to."""
    if not text:
        return
    if _output is None:
        print(text)
        sys.stdout.flush()
        return
    try:
        _output.speak(text, interrupt=interrupt)
    except Exception:
        print(text)
        sys.stdout.flush()


def speak_all(parts, interrupt=True):
    """Say several fragments as one utterance, skipping empty ones."""
    text = ". ".join(p for p in parts if p)
    speak(text, interrupt=interrupt)
