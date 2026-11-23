import math

import pygame

TILE, ROWS = 40, 9
FLOOR, WALL, OBST, THORN, SLIME, DOOR, VENT = range(7)


def lerp_col(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(color, factor):
    return tuple(max(0, min(255, int(value * factor))) for value in color)


def ihash(a, b, c=0):
    value = (a * 374761393 + b * 668265263 + c * 2147483629) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 1274126177) & 0xFFFFFFFF
    return value ^ (value >> 16)


def draw_car(game, car, camera_x, offset_y, first_tile, last_tile):
    screen = game.screen
    biome = car.b
    left = car.tx0 + (0 if car.index == 0 else 1)
    right = car.tx0 + car.cols - 1
    window_color = lerp_col(game.col_sky, (255, 255, 255), 0.25)
    key = car.key

    for tile_x in range(max(left, first_tile), min(right, last_tile) + 1):
        local_x = tile_x - car.tx0
        screen_x = tile_x * TILE - camera_x
        for tile_y in range(ROWS):
            screen_y = tile_y * TILE + offset_y
            tile = car.grid[tile_y][local_x]
            floor_color = biome["floor"][(tile_x + tile_y) % 2]

            if tile == WALL:
                pygame.draw.rect(screen, biome["wall"], (screen_x, screen_y, TILE, TILE))
                if tile_y in (0, ROWS - 1):
                    if tile_x % 4 == 1:
                        frame = pygame.Rect(screen_x + 3, screen_y + 6, TILE - 6, TILE - 12)
                        glass = pygame.Rect(screen_x + 7, screen_y + 10, TILE - 14, TILE - 20)
                        pygame.draw.rect(screen, shade(biome["wall"], 0.48), frame, border_radius=5)
                        pygame.draw.rect(screen, shade(window_color, 0.68), glass, border_radius=3)
                        pygame.draw.polygon(screen, window_color, [
                            (glass.left + 2, glass.bottom - 2),
                            (glass.left + 8, glass.top + 2),
                            (glass.left + 13, glass.top + 2),
                            (glass.left + 7, glass.bottom - 2),
                        ])
                        pygame.draw.line(screen, shade(biome["wall"], 0.55),
                                         (screen_x + TILE // 2, glass.top),
                                         (screen_x + TILE // 2, glass.bottom), 2)
                        pygame.draw.line(screen, shade(biome["wall"], 1.35),
                                         (frame.left + 3, frame.top + 1),
                                         (frame.right - 3, frame.top + 1), 1)
                    else:
                        panel = pygame.Rect(screen_x + 3, screen_y + 4, TILE - 6, TILE - 8)
                        pygame.draw.rect(screen, shade(biome["wall"], 0.78), panel, 1, border_radius=3)
                        pygame.draw.circle(screen, shade(biome["decor"], 0.7),
                                           (screen_x + 6, screen_y + TILE // 2), 1)
                        if tile_x % 7 == 3:
                            lamp_y = screen_y + (TILE - 7 if tile_y == 0 else 2)
                            lamp = 0.78 + 0.22 * math.sin(game.time * 2.2 + tile_x)
                            lamp_color = shade(biome["decor"], lamp)
                            pygame.draw.rect(screen, shade(biome["wall"], 0.45),
                                             (screen_x + 10, lamp_y - 1, TILE - 20, 6), border_radius=3)
                            pygame.draw.rect(screen, lamp_color,
                                             (screen_x + 12, lamp_y, TILE - 24, 3), border_radius=2)
                else:
                    pygame.draw.rect(screen, shade(biome["wall"], 1.15),
                                     (screen_x + 4, screen_y + 4, TILE - 8, TILE - 8), 2)
                continue

            pygame.draw.rect(screen, floor_color, (screen_x, screen_y, TILE, TILE))
            pygame.draw.line(screen, shade(floor_color, 0.88),
                             (screen_x, screen_y + TILE - 1), (screen_x + TILE, screen_y + TILE - 1))
            pygame.draw.line(screen, shade(floor_color, 1.08),
                             (screen_x + TILE - 1, screen_y), (screen_x + TILE - 1, screen_y + TILE))
            tile_hash = ihash(tile_x, tile_y, car.seed)
            if tile == FLOOR and tile_hash % 19 == 0:
                pygame.draw.circle(screen, biome["decor"],
                                   (screen_x + 4 + tile_hash % 31, screen_y + 4 + (tile_hash >> 5) % 31),
                                   2 + tile_hash % 3)
            if tile == FLOOR and key == "freezer" and tile_hash % 7 == 0:
                pygame.draw.line(screen, (240, 250, 255),
                                 (screen_x + 6, screen_y + 30), (screen_x + 28, screen_y + 8), 1)
            if tile == OBST:
                draw_obstacle(screen, key, biome, screen_x, screen_y, tile_x)
            elif tile == THORN:
                for i in range(3):
                    px = screen_x + 6 + i * 12
                    pygame.draw.polygon(screen, (190, 60, 70), [
                        (px, screen_y + 30), (px + 6, screen_y + 8), (px + 12, screen_y + 30)])
                    pygame.draw.polygon(screen, (120, 30, 40), [
                        (px, screen_y + 30), (px + 6, screen_y + 8), (px + 12, screen_y + 30)], 1)
            elif tile == SLIME:
                pygame.draw.ellipse(screen, (130, 86, 40),
                                    (screen_x + 3, screen_y + 8, TILE - 6, TILE - 16))
                pygame.draw.ellipse(screen, (170, 120, 60), (screen_x + 10, screen_y + 14, 14, 8))
            elif tile == VENT:
                state = game.vent_state(car, local_x, tile_y)
                pygame.draw.rect(screen, (30, 26, 28),
                                 (screen_x + 2, screen_y + 2, TILE - 4, TILE - 4))
                for i in range(4):
                    pygame.draw.line(screen, (60, 56, 58),
                                     (screen_x + 6, screen_y + 8 + i * 8),
                                     (screen_x + TILE - 6, screen_y + 8 + i * 8), 2)
                if state == 1 and int(game.time * 12) % 2:
                    pygame.draw.rect(screen, (255, 150, 40),
                                     (screen_x + 2, screen_y + 2, TILE - 4, TILE - 4), 2)
                elif state == 2:
                    pygame.draw.rect(screen, (255, 120, 20),
                                     (screen_x + 2, screen_y + 2, TILE - 4, TILE - 4))
                    pulse = 10 + int(math.sin(game.time * 30) * 3)
                    pygame.draw.circle(screen, (255, 220, 80),
                                       (screen_x + 20, screen_y + 20), pulse)
            elif tile == DOOR:
                pygame.draw.rect(screen, (80, 24, 30), (screen_x, screen_y, TILE, TILE))
                pygame.draw.rect(screen, (160, 58, 60),
                                 (screen_x + 4, screen_y + 2, TILE - 8, TILE - 4), border_radius=4)
                pygame.draw.line(screen, (210, 115, 82),
                                 (screen_x + 7, screen_y + 4), (screen_x + 7, screen_y + TILE - 4), 2)
                pygame.draw.circle(screen, (245, 196, 100), (screen_x + TILE - 10, screen_y + 20), 2)
                for stripe in range(-1, 4):
                    pygame.draw.line(screen, (70, 28, 32),
                                     (screen_x + stripe * 12, screen_y + TILE),
                                     (screen_x + stripe * 12 + TILE, screen_y), 3)

    visible_left = max(left, first_tile) * TILE - camera_x
    visible_right = (min(right, last_tile) + 1) * TILE - camera_x
    for y in (offset_y + TILE, offset_y + (ROWS - 1) * TILE):
        pygame.draw.line(screen, shade(biome["edge"], 0.72),
                         (visible_left, y), (visible_right, y), 4)
        pygame.draw.line(screen, shade(biome["decor"], 0.75),
                         (visible_left, y - 2), (visible_right, y - 2), 1)

    if car.cleared and car is game.player_car():
        exit_x = (car.tx0 + car.cols - 1) * TILE - camera_x
        if -80 < exit_x < screen.get_width() + 80:
            pulse = int(math.sin(game.time * 6) * 5)
            center_y = 4 * TILE + offset_y + TILE // 2
            pygame.draw.polygon(screen, (120, 255, 150), [
                (exit_x - 40 + pulse, center_y - 14),
                (exit_x - 14 + pulse, center_y),
                (exit_x - 40 + pulse, center_y + 14),
            ])


def draw_obstacle(screen, key, biome, x, y, tile_x):
    obstacle, edge = biome["obst"], biome["edge"]
    if key == "jungle":
        pygame.draw.circle(screen, edge, (x + 20, y + 22), 19)
        pygame.draw.circle(screen, obstacle, (x + 20, y + 18), 18)
        pygame.draw.circle(screen, shade(obstacle, 1.3), (x + 14, y + 12), 6)
    elif key == "freezer":
        points = [(x + 20, y + 2), (x + 38, y + 20), (x + 20, y + 38), (x + 2, y + 20)]
        pygame.draw.polygon(screen, obstacle, points)
        pygame.draw.polygon(screen, edge, points, 3)
        pygame.draw.line(screen, (255, 255, 255), (x + 12, y + 18), (x + 20, y + 8), 2)
    elif key == "void":
        pygame.draw.circle(screen, edge, (x + 20, y + 20), 18)
        pygame.draw.circle(screen, obstacle, (x + 20, y + 20), 14)
        pygame.draw.circle(screen, (20, 10, 40), (x + 20, y + 20), 7)
    elif key == "library":
        pygame.draw.rect(screen, edge, (x + 1, y + 1, TILE - 2, TILE - 2))
        pygame.draw.rect(screen, obstacle, (x + 4, y + 4, TILE - 8, TILE - 8))
        colors = ((190, 70, 60), (70, 120, 190), (200, 180, 70), (90, 160, 90))
        for i in range(4):
            pygame.draw.rect(screen, colors[(tile_x + i) % 4],
                             (x + 6 + i * 7, y + 7, 5, TILE - 14))
    elif key == "cargo":
        pygame.draw.rect(screen, edge, (x + 1, y + 1, TILE - 2, TILE - 2))
        pygame.draw.rect(screen, obstacle, (x + 4, y + 4, TILE - 8, TILE - 8))
        pygame.draw.line(screen, edge, (x + 4, y + 4), (x + TILE - 5, y + TILE - 5), 2)
        pygame.draw.line(screen, edge, (x + TILE - 5, y + 4), (x + 4, y + TILE - 5), 2)
    elif key == "boiler":
        pygame.draw.rect(screen, edge, (x + 2, y + 2, TILE - 4, TILE - 4), border_radius=8)
        pygame.draw.rect(screen, obstacle, (x + 6, y + 5, TILE - 12, TILE - 12), border_radius=6)
        pygame.draw.circle(screen, (255, 140, 40), (x + 20, y + 20), 3)
    elif key == "diner":
        pygame.draw.rect(screen, edge, (x + 1, y + 1, TILE - 2, TILE - 2), border_radius=6)
        pygame.draw.rect(screen, obstacle, (x + 4, y + 4, TILE - 8, TILE - 8), border_radius=5)
        pygame.draw.circle(screen, (250, 245, 235), (x + 20, y + 20), 6)
    else:
        pygame.draw.rect(screen, edge, (x + 1, y + 1, TILE - 2, TILE - 2), border_radius=4)
        pygame.draw.rect(screen, obstacle, (x + 4, y + 4, TILE - 8, TILE - 12), border_radius=3)
        pygame.draw.rect(screen, shade(obstacle, 1.25),
                         (x + 6, y + 6, TILE - 12, 6), border_radius=3)
