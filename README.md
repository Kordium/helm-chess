# Helm Chess

**H**ear **E**very **L**egal **M**ove.

A chess client you play entirely from the keyboard, built for screen reader
users. Instead of typing coordinates, you steer: walk a cursor around the
board, pick up a piece, and then drive that piece where you want it. If a
move is not legal, the piece simply will not go there, and you are told why.

Helm Chess is an independent project. It is not affiliated with, endorsed
by, or derived from any other chess product, and it shares no code with one.

It runs on any computer that can run Python. No graphics card, no browser,
no account, no internet connection needed to play.

## Installing

1. Install Python 3.8 or newer from <https://www.python.org/downloads/>.
   During setup, tick **Add python.exe to PATH**.
2. Download this project (green **Code** button, then **Download ZIP**) and
   unzip it somewhere you can find again.
3. Run the installer:
   - On Windows, double-click `install.bat`.
   - Or from a command prompt, in the project folder: `python install.py`

The installer checks your Python, installs the two libraries the game needs,
tells you whether Stockfish was found, and offers a desktop shortcut.

To see what it would do without changing anything: `python install.py --check`

## Playing

Start it from the desktop shortcut, or with:

```bash
python helm_chess.py
```

It opens on the **main menu**, not on a board. Up and down walk the list,
enter chooses:

1. **Start game** — asks which difficulty, 1 to 8, each one described. Pick
   one and the game begins.
2. **Settings** — see below.
3. **Exit** — asks whether you are sure first.

While playing, **shift and escape** asks whether you want to close the
program. The safe answer comes first, so pressing enter straight away keeps
the game open. Plain escape on its own still just puts down a piece you are
holding. **F10** reopens the main menu at any time.

Useful switches: `--black` to play black, `--level 5` to preselect the
opponent's strength, `--no-stockfish` to always use the built-in engine.

## The keys

Press **F1** at any time to hear this list read out.

### Moving around

With nothing picked up, the arrow keys walk a cursor around the board, and
every square is announced as you land on it.

Two arrows **at the same time** move diagonally. Up and right together goes
up-right one square. This is the same idea everywhere in the game: if a
direction needs two dimensions, it needs two keys.

### Moving a piece

- **Enter** picks up the piece under the cursor. You hear what it is and how
  many legal moves it has.
- The arrow keys now steer that piece, one square per press. Two arrows
  together steer it diagonally.
- A **knight** cannot be walked, so press the two arrows for the corner you
  want. If both of that corner's L-shapes are available, the game names them
  and you press one more arrow, the direction of the long leg, to choose.
- **Enter** again plays the move. **Escape** puts the piece back.

Anything illegal is refused with a reason: "blocked by your own pawn",
"that would leave your king in check", "a bishop cannot move to e5".

Sometimes a piece has to travel over squares it is not allowed to stop on.
When you are in check, a bishop's only legal move might be the square three
along that blocks it, and every square on the way is illegal by itself. Those
are announced as "c4, empty, cannot stop here" and you simply keep going. If
you try to commit there it says so rather than just refusing.

Castling needs no special key. Pick up the king and walk it two squares
towards the rook; it is announced as castling before you commit.

Promotion asks which piece: **q**, **r**, **b**, or **n**.

### Hearing the position

- **Shift and arrows** say what lies in that direction without moving
  anything. With a piece held, it lists every legal move that way.
- **C** says the square the cursor is on.
- **S** says whose move it is, and whether anyone is in check.
- **W** and **B** read out all the white or black pieces and where they are.
- **V** gives the material count and who is ahead.
- **L** repeats the last move. **M** reads the whole game so far.
- **F** gives the position code (FEN), for pasting elsewhere.
- **J** jumps the cursor to a square you type, like `j` then `c` then `5`.
- **K** jumps to your king.

### The game

- **H** asks the engine for a hint.
- **U** takes back your last move and the reply, so a blunder becomes a
  lesson instead of a lost game.
- **O** opens the settings menu. **F10** opens the main menu.
- **Plus** and **minus** change the opponent's strength, 1 to 8.
- **Control N** starts a new game at the difficulty you are on. **Control S**
  saves the game to a PGN file. **Control U** checks for updates.
- **Shift and escape** asks whether you want to close the program.

## The opponent

The opponent plays honestly. It is handed the same position you are looking
at, it plays legal moves, it does not take moves back, and it does not read
anything it should not. Lower strength settings make it think less deeply.
They do not make it throw pieces away on purpose, so a win at level 3 is a
real win at level 3.

If **Stockfish** is on your computer, the game uses it and limits its rating
to match the level you chose. Download it from
<https://stockfishchess.org/download/> and put the executable in an
`engines` folder next to the game, or anywhere on your PATH.

If Stockfish is not there, a small engine built into the game plays instead.
It is written in plain Python, uses one core, and needs no installation.
Level 8 will take a few seconds a move on a modest machine.

## Updates

The game checks for a new version when it starts and tells you if one is
available. It never installs anything without you pressing **y**.

To check at any time, press **Control U**, or from the project folder:

```bash
python updater.py
```

Add `--check` to see what is available without installing it. The updater
keeps a copy of the previous version in `.update-backup`, and restores it if
anything goes wrong partway through.

## Settings

Press **O** to open the settings menu. Up and down walk the list, left and
right change the setting under you, and escape closes and saves. Each entry
reads out its name, how it is currently set, and what it does. Nothing is a
dialog box; it is all spoken.

- **Inverted mode** (off by default). When playing as black, should the
  board face you like a real chess board, or should it stay as if you were
  playing white? Off means the board faces you, so up is always forward for
  your own pieces. On leaves the board the way white sees it, which means
  you play top down and up moves your pieces backwards.
- **Opponent strength**, 1 to 8.
- **You play**, white or black. Applies at the next new game.
- **Phonetic squares**. Says "echo 4" instead of "e4", for synthesisers that
  mangle single letters next to digits.
- **Diagonal timing**. How long the game waits for a second arrow key before
  deciding you meant a single direction. It starts at 90 milliseconds. Raise
  it if diagonals are not registering, lower it if single presses feel slow.
- **Sound effects**, **Use Stockfish when available**, and **Check for
  updates on start**.

Settings and saved games live in `%APPDATA%\HelmChess`, not in the project
folder, so updating the game never disturbs them.

## Checking it still works

```bash
python selftest.py
```

This drives the real game through real key presses, chords included, and
checks both what it does and what it says. It is silent: the speech is
captured rather than spoken. Run it after changing anything.

## What it needs

- Python 3.8 or newer, with tkinter (included in the standard Windows
  installer)
- `chess` for the rules
- `accessible_output2` for speech through NVDA, JAWS, or SAPI

The installer handles the last two.

## Licence

MIT. See `LICENSE`.
