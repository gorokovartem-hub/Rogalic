#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПОЕЗД БЕЗ КОНЦА — рогалик (pygame)

Поезд едет бесконечно. Каждый вагон — отдельный биом, генерируется на лету.
Зачисти вагон -> откроется дверь и появится сундук с перком.
Позади расползается «Разрыв» — не стой на месте.

Запуск:  pip install pygame   ->   python train_rogue.py

Управление:
  WASD / стрелки — движение     ЛКМ — стрельба (можно зажать)
  Shift / Пробел — рывок        E — открыть сундук
  Esc / P — пауза               F11 — полный экран
"""
import json
import math
import os
import random
import sys
from collections import deque

import pygame

from conten import ENEMIES as ETYPES, PERKS, PERK_EFFECTS, MULT_STATS, RARITIES, rarity_of, roll_perks
from train_visuals import (
    DOOR, FLOOR, OBST, ROWS, SLIME, THORN, TILE, VENT, WALL,
    draw_car as draw_train_car, ihash, lerp_col, shade,
)

# ----------------------------------------------------------------------------
# Константы
# ----------------------------------------------------------------------------
W, H = 1280, 720
OY = (H - ROWS * TILE) // 2
FPS = 60
INF = 10 ** 6
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "train_save.json")

SOLID = {WALL, OBST, DOOR}


# ----------------------------------------------------------------------------
# Данные: биомы, враги, перки
# ----------------------------------------------------------------------------
BIOMES = {
    "bunk": dict(name="Плацкарт", floor=((112, 90, 68), (104, 83, 62)), wall=(62, 44, 36),
                 obst=(150, 108, 74), edge=(96, 66, 46), decor=(200, 180, 150),
                 sky=(60, 84, 104), ground=(52, 78, 56), enemies=["passenger", "rat"], min=0),
    "diner": dict(name="Вагон-ресторан", floor=((158, 148, 136), (134, 64, 66)), wall=(70, 40, 44),
                  obst=(190, 150, 90), edge=(120, 90, 50), decor=(240, 230, 210),
                  sky=(88, 70, 96), ground=(60, 70, 52), enemies=["chef", "passenger"], min=1),
    "cargo": dict(name="Грузовой", floor=((92, 92, 98), (84, 84, 90)), wall=(48, 48, 56),
                  obst=(168, 124, 60), edge=(110, 78, 36), decor=(60, 60, 66),
                  sky=(96, 100, 112), ground=(88, 84, 70), enemies=["rat", "golem", "passenger"], min=2),
    "freezer": dict(name="Рефрижератор", floor=((156, 196, 216), (144, 184, 206)), wall=(66, 98, 130),
                    obst=(206, 234, 248), edge=(130, 170, 200), decor=(255, 255, 255),
                    sky=(150, 175, 200), ground=(206, 222, 234), enemies=["frost", "passenger"],
                    min=3, ice=True),
    "jungle": dict(name="Оранжерея", floor=((52, 94, 52), (46, 84, 46)), wall=(28, 50, 34),
                   obst=(38, 128, 56), edge=(22, 84, 36), decor=(120, 200, 90),
                   sky=(70, 130, 110), ground=(40, 100, 50), enemies=["spore", "rat"], min=3),
    "boiler": dict(name="Котельная", floor=((74, 62, 62), (66, 54, 56)), wall=(40, 32, 34),
                   obst=(116, 116, 128), edge=(70, 70, 80), decor=(255, 140, 40),
                   sky=(110, 70, 50), ground=(70, 56, 46), enemies=["golem", "passenger"], min=4),
    "library": dict(name="Библиотека", floor=((120, 92, 68), (112, 84, 62)), wall=(60, 40, 28),
                    obst=(86, 54, 34), edge=(54, 32, 18), decor=(230, 210, 160),
                    sky=(60, 60, 84), ground=(46, 60, 56), enemies=["ghost", "passenger"], min=5),
    "void": dict(name="Пустота", floor=((36, 26, 62), (30, 20, 54)), wall=(16, 10, 32),
                 obst=(96, 64, 170), edge=(60, 36, 120), decor=(160, 120, 255),
                 sky=(14, 8, 30), ground=(24, 16, 44), enemies=["ghost", "frost", "golem"],
                 min=7, wind=True),
}


# Профили процедурной генерации: какие "алгоритмы раскладки" (с весами) и какие опасности
# возможны в биоме. Каждый вагон выбирает 1-2 раскладки случайно и параметры тоже случайные.
PROFILES = {
    "bunk": ({"partitions": 3, "lanes": 2, "pillars": 2, "scatter": 1}, []),
    "diner": ({"scatter": 3, "islands": 2, "pillars": 2, "lanes": 1}, [("slime", 0.8)]),
    "cargo": ({"scatter": 4, "partitions": 2, "stairs": 2, "islands": 2}, [("thorn", 0.15)]),
    "freezer": ({"pillars": 3, "scatter": 2, "cave": 2, "islands": 1}, []),
    "jungle": ({"cave": 4, "scatter": 2, "islands": 1}, [("thorn", 0.9)]),
    "boiler": ({"pillars": 3, "partitions": 2, "lanes": 2}, [("vent", 0.95)]),
    "library": ({"lanes": 4, "partitions": 3, "pillars": 1}, []),
    "void": ({"cave": 3, "islands": 3, "stairs": 2, "scatter": 2}, [("thorn", 0.3)]),
}

# ----------------------------------------------------------------------------
# Сущности
# ----------------------------------------------------------------------------
class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "dmg", "own", "life", "pierce", "bounce", "r", "col", "slow",
                 "arc", "blast", "hit")

    def __init__(self, x, y, ang, spd, dmg, own, col, r=5, life=1.0, pierce=0, bounce=0, slow=0,
                 arc=0, blast=0):
        self.x = x
        self.y = y
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd
        self.dmg = dmg
        self.own = own
        self.life = life
        self.pierce = pierce
        self.bounce = bounce
        self.r = r
        self.col = col
        self.slow = slow
        self.arc = arc
        self.blast = blast
        self.hit = []


class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.r = 11
        self.maxhp = 6
        self.hp = 6
        self.iframes = 0.0
        self.fire_cd = 0.0
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.dash_dir = (1.0, 0.0)
        self.slow = 0.0
        self.shield = 0
        self.max_shield = 0
        self.kill_count = 0
        self.shot_count = 0
        self.perks = {k: 0 for k, _, _ in PERKS}
        self.recalc()

    def recalc(self):
        st = {"fire_cd": 1.0, "speed": 1.0, "dash_cd": 1.0, "dmg": 0, "shots": 0, "maxhp": 0,
              "bounce": 0, "pierce": 0, "cold": 0, "shield": 0, "vamp": 0,
              "arc": 0, "blast": 0, "ram": 0, "nova": 0}
        for key, n in self.perks.items():
            if not n:
                continue
            for stat, val in PERK_EFFECTS.get(key, {}).items():
                if stat in MULT_STATS:
                    st[stat] *= val ** n
                else:
                    st[stat] += val * n
        self.fire_cd_base = 0.30 * st["fire_cd"]
        self.dmg = 1 + st["dmg"]
        self.shots = 1 + st["shots"]
        self.speed = 215 * st["speed"]
        self.dash_cd_base = 1.1 * st["dash_cd"]
        self.bounce = st["bounce"]
        self.pierce = st["pierce"]
        self.cold = st["cold"]
        self.arc = st["arc"]
        self.blast = st["blast"]
        self.ram = st["ram"]
        self.nova = st["nova"]
        self.vamp_need = max(4, 14 - 3 * st["vamp"]) if st["vamp"] else 0
        new_max = 6 + st["maxhp"]
        if new_max > self.maxhp:
            self.hp = min(new_max, self.hp + (new_max - self.maxhp))
        self.maxhp = new_max
        if st["shield"] > self.max_shield:
            self.shield += st["shield"] - self.max_shield
        self.max_shield = st["shield"]


class Enemy:
    def __init__(self, kind, x, y, index, car):
        d = ETYPES[kind]
        self.kind = kind
        self.d = d
        self.car = car
        self.x, self.y = x, y
        self.r = d["r"]
        if kind == "boss":
            self.hp = 40 + index * 4
        else:
            self.hp = max(1, round(d["hp"] * (1 + index * 0.05)))
        self.maxhp = self.hp
        self.age = random.random()
        self.flash = 0.0
        self.slow = 0.0
        self.wob = random.random() * 6.28
        self.cd = random.uniform(0.8, d.get("shoot", 1.5) + 0.5) if d.get("shoot") else 0
        self.burst_t = 2.0
        self.summon_t = 5.0
        self.strafe = random.choice((-1, 1))
        self.strafe_t = random.uniform(1.0, 2.5)
        self.pat = 0


class Car:
    def __init__(self, index, tx0, key, rng):
        self.index = index
        self.tx0 = tx0
        self.key = key
        self.b = BIOMES[key]
        self.cols = 28 if index == 0 else rng.randint(24, 58)
        self.seed = rng.randrange(1, 10 ** 6)
        self.vent_phase = {}
        for attempt in range(14):
            self.build(rng, plain=(attempt == 13))
            if self.connected():
                break
        self.enemies = []
        self.activated = False
        self.cleared = (index == 0)
        self.boss = index > 0 and index % 5 == 0
        self.flow = None
        self.flow_src = None
        self.populate(rng)
        if self.cleared:
            self.open_door()

    # --- генерация -----------------------------------------------------------
    def build(self, rng, plain):
        c, r = self.cols, ROWS
        g = [[FLOOR] * c for _ in range(r)]
        for x in range(c):
            g[0][x] = WALL
            g[r - 1][x] = WALL
        for y in range(r):
            g[y][0] = WALL
            g[y][c - 1] = WALL
        for y in (3, 4, 5):
            g[y][0] = WALL if self.index == 0 else FLOOR
            g[y][c - 1] = DOOR
        self.grid = g
        self.vent_phase = {}
        if not plain:
            self.generate(rng)

    def put(self, x, y, t=OBST):
        if 5 <= x <= self.cols - 6 and 1 <= y <= ROWS - 2 and self.grid[y][x] == FLOOR:
            self.grid[y][x] = t
            return True
        return False

    def put_block(self, x, y, w, h, t=OBST):
        cells = [(x + i, y + j) for i in range(w) for j in range(h)]
        for cx, cy in cells:
            if not (5 <= cx <= self.cols - 6 and 1 <= cy <= ROWS - 2 and self.grid[cy][cx] == FLOOR):
                return False
        for cx, cy in cells:
            self.grid[cy][cx] = t
        return True

    def rx(self, rng):
        return rng.randint(5, self.cols - 6)

    # --- процедурная генерация раскладки -----------------------------------------
    def generate(self, rng):
        weights, hazards = PROFILES[self.key]
        names = list(weights)
        w = [weights[n] for n in names]
        chosen = []
        for _ in range(rng.choice((1, 1, 2))):
            n = rng.choices(names, w)[0]
            if n not in chosen:
                chosen.append(n)
        for n in chosen:
            getattr(self, "lay_" + n)(rng)
        if rng.random() < 0.4:
            self.mirror()
        for name, prob in hazards:
            if rng.random() < prob:
                getattr(self, "haz_" + name)(rng)

    def mirror(self):
        for y in range(1, 4):
            for x in range(5, self.cols - 5):
                if self.grid[y][x] in (FLOOR, OBST) and self.grid[ROWS - 1 - y][x] in (FLOOR, OBST):
                    self.grid[ROWS - 1 - y][x] = self.grid[y][x]

    def lay_scatter(self, rng):
        shapes = [(1, 1), (1, 1), (2, 1), (1, 2), (2, 2), (3, 1), (1, 3)]
        for _ in range(int(self.cols * rng.uniform(0.2, 0.7))):
            w, h = rng.choice(shapes)
            self.put_block(self.rx(rng), rng.randint(1, 7), w, h)

    def lay_partitions(self, rng):
        x = rng.randint(6, 9)
        while x <= self.cols - 7:
            gh = rng.choice((1, 2, 2, 3))
            gaps = [rng.randint(1, 7 - gh + 1)]
            if rng.random() < 0.4:
                gaps.append(rng.randint(1, 7 - gh + 1))
            thick = 2 if rng.random() < 0.3 else 1
            for y in range(1, 8):
                if any(g0 <= y < g0 + gh for g0 in gaps):
                    continue
                for t in range(thick):
                    self.put(x + t, y)
            x += rng.randint(5, 10)

    def lay_cave(self, rng):
        x0, x1 = 5, self.cols - 6
        fill = rng.uniform(0.32, 0.45)
        cells = {(x, y): rng.random() < fill for x in range(x0, x1 + 1) for y in range(1, 8)}
        for _ in range(3):
            nxt = {}
            for (x, y), v in cells.items():
                n = 0
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx or dy:
                            n += cells.get((x + dx, y + dy), False)
                nxt[(x, y)] = n >= 5 or (v and n >= 4)
            cells = nxt
        # гарантированный извилистый тоннель
        y = 4
        for x in range(x0, x1 + 1):
            cells[(x, y)] = False
            if rng.random() < 0.35:
                y = max(1, min(7, y + rng.choice((-1, 1))))
                cells[(x, y)] = False
        for (x, y), v in cells.items():
            if v:
                self.put(x, y)

    def lay_pillars(self, rng):
        sx, sy = rng.choice((3, 4, 5)), rng.choice((2, 3))
        ox = rng.randint(0, sx - 1)
        stagger = rng.random() < 0.5
        for i, x in enumerate(range(5 + ox, self.cols - 5, sx)):
            y0 = 1 + (1 if (stagger and i % 2) else rng.randint(0, 1) * 0)
            for y in range(y0, 8, sy):
                if rng.random() > 0.15:
                    self.put(x, y)

    def lay_lanes(self, rng):
        rows = rng.choice(((2, 6), (3, 5), (2, 4, 6), (2, 5)))
        for r in rows:
            x = rng.randint(5, 8)
            while x <= self.cols - 6:
                ln = rng.randint(4, 9)
                for k in range(ln):
                    self.put(x + k, r)
                x += ln + rng.randint(2, 3)

    def lay_islands(self, rng):
        for _ in range(rng.randint(2, max(3, self.cols // 9))):
            w, h = rng.randint(2, 6), rng.randint(2, 3)
            x, y = self.rx(rng), rng.randint(1, 8 - h)
            if self.put_block(x, y, w, h) and w >= 4 and h >= 3 and rng.random() < 0.6:
                # кольцо: вырезаем внутренность и проход
                for ix in range(x + 1, x + w - 1):
                    self.grid[y + 1][ix] = FLOOR
                self.grid[y + 1][x + (w - 1 if rng.random() < 0.5 else 0)] = FLOOR

    def lay_stairs(self, rng):
        for _ in range(rng.randint(2, max(3, self.cols // 10))):
            x, y = self.rx(rng), rng.choice((1, 7))
            dy = 1 if y == 1 else -1
            for k in range(rng.randint(3, 6)):
                self.put(x + k, y + dy * k)

    def haz_thorn(self, rng):
        for _ in range(self.cols // rng.randint(3, 6)):
            self.put_block(self.rx(rng), rng.randint(1, 7), rng.choice((1, 2, 3)), rng.choice((1, 1, 2)), THORN)

    def haz_slime(self, rng):
        for _ in range(self.cols // rng.randint(3, 6)):
            self.put_block(self.rx(rng), rng.randint(1, 7), rng.choice((1, 2)), rng.choice((1, 2)), SLIME)

    def haz_vent(self, rng):
        for _ in range(max(2, self.cols // rng.randint(5, 9))):
            x, y = self.rx(rng), rng.randint(1, 6)
            if self.put_block(x, y, 2, 2, VENT):
                off = rng.random() * 3.5
                for cx in (x, x + 1):
                    for cy in (y, y + 1):
                        self.vent_phase[(cx, cy)] = off

    def connected(self):
        start, goal = (1, 4), (self.cols - 2, 4)
        seen = {start}
        dq = deque([start])
        while dq:
            x, y = dq.popleft()
            if (x, y) == goal:
                return True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.cols and 0 <= ny < ROWS and (nx, ny) not in seen \
                        and self.grid[ny][nx] not in SOLID:
                    seen.add((nx, ny))
                    dq.append((nx, ny))
        return False

    def populate(self, rng):
        if self.index == 0:
            return
        budget = min(3 + self.index * 0.9, 26) * (self.cols / 38.0) ** 0.5
        pool = self.b["enemies"]
        free = [(x, y) for y in range(1, ROWS - 1) for x in range(9, self.cols - 3)
                if self.grid[y][x] in (FLOOR, SLIME)]
        if not free:
            return
        if self.boss:
            self.enemies.append(Enemy("boss", (self.tx0 + self.cols - 8 + 0.5) * TILE, 4.5 * TILE,
                                      self.index, self))
            budget *= 0.4
        tries = 0
        while budget > 0.4 and tries < 80:
            tries += 1
            k = rng.choice(pool)
            t = ETYPES[k]
            n = rng.randint(*t["group"]) if "group" in t else 1
            cost = t["cost"] * n
            if cost > budget + 0.6:
                continue
            budget -= cost
            fx, fy = rng.choice(free)
            bx, by = (self.tx0 + fx + 0.5) * TILE, (fy + 0.5) * TILE
            for _ in range(n):
                jx = rng.uniform(-12, 12) if n > 1 else 0
                jy = rng.uniform(-12, 12) if n > 1 else 0
                self.enemies.append(Enemy(k, bx + jx, by + jy, self.index, self))

    def open_door(self):
        for y in (3, 4, 5):
            if self.grid[y][self.cols - 1] == DOOR:
                self.grid[y][self.cols - 1] = FLOOR

    def seal_door(self):
        for y in (3, 4, 5):
            self.grid[y][self.cols - 1] = WALL

    def compute_flow(self, lx, ly):
        if not (0 <= lx < self.cols and 0 <= ly < ROWS) or self.grid[ly][lx] in SOLID:
            return
        f = [[INF] * self.cols for _ in range(ROWS)]
        f[ly][lx] = 0
        dq = deque([(lx, ly)])
        while dq:
            x, y = dq.popleft()
            v = f[y][x] + 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.cols and 0 <= ny < ROWS and f[ny][nx] > v \
                        and self.grid[ny][nx] not in SOLID:
                    f[ny][nx] = v
                    dq.append((nx, ny))
        self.flow = f
        self.flow_src = (lx, ly)


# ----------------------------------------------------------------------------
# Игра
# ----------------------------------------------------------------------------
def find_font():
    for name in ("segoeui", "arial", "dejavusans", "verdana", "tahoma", "liberationsans", "notosans"):
        f = pygame.font.match_font(name)
        if f:
            return f
    return None


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.font_path = find_font()
        self.fonts = {}
        self.perk_icons = {}
        icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        for key, _, _ in PERKS:
            icon_path = os.path.join(icon_dir, f"{key}.png")
            if os.path.isfile(icon_path):
                image = pygame.image.load(icon_path).convert_alpha()
                scale = 56 / max(image.get_size())
                size = tuple(max(1, int(value * scale)) for value in image.get_size())
                scaled = pygame.transform.smoothscale(image, size)
                icon = pygame.Surface((64, 64), pygame.SRCALPHA)
                icon.blit(scaled, ((64 - size[0]) // 2, (64 - size[1]) // 2))
                self.perk_icons[key] = icon
        self.best_score = 0
        self.best_depth = 0
        self.load()
        self.anim = 0.0
        self.trees = [[random.uniform(0, W), self.rand_band_y(), random.uniform(10, 22), random.random()]
                      for _ in range(22)]
        self.streaks = [[random.uniform(0, W), self.rand_band_y(), random.uniform(30, 90)] for _ in range(40)]
        self.col_ground = BIOMES["bunk"]["ground"]
        self.col_sky = BIOMES["bunk"]["sky"]
        self.state = "menu"
        self.cards = []
        self.card_rects = []
        self.new_run()

    # --- сервис ---------------------------------------------------------------
    def rand_band_y(self):
        if random.random() < 0.5:
            return random.uniform(8, OY - 12)
        return random.uniform(OY + ROWS * TILE + 12, H - 8)

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.Font(self.font_path, size)
        return self.fonts[size]

    def text(self, s, size, pos, col=(240, 240, 240), center=False, shadow=True, alpha=255):
        f = self.font(size)
        img = f.render(s, True, col)
        if shadow:
            sh = f.render(s, True, (0, 0, 0))
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        if alpha < 255:
            img.set_alpha(alpha)
        if shadow:
            if alpha < 255:
                sh.set_alpha(alpha)
            self.screen.blit(sh, (r.x + 2, r.y + 2))
        self.screen.blit(img, r)
        return r

    def wrap(self, s, size, maxw):
        f = self.font(size)
        words, lines, cur = s.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if f.size(t)[0] <= maxw:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def load(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            self.best_score = int(d.get("score", 0))
            self.best_depth = int(d.get("depth", 0))
        except Exception:
            pass

    def save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as fh:
                json.dump({"score": self.best_score, "depth": self.best_depth}, fh)
        except Exception:
            pass

    # --- новая игра -------------------------------------------------------------
    def new_run(self):
        self.rng = random.Random()
        self.cars = []
        self.bullets = []
        self.parts = []
        self.rings = []
        self.zaps = []
        self.pickups = []
        self.chests = []
        self.depth = 0
        self.score = 0
        self.kills = 0
        self.time = 0.0
        self.banner = None
        self.shake = 0.0
        self.shake_off = (0, 0)
        self.damage_flash = 0.0
        self.gap_x = -TILE * 6
        self.gap_started = False
        self.gap_dmg_t = 0.0
        self.last_key = None
        self.hint_t = 14.0
        self.last_activated = 0
        car0 = self.make_car(0, 0)
        car0.activated = True
        self.player = Player(3.5 * TILE, 4.5 * TILE)
        self.cam_x = self.player.x - W * 0.42
        spot = self.chest_spot(car0, 10)
        self.chests.append({"x": (spot[0] + 0.5) * TILE, "y": (spot[1] + 0.5) * TILE, "t": random.random() * 6})
        self.banner = ["Последний вагон", "Поезд не остановить. Двигайся вперёд.", 3.5]

    def make_car(self, index, tx0):
        cands = [k for k, b in BIOMES.items() if b["min"] <= index and k != self.last_key]
        key = "bunk" if index == 0 else self.rng.choice(cands)
        self.last_key = key
        car = Car(index, tx0, key, self.rng)
        self.cars.append(car)
        return car

    def extend(self):
        while True:
            last = self.cars[-1]
            if (last.tx0 + last.cols) * TILE > self.player.x + 2600:
                break
            self.make_car(last.index + 1, last.tx0 + last.cols - 1)

    # --- мир ---------------------------------------------------------------------
    def car_at_tx(self, tx):
        for c in self.cars:
            lo = c.tx0 + (0 if c.index == 0 else 1)
            if lo <= tx <= c.tx0 + c.cols - 1:
                return c
        return None

    def tile_at(self, px, py):
        ty = int(math.floor(py / TILE))
        if ty < 0 or ty >= ROWS:
            return WALL
        tx = int(math.floor(px / TILE))
        c = self.car_at_tx(tx)
        if c is None:
            return WALL
        return c.grid[ty][tx - c.tx0]

    def solid_at(self, px, py):
        return self.tile_at(px, py) in SOLID

    def blocked(self, x, y, r):
        for ox in (-r, 0, r):
            for oy in (-r, 0, r):
                if self.tile_at(x + ox, y + oy) in SOLID:
                    return True
        return False

    def move(self, ent, dx, dy):
        nx = ent.x + dx
        if not self.blocked(nx, ent.y, ent.r):
            ent.x = nx
        ny = ent.y + dy
        if not self.blocked(ent.x, ny, ent.r):
            ent.y = ny

    def line_clear(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = int(d / 10) + 1
        for i in range(1, n):
            t = i / n
            if self.solid_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t):
                return False
        return True

    def player_car(self):
        c = self.car_at_tx(int(self.player.x // TILE))
        return c or self.cars[0]

    def vent_state(self, car, lx, ly):
        ph = (self.time + car.vent_phase.get((lx, ly), 0.0)) % 3.5
        if 1.2 <= ph < 2.0:
            return 2
        if 0.5 <= ph < 1.2:
            return 1
        return 0

    # --- эффекты -----------------------------------------------------------------
    def burst(self, x, y, col, n=8, spd=120):
        for _ in range(n):
            a = random.random() * 6.283
            v = random.uniform(0.3, 1.0) * spd
            life = random.uniform(0.25, 0.6)
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life, col, random.uniform(2, 4)])

    def ring(self, x, y, col, radius=36, life=0.24, width=2):
        self.rings.append([x, y, life, life, col, radius, width])

    def dash_burst(self):
        p = self.player
        radius = 86 + 8 * (p.ram - 1)
        damage = 2 + p.ram - 1
        self.ring(p.x, p.y, (255, 170, 90), radius, 0.34, 4)
        self.burst(p.x, p.y, (255, 170, 90), 16, 180)
        for car in self.cars:
            if not car.activated:
                continue
            for enemy in list(car.enemies):
                dx, dy = enemy.x - p.x, enemy.y - p.y
                distance = math.hypot(dx, dy)
                if distance > radius:
                    continue
                enemy.hp -= damage
                enemy.flash = 0.12
                if distance:
                    self.move(enemy, dx / distance * 28, dy / distance * 28)
                if enemy.hp <= 0:
                    self.kill_enemy(enemy)

    def chain_lightning(self, source, bullet):
        start_x, start_y = source.x, source.y
        previous = source
        for _ in range(bullet.arc):
            nearest = None
            nearest_distance = 145
            for car in self.cars:
                if not car.activated:
                    continue
                for enemy in car.enemies:
                    if enemy in bullet.hit:
                        continue
                    distance = math.hypot(enemy.x - previous.x, enemy.y - previous.y)
                    if distance < nearest_distance:
                        nearest = enemy
                        nearest_distance = distance
            if nearest is None:
                break
            bullet.hit.append(nearest)
            nearest.hp -= max(1, bullet.dmg // 2)
            nearest.flash = 0.12
            self.zaps.append([start_x, start_y, nearest.x, nearest.y, 0.14])
            self.ring(nearest.x, nearest.y, (150, 210, 255), 20, 0.18)
            self.burst(nearest.x, nearest.y, (150, 210, 255), 5, 95)
            if nearest.hp <= 0:
                self.kill_enemy(nearest)
            start_x, start_y = nearest.x, nearest.y
            previous = nearest

    def explode(self, x, y, bullet):
        radius = 54 + 10 * (bullet.blast - 1)
        damage = max(1, (bullet.dmg + bullet.blast - 1) // 2)
        self.ring(x, y, (255, 150, 70), radius, 0.3, 3)
        self.burst(x, y, (255, 170, 90), 12, 150)
        for car in self.cars:
            if not car.activated:
                continue
            for enemy in list(car.enemies):
                if enemy in bullet.hit or math.hypot(enemy.x - x, enemy.y - y) > radius:
                    continue
                bullet.hit.append(enemy)
                enemy.hp -= damage
                enemy.flash = 0.12
                if enemy.hp <= 0:
                    self.kill_enemy(enemy)

    # --- ввод --------------------------------------------------------------------
    def event(self, ev):
        if ev.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if ev.type == pygame.KEYDOWN:
            k = ev.key
            if k == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            if self.state == "menu":
                if k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    self.new_run()
                    self.state = "play"
                elif k == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
            elif self.state == "dead":
                if k in (pygame.K_RETURN, pygame.K_r, pygame.K_SPACE):
                    self.new_run()
                    self.state = "play"
                elif k == pygame.K_ESCAPE:
                    self.state = "menu"
            elif self.state == "pause":
                if k in (pygame.K_ESCAPE, pygame.K_p):
                    self.state = "play"
                elif k == pygame.K_q:
                    self.state = "menu"
            elif self.state == "perk":
                if k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3):
                    idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                           pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2}[k]
                    self.pick_card(idx)
            elif self.state == "play":
                if k in (pygame.K_ESCAPE, pygame.K_p):
                    self.state = "pause"
                elif k in (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_SPACE):
                    self.try_dash(pygame.key.get_pressed(), pygame.mouse.get_pos())
                elif k == pygame.K_e:
                    self.try_open_chest()
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.state == "perk":
            for i, r in enumerate(self.card_rects):
                if r.collidepoint(ev.pos):
                    self.pick_card(i)

    def move_dir(self, keys):
        mx = (1 if (keys[pygame.K_d] or keys[pygame.K_RIGHT]) else 0) - \
             (1 if (keys[pygame.K_a] or keys[pygame.K_LEFT]) else 0)
        my = (1 if (keys[pygame.K_s] or keys[pygame.K_DOWN]) else 0) - \
             (1 if (keys[pygame.K_w] or keys[pygame.K_UP]) else 0)
        n = math.hypot(mx, my)
        if n:
            return mx / n, my / n
        return 0.0, 0.0

    def try_dash(self, keys, mpos):
        p = self.player
        if p.dash_cd > 0 or p.dash_t > 0:
            return
        dx, dy = self.move_dir(keys)
        if not (dx or dy):
            wx, wy = mpos[0] + self.cam_x, mpos[1] - OY
            d = math.hypot(wx - p.x, wy - p.y) or 1
            dx, dy = (wx - p.x) / d, (wy - p.y) / d
        p.dash_dir = (dx, dy)
        p.dash_t = 0.17
        p.dash_cd = p.dash_cd_base
        p.iframes = max(p.iframes, 0.3)
        self.ring(p.x, p.y, (150, 220, 255), 52, 0.32, 3)
        self.burst(p.x, p.y, (150, 220, 255), 10, 90)
        if p.ram:
            self.dash_burst()

    def try_open_chest(self):
        p = self.player
        for ch in self.chests:
            if math.hypot(ch["x"] - p.x, ch["y"] - p.y) < 64:
                self.cards = roll_perks(3, self.depth, ch.get("bonus", 1.0))
                self.open_chest = ch
                self.state = "perk"
                return

    def pick_card(self, idx):
        if idx >= len(self.cards):
            return
        key = self.cards[idx][0]
        p = self.player
        p.perks[key] += 1
        p.recalc()
        if self.open_chest in self.chests:
            self.chests.remove(self.open_chest)
        self.burst(p.x, p.y, (255, 220, 100), 20, 160)
        self.state = "play"

    # --- обновление --------------------------------------------------------------
    def update(self, dt):
        self.anim += dt
        self.update_scenery(dt)
        self.damage_flash = max(0.0, self.damage_flash - dt)
        # плавная смена цветов окружения
        b = self.player_car().b
        self.col_ground = lerp_col(self.col_ground, b["ground"], min(1, dt * 2.0))
        self.col_sky = lerp_col(self.col_sky, b["sky"], min(1, dt * 2.0))
        if self.state != "play":
            return
        keys = pygame.key.get_pressed()
        mpos = pygame.mouse.get_pos()
        mb = pygame.mouse.get_pressed()
        self.time += dt
        self.hint_t = max(0, self.hint_t - dt)
        p = self.player

        self.extend()
        cur = self.player_car()

        # активация вагона
        if not cur.activated and int(p.x // TILE) >= cur.tx0 + 3:
            self.activate(cur)

        # --- игрок ---
        p.iframes = max(0, p.iframes - dt)
        p.fire_cd = max(0, p.fire_cd - dt)
        p.dash_cd = max(0, p.dash_cd - dt)
        p.slow = max(0, p.slow - dt)
        tile_here = self.tile_at(p.x, p.y)
        mdx, mdy = self.move_dir(keys)
        if p.dash_t > 0:
            p.dash_t -= dt
            p.vx, p.vy = p.dash_dir[0] * 680, p.dash_dir[1] * 680
            if random.random() < 0.8:
                self.parts.append([p.x, p.y, 0, 0, 0.25, 0.25, (150, 220, 255), 6])
        else:
            sp = p.speed
            if p.slow > 0:
                sp *= 0.6
            if tile_here == SLIME:
                sp *= 0.55
            tx, ty = mdx * sp, mdy * sp
            if cur.b.get("wind"):
                tx += math.cos(self.time * 0.4) * 90
                ty += math.sin(self.time * 0.27) * 90
            k = 2.3 if cur.b.get("ice") else 16.0
            f = min(1.0, k * dt)
            p.vx += (tx - p.vx) * f
            p.vy += (ty - p.vy) * f
        self.move(p, p.vx * dt, p.vy * dt)

        # опасные клетки
        if tile_here == THORN:
            self.hurt(1)
        elif tile_here == VENT:
            lx = int(p.x // TILE) - cur.tx0
            ly = int(p.y // TILE)
            if self.vent_state(cur, lx, ly) == 2:
                self.hurt(1)

        # Разрыв
        if self.gap_started:
            sp = min(70, 16 + self.depth * 1.5)
            self.gap_x += sp * dt
            if p.x < self.gap_x:
                self.gap_dmg_t -= dt
                if self.gap_dmg_t <= 0:
                    self.gap_dmg_t = 0.7
                    self.hurt(1, force=True)
        # убрать врагов позади Разрыва
        for c in self.cars:
            for e in list(c.enemies):
                if e.x < self.gap_x:
                    c.enemies.remove(e)

        # стрельба
        wx, wy = mpos[0] + self.cam_x, mpos[1] - OY
        aim = math.atan2(wy - p.y, wx - p.x)
        self.aim = aim
        if mb[0] and p.fire_cd <= 0:
            p.fire_cd = p.fire_cd_base
            p.shot_count += 1
            n = p.shots
            muzzle_x, muzzle_y = p.x + math.cos(aim) * 18, p.y + math.sin(aim) * 18
            self.burst(muzzle_x, muzzle_y, (255, 220, 130), 3, 75)
            for i in range(n):
                a = aim + (i - (n - 1) / 2) * 0.16
                bx, by = p.x + math.cos(a) * 14, p.y + math.sin(a) * 14
                self.bullets.append(Bullet(bx, by, a, 640, p.dmg, "p", (255, 240, 140),
                                           r=4 + min(3, p.dmg - 1), life=0.9,
                                           pierce=p.pierce, bounce=p.bounce, slow=p.cold,
                                           arc=p.arc, blast=p.blast))
            if p.nova and p.shot_count % max(3, 7 - 2 * p.nova) == 0:
                self.ring(p.x, p.y, (205, 130, 255), 72, 0.3, 3)
                self.burst(p.x, p.y, (205, 130, 255), 12, 150)
                for i in range(8):
                    angle = i * math.tau / 8
                    self.bullets.append(Bullet(
                        p.x, p.y, angle, 480, max(1, p.dmg // 2), "p", (205, 130, 255),
                        r=4, life=0.7, pierce=p.pierce,
                    ))
        # --- враги ---
        if cur.activated:
            if cur.flow_src != self.flow_target(cur):
                tgt = self.flow_target(cur)
                cur.compute_flow(*tgt)
        for c in self.cars:
            if not c.activated:
                continue
            for e in list(c.enemies):
                self.update_enemy(e, dt)
            self.separate(c)

        self.update_bullets(dt)

        # зачистка
        if cur.activated and not cur.cleared and not cur.enemies:
            self.clear_car(cur)

        # подборы
        for pk in list(self.pickups):
            if math.hypot(pk[0] - p.x, pk[1] - p.y) < 22:
                if p.hp < p.maxhp:
                    p.hp += 1
                    self.pickups.remove(pk)
                    self.burst(pk[0], pk[1], (255, 90, 120), 8)

        # частицы
        for pt in self.parts:
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[4] -= dt
        self.parts = [pt for pt in self.parts if pt[4] > 0]
        for ring in self.rings:
            ring[2] -= dt
        self.rings = [ring for ring in self.rings if ring[2] > 0]
        for zap in self.zaps:
            zap[4] -= dt
        self.zaps = [zap for zap in self.zaps if zap[4] > 0]

        # баннер
        if self.banner:
            self.banner[2] -= dt
            if self.banner[2] <= 0:
                self.banner = None

        # камера
        target = p.x - W * 0.42
        self.cam_x += (target - self.cam_x) * (1 - math.exp(-8 * dt))
        self.shake = max(0, self.shake - dt * 30)
        if self.shake > 0:
            self.shake_off = (random.uniform(-1, 1) * self.shake, random.uniform(-1, 1) * self.shake)
        else:
            self.shake_off = (0, 0)

        # убрать далёкие вагоны
        self.cars = [c for c in self.cars
                     if not ((c.tx0 + c.cols) * TILE < self.cam_x - 400 and c.index < cur.index)]

    def flow_target(self, car):
        p = self.player
        lx = max(1, min(car.cols - 2, int(p.x // TILE) - car.tx0))
        ly = max(1, min(ROWS - 2, int(p.y // TILE)))
        return (lx, ly)

    def activate(self, car):
        car.activated = True
        self.depth = car.index
        self.last_activated = car.index
        prev = None
        for c in self.cars:
            if c.index == car.index - 1:
                prev = c
        if prev:
            prev.seal_door()
        if car.index >= 1 and not self.gap_started:
            self.gap_started = True
            self.gap_x = car.tx0 * TILE - 14 * TILE
        self.player.shield = self.player.max_shield
        sub = car.b["name"]
        if car.boss:
            sub += " — КОНДУКТОР!"
        self.banner = [f"Вагон №{car.index}", sub, 3.0]
        self.score += 50

    def chest_spot(self, car, cx, cy=4):
        for r in range(0, 10):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    x, y = cx + dx, cy + dy
                    if 3 <= x <= car.cols - 4 and 1 <= y <= ROWS - 2 and car.grid[y][x] == FLOOR:
                        return (x, y)
        return None

    def clear_car(self, car):
        car.cleared = True
        car.open_door()
        self.score += 100 + car.index * 10
        self.gap_x -= 3 * TILE
        # сундук
        spot = self.chest_spot(car, car.cols // 2)
        if spot:
            self.chests.append({"x": (car.tx0 + spot[0] + 0.5) * TILE, "y": (spot[1] + 0.5) * TILE,
                                "t": random.random() * 6, "bonus": 3.0 if car.boss else 1.0})
        self.banner = ["Вагон зачищен", "Дверь открыта · сундук ждёт (E)", 2.5]

    def hurt(self, n, force=False):
        p = self.player
        if p.dash_t > 0 and not force:
            return
        if p.iframes > 0 and not force:
            return
        if p.shield > 0:
            p.shield -= 1
            p.iframes = max(p.iframes, 0.6)
            self.ring(p.x, p.y, (120, 200, 255), 48, 0.28, 3)
            self.burst(p.x, p.y, (120, 200, 255), 14)
            self.shake = max(self.shake, 5)
            return
        p.hp -= n
        p.iframes = max(p.iframes, 1.0) if not force else p.iframes
        self.damage_flash = 0.28
        self.ring(p.x, p.y, (255, 85, 95), 58, 0.34, 3)
        self.shake = max(self.shake, 9)
        self.burst(p.x, p.y, (255, 80, 80), 12, 150)
        if p.hp <= 0:
            self.die()

    def die(self):
        self.state = "dead"
        self.best_score = max(self.best_score, self.score)
        self.best_depth = max(self.best_depth, self.depth)
        self.save()

    # --- враги -------------------------------------------------------------------
    def steer(self, e, dx, dy, dist):
        if self.line_clear(e.x, e.y, e.x + dx, e.y + dy):
            return dx / dist, dy / dist
        c = e.car
        if c.flow is None:
            return dx / dist, dy / dist
        lx = int(e.x // TILE) - c.tx0
        ly = int(e.y // TILE)
        if not (0 <= lx < c.cols and 0 <= ly < ROWS):
            return dx / dist, dy / dist
        best = c.flow[ly][lx]
        bx = by = None
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = lx + ox, ly + oy
            if 0 <= nx < c.cols and 0 <= ny < ROWS:
                if ox and oy and (c.flow[ly][nx] >= INF or c.flow[ny][lx] >= INF):
                    continue
                v = c.flow[ny][nx]
                if v < best:
                    best = v
                    bx, by = nx, ny
        if bx is None:
            return dx / dist, dy / dist
        tx, ty = (c.tx0 + bx + 0.5) * TILE, (by + 0.5) * TILE
        ddx, ddy = tx - e.x, ty - e.y
        dd = math.hypot(ddx, ddy) or 1
        return ddx / dd, ddy / dd

    def eshoot(self, e, ang, spd, slow=0):
        col = (140, 220, 255) if slow else (255, 100, 70)
        self.bullets.append(Bullet(e.x + math.cos(ang) * e.r, e.y + math.sin(ang) * e.r, ang, spd, 1, "e", col,
                                   r=5, life=3.0, slow=slow))

    def update_enemy(self, e, dt):
        p = self.player
        d = e.d
        e.age += dt
        e.flash = max(0, e.flash - dt)
        e.slow = max(0, e.slow - dt)
        dx, dy = p.x - e.x, p.y - e.y
        dist = math.hypot(dx, dy) or 1.0
        ang = math.atan2(dy, dx)
        spd = d["spd"] * (0.45 if e.slow > 0 else 1.0) * (1 + min(self.depth, 40) * 0.01)
        beh = d["beh"]
        if beh == "chase":
            vx, vy = self.steer(e, dx, dy, dist)
            self.move(e, vx * spd * dt, vy * spd * dt)
        elif beh == "kite":
            e.strafe_t -= dt
            if e.strafe_t <= 0:
                e.strafe = -e.strafe
                e.strafe_t = random.uniform(1.2, 2.6)
            vx, vy = self.steer(e, dx, dy, dist)
            if dist < 200:
                self.move(e, -dx / dist * spd * dt, -dy / dist * spd * dt)
                self.move(e, -dy / dist * e.strafe * spd * 0.5 * dt, dx / dist * e.strafe * spd * 0.5 * dt)
            elif dist > 320:
                self.move(e, vx * spd * dt, vy * spd * dt)
            else:
                self.move(e, -dy / dist * e.strafe * spd * 0.6 * dt, dx / dist * e.strafe * spd * 0.6 * dt)
            e.cd -= dt
            if e.cd <= 0 and dist < 560 and self.line_clear(e.x, e.y, p.x, p.y):
                self.eshoot(e, ang, d["bspd"], 1 if d.get("slow") else 0)
                e.cd = d["shoot"] * random.uniform(0.9, 1.3)
        elif beh == "phase":
            a = ang + math.sin(e.age * 3 + e.wob) * 0.3
            e.x += math.cos(a) * spd * dt
            e.y += math.sin(a) * spd * dt
            c = e.car
            e.x = max((c.tx0 + 1) * TILE + e.r, min((c.tx0 + c.cols - 1) * TILE - e.r, e.x))
            e.y = max(TILE + e.r, min((ROWS - 1) * TILE - e.r, e.y))
        elif beh == "still":
            e.cd -= dt
            if e.cd <= 0 and dist < 620:
                e.pat ^= 1
                if e.pat:
                    for i in (-1, 0, 1):
                        self.eshoot(e, ang + i * 0.28, d["bspd"])
                else:
                    off = e.age
                    for i in range(6):
                        self.eshoot(e, off + i * math.pi / 3, d["bspd"] * 0.8)
                e.cd = d["shoot"]
        elif beh == "boss":
            ph2 = e.hp < e.maxhp * 0.5
            vx, vy = self.steer(e, dx, dy, dist)
            m = 1.5 if ph2 else 1.0
            self.move(e, vx * spd * m * dt, vy * spd * m * dt)
            e.burst_t -= dt
            if e.burst_t <= 0:
                n = 14 if ph2 else 10
                for i in range(n):
                    self.eshoot(e, e.age + i * 2 * math.pi / n, 190)
                e.burst_t = 2.2 if ph2 else 3.0
            e.summon_t -= dt
            if e.summon_t <= 0:
                e.summon_t = 7.0
                if len(e.car.enemies) < 10:
                    for _ in range(2):
                        ox, oy = random.uniform(-30, 30), random.uniform(-30, 30)
                        if self.solid_at(e.x + ox, e.y + oy):
                            ox = oy = 0
                        e.car.enemies.append(Enemy("passenger", e.x + ox, e.y + oy, e.car.index, e.car))
        if dist < e.r + p.r:
            self.hurt(d.get("contact", 1))

    def separate(self, car):
        es = car.enemies
        for i in range(len(es)):
            a = es[i]
            if a.kind == "ghost":
                continue
            for j in range(i + 1, len(es)):
                b = es[j]
                if b.kind == "ghost":
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                dd = math.hypot(dx, dy)
                m = a.r + b.r
                if 0 < dd < m:
                    push = (m - dd) * 0.5
                    ux, uy = dx / dd, dy / dd
                    self.move(a, -ux * push, -uy * push)
                    self.move(b, ux * push, uy * push)

    def kill_enemy(self, e):
        c = e.car
        if e in c.enemies:
            c.enemies.remove(e)
        p = self.player
        self.kills += 1
        self.score += e.d["score"]
        self.burst(e.x, e.y, e.d["col"], 16, 190)
        if e.kind == "boss":
            self.shake = 14
            for i in range(2):
                self.pickups.append([e.x + i * 24 - 12, e.y])
        elif random.random() < 0.10:
            self.pickups.append([e.x, e.y])
        if p.vamp_need:
            p.kill_count += 1
            if p.kill_count >= p.vamp_need:
                p.kill_count = 0
                if p.hp < p.maxhp:
                    p.hp += 1
                    self.burst(p.x, p.y, (255, 90, 120), 10)

    def update_bullets(self, dt):
        p = self.player
        alive = []
        for b in self.bullets:
            b.life -= dt
            if b.life <= 0 or b.x < self.cam_x - 300 or b.x > self.cam_x + W + 300:
                continue
            nx, ny = b.x + b.vx * dt, b.y + b.vy * dt
            if self.solid_at(nx, ny):
                if b.bounce > 0:
                    b.bounce -= 1
                    sx = self.solid_at(nx, b.y)
                    sy = self.solid_at(b.x, ny)
                    if sx and not sy:
                        b.vx = -b.vx
                    elif sy and not sx:
                        b.vy = -b.vy
                    else:
                        b.vx, b.vy = -b.vx, -b.vy
                    self.ring(b.x, b.y, b.col, 24, 0.18)
                    self.burst(b.x, b.y, b.col, 3, 60)
                    alive.append(b)
                else:
                    self.ring(nx, ny, b.col, 20, 0.16)
                    self.burst(nx, ny, b.col, 3, 60)
                    if b.blast:
                        self.explode(nx, ny, b)
                continue
            b.x, b.y = nx, ny
            if b.own == "p":
                dead = False
                for c in self.cars:
                    if not c.activated:
                        continue
                    for e in list(c.enemies):
                        if e in b.hit:
                            continue
                        if math.hypot(e.x - b.x, e.y - b.y) < e.r + b.r:
                            e.hp -= b.dmg
                            e.flash = 0.1
                            if b.slow:
                                e.slow = 1.0 + 0.8 * b.slow
                            b.hit.append(e)
                            self.ring(b.x, b.y, (255, 255, 200), 24, 0.18)
                            self.burst(b.x, b.y, (255, 255, 200), 4, 100)
                            if e.hp <= 0:
                                self.kill_enemy(e)
                            if b.arc:
                                self.chain_lightning(e, b)
                            if b.blast:
                                self.explode(e.x, e.y, b)
                            if b.pierce > 0:
                                b.pierce -= 1
                            else:
                                dead = True
                                break
                    if dead:
                        break
                if dead:
                    continue
            else:
                if math.hypot(p.x - b.x, p.y - b.y) < p.r + b.r:
                    if p.dash_t <= 0 and p.iframes <= 0:
                        self.hurt(b.dmg)
                        if b.slow:
                            p.slow = 1.6
                        continue
                    elif p.dash_t > 0:
                        pass
            alive.append(b)
        self.bullets = alive

    def update_scenery(self, dt):
        sp = 420
        for t in self.trees:
            t[0] -= sp * dt * (0.8 + t[2] / 40)
            if t[0] < -40:
                t[0] = W + 40
                t[1] = self.rand_band_y()
                t[2] = random.uniform(10, 22)
                t[3] = random.random()
        for s in self.streaks:
            s[0] -= 900 * dt
            if s[0] < -100:
                s[0] = W + random.uniform(0, 200)
                s[1] = self.rand_band_y()
                s[2] = random.uniform(30, 90)

    # --- отрисовка ---------------------------------------------------------------
    def draw(self):
        s = self.screen
        cam = int(self.cam_x + self.shake_off[0])
        oy = OY + int(self.shake_off[1])
        s.fill(self.col_ground)
        dark = shade(self.col_ground, 0.82)
        for x, y, l in self.streaks:
            pygame.draw.line(s, dark, (x, y), (x + l, y), 2)
        for x, y, sz, kind in self.trees:
            if kind > 0.82:
                pygame.draw.line(s, shade(self.col_ground, 0.6), (x, y - 26), (x, y + 18), 3)
                pygame.draw.line(s, shade(self.col_ground, 0.6), (x - 10, y - 20), (x + 10, y - 20), 2)
            else:
                pygame.draw.circle(s, shade(self.col_ground, 0.72), (int(x), int(y)), int(sz))
                pygame.draw.circle(s, shade(self.col_ground, 1.18), (int(x - 3), int(y - 3)), int(sz * 0.5))
        ta, tb = cam // TILE - 1, (cam + W) // TILE + 1
        for c in self.cars:
            draw_train_car(self, c, cam, oy, ta, tb)
        self.draw_entities(cam, oy)
        self.draw_gap(cam)
        if self.damage_flash > 0:
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            alpha = int(150 * self.damage_flash / 0.28)
            for inset, strength in ((0, 1.0), (8, 0.55), (16, 0.25)):
                pygame.draw.rect(overlay, (255, 30, 45, int(alpha * strength)),
                                 (inset, inset, W - inset * 2, H - inset * 2), 5)
            s.blit(overlay, (0, 0))
        self.draw_hud()
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "pause":
            self.overlay(150)
            self.text("ПАУЗА", 64, (W // 2, H // 2 - 30), center=True)
            self.text("Esc — продолжить · Q — в меню", 24, (W // 2, H // 2 + 30), (200, 200, 200), center=True)
        elif self.state == "perk":
            self.draw_perks()
        elif self.state == "dead":
            self.draw_dead()

    def overlay(self, a):
        o = pygame.Surface((W, H), pygame.SRCALPHA)
        o.fill((0, 0, 0, a))
        self.screen.blit(o, (0, 0))

    def draw_entities(self, cam, oy):
        s = self.screen
        p = self.player
        # сундуки
        for ch in self.chests:
            x, y = ch["x"] - cam, ch["y"] + oy
            glow = 18 + int(math.sin(self.anim * 4 + ch["t"]) * 4)
            g = pygame.Surface((90, 90), pygame.SRCALPHA)
            gc = (190, 100, 255, 90) if ch.get("bonus", 1.0) > 1 else (255, 220, 90, 70)
            pygame.draw.circle(g, gc, (45, 45), glow + 12)
            s.blit(g, (x - 45, y - 45))
            pygame.draw.rect(s, (120, 76, 30), (x - 15, y - 10, 30, 22), border_radius=3)
            pygame.draw.rect(s, (230, 190, 70), (x - 15, y - 10, 30, 22), 2, border_radius=3)
            pygame.draw.rect(s, (230, 190, 70), (x - 3, y - 2, 6, 8))
            if math.hypot(ch["x"] - p.x, ch["y"] - p.y) < 64 and self.state == "play":
                self.text("E — открыть", 20, (x, y - 34), (255, 240, 160), center=True)
        # сердечки
        for pk in self.pickups:
            self.draw_heart(int(pk[0] - cam - 10), int(pk[1] + oy - 10 + math.sin(self.anim * 5) * 2), 20,
                            (255, 80, 110))
        # враги
        for c in self.cars:
            for e in c.enemies:
                x, y = int(e.x - cam), int(e.y + oy)
                if x < -60 or x > W + 60:
                    continue
                col = (255, 255, 255) if e.flash > 0 else e.d["col"]
                if e.slow > 0 and e.flash <= 0:
                    col = lerp_col(col, (140, 200, 255), 0.5)
                if e.kind == "ghost":
                    g = pygame.Surface((50, 50), pygame.SRCALPHA)
                    pygame.draw.circle(g, col + (150,), (25, 25), e.r)
                    s.blit(g, (x - 25, y - 25 + int(math.sin(e.age * 4) * 3)))
                elif e.kind == "spore":
                    pygame.draw.circle(s, shade(col, 0.6), (x, y), e.r + 3)
                    pygame.draw.circle(s, col, (x, y), e.r)
                    for i in range(5):
                        a = e.age * 1.5 + i * 1.256
                        pygame.draw.circle(s, (220, 255, 150), (int(x + math.cos(a) * 8), int(y + math.sin(a) * 8)), 3)
                else:
                    pygame.draw.circle(s, shade(col, 0.55), (x, y), e.r + 2)
                    pygame.draw.circle(s, col, (x, y), e.r)
                    a = math.atan2(p.y - e.y, p.x - e.x)
                    ex, ey = math.cos(a) * e.r * 0.45, math.sin(a) * e.r * 0.45
                    pygame.draw.circle(s, (255, 255, 255), (int(x + ex - 3), int(y + ey - 2)), max(2, e.r // 5))
                    pygame.draw.circle(s, (255, 255, 255), (int(x + ex + 3), int(y + ey - 2)), max(2, e.r // 5))
                    pygame.draw.circle(s, (20, 20, 30), (int(x + ex - 3 + math.cos(a)), int(y + ey - 2 + math.sin(a))), 1)
                    pygame.draw.circle(s, (20, 20, 30), (int(x + ex + 3 + math.cos(a)), int(y + ey - 2 + math.sin(a))), 1)
                    if e.kind == "boss":
                        pygame.draw.rect(s, (40, 20, 30), (x - 16, y - e.r - 12, 32, 10))
                if e.hp < e.maxhp and e.kind != "boss":
                    w = 26
                    pygame.draw.rect(s, (40, 10, 10), (x - w // 2, y - e.r - 9, w, 4))
                    pygame.draw.rect(s, (230, 60, 60), (x - w // 2, y - e.r - 9, int(w * e.hp / e.maxhp), 4))
        # частицы
        for x, y, vx, vy, life, ml, col, sz in self.parts:
            a = max(0.0, life / ml)
            pygame.draw.circle(s, lerp_col((0, 0, 0), col, 0.4 + 0.6 * a), (int(x - cam), int(y + oy)), max(1, int(sz * a)))
        for x, y, life, ml, col, max_radius, width in self.rings:
            progress = 1.0 - life / ml
            radius = int(5 + (max_radius - 5) * progress)
            ring_col = shade(col, 0.35 + 0.65 * (life / ml))
            pygame.draw.circle(s, ring_col, (int(x - cam), int(y + oy)), radius, width)
        for x1, y1, x2, y2, life in self.zaps:
            start = (int(x1 - cam), int(y1 + oy))
            end = (int(x2 - cam), int(y2 + oy))
            mid_x = (start[0] + end[0]) // 2 + int(math.sin(self.anim * 80 + x2) * 8)
            mid_y = (start[1] + end[1]) // 2 + int(math.cos(self.anim * 70 + y2) * 8)
            pygame.draw.line(s, (65, 110, 210), start, (mid_x, mid_y), 5)
            pygame.draw.line(s, (180, 225, 255), (mid_x, mid_y), end, 3)
        # пули
        for b in self.bullets:
            x, y = int(b.x - cam), int(b.y + oy)
            speed = math.hypot(b.vx, b.vy) or 1
            tail = 18 + b.r * 2
            tx = int(x - b.vx / speed * tail)
            ty = int(y - b.vy / speed * tail)
            pygame.draw.line(s, shade(b.col, 0.45), (tx, ty), (x, y), b.r + 3)
            pygame.draw.line(s, b.col, (tx, ty), (x, y), max(1, b.r))
            pygame.draw.circle(s, shade(b.col, 0.5), (x, y), b.r + 2)
            pygame.draw.circle(s, b.col, (x, y), b.r)
        # игрок
        if self.state != "dead":
            x, y = int(p.x - cam), int(p.y + oy)
            blink = p.iframes > 0 and p.dash_t <= 0 and int(self.anim * 20) % 2 == 0
            if not blink:
                a = getattr(self, "aim", 0)
                pygame.draw.line(s, (60, 70, 90), (x, y), (x + math.cos(a) * 20, y + math.sin(a) * 20), 6)
                pygame.draw.circle(s, (30, 60, 90), (x, y), p.r + 2)
                pygame.draw.circle(s, (100, 210, 255), (x, y), p.r)
                pygame.draw.circle(s, (255, 255, 255), (int(x + math.cos(a) * 5), int(y + math.sin(a) * 5)), 3)
            if p.shield > 0:
                pygame.draw.circle(s, (120, 200, 255), (x, y), p.r + 7, 2)
        # ветер в пустоте
        if self.player_car().b.get("wind"):
            for i in range(14):
                wx = (ihash(i, 7) % W + int(self.anim * 160)) % W
                wy = oy + (ihash(i, 11) % (ROWS * TILE))
                pygame.draw.line(s, (120, 90, 200), (wx, wy), (wx + 22, wy + int(math.sin(self.time * 0.27) * 6)), 1)

    def draw_gap(self, cam):
        s = self.screen
        gx = int(self.gap_x - cam)
        if gx <= 0:
            return
        gx = min(gx, W)
        pygame.draw.rect(s, (8, 4, 14), (0, 0, gx, H))
        # рваный край
        for i in range(0, H, 14):
            off = int(math.sin(i * 0.13 + self.anim * 6) * 9 + (ihash(i, int(self.anim * 8)) % 7))
            pygame.draw.rect(s, (8, 4, 14), (gx - 4, i, 14 + off, 14))
            if (i // 14 + int(self.anim * 10)) % 5 == 0:
                pygame.draw.circle(s, (255, 90, 60), (gx + off, i + 7), 3)
        for i in range(24):
            sy = ihash(i, 3) % H
            sx = (ihash(i, 5) % max(1, gx)) - int(self.anim * 60) % max(1, gx)
            pygame.draw.circle(s, (80, 30, 90), (abs(sx) % gx, sy), 2)

    def draw_heart(self, x, y, size, col):
        r = size // 4
        pygame.draw.circle(self.screen, col, (x + r, y + r), r)
        pygame.draw.circle(self.screen, col, (x + 3 * r, y + r), r)
        pygame.draw.polygon(self.screen, col, [(x, y + r + 1), (x + 4 * r, y + r + 1), (x + 2 * r, y + 4 * r)])

    def draw_hud(self):
        if self.state == "menu":
            return
        p = self.player
        for i in range(p.maxhp):
            col = (235, 70, 95) if i < p.hp else (70, 30, 40)
            self.draw_heart(18 + i * 30, 14, 24, col)
        for i in range(p.shield):
            pygame.draw.circle(self.screen, (120, 200, 255), (24 + i * 24, 58), 8, 2)
        cur = self.player_car()
        title = f"Вагон №{cur.index} · {cur.b['name']}"
        tw = self.font(26).size(title)[0]
        self.text(title, 26, (W - 20 - tw, 14))
        stats = f"Счёт {self.score}   ·   Убито {self.kills}   ·   Рекорд {max(self.best_score, self.score)}"
        sw = self.font(20).size(stats)[0]
        self.text(stats, 20, (W - 20 - sw, 46), (220, 220, 230))
        # рывок
        w = 120
        pygame.draw.rect(self.screen, (30, 30, 40), (18, H - 28, w, 8))
        frac = 1.0 - (p.dash_cd / p.dash_cd_base if p.dash_cd_base else 0)
        pygame.draw.rect(self.screen, (120, 220, 255) if frac >= 1 else (70, 120, 150),
                         (18, H - 28, int(w * max(0, min(1, frac))), 8))
        self.text("рывок", 16, (18 + w + 8, H - 34), (200, 210, 220))
        # перки
        y = H - 56
        for k, name, _ in reversed(PERKS):
            n = p.perks[k]
            if n:
                self.text(f"{name}" + (f" ×{n}" if n > 1 else ""), 16, (18, y), RARITIES[rarity_of(k)][1])
                y -= 18
        # подсказка
        if self.hint_t > 0 and self.state == "play":
            a = int(255 * min(1, self.hint_t / 2))
            self.text("WASD — движение · ЛКМ — стрельба · Shift/Пробел — рывок · E — сундук", 22,
                      (W // 2, H - 24), (255, 255, 255), center=True, alpha=a)
        # босс
        for e in cur.enemies:
            if e.kind == "boss":
                w = 420
                x = W // 2 - w // 2
                pygame.draw.rect(self.screen, (40, 10, 20), (x, 70, w, 14))
                pygame.draw.rect(self.screen, (220, 50, 70), (x, 70, int(w * max(0, e.hp) / e.maxhp), 14))
                self.text("КОНДУКТОР", 18, (W // 2, 58), center=True)
        # предупреждение о Разрыве
        if self.state == "play" and self.gap_started:
            d = p.x - self.gap_x
            if d < 360:
                a = int(120 * (1 - max(0, d) / 360))
                v = pygame.Surface((W, H), pygame.SRCALPHA)
                pygame.draw.rect(v, (200, 20, 40, a), (0, 0, 120, H))
                self.screen.blit(v, (0, 0))
                if int(self.anim * 4) % 2 == 0:
                    self.text("РАЗРЫВ ПОЗАДИ! ВПЕРЁД!", 28, (W // 2, 110), (255, 90, 90), center=True)
        # баннер
        if self.banner and self.state in ("play", "pause", "perk"):
            t = self.banner[2]
            a = int(255 * min(1, t / 0.6, (3.5 - t) / 0.3 if t > 3.2 else 1))
            self.text(self.banner[0], 54, (W // 2, 140), center=True, alpha=max(0, min(255, a)))
            self.text(self.banner[1], 26, (W // 2, 185), (220, 220, 220), center=True, alpha=max(0, min(255, a)))

    def draw_menu(self):
        self.overlay(170)
        self.text("ПОЕЗД БЕЗ КОНЦА", 88, (W // 2, 210), (255, 220, 140), center=True)
        self.text("рогалик про вагоны, которые никогда не кончаются", 28, (W // 2, 280), (210, 210, 220), center=True)
        lines = ["Каждый вагон — новый биом: плацкарт, ресторан, рефрижератор, оранжерея, котельная...",
                 "Зачисти вагон -> дверь откроется -> бери перк из сундука -> беги дальше.",
                 "Сзади ползёт Разрыв. Остановишься — поезд тебя разорвёт.",
                 "Каждый 5-й вагон — Кондуктор."]
        for i, l in enumerate(lines):
            self.text(l, 22, (W // 2, 350 + i * 30), (200, 200, 210), center=True)
        if int(self.anim * 2) % 2 == 0:
            self.text("Enter — начать · Esc — выход", 30, (W // 2, 520), (255, 255, 255), center=True)
        self.text(f"Рекорд: {self.best_score} очков · {self.best_depth} вагонов", 24, (W // 2, 580),
                  (170, 220, 170), center=True)

    def draw_perks(self):
        self.overlay(170)
        self.text("СУНДУК — выбери перк", 44, (W // 2, 100), (255, 230, 150), center=True)
        self.card_rects = []
        mp = pygame.mouse.get_pos()
        for i, (key, name, desc) in enumerate(self.cards):
            rname, rcol, _, _ = RARITIES[rarity_of(key)]
            r = pygame.Rect(W // 2 - 480 + i * 330, 170, 300, 380)
            self.card_rects.append(r)
            hov = r.collidepoint(mp)
            if hov:
                pulse = 0.5 + 0.5 * math.sin(self.anim * 5 + i)
                g = pygame.Surface((r.w + 40, r.h + 40), pygame.SRCALPHA)
                pygame.draw.rect(g, rcol + (int(28 + pulse * 34),), g.get_rect(), border_radius=24)
                self.screen.blit(g, (r.x - 20, r.y - 20))
            pygame.draw.rect(self.screen, shade(rcol, 0.28) if hov else shade(rcol, 0.16), r, border_radius=14)
            pygame.draw.rect(self.screen, rcol + (32 if hov else 16,),
                             (r.x + 5, r.y + 5, r.w - 10, 78), border_radius=10)
            if hov:
                shine = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                progress = (self.anim * 0.55 + i * 0.37) % 1.0
                shine_x = int(progress * (r.w + 90)) - 45
                pygame.draw.polygon(shine, (255, 255, 255, 24),
                                    [(shine_x - 30, 0), (shine_x - 6, 0),
                                     (shine_x + 90, r.h), (shine_x + 66, r.h)])
                self.screen.blit(shine, r.topleft)
                for spark in range(5):
                    phase = self.anim * 1.7 + spark * 1.31 + i
                    sx = r.x + 18 + ihash(i, spark, 3) % (r.w - 36)
                    sy = r.y + 92 + int((phase * 34 + ihash(i, spark, 7) % 180) % (r.h - 110))
                    spark_size = 2 + int((math.sin(phase * 2) + 1) * 1.5)
                    pygame.draw.line(self.screen, rcol, (sx - spark_size, sy), (sx + spark_size, sy), 1)
                    pygame.draw.line(self.screen, rcol, (sx, sy - spark_size), (sx, sy + spark_size), 1)
            pygame.draw.rect(self.screen, rcol, r, 4 if hov else 3, border_radius=14)
            self.text(str(i + 1), 40, (r.x + 24, r.y + 14), rcol)
            self.text(rname.upper(), 20, (r.centerx, r.y + 40), rcol, center=True)
            icon = self.perk_icons.get(key)
            if icon:
                icon_y = r.y + 78
                pygame.draw.circle(self.screen, rcol, (r.centerx, icon_y + 32), 36, 2)
                self.screen.blit(icon, (r.centerx - 32, icon_y))
            self.text(name, 30, (r.centerx, r.y + 154), (255, 255, 255), center=True)
            for j, ln in enumerate(self.wrap(desc, 22, r.w - 40)):
                self.text(ln, 22, (r.centerx, r.y + 202 + j * 28), (210, 210, 225), center=True)
            have = self.player.perks[key]
            if have:
                self.text(f"уже есть: ×{have}", 20, (r.centerx, r.bottom - 36), (150, 220, 150), center=True)
        self.text("клик или клавиши 1 · 2 · 3", 22, (W // 2, 610), (190, 190, 200), center=True)

    def draw_dead(self):
        self.overlay(190)
        self.text("ПОЕЗД ТЕБЯ ПОХОРОНИЛ", 70, (W // 2, 200), (240, 90, 100), center=True)
        self.text(f"Вагонов пройдено: {self.depth}", 34, (W // 2, 310), center=True)
        self.text(f"Убито врагов: {self.kills}", 28, (W // 2, 355), (210, 210, 220), center=True)
        self.text(f"Счёт: {self.score}   ·   Рекорд: {self.best_score}", 28, (W // 2, 400), (255, 230, 150), center=True)
        got = [f"{n}" + (f" ×{self.player.perks[k]}" if self.player.perks[k] > 1 else "")
               for k, n, _ in PERKS if self.player.perks[k]]
        if got:
            self.text("Перки: " + ", ".join(got), 20, (W // 2, 450), (190, 200, 190), center=True)
        self.text("Enter / R — новый забег · Esc — меню", 26, (W // 2, 530), center=True)


def main():
    pygame.init()
    pygame.display.set_caption("Поезд без конца")
    flags = pygame.SCALED | pygame.RESIZABLE
    try:
        screen = pygame.display.set_mode((W, H), flags)
    except pygame.error:
        screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    game = Game(screen)
    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
        for ev in pygame.event.get():
            game.event(ev)
        game.update(dt)
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()