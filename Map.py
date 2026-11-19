import pygame
import pytmx
from collision import CollisionSystem


class GameMap:
    def __init__(self, map_path):
        self.map_path = map_path
        self.tmx_data = pytmx.load_pygame(map_path)

        # Map dimensions
        self.tile_width = self.tmx_data.tilewidth
        self.tile_height = self.tmx_data.tileheight
        self.width = self.tmx_data.width * self.tile_width
        self.height = self.tmx_data.height * self.tile_height

        # Separated collision geometry:
        # - self.collisions: Solid walls & floors (block all 4 directions, non-droppable)
        # - self.platforms: One-Way / Drop-Through elevated platforms (pass-through from below/sides, S+Space drop)
        # - self.polygons: SAT slope polygons + precomputed AABB bounding boxes
        self.collisions = []
        self.collision_rects = self.collisions
        self.platforms = []
        self.visible_platforms = []
        self.polygons = []
        self.polygon_bboxes = []
        self.portals = []

        self.collision_system = CollisionSystem(self)
        self.show_collision_debug = True

        # Find Collisions object group (case-insensitive)
        collision_layer = None
        for layer in self.tmx_data.layers:
            if (getattr(layer, "name", "") or "").strip().lower() == "collisions":
                collision_layer = layer
                break

        if collision_layer is not None:
            for obj in collision_layer:
                if getattr(obj, "name", "") == "starting point":
                    continue

                props = getattr(obj, "properties", {}) or {}
                target_map = (
                    props.get("target")
                    or props.get("target_map")
                    or props.get("target map")
                )

                if target_map:
                    spawn_x = props.get("spawn_x") or props.get("spawn x") or 100
                    spawn_y = props.get("spawn_y") or props.get("spawn y") or 100
                    portal_data = {
                        "rect": pygame.Rect(
                            round(obj.x),
                            round(obj.y),
                            round(obj.width),
                            round(obj.height),
                        ),
                        "target_map": str(target_map),
                        "spawn_x": float(spawn_x),
                        "spawn_y": float(spawn_y),
                        "properties": props,
                    }
                    self.portals.append(portal_data)
                    continue

                points = getattr(obj, "points", None)
                if points:
                    first_pt_x, first_pt_y = points[0]
                    is_absolute = (
                        abs(first_pt_x - obj.x) < 2 and abs(first_pt_y - obj.y) < 2
                    )
                    if is_absolute:
                        polygon = [(round(pt[0]), round(pt[1])) for pt in points]
                    else:
                        polygon = [
                            (round(obj.x + pt[0]), round(obj.y + pt[1]))
                            for pt in points
                        ]
                    if len(polygon) >= 3:
                        self.polygons.append(polygon)
                        xs = [p[0] for p in polygon]
                        ys = [p[1] for p in polygon]
                        min_x, max_x = min(xs), max(xs)
                        min_y, max_y = min(ys), max(ys)
                        self.polygon_bboxes.append(
                            pygame.Rect(
                                min_x,
                                min_y,
                                max(1, max_x - min_x),
                                max(1, max_y - min_y),
                            )
                        )
                else:
                    if getattr(obj, "width", 0) <= 0 or getattr(obj, "height", 0) <= 0:
                        continue
                    rect = pygame.Rect(
                        round(obj.x),
                        round(obj.y),
                        round(obj.width),
                        round(obj.height),
                    )
                    is_one_way = str(props.get("one_way", "")).lower() in (
                        "true",
                        "1",
                        "yes",
                    ) or bool(props.get("one_way", False))
                    if is_one_way:
                        self.platforms.append(rect)
                        invisible_art = str(props.get("invisible_art", "")).lower() in (
                            "true",
                            "1",
                            "yes",
                        ) or bool(props.get("invisible_art", False))
                        if not invisible_art:
                            self.visible_platforms.append(rect)
                    else:
                        self.collisions.append(rect)

    def draw(self, screen, camera_x=0, camera_y=0):
        sw = screen.get_width()
        sh = screen.get_height()

        # 1. Draw Tiled Image Layers & Tile Layers (with viewport culling)
        for layer in self.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledImageLayer):
                if layer.image:
                    img_x = getattr(layer, "offsetx", getattr(layer, "x", 0)) or 0
                    img_y = getattr(layer, "offsety", getattr(layer, "y", 0)) or 0
                    screen_x = img_x - camera_x
                    screen_y = img_y - camera_y
                    if (
                        screen_x + layer.image.get_width() < 0
                        or screen_x > sw
                        or screen_y + layer.image.get_height() < 0
                        or screen_y > sh
                    ):
                        continue
                    screen.blit(layer.image, (screen_x, screen_y))

            elif isinstance(layer, pytmx.TiledTileLayer):
                for x, y, image in layer.tiles():
                    if image is None:
                        continue
                    screen_x = x * self.tile_width - camera_x
                    screen_y = y * self.tile_height - camera_y
                    if (
                        screen_x + self.tile_width < 0
                        or screen_x > sw
                        or screen_y + self.tile_height < 0
                        or screen_y > sh
                    ):
                        continue
                    screen.blit(image, (screen_x, screen_y))

        # 2. Render 3-part pixel-art stone platforms (left end-cap, tiled middle bricks, right end-cap)
        for plat in self.visible_platforms:
            sr = plat.move(-camera_x, -camera_y)
            if sr.right < 0 or sr.left > sw or sr.bottom < 0 or sr.top > sh:
                continue
            vis_h = 16
            body_rect = pygame.Rect(sr.x, sr.y, sr.width, vis_h)
            # Base stone body
            pygame.draw.rect(screen, (62, 58, 72), body_rect)
            # Top sandstone/cyan highlight ledge
            pygame.draw.rect(screen, (148, 138, 128), (sr.x + 2, sr.y + 2, sr.width - 4, 4))
            pygame.draw.rect(screen, (95, 190, 235), (sr.x + 2, sr.y, sr.width - 4, 2))
            # Bottom shadow rim
            pygame.draw.rect(screen, (32, 30, 42), (sr.x, sr.y + vis_h - 3, sr.width, 3))
            # Left & Right stone end-caps
            pygame.draw.rect(screen, (84, 78, 94), (sr.x, sr.y + 2, 10, vis_h - 4))
            pygame.draw.rect(
                screen, (84, 78, 94), (sr.right - 10, sr.y + 2, 10, vis_h - 4)
            )
            # Tiled middle brick seams
            for bx in range(sr.x + 16, sr.right - 10, 20):
                pygame.draw.line(
                    screen, (38, 36, 48), (bx, sr.y + 4), (bx, sr.y + vis_h - 3), 2
                )
            # Crisp dark pixel outer border
            pygame.draw.rect(screen, (22, 20, 30), body_rect, 2)

    def move_with_collisions(self, entity_rect, dx, dy, drop_through=False):
        return self.collision_system.move_with_collisions(
            entity_rect, dx, dy, drop_through=drop_through
        )

    @property
    def last_on_one_way(self):
        return self.collision_system.last_on_one_way

    def has_ground_ahead(self, entity_rect, direction, look_ahead=26, drop_depth=56):
        return self.collision_system.has_ground_ahead(
            entity_rect, direction, look_ahead=look_ahead, drop_depth=drop_depth
        )

    def get_camera_offset(self, target_rect, screen_width, screen_height):
        camera_x = target_rect.centerx - screen_width // 2
        camera_y = target_rect.centery - screen_height // 2

        max_camera_x = max(0, self.width - screen_width)
        max_camera_y = max(0, self.height - screen_height)

        camera_x = max(0, min(camera_x, max_camera_x))
        camera_y = max(0, min(camera_y, max_camera_y))
        return camera_x, camera_y

    def draw_collision_debug(self, screen, camera_x=0, camera_y=0):
        if not self.show_collision_debug:
            return

        # Green: Solid Walls & Ground
        for rect in self.collisions:
            screen_rect = rect.move(-camera_x, -camera_y)
            pygame.draw.rect(screen, (0, 255, 0), screen_rect, 1)

        # Cyan-Blue: One-Way / Drop-Through Platforms
        for rect in self.platforms:
            screen_rect = rect.move(-camera_x, -camera_y)
            pygame.draw.rect(screen, (0, 195, 255), screen_rect, 2)

        # Orange: SAT Slope Polygons
        for polygon in self.polygons:
            if len(polygon) < 3:
                continue
            screen_points = [
                (round(x - camera_x), round(y - camera_y)) for x, y in polygon
            ]
            pygame.draw.polygon(screen, (255, 140, 0), screen_points, 2)

        # Magenta: Portals
        for portal in self.portals:
            p_rect = portal["rect"].move(-camera_x, -camera_y)
            pygame.draw.rect(screen, (255, 0, 255), p_rect, 2)

    def check_portal(self, player_rect):
        for portal in self.portals:
            if player_rect.colliderect(portal["rect"]):
                return portal
        return None
