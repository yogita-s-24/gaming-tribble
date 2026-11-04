# Tribble Run

An original side-scrolling platformer written in Python with pygame. Guide Tribble, a fuzzy purple
creature, through the level. Stomp the spiky Grumbles, bump bonus blocks for coins, break bricks,
jump the pits and reach the flag before time runs out.

## Run it

```bash
pip install -r requirements.txt
python tribble_run.py
```

## Controls

| Key                     | Action                        |
|-------------------------|-------------------------------|
| Left / Right or A / D   | Move                          |
| Space / Up / W / Z      | Jump (hold for a higher jump) |
| Shift / X               | Run                           |
| P                       | Pause                         |
| Enter                   | Start / restart               |
| Esc                     | Quit                          |

## Gameplay

- **Stomp** enemies by landing on them. Chaining stomps without touching the ground scores more.
- **Bonus blocks** (gold with a gem) give a coin. **Bricks** break when you hit them from below.
  Hitting a block knocks out any enemy standing on it.
- Every 100 coins gives you an extra life.
- The higher you grab the flagpole, the bigger the bonus. Any time left over is added to your score.

## Make your own level

Edit `build_level()` in `tribble_run.py`. The level is a grid 12 tiles tall. Row 9 is the row
just above the ground. Use these helpers:

- `put(x, y, ch)` places one tile
- `hline(x0, x1, y, ch)` places a horizontal row of tiles
- `column(x, height)` places a stone pillar standing on the ground
- `gaps` lists the pits
- `enemies` lists where the Grumbles start

Tile characters: `#` ground, `B` brick, `?` bonus block, `S` stone, `C` coin.
