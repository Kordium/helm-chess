# Changelog

## 1.0.5

- The game now opens on a **main menu**: start game, settings, exit. Start
  game asks which difficulty first, with each level described, and the game
  begins once you pick one.
- **Shift and escape** asks whether you really want to close the program.
  The safe answer comes first, so enter keeps the game open. Plain escape
  still just puts down a piece. **F10** reopens the main menu.
- Fixed the opening announcement, which used to read out a square and a
  piece as though you had selected the king.
- Fixed a bug that could make a legal move impossible to play. When you are
  in check, a bishop or rook often has one legal square several squares
  away, and every square on the route is illegal on its own. The piece now
  travels over them, announced as "cannot stop here", instead of the step
  being refused and the move being unreachable.

## 1.0.4

- The `sounds` folder is now replaced wholesale on update rather than merged
  into. Rename or drop a sound and no orphan is left behind, so what you
  have on disk is always exactly what the release shipped.
- Two things keep that safe. A folder is only touched when the download
  actually contains it with files in it, so a release that forgot to include
  one cannot wipe yours. And the old contents go to `.update-backup` first.
- Your own `engines` folder is still never touched, so an update cannot
  delete a Stockfish you installed yourself.

## 1.0.3

- The sword unsheathe is now the capture sound, replacing the two sword
  clashes.
- Picking a piece up has no sound for the moment, on purpose, until there is
  one that tells it apart from a capture.

## 1.0.2

- Added a `sounds` folder of sword and impact effects, all Creative Commons
  0, credited in `sounds/CREDITS.txt`. They are not wired into the game yet.
- The updater now keeps bundled folders such as `sounds` in step with the
  rest of the game. Your own `engines` folder is deliberately left alone, so
  an update never deletes a Stockfish you installed yourself.

## 1.0.1

- New settings menu, opened with **O**. Walk it with up and down, change
  things with left and right, escape to close. Every entry reads out its
  name, its current value, and what it does.
- New **inverted mode** setting. Off by default, where the board faces you
  like a real game. On leaves the board the way white sees it, so as black
  you play top down.
- Fixed: as black, a knight with two moves in the same corner could not be
  moved at all. The game asked which one you wanted, then ignored both
  answers, because it stored them as screen directions and read them back as
  board directions.
- Fixed: an engine reply arriving after a new game or a takeback is now
  discarded instead of being played into the new position.
- Fixed: alt-tabbing away while holding an arrow key no longer leaves that
  arrow stuck and unusable.
- Added this changelog, so the updater can tell you what changed before you
  install it.

## 1.0.0

First release.

- Cursor navigation with the arrow keys, every square announced.
- Pick a piece up with enter, then steer it. Two arrows pressed together for
  anything diagonal.
- Knights are steered by the corner, with a follow-up arrow to choose the L
  when both are available.
- Illegal moves refused with a spoken reason.
- Castling by walking the king two squares; promotion asks which piece.
- Shift with the arrows previews a direction without moving anything.
- Speech through NVDA, JAWS, or SAPI.
- Built-in pure-Python opponent, or Stockfish when installed, at eight levels.
- Installer, self-updater, and a self-test that drives the real key handling.
