import pygame


class CollisionSystem:
    def __init__(self, game_map):
        self.game_map = game_map
        self.last_on_one_way = False

    # ==========================================
    # 1. SAT: Minimum Translation Vector for Rect vs Polygon
    # ==========================================
    def polygon_mtv(self, rect, polygon):
        rect_points = (
            (rect.left, rect.top),
            (rect.right, rect.top),
            (rect.right, rect.bottom),
            (rect.left, rect.bottom),
        )

        axes = [(1.0, 0.0), (0.0, 1.0)]
        n_pts = len(polygon)

        for i in range(n_pts):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % n_pts]
            edge_x = p2[0] - p1[0]
            edge_y = p2[1] - p1[1]

            axis_x, axis_y = -edge_y, edge_x
            length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
            if length == 0.0:
                continue
            axes.append((axis_x / length, axis_y / length))

        min_overlap = float("inf")
        smallest_axis = None

        polygon_center_x = sum(p[0] for p in polygon) / n_pts
        polygon_center_y = sum(p[1] for p in polygon) / n_pts
        rect_center_x, rect_center_y = rect.centerx, rect.centery

        for axis_x, axis_y in axes:
            r_proj = [p[0] * axis_x + p[1] * axis_y for p in rect_points]
            p_proj = [p[0] * axis_x + p[1] * axis_y for p in polygon]

            overlap = min(max(r_proj), max(p_proj)) - max(min(r_proj), min(p_proj))
            if overlap <= 0.0:
                return None
            if overlap < min_overlap:
                min_overlap = overlap
                smallest_axis = (axis_x, axis_y)

        if smallest_axis is None:
            return None

        dir_x = rect_center_x - polygon_center_x
        dir_y = rect_center_y - polygon_center_y
        ax, ay = smallest_axis
        if dir_x * ax + dir_y * ay < 0.0:
            ax, ay = -ax, -ay
        return (ax * min_overlap, ay * min_overlap)

    def polygon_collide(self, rect, polygon):
        return self.polygon_mtv(rect, polygon) is not None

    # ==========================================
    # 2. Spatial Broad-Phase Filtered Collision & One-Way / Drop-Through Platforms
    # ==========================================
    def move_with_collisions(self, entity_rect, dx, dy, drop_through=False):
        """
        Move entity_rect by (dx, dy) resolving Solid Tiles, Polygons, and One-Way Platforms.
        - Solid Tiles (self.game_map.collisions): block all 4 directions, never drop-through.
        - One-Way Platforms (self.game_map.platforms):
          * 100% pass-through horizontally and when moving upward (dy < 0).
          * Only land when moving downward (dy >= 0), prev_bottom <= platform.top + tolerance,
            and drop_through is False.
        Sets self.last_on_one_way = True if standing on a One-Way Platform.
        Returns (on_ground, hit_ceiling).
        """
        dx_int = round(dx)
        dy_int = round(dy)

        # Spatial Broad-Phase AABB around the entity's movement sweep
        pad_x = abs(dx_int) + 48
        pad_y = abs(dy_int) + 48
        search_rect = entity_rect.inflate(pad_x * 2, pad_y * 2)

        nearby_walls = [
            w for w in self.game_map.collisions if search_rect.colliderect(w)
        ]
        nearby_platforms = (
            []
            if drop_through
            else [p for p in self.game_map.platforms if search_rect.colliderect(p)]
        )

        poly_bboxes = getattr(self.game_map, "polygon_bboxes", None)
        if poly_bboxes and len(poly_bboxes) == len(self.game_map.polygons):
            nearby_polygons = [
                poly
                for poly, bbox in zip(self.game_map.polygons, poly_bboxes)
                if search_rect.colliderect(bbox)
            ]
        else:
            nearby_polygons = self.game_map.polygons

        on_ground = False
        hit_ceiling = False
        on_one_way = False

        # ---------- A. Horizontal Movement (Solid Walls & Polygons ONLY; One-Way Platforms Ignored) ----------
        entity_rect.x += dx_int
        for wall in nearby_walls:
            if entity_rect.colliderect(wall):
                if dx_int > 0:
                    entity_rect.right = wall.left
                elif dx_int < 0:
                    entity_rect.left = wall.right

        for polygon in nearby_polygons:
            mtv = self.polygon_mtv(entity_rect, polygon)
            if mtv is not None:
                entity_rect.x += round(mtv[0])
                entity_rect.y += round(mtv[1])
                if mtv[1] < 0:
                    on_ground = True
                elif mtv[1] > 0:
                    hit_ceiling = True

        # ---------- B. Vertical Movement (Solid Walls, Polygons & One-Way Platforms) ----------
        prev_bottom = entity_rect.bottom
        entity_rect.y += dy_int

        # B1. Solid Walls (block both downward landing and upward head-bonk)
        for wall in nearby_walls:
            if entity_rect.colliderect(wall):
                if dy_int > 0:
                    entity_rect.bottom = wall.top
                    on_ground = True
                elif dy_int < 0:
                    entity_rect.top = wall.bottom
                    hit_ceiling = True

        # B2. Polygons / Slopes
        for polygon in nearby_polygons:
            mtv = self.polygon_mtv(entity_rect, polygon)
            if mtv is not None:
                entity_rect.x += round(mtv[0])
                entity_rect.y += round(mtv[1])
                if mtv[1] < 0:
                    on_ground = True
                elif mtv[1] > 0:
                    hit_ceiling = True

        # B3. One-Way Platforms: ONLY when falling/stationary (dy_int >= 0) and NOT dropping through
        if dy_int >= 0 and not drop_through:
            tolerance = 6
            for platform in nearby_platforms:
                horiz_overlap = (
                    entity_rect.right > platform.left + 2
                    and entity_rect.left < platform.right - 2
                )
                if not horiz_overlap:
                    continue
                crossed_top = (
                    prev_bottom <= platform.top + tolerance
                    and entity_rect.bottom >= platform.top
                )
                if crossed_top:
                    entity_rect.bottom = platform.top
                    on_ground = True
                    on_one_way = True

        # ---------- C. Ground Contact Probe (1px below feet) ----------
        ground_probe = entity_rect.move(0, 1)

        if not on_ground:
            for wall in nearby_walls:
                if ground_probe.colliderect(wall):
                    on_ground = True
                    break

        if not on_ground and not drop_through and dy_int >= 0:
            for platform in nearby_platforms:
                horiz_overlap = (
                    entity_rect.right > platform.left + 2
                    and entity_rect.left < platform.right - 2
                )
                if horiz_overlap and abs(entity_rect.bottom - platform.top) <= 2:
                    entity_rect.bottom = platform.top
                    on_ground = True
                    on_one_way = True
                    break

        if not on_ground:
            for polygon in nearby_polygons:
                if self.polygon_collide(ground_probe, polygon):
                    on_ground = True
                    break

        # Also check if already standing on a one-way platform when on_ground is True
        if on_ground and not on_one_way and not drop_through:
            for platform in nearby_platforms:
                if (
                    entity_rect.right > platform.left + 2
                    and entity_rect.left < platform.right - 2
                    and abs(entity_rect.bottom - platform.top) <= 2
                ):
                    on_one_way = True
                    break

        self.last_on_one_way = on_one_way
        return on_ground, hit_ceiling

    # ==========================================
    # 3. AI Helper: Probe Ground Ahead for Gap Detection
    # ==========================================
    def has_ground_ahead(self, entity_rect, direction, look_ahead=26, drop_depth=56):
        """
        Check if there is a solid floor, one-way platform, or slope ahead of entity_rect
        in the given horizontal direction (-1 or +1). Used by Boss AI to jump over gaps.
        """
        probe_x = (
            entity_rect.right + look_ahead
            if direction > 0
            else entity_rect.left - look_ahead - 8
        )
        probe_rect = pygame.Rect(int(probe_x), int(entity_rect.bottom - 4), 8, drop_depth)

        for wall in self.game_map.collisions:
            if probe_rect.colliderect(wall):
                return True
        for platform in self.game_map.platforms:
            if probe_rect.colliderect(platform):
                return True
        for poly, bbox in zip(
            self.game_map.polygons, getattr(self.game_map, "polygon_bboxes", [])
        ):
            if probe_rect.colliderect(bbox) and self.polygon_collide(probe_rect, poly):
                return True
        return False
