# Changelog

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
