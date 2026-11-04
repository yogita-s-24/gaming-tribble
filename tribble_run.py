"""
Tribble Run - an original side-scrolling platformer made with pygame.

Controls
    Left / Right  or  A / D   move
    Space / Up / W / Z        jump (hold for a higher jump)
    Shift / X                 run
    P                         pause
    Enter                     start / restart
    Esc                       quit
"""
import math
import random
import sys

import pygame

# --------------------------------------------------------------------------- settings
WIDTH, HEIGHT = 800, 480
TILE = 40
ROWS = HEIGHT // TILE  # 12 rows of tiles
FPS = 60

GRAVITY = 0.6
MAX_FALL = 14.0
GROUND_ACCEL = 0.45
AIR_ACCEL = 0.30
FRICTION = 0.82
WALK_SPEED = 4.5
RUN_SPEED = 7.0
JUMP_SPEED = 13.0
JUMP_CUT = 4.0          # releasing jump early caps upward speed -> short hop
STOMP_BOUNCE = 8.0
COYOTE_FRAMES = 6       # can still jump a few frames after leaving a ledge
JUMP_BUFFER_FRAMES = 7  # jump pressed slightly before landing still counts
START_LIVES = 3
START_TIME = 300

# Tile legend:  # ground   B brick   ? bonus block   U used block   S stone   C coin
SOLID = set("#BS?U")

JUMP_KEYS = (pygame.K_SPACE, pygame.K_UP, pygame.K_w, pygame.K_z)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
SKY_TOP = (105, 165, 255)
SKY_BOTTOM = (195, 228, 255)
HILL = (118, 192, 120)
HILL_DARK = (96, 168, 100)
FUR = (165, 95, 215)
FUR_DARK = (118, 62, 168)
FUR_LIGHT = (226, 192, 246)
FOOT = (90, 45, 120)
ENEMY = (196, 74, 52)
ENEMY_DARK = (128, 40, 30)
ENEMY_FOOT = (60, 30, 20)
COIN = (255, 210, 40)
COIN_DARK = (200, 140, 10)


# --------------------------------------------------------------------------- level
def build_level():
    """Build the level grid. Edit this function to design your own stages."""
    width = 170
    g = [[" "] * width for _ in range(ROWS)]

    def put(x, y, ch):
        g[y][x] = ch

    def hline(x0, x1, y, ch):
        for x in range(x0, x1 + 1):
            g[y][x] = ch

    def column(x, height):  # stone column standing on the ground
        for i in range(height):
            g[9 - i][x] = "S"

    # ground (rows 10-11) with pits
    gaps = [(38, 40), (71, 73), (118, 120)]
    for x in range(width):
        if not any(a <= x <= b for a, b in gaps):
            g[10][x] = g[11][x] = "#"

    # section 1 - warm-up
    put(10, 6, "?")
    hline(14, 18, 6, "B")
    put(15, 6, "?")
    put(17, 6, "?")
    column(23, 2)
    column(30, 3)
    for x, y in [(36, 8), (37, 7), (38, 6), (39, 6), (40, 7), (41, 8)]:
        put(x, y, "C")

    # section 2 - floating platform and a plateau
    hline(45, 52, 7, "B")
    hline(46, 51, 6, "C")
    put(48, 3, "?")
    put(49, 3, "?")
    hline(56, 58, 6, "?")
    for i in range(4):
        column(63 + i, i + 1)
    for x in range(67, 71):
        column(x, 4)

    # section 3 - brick bridges
    hline(80, 84, 7, "B")
    put(82, 7, "?")
    hline(87, 93, 4, "B")
    hline(88, 92, 3, "C")
    column(97, 2)
    column(104, 3)
    hline(108, 112, 6, "B")
    put(110, 6, "?")
    for x, y in [(117, 8), (118, 7), (119, 6), (120, 7), (121, 8)]:
        put(x, y, "C")

    # section 4 - final run and staircase
    put(126, 6, "?")
    put(128, 6, "B")
    put(130, 6, "?")
    hline(134, 136, 6, "C")
    for i in range(6):
        column(140 + i, i + 1)
    column(146, 6)

    goal_x = 154
    put(goal_x, 9, "S")  # base of the flagpole

    enemies = [(19, 9), (27, 9), (34, 9), (48, 6), (53, 9), (59, 9), (60, 9),
               (78, 9), (86, 9), (90, 9), (92, 9), (100, 9), (113, 9),
               (128, 9), (131, 9), (135, 9)]
    player_spawn = (3, 9)
    return g, enemies, player_spawn, goal_x


class Level:
    def __init__(self):
        self.grid, self.enemy_spawns, self.player_spawn, self.goal_x = build_level()
        self.width = len(self.grid[0])
        self.pixel_width = self.width * TILE
        self.bumps = {}  # (tx, ty) -> frames left in bump animation

        self.pole_x = self.goal_x * TILE + TILE // 2 - 3
        self.pole_top = 20
        self.pole_bottom = 9 * TILE
        self.goal_rect = pygame.Rect(self.pole_x - 4, self.pole_top,
                                     14, self.pole_bottom - self.pole_top)

    def tile(self, tx, ty):
        if ty < 0 or ty >= ROWS:
            return " "
        if tx < 0 or tx >= self.width:
            return "#"  # invisible walls at both ends
        return self.grid[ty][tx]

    def is_solid(self, tx, ty):
        return self.tile(tx, ty) in SOLID

    def tiles_in(self, rect):
        for ty in range(rect.top // TILE, (rect.bottom - 1) // TILE + 1):
            for tx in range(rect.left // TILE, (rect.right - 1) // TILE + 1):
                yield tx, ty

    def solids_in(self, rect):
        return [(tx, ty) for tx, ty in self.tiles_in(rect) if self.is_solid(tx, ty)]


# --------------------------------------------------------------------------- entities
class Body:
    """Something with a position, a velocity and tile collision."""

    def __init__(self, x, y, w, h):
        self.x, self.y = float(x), float(y)
        self.w, self.h = w, h
        self.vx = self.vy = 0.0

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def move_x(self, level):
        self.x += self.vx
        hit = False
        for tx, ty in level.solids_in(self.rect):
            tile = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
            if not self.rect.colliderect(tile):
                continue
            if self.vx > 0:
                self.x = tile.left - self.w
            elif self.vx < 0:
                self.x = tile.right
            hit = True
        if hit:
            self.vx = 0.0
        return hit

    def move_y(self, level):
        """Returns (on_ground, list of tiles bumped from below)."""
        self.y += self.vy
        landed, bumped = False, []
        for tx, ty in level.solids_in(self.rect):
            tile = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
            if not self.rect.colliderect(tile):
                continue
            if self.vy > 0:
                self.y = tile.top - self.h
                landed = True
            elif self.vy < 0:
                self.y = tile.bottom
                bumped.append((tx, ty))
        if landed or bumped:
            self.vy = 0.0
        if not landed and self.vy >= 0:
            landed = bool(level.solids_in(self.rect.move(0, 1)))
        return landed, bumped


class Player(Body):
    def __init__(self, x, y):
        super().__init__(x, y, 28, 34)
        self.on_ground = False
        self.facing = 1
        self.coyote = 0
        self.jump_buffer = 0
        self.walk_anim = 0.0
        self.stomp_chain = 0

    def update(self, keys, level, jump_pressed):
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        run = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or keys[pygame.K_x]
        jump_held = any(keys[k] for k in JUMP_KEYS)

        # horizontal movement
        direction = int(right) - int(left)
        top_speed = RUN_SPEED if run else WALK_SPEED
        if direction:
            accel = GROUND_ACCEL if self.on_ground else AIR_ACCEL
            if self.vx * direction < 0:
                accel *= 2  # turning around is snappier
            new_vx = self.vx + direction * accel
            if abs(new_vx) <= top_speed or abs(new_vx) < abs(self.vx):
                self.vx = new_vx
            else:  # over the speed limit (e.g. let go of run): ease down
                self.vx = math.copysign(max(top_speed, abs(self.vx) - 0.2), self.vx)
            self.facing = direction
        else:
            self.vx *= FRICTION if self.on_ground else 0.98
            if abs(self.vx) < 0.1:
                self.vx = 0.0

        # jumping (with coyote time and jump buffering)
        if jump_pressed:
            self.jump_buffer = JUMP_BUFFER_FRAMES
        else:
            self.jump_buffer = max(0, self.jump_buffer - 1)
        self.coyote = COYOTE_FRAMES if self.on_ground else max(0, self.coyote - 1)
        if self.jump_buffer and self.coyote:
            self.vy = -(JUMP_SPEED + abs(self.vx) * 0.15)
            self.jump_buffer = self.coyote = 0
            self.on_ground = False
        if not jump_held and self.vy < -JUMP_CUT:
            self.vy = -JUMP_CUT

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.move_x(level)
        self.on_ground, bumped = self.move_y(level)
        if self.on_ground:
            self.stomp_chain = 0
            self.walk_anim += abs(self.vx) * 0.08
        return bumped


class Enemy(Body):
    SPEED = 1.1

    def __init__(self, x, y):
        super().__init__(x, y, 32, 30)
        self.vx = -self.SPEED
        self.state = "walk"  # walk | squashed | knocked
        self.timer = 0
        self.active = False
        self.anim = 0

    def update(self, level):
        if self.state == "squashed":
            self.timer -= 1
            return
        if self.state == "knocked":
            self.vy = min(self.vy + GRAVITY, MAX_FALL)
            self.x += self.vx
            self.y += self.vy
            return

        self.anim += 1
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        direction = 1 if self.vx > 0 else -1
        if self.move_x(level):
            direction = -direction
            self.vx = direction * self.SPEED
        landed, _ = self.move_y(level)
        if landed:  # turn around at ledges
            r = self.rect
            ahead = r.right if direction > 0 else r.left - 1
            if not level.is_solid(ahead // TILE, r.bottom // TILE):
                self.vx = -self.vx

    def squash(self):
        self.state, self.timer = "squashed", 30

    def knock(self, direction):
        self.state = "knocked"
        self.vy, self.vx = -7.0, 2.0 * direction

    @property
    def gone(self):
        return (self.state == "squashed" and self.timer <= 0) or self.y > HEIGHT + 60


class Particle:
    def __init__(self, kind, x, y, vx=0.0, vy=0.0, life=40, color=WHITE, text=""):
        self.kind, self.x, self.y = kind, x, y
        self.vx, self.vy = vx, vy
        self.life, self.color, self.text = life, color, text

    def update(self):
        self.life -= 1
        self.x += self.vx
        self.y += self.vy
        if self.kind in ("debris", "coin"):
            self.vy += 0.5


# --------------------------------------------------------------------------- art
def make_sky():
    sky = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / HEIGHT
        color = [int(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOTTOM)]
        pygame.draw.line(sky, color, (0, y), (WIDTH, y))
    return sky


def make_tiles():
    rng = random.Random(7)
    tiles = {}

    dirt = pygame.Surface((TILE, TILE))
    dirt.fill((150, 92, 52))
    for _ in range(10):
        pygame.draw.circle(dirt, (124, 74, 40),
                           (rng.randrange(TILE), rng.randrange(TILE)), rng.randint(2, 4))
    tiles["dirt"] = dirt

    grass = dirt.copy()
    pygame.draw.rect(grass, (60, 150, 52), (0, 0, TILE, 14))
    pygame.draw.rect(grass, (88, 192, 74), (0, 0, TILE, 10))
    for i in range(0, TILE, 10):
        pygame.draw.circle(grass, (88, 192, 74), (i + 5, 11), 5)
    tiles["grass"] = grass

    brick = pygame.Surface((TILE, TILE))
    brick.fill((192, 92, 48))
    mortar = (110, 52, 30)
    for row in range(4):
        y = row * 10
        pygame.draw.line(brick, (226, 132, 84), (0, y + 1), (TILE, y + 1))
        pygame.draw.line(brick, mortar, (0, y), (TILE, y), 2)
        for x in range(0 if row % 2 == 0 else 10, TILE, 20):
            pygame.draw.line(brick, mortar, (x, y), (x, y + 10), 2)
    pygame.draw.rect(brick, mortar, brick.get_rect(), 2)
    tiles["B"] = brick

    used = pygame.Surface((TILE, TILE))
    used.fill((140, 100, 70))
    pygame.draw.rect(used, (90, 60, 40), used.get_rect(), 3)
    for cx, cy in ((7, 7), (TILE - 7, 7), (7, TILE - 7), (TILE - 7, TILE - 7)):
        pygame.draw.circle(used, (90, 60, 40), (cx, cy), 3)
    tiles["U"] = used

    stone = pygame.Surface((TILE, TILE))
    stone.fill((130, 130, 145))
    pygame.draw.lines(stone, (190, 190, 205), False, [(0, TILE - 1), (0, 0), (TILE - 1, 0)], 4)
    pygame.draw.lines(stone, (80, 80, 95), False, [(1, TILE - 1), (TILE - 1, TILE - 1), (TILE - 1, 1)], 4)
    pygame.draw.line(stone, (105, 105, 120), (12, 14), (22, 22), 2)
    tiles["S"] = stone

    bonus = pygame.Surface((TILE, TILE))
    bonus.fill((242, 182, 40))
    pygame.draw.rect(bonus, (170, 110, 20), bonus.get_rect(), 3)
    for cx, cy in ((7, 7), (TILE - 7, 7), (7, TILE - 7), (TILE - 7, TILE - 7)):
        pygame.draw.circle(bonus, (170, 110, 20), (cx, cy), 2)
    tiles["?"] = bonus
    return tiles


# --------------------------------------------------------------------------- game
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Tribble Run")
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 80)
        self.font = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 26)
        self.sky = make_sky()
        self.tiles = make_tiles()
        self.shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.shade.fill((0, 0, 0, 140))
        self.state = "title"  # title | play | dying | win | gameover
        self.paused = False
        self.tick = 0
        self.new_game()

    # ----------------------------------------------------------------- setup
    def new_game(self):
        self.score = 0
        self.coins = 0
        self.lives = START_LIVES
        self.load_level()

    def load_level(self):
        self.level = Level()
        px, py = self.level.player_spawn
        self.player = Player(px * TILE + 6, (py + 1) * TILE - 34)
        self.enemies = [Enemy(x * TILE + 4, (y + 1) * TILE - 30)
                        for x, y in self.level.enemy_spawns]
        self.particles = []
        self.cam_x = 0.0
        self.time_left = START_TIME
        self.time_frames = 0
        self.state_timer = 0
        self.win_phase = ""
        self.flag_y = self.level.pole_top + 6

    # ----------------------------------------------------------------- loop
    def run(self):
        while True:
            jump_pressed = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.quit()
                    if event.key in JUMP_KEYS:
                        jump_pressed = True
                    if event.key == pygame.K_p and self.state == "play":
                        self.paused = not self.paused
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.press_enter()
            self.update(jump_pressed)
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

    def press_enter(self):
        if self.state == "title":
            self.state = "play"
        elif self.state == "gameover" or (self.state == "win" and self.win_phase == "done"):
            self.new_game()
            self.state = "play"

    @staticmethod
    def quit():
        pygame.quit()
        sys.exit()

    # ----------------------------------------------------------------- update
    def update(self, jump_pressed):
        if self.paused:
            return
        self.tick += 1
        for key in list(self.level.bumps):
            self.level.bumps[key] -= 1
            if self.level.bumps[key] <= 0:
                del self.level.bumps[key]
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]

        if self.state == "play":
            self.update_play(jump_pressed)
        elif self.state == "dying":
            self.update_dying()
        elif self.state == "win":
            self.update_win()

        if self.state != "dying":
            target = self.player.x + self.player.w / 2 - WIDTH * 0.4
            self.cam_x = max(0, min(target, self.level.pixel_width - WIDTH))

    def update_play(self, jump_pressed):
        p = self.player
        bumped = p.update(pygame.key.get_pressed(), self.level, jump_pressed)
        if bumped:  # only the block closest to the player's head reacts
            cx = p.rect.centerx
            tx, ty = min(bumped, key=lambda t: abs(t[0] * TILE + TILE / 2 - cx))
            self.hit_block(tx, ty)
        self.collect_coins()

        for e in self.enemies:
            if not e.active and e.x < self.cam_x + WIDTH + TILE:
                e.active = True
            if e.active:
                e.update(self.level)
        walkers = [e for e in self.enemies if e.active and e.state == "walk"]
        for i, a in enumerate(walkers):  # enemies bounce off each other
            for b in walkers[i + 1:]:
                if a.rect.colliderect(b.rect):
                    left, right = (a, b) if a.x < b.x else (b, a)
                    left.vx, right.vx = -Enemy.SPEED, Enemy.SPEED
        self.enemies = [e for e in self.enemies if not e.gone]
        self.check_enemy_hits()

        self.time_frames += 1
        if self.time_frames >= FPS:
            self.time_frames = 0
            self.time_left -= 1
            if self.time_left <= 0:
                self.kill_player()

        if p.y > HEIGHT:
            self.kill_player()
        elif self.state == "play" and p.rect.colliderect(self.level.goal_rect):
            self.start_win()

    def check_enemy_hits(self):
        p = self.player
        pr = p.rect
        falling = p.vy > 0
        for e in self.enemies:
            if e.state != "walk" or not pr.colliderect(e.rect):
                continue
            if falling and pr.bottom - e.rect.top < 18:
                e.squash()
                held = any(pygame.key.get_pressed()[k] for k in JUMP_KEYS)
                p.vy = -JUMP_SPEED if held else -STOMP_BOUNCE
                self.add_score(100 * 2 ** min(p.stomp_chain, 4), e.rect.centerx, e.rect.top)
                p.stomp_chain += 1
            else:
                self.kill_player()
                return

    def hit_block(self, tx, ty):
        tile = self.level.tile(tx, ty)
        if tile not in "?B":
            return
        self.level.bumps[(tx, ty)] = 10
        top = pygame.Rect(tx * TILE, ty * TILE - 6, TILE, 6)
        for e in self.enemies:  # knock out enemies standing on the block
            if e.state == "walk" and e.rect.colliderect(top):
                e.knock(1 if e.rect.centerx > top.centerx else -1)
                self.add_score(100, e.rect.centerx, e.rect.top)
        x, y = tx * TILE + TILE / 2, ty * TILE
        if tile == "?":
            self.level.grid[ty][tx] = "U"
            self.particles.append(Particle("coin", x, y - 10, vy=-9, life=28))
            self.add_coin(x, y - 30)
        else:
            self.level.grid[ty][tx] = " "
            self.level.bumps.pop((tx, ty), None)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                self.particles.append(Particle("debris", x + dx * 8, y + 20 + dy * 8,
                                               vx=dx * 2.5, vy=-8 + dy * 2, life=60,
                                               color=(192, 92, 48)))
            self.add_score(50, x, y)

    def collect_coins(self):
        for tx, ty in self.level.tiles_in(self.player.rect):
            if self.level.tile(tx, ty) == "C":
                self.level.grid[ty][tx] = " "
                self.add_coin(tx * TILE + TILE / 2, ty * TILE)

    def add_coin(self, x, y):
        self.coins += 1
        self.add_score(100, x, y)
        if self.coins >= 100:
            self.coins -= 100
            self.lives += 1
            self.particles.append(Particle("text", x, y - 20, vy=-1, life=60,
                                           color=(120, 255, 120), text="1UP"))

    def add_score(self, points, x, y):
        self.score += points
        self.particles.append(Particle("text", x, y, vy=-1.2, life=45, text=str(points)))

    def kill_player(self):
        if self.state != "play":
            return
        self.state = "dying"
        self.state_timer = 0
        self.player.vx = 0.0
        self.player.vy = -11.0

    def update_dying(self):
        self.state_timer += 1
        p = self.player
        if self.state_timer > 25:  # short freeze, then the hop-and-fall
            p.vy = min(p.vy + GRAVITY, MAX_FALL)
            p.y += p.vy
        if self.state_timer > 130:
            self.lives -= 1
            if self.lives <= 0:
                self.state = "gameover"
            else:
                self.load_level()
                self.state = "play"

    def start_win(self):
        lvl, p = self.level, self.player
        self.state = "win"
        self.win_phase = "slide"
        height = (lvl.pole_bottom - p.rect.bottom) / (lvl.pole_bottom - lvl.pole_top)
        bonus = 100 + int(max(0.0, min(1.0, height)) * 49) * 100
        self.add_score(bonus, lvl.pole_x, p.rect.top)
        p.x = lvl.pole_x - p.w + 2
        p.vx = p.vy = 0.0
        p.facing = 1

    def update_win(self):
        p, lvl = self.player, self.level
        if self.win_phase == "slide":
            p.y = min(p.y + 5, lvl.pole_bottom - p.h)
            self.flag_y = min(self.flag_y + 5, lvl.pole_bottom - 30)
            if p.y >= lvl.pole_bottom - p.h and self.flag_y >= lvl.pole_bottom - 30:
                self.win_phase = "walk"
        elif self.win_phase == "walk":
            p.vx = 2.5
            p.vy = min(p.vy + GRAVITY, MAX_FALL)
            p.move_x(lvl)
            p.on_ground, _ = p.move_y(lvl)
            p.walk_anim += 0.2
            if p.x > (lvl.goal_x + 4) * TILE:
                p.vx = 0.0
                self.win_phase = "tally"
        elif self.win_phase == "tally":  # leftover time becomes points
            if self.time_left > 0:
                step = min(self.time_left, 2)
                self.time_left -= step
                self.score += 50 * step
            else:
                self.win_phase = "done"

    # ----------------------------------------------------------------- draw
    def draw(self):
        cam = int(self.cam_x)
        self.screen.blit(self.sky, (0, 0))
        self.draw_scenery(cam)
        self.draw_tiles(cam)
        self.draw_goal(cam)
        for e in self.enemies:
            if e.active or e.x < cam + WIDTH:
                self.draw_enemy(e, cam)
        self.draw_player(cam)
        self.draw_particles(cam)
        self.draw_hud()
        self.draw_overlay()

    def draw_scenery(self, cam):
        off, spacing = cam * 0.25, 260
        k0 = int(off // spacing) - 1
        for k in range(k0, k0 + WIDTH // spacing + 4):
            r = 110 + (k * 53) % 70
            cx = int(k * spacing - off + 130)
            color = HILL if k % 2 else HILL_DARK
            pygame.draw.circle(self.screen, color, (cx, HEIGHT - 40 + r // 3), r)
        off, spacing = cam * 0.5, 330
        k0 = int(off // spacing) - 1
        for k in range(k0, k0 + WIDTH // spacing + 3):
            cx = int(k * spacing - off + 80)
            cy = 50 + (k * 47) % 90
            for dx, dy, r in ((-26, 6, 18), (0, -4, 24), (26, 6, 18)):
                pygame.draw.circle(self.screen, WHITE, (cx + dx, cy + dy), r)
            pygame.draw.rect(self.screen, WHITE, (cx - 26, cy + 6, 52, 18))

    def draw_tiles(self, cam):
        lvl = self.level
        x0 = max(0, cam // TILE)
        x1 = min(lvl.width, (cam + WIDTH) // TILE + 2)
        for ty in range(ROWS):
            for tx in range(x0, x1):
                ch = lvl.grid[ty][tx]
                if ch == " ":
                    continue
                x, y = tx * TILE - cam, ty * TILE
                if (tx, ty) in lvl.bumps:
                    y -= int(math.sin((10 - lvl.bumps[(tx, ty)]) / 10 * math.pi) * 8)
                if ch == "#":
                    above = lvl.tile(tx, ty - 1)
                    self.screen.blit(self.tiles["dirt" if above == "#" else "grass"], (x, y))
                elif ch == "C":
                    self.draw_coin(x + TILE // 2, y + TILE // 2, phase=tx * 0.7)
                else:
                    self.screen.blit(self.tiles[ch], (x, y))
                    if ch == "?":  # pulsing gem in the bonus block
                        s = 8 + int(math.sin(self.tick * 0.12) * 2)
                        cx, cy = x + TILE // 2, y + TILE // 2
                        pts = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
                        pygame.draw.polygon(self.screen, (255, 248, 210), pts)
                        pygame.draw.polygon(self.screen, (170, 110, 20), pts, 2)

    def draw_coin(self, cx, cy, phase=0.0):
        w = max(3, int(abs(math.cos(self.tick * 0.08 + phase)) * 22))
        rect = pygame.Rect(0, 0, w, 26)
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(self.screen, COIN_DARK, rect)
        pygame.draw.ellipse(self.screen, COIN, rect.inflate(-4, -4))

    def draw_goal(self, cam):
        lvl = self.level
        x = lvl.pole_x - cam
        if x < -60 or x > WIDTH + 60:
            return
        pygame.draw.rect(self.screen, (220, 220, 225), (x, lvl.pole_top, 6, lvl.pole_bottom - lvl.pole_top))
        pygame.draw.rect(self.screen, (150, 150, 160), (x + 4, lvl.pole_top, 2, lvl.pole_bottom - lvl.pole_top))
        pygame.draw.circle(self.screen, (255, 210, 40), (x + 3, lvl.pole_top), 8)
        fy = int(self.flag_y)
        flag = [(x, fy), (x - 46, fy + 14), (x, fy + 28)]
        pygame.draw.polygon(self.screen, (60, 190, 90), flag)
        pygame.draw.polygon(self.screen, (30, 120, 50), flag, 2)
        pygame.draw.circle(self.screen, WHITE, (x - 14, fy + 14), 5)

    def draw_player(self, cam):
        p = self.player
        r = p.rect.move(-cam, 0)
        if r.top > HEIGHT + 40:
            return
        sx, sy = 1.0, 1.0
        if not p.on_ground and self.state not in ("dying", "title"):
            sx, sy = (0.9, 1.1) if p.vy < 0 else (1.05, 0.96)
        bw, bh = int((p.w + 2) * sx), int((p.h - 4) * sy)
        body = pygame.Rect(0, 0, bw, bh)
        body.midbottom = (r.centerx, r.bottom - 3)
        cx, cy = body.center

        moving = p.on_ground and abs(p.vx) > 0.3
        step = math.sin(p.walk_anim) * 4 if moving else 0
        pygame.draw.ellipse(self.screen, FOOT, (r.centerx - 14, r.bottom - 8 - max(0, step), 13, 8))
        pygame.draw.ellipse(self.screen, FOOT, (r.centerx + 1, r.bottom - 8 - max(0, -step), 13, 8))

        for i in range(18):  # fuzzy outline
            a = i / 18 * math.tau
            fx = cx + math.cos(a) * bw / 2
            fy = cy + math.sin(a) * bh / 2
            pygame.draw.circle(self.screen, FUR_DARK, (int(fx), int(fy)), 4)
        pygame.draw.ellipse(self.screen, FUR, body)
        belly = pygame.Rect(0, 0, int(bw * 0.6), int(bh * 0.5))
        belly.midbottom = (cx + p.facing * 2, body.bottom - 2)
        pygame.draw.ellipse(self.screen, FUR_LIGHT, belly)
        for dx in (-4, 0, 4):  # tuft of hair
            pygame.draw.line(self.screen, FUR_DARK, (cx + dx, body.top + 3),
                             (cx + int(dx * 1.8), body.top - 6), 3)

        f = p.facing
        ey = body.top + int(bh * 0.32)
        blink = self.tick % 200 < 6
        for ex in (cx + f * 3 - 6, cx + f * 3 + 6):
            if self.state == "dying":
                pygame.draw.line(self.screen, BLACK, (ex - 3, ey - 3), (ex + 3, ey + 3), 2)
                pygame.draw.line(self.screen, BLACK, (ex - 3, ey + 3), (ex + 3, ey - 3), 2)
            elif blink:
                pygame.draw.line(self.screen, BLACK, (ex - 4, ey), (ex + 4, ey), 2)
            else:
                pygame.draw.circle(self.screen, WHITE, (ex, ey), 5)
                pygame.draw.circle(self.screen, BLACK, (ex + f * 2, ey + 1), 2)

    def draw_enemy(self, e, cam):
        surf = pygame.Surface((e.w, e.h), pygame.SRCALPHA)
        if e.state == "squashed":
            pygame.draw.ellipse(surf, ENEMY_DARK, (0, e.h - 11, e.w, 11))
            pygame.draw.ellipse(surf, ENEMY, (2, e.h - 12, e.w - 4, 8))
        else:
            step = (e.anim // 8) % 2
            pygame.draw.ellipse(surf, ENEMY_FOOT, (2 + step * 3, e.h - 8, 12, 8))
            pygame.draw.ellipse(surf, ENEMY_FOOT, (e.w - 14 - step * 3, e.h - 8, 12, 8))
            for sx in (8, 16, 24):  # spikes
                pygame.draw.polygon(surf, ENEMY_DARK, [(sx - 5, 9), (sx, 0), (sx + 5, 9)])
            pygame.draw.ellipse(surf, ENEMY, (0, 4, e.w, e.h - 8))
            look = 1 if e.vx > 0 else -1
            for ex in (11, 21):
                pygame.draw.circle(surf, WHITE, (ex, 14), 4)
                pygame.draw.circle(surf, BLACK, (ex + look, 15), 2)
            pygame.draw.line(surf, BLACK, (5, 7), (13, 11), 2)   # angry brows
            pygame.draw.line(surf, BLACK, (27, 7), (19, 11), 2)
            pygame.draw.line(surf, BLACK, (12, 21), (20, 21), 2)
        if e.state == "knocked":
            surf = pygame.transform.flip(surf, False, True)
        self.screen.blit(surf, (int(e.x) - cam, int(e.y)))

    def draw_particles(self, cam):
        for p in self.particles:
            x, y = int(p.x) - cam, int(p.y)
            if p.kind == "debris":
                pygame.draw.rect(self.screen, p.color, (x - 6, y - 6, 12, 12))
                pygame.draw.rect(self.screen, (110, 52, 30), (x - 6, y - 6, 12, 12), 2)
            elif p.kind == "coin":
                self.draw_coin(p.x - cam, p.y)
            elif p.kind == "text":
                self.text(p.text, self.font_small, p.color, (x, y), center=True)

    def draw_hud(self):
        self.text(f"SCORE {self.score:06d}", self.font, WHITE, (16, 12))
        self.draw_coin(236, 24)
        self.text(f"x {self.coins:02d}", self.font, WHITE, (252, 12))
        self.text(f"LIVES {self.lives}", self.font, WHITE, (370, 12))
        self.text("LEVEL 1", self.font, WHITE, (520, 12))
        self.text(f"TIME {self.time_left:03d}", self.font, WHITE, (670, 12))

    def draw_overlay(self):
        mid = WIDTH // 2
        if self.state == "title":
            self.screen.blit(self.shade, (0, 0))
            self.text("TRIBBLE RUN", self.font_big, (255, 220, 90), (mid, 140), center=True)
            lines = ["Arrows / A D : move      Space / W / Up : jump",
                     "Shift / X : run      P : pause      Esc : quit",
                     "Stomp the Grumbles, bump blocks, grab coins",
                     "and reach the flag!"]
            for i, line in enumerate(lines):
                self.text(line, self.font_small, WHITE, (mid, 220 + i * 30), center=True)
            if (self.tick // 30) % 2 == 0:
                self.text("Press ENTER to start", self.font, (255, 220, 90), (mid, 370), center=True)
        elif self.state == "gameover":
            self.screen.blit(self.shade, (0, 0))
            self.text("GAME OVER", self.font_big, (255, 90, 90), (mid, 180), center=True)
            self.text(f"Final score: {self.score}", self.font, WHITE, (mid, 250), center=True)
            self.text("Press ENTER to try again", self.font, WHITE, (mid, 300), center=True)
        elif self.state == "win" and self.win_phase == "done":
            self.screen.blit(self.shade, (0, 0))
            self.text("LEVEL CLEAR!", self.font_big, (120, 255, 140), (mid, 180), center=True)
            self.text(f"Score: {self.score}", self.font, WHITE, (mid, 250), center=True)
            self.text("Press ENTER to play again", self.font, WHITE, (mid, 300), center=True)
        elif self.paused:
            self.screen.blit(self.shade, (0, 0))
            self.text("PAUSED", self.font_big, WHITE, (mid, HEIGHT // 2), center=True)

    def text(self, msg, font, color, pos, center=False):
        img = font.render(msg, True, color)
        shadow = font.render(msg, True, BLACK)
        rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.screen.blit(shadow, rect.move(2, 2))
        self.screen.blit(img, rect)


if __name__ == "__main__":
    Game().run()
