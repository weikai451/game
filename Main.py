import math
import os
import random
import pygame
from Settings import (
    WIDTH,
    HEIGHT,
    FPS,
    GROUND_Y,
    HITSTOP_DURATION,
    BULLET_TIME_SCALE,
    BULLET_TIME_DURATION,
    BULLET_TIME_RECOVERY_SPEED,
    PARRY_ZOOM_SCALE,
    PARRY_ZOOM_RECOVERY_SPEED,
    get_pixel_font,
)
from Game_state import State
from Map import GameMap
from hud import HUD
from transition_system import (
    MapTrigger,
    find_interactable_portal,
    TransitionManager,
    change_map,
)
from checkpoint import load_checkpoints
from menu import Menu
from tutorial_system import GuidedTutorialManager
import Player
import Boss1
from VFX import draw_debug_boxes, HealVFX, PortalTeleportVFX


MAIN_WORLD_PATH = "map/main_world.tmx"
TUTORIAL_PATH = "map/tutorial.tmx"

# Map filenames containing these keywords are treated as Boss Arenas (fixed camera, Boss fight)
BOSS_ARENA_KEYWORDS = ("boss1arena", "boss1_arena", "boss1", "bass1")

# Delay (in seconds) after defeating the Boss in the arena before returning to the next checkpoint
VICTORY_RETURN_DELAY = 3.0

# Optional custom triggers per map
MAP_TRIGGERS = {}


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (WIDTH, HEIGHT), pygame.RESIZABLE | pygame.SCALED
        )
        pygame.display.set_caption("Final Project - Hollow Action")
        self.clock = pygame.time.Clock()
        self.running = True

        # Global pixel fonts (rendered with antialias=False)
        self.font_big = get_pixel_font(55)
        self.font_small = get_pixel_font(22)
        self.font_hud = get_pixel_font(16)
        self.font_prompt = get_pixel_font(16)

        # Load background image
        try:
            if os.path.exists("Background/cloud_back .jpg"):
                bg_img = pygame.image.load("Background/cloud_back .jpg").convert()
            else:
                bg_img = pygame.image.load(
                    "asset/Legacy-Fantasy - High Forest 2.3/Background/Background.png"
                ).convert()
            self.background = pygame.transform.scale(bg_img, (WIDTH, HEIGHT))
        except Exception:
            self.background = pygame.Surface((WIDTH, HEIGHT))
            self.background.fill((20, 20, 35))

        # Dedicated World Surface for 1.15x Camera Zoom-in (decoupled from top-layer HUD)
        self.world_surface = pygame.Surface((WIDTH, HEIGHT))

        self.pause_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.pause_overlay.fill((0, 0, 0, 150))

        # Perfect Parry background dimming layer & pre-allocated speed line surface
        self.parry_dim_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.speed_line_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # Pre-computed radial speed lines for Perfect Parry
        self.speed_line_specs = []
        num_lines = 76
        for i in range(num_lines):
            ang = (i / num_lines) * math.tau + random.uniform(-0.018, 0.018)
            inner_ratio = random.uniform(0.36, 0.54)
            thickness = random.choice([2, 2, 3, 4])
            self.speed_line_specs.append((ang, inner_ratio, thickness))

        # Main Menu & Pause Menu (100% English UI)
        self.main_menu = Menu("HOLLOW ACTION", ["START", "QUIT"])
        self.pause_menu = Menu(
            "PAUSED",
            ["BACK TO GAME", "RESTART", "MAIN MENU", "QUIT"],
            fill_background=False,
        )

        # Camera offset & zoom state
        self.camera_x = 0
        self.camera_y = 0
        self.zoom_scale = 1.0
        self.zoom_focus_world = [WIDTH / 2.0, HEIGHT / 2.0]

        self.state = State.MENU
        self.debug_mode = False  # Press F1 or TAB to toggle Debug Wireframes & God Mode

        # Tutorial prompt dialog state
        self.prompt_selection = 0  # 0: YES, 1: NO
        self.prompt_buttons = {}
        self.is_tutorial = False
        self.tutorial_manager = None

        # Transition Manager & Portal Triggers
        self.transition = TransitionManager(fade_speed=460.0)
        self.triggers = []
        self.transition_cooldown = 0.0

        # Checkpoints & Soul-like Respawn tracking
        self.checkpoints = []
        self.active_checkpoint = None
        self.respawn_map_path = MAIN_WORLD_PATH
        self.respawn_position = (140.0, 640.0)
        self.checkpoint_msg_timer = 0.0

        # Boss arena victory timer & main world Boss defeat flag
        self.victory_timer = 0.0
        self.main_boss_defeated = False

        # Bullet Time, Hitstop, and Screen Dimming timers
        self.time_scale = 1.0
        self.bullet_time_timer = 0.0
        self.hitstop_timer = 0.0
        self.screen_dim_timer = 0.0

        self.current_map_path = MAIN_WORLD_PATH
        self.game_map = None
        self.boss = None
        self.hud = None
        self.new_game(map_path=MAIN_WORLD_PATH, is_tutorial=False)

    # ------------------------------------------------------------------
    # Map, Floor Height Lookup, Checkpoints, Portals & Enemy Reset
    # ------------------------------------------------------------------
    def resolve_map_path(self, map_filename: str) -> str:
        """Resolve map path across root and map/ folder (supports boss1/bass1 naming)"""
        candidates = [
            map_filename,
            os.path.join("map", map_filename),
            os.path.join("map", os.path.basename(map_filename)),
            map_filename.replace("boss1", "bass1"),
            os.path.join("map", map_filename.replace("boss1", "bass1")),
            os.path.join(
                "map", os.path.basename(map_filename).replace("boss1", "bass1")
            ),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return map_filename

    def load_map(self, map_path: str) -> GameMap:
        resolved = self.resolve_map_path(map_path)
        print(f"[Map System] Loading map: {resolved}")
        return GameMap(resolved)

    def map_name(self):
        return os.path.basename(self.current_map_path).lower()

    def is_boss_arena(self):
        name = self.map_name()
        return any(k in name for k in BOSS_ARENA_KEYWORDS)

    def is_main_world(self):
        return "main_world" in self.map_name()

    def get_floor_y_at(self, x: float, default=640) -> int:
        """
        Find the true ground surface Y coordinate directly beneath horizontal coordinate x.
        Prevents spawning entities on high floating platforms when a ground floor exists below.
        """
        if not self.game_map or not getattr(self.game_map, "collisions", None):
            return default

        matching_tops = []
        for rect in self.game_map.collisions:
            # Ignore vertical boundary walls (very tall & narrow)
            if rect.height > 300 and rect.width < 120:
                continue
            if rect.left <= x <= rect.right:
                matching_tops.append(rect.top)

        if matching_tops:
            # Choose the lowest ground floor at this X (so entities don't get stuck on high roofs)
            return max(matching_tops)

        # Fallback: find the widest ground collision box in the map
        floor_candidates = [
            r.top
            for r in self.game_map.collisions
            if r.width >= 200 and r.top >= 450
        ]
        if floor_candidates:
            return max(floor_candidates)
        return default

    def get_floor_y(self, default=640):
        return self.get_floor_y_at(240.0, default=default)

    def _convert_tiled_portals_to_triggers(self):
        """
        Convert Tiled portals into interactive MapTrigger objects that display
        the floating '[E] Enter Portal' prompt window and trigger on pressing E.
        """
        triggers = list(MAP_TRIGGERS.get(self.map_name(), []))
        if not self.game_map or not getattr(self.game_map, "portals", None):
            return triggers

        tile_w = getattr(self.game_map, "tile_width", 16)
        tile_h = getattr(self.game_map, "tile_height", 16)

        for portal in self.game_map.portals:
            p_rect = portal["rect"]
            target_map = self.resolve_map_path(portal["target_map"])
            raw_sx = portal.get("spawn_x", 140.0)
            raw_sy = portal.get("spawn_y", 640.0)

            sx = float(raw_sx * tile_w) if raw_sx <= 100 else float(raw_sx)
            sy = float(raw_sy * tile_h) if raw_sy <= 60 else float(raw_sy)

            triggers.append(
                MapTrigger(
                    rect=p_rect,
                    target_map=target_map,
                    spawn_pos=(sx, sy),
                    require_boss_dead=False,
                    name="Portal",
                )
            )
        return triggers

    def spawn_boss(self, floor_y=None, start_x=380):
        """Spawn Boss with full map collision & gravity binding"""
        if floor_y is None:
            floor_y = self.get_floor_y_at(start_x, default=640)
        self.boss = Boss1.Vergil(
            self.player,
            start_x=start_x,
            ground_y=floor_y,
            game_map=self.game_map,
        )
        self.enemies = pygame.sprite.Group(self.boss)
        self.all_sprites = pygame.sprite.Group(self.player, self.boss)

    def reset_level_enemies(self):
        """
        Soul-like Enemy & Boss State Reset (called on player death respawn or Checkpoint rest):
        1. Clear all lingering hitboxes and enemy projectiles/VFX
        2. Restore Boss to full HP, initial spawn position, and IDLE state (or re-spawn if killed)
        """
        self.active_hitboxes.clear()
        for vfx in list(self.vfx_group):
            if not isinstance(vfx, (HealVFX, PortalTeleportVFX)):
                vfx.destroy()

        if self.is_tutorial:
            return

        if self.is_boss_arena():
            px = getattr(self.player, "pos_x", 260.0)
            boss_x = min(float(self.game_map.width - 260), px + 420.0)
            floor_y = self.get_floor_y_at(boss_x, default=656)
            if self.boss is not None and self.boss.alive():
                self.boss.game_map = self.game_map
                self.boss.spawn_x = float(boss_x)
                self.boss.spawn_y = float(floor_y)
                self.boss.reset()
            else:
                self.spawn_boss(floor_y=floor_y, start_x=boss_x)
        elif self.is_main_world():
            self.main_boss_defeated = False
            boss_x = 380.0
            floor_y = self.get_floor_y_at(boss_x, default=640)
            if self.boss is not None and self.boss.alive():
                self.boss.game_map = self.game_map
                self.boss.spawn_x = float(boss_x)
                self.boss.spawn_y = float(floor_y)
                self.boss.reset()
            else:
                self.spawn_boss(floor_y=floor_y, start_x=boss_x)

        if self.hud is not None and self.boss is not None:
            self.hud.boss = self.boss
            self.hud.boss_display_hp = float(self.boss.boss_health)

    def update_camera(self):
        if self.is_boss_arena():
            self.camera_x = (self.game_map.width - WIDTH) // 2
            self.camera_y = (self.game_map.height - HEIGHT) // 2
        else:
            player_rect = getattr(self.player, "collision_rect", self.player.rect)
            self.camera_x, self.camera_y = self.game_map.get_camera_offset(
                player_rect, WIDTH, HEIGHT
            )

    def setup_map_state(self):
        """Configure Boss, Guided Tutorial, Checkpoints, Portals, and HUD for the loaded map"""
        self.is_tutorial = "tutorial" in self.map_name()
        self.victory_timer = 0.0
        self.tutorial_manager = None

        # Load checkpoints from the current .tmx map (works for both Tutorial Stage 5 and Main World)
        self.checkpoints = load_checkpoints(
            self.resolve_map_path(self.current_map_path)
        )

        if self.is_tutorial:
            self.boss = None
            self.enemies = pygame.sprite.Group()
            self.all_sprites = pygame.sprite.Group(self.player)
            self.tutorial_manager = GuidedTutorialManager(self)
        elif self.is_boss_arena():
            px = getattr(self.player, "pos_x", 260.0)
            boss_x = min(float(self.game_map.width - 260), px + 420.0)
            floor_y = self.get_floor_y_at(boss_x, default=656)
            self.spawn_boss(floor_y=floor_y, start_x=boss_x)
        elif self.is_main_world() and not self.main_boss_defeated:
            boss_x = 380.0
            floor_y = self.get_floor_y_at(boss_x, default=640)
            self.spawn_boss(floor_y=floor_y, start_x=boss_x)
        else:
            self.boss = None
            self.enemies = pygame.sprite.Group()
            self.all_sprites = pygame.sprite.Group(self.player)

        self.triggers = self._convert_tiled_portals_to_triggers()

        if self.hud is not None:
            self.hud.reset(self.player, self.boss, is_tutorial=self.is_tutorial)

    def new_game(
        self,
        map_path=MAIN_WORLD_PATH,
        is_tutorial=False,
        spawn_pos=None,
        keep_progress=False,
    ):
        """Initialize a new game session"""
        self.is_tutorial = is_tutorial
        self.current_map_path = map_path
        self.game_map = self.load_map(map_path)

        if spawn_pos is not None:
            spawn_x, spawn_y = float(spawn_pos[0]), float(spawn_pos[1])
        elif is_tutorial:
            spawn_x = 96.0
            spawn_y = float(self.get_floor_y_at(spawn_x, default=640))
        else:
            spawn_x = 140.0
            spawn_y = float(self.get_floor_y_at(spawn_x, default=640))

        if not keep_progress:
            self.checkpoints = []
            self.active_checkpoint = None
            self.main_boss_defeated = False
            self.respawn_map_path = map_path
            self.respawn_position = (spawn_x, spawn_y)
        self.checkpoint_msg_timer = 0.0

        self.player = Player.Player(start_x=spawn_x, ground_y=spawn_y)
        self.player.god_mode = self.debug_mode
        self.player.game_map = self.game_map
        self.player.pos_y = float(spawn_y)
        self.player.sync_boxes()

        self.boss = None
        self.enemies = pygame.sprite.Group()
        self.all_sprites = pygame.sprite.Group(self.player)
        self.vfx_group = pygame.sprite.Group()
        self.active_hitboxes = []

        self.time_scale = 1.0
        self.bullet_time_timer = 0.0
        self.hitstop_timer = 0.0
        self.screen_dim_timer = 0.0
        self.zoom_scale = 1.0
        self.transition_cooldown = 0.0

        if self.hud is None:
            self.hud = HUD(self.player, self.boss, is_tutorial=self.is_tutorial)

        self.setup_map_state()
        self.update_camera()

    def handle_map_switch(self, trigger):
        """
        Executed at the peak of a transition (full black screen or closed Iris Wipe):
        - If is_death_respawn: teleport player to last saved Checkpoint, restore full HP, and reset Boss/enemies
        - Otherwise: switch to target map, position player, and play arrival particle VFX
        """
        if getattr(trigger, "is_death_respawn", False):
            target_resolved = self.resolve_map_path(trigger.target_map)
            if target_resolved != self.resolve_map_path(self.current_map_path):
                self.current_map_path = target_resolved
                self.game_map = self.load_map(target_resolved)
                self.player.game_map = self.game_map
                self.setup_map_state()

            sx, sy = trigger.spawn_pos
            self.player.ground_y = float(self.get_floor_y_at(sx, default=int(sy)))
            self.player.reset_state_on_respawn(sx, sy)
            self.reset_level_enemies()
            if self.hud is not None:
                self.hud.reset(
                    self.player, self.boss, is_tutorial=self.is_tutorial
                )
            self.vfx_group.add(
                HealVFX(self.player.pos_x, self.player.pos_y, duration=0.95)
            )
            self.update_camera()
        else:
            change_map(self, trigger, GameMap)
            sx, sy = trigger.spawn_pos
            floor_y = self.get_floor_y_at(sx, default=int(sy))
            self.player.ground_y = float(floor_y)
            self.player.teleport(sx, min(float(sy), float(floor_y)))
            self.setup_map_state()
            self.update_camera()

            self.vfx_group.add(
                PortalTeleportVFX(
                    self.player.pos_x,
                    self.player.pos_y,
                    duration=0.55,
                    mode="arrive",
                )
            )
            self.transition.focus_screen_pos = (
                int(self.player.pos_x - self.camera_x),
                int(self.player.hurtbox.centery - self.camera_y),
            )

        self.transition_cooldown = 0.85

    # ------------------------------------------------------------------
    # [E] Key Interaction: Checkpoint Save/Heal & Portal Teleportation
    # ------------------------------------------------------------------
    def handle_interact_key(self):
        if self.transition.is_transitioning or self.player.is_teleporting:
            return

        # 1. Checkpoint Interaction ([E] Save & Heal)
        for cp in self.checkpoints:
            if cp.can_interact:
                self.active_checkpoint = cp
                self.respawn_map_path = self.current_map_path
                self.respawn_position = cp.spawn_pos
                cp.trigger_save()

                self.player.full_heal()
                self.player.parry_cooldown = 0.0
                self.player.pogo_bounce_count = 0

                self.vfx_group.add(
                    HealVFX(self.player.pos_x, self.player.pos_y, duration=0.90)
                )
                self.vfx_group.add(
                    HealVFX(cp.spawn_pos[0], cp.spawn_pos[1], duration=0.90)
                )

                self.reset_level_enemies()
                print(
                    f"[Checkpoint] Saved & Healed at {cp.name} {cp.spawn_pos}, Stage Enemies Reset."
                )
                return

        # 2. Portal Interaction ([E] Enter Portal)
        if self.transition_cooldown <= 0.0:
            portal_trigger = find_interactable_portal(
                self.player, self.triggers, self.boss
            )
            if portal_trigger is not None:
                self.player.is_teleporting = True
                self.vfx_group.add(
                    PortalTeleportVFX(
                        self.player.pos_x,
                        self.player.pos_y,
                        duration=0.55,
                        mode="depart",
                    )
                )
                focus_screen = (
                    int(self.player.pos_x - self.camera_x),
                    int(self.player.hurtbox.centery - self.camera_y),
                )
                self.transition.start(
                    portal_trigger,
                    mode="PORTAL",
                    focus_screen_pos=focus_screen,
                )
                print(
                    f"[Portal] Entering portal -> {portal_trigger.target_map} at {portal_trigger.spawn_pos}"
                )

    def update_checkpoints_and_portals(self, raw_dt):
        if self.checkpoint_msg_timer > 0.0:
            self.checkpoint_msg_timer = max(0.0, self.checkpoint_msg_timer - raw_dt)

        player_rect = self.player.collision_rect
        for cp in self.checkpoints:
            cp.update(raw_dt, player_rect)

        for trigger in self.triggers:
            trigger.update(raw_dt, player_rect)

    def get_respawn_target(self):
        if self.active_checkpoint is not None:
            return self.respawn_map_path, self.active_checkpoint.spawn_pos
        if self.checkpoints:
            return MAIN_WORLD_PATH, self.checkpoints[0].spawn_pos
        return self.respawn_map_path, self.respawn_position

    def get_next_checkpoint(self):
        current = self.active_checkpoint.order if self.active_checkpoint else -(10**9)
        for cp in self.checkpoints:
            if cp.order > current:
                return cp
        return self.active_checkpoint

    def start_death_respawn(self):
        """Trigger Soul-like death respawn transition to last saved Checkpoint"""
        if self.transition.is_transitioning:
            return

        target_map, spawn_pos = self.get_respawn_target()
        respawn_trigger = MapTrigger(
            rect=(0, 0, 0, 0),
            target_map=target_map,
            spawn_pos=spawn_pos,
        )
        respawn_trigger.is_death_respawn = True
        self.player.is_teleporting = True
        self.transition.start(
            respawn_trigger,
            mode="RESPAWN",
            banner_text="YOU DIED — Respawning at Checkpoint...",
        )
        print(f"[Soul-like Respawn] Respawning at {target_map} {spawn_pos}")

    def handle_boss_arena_outcome(self, raw_dt):
        if self.player.player_hp <= 0 and not self.debug_mode:
            self.start_death_respawn()
            return True

        if self.boss is not None and not self.boss.alive():
            self.victory_timer += raw_dt
            if self.victory_timer >= VICTORY_RETURN_DELAY:
                self.victory_timer = 0.0
                self.main_boss_defeated = True
                cp = self.get_next_checkpoint()
                if cp is not None:
                    self.active_checkpoint = cp
                    cp.activated = True
                    spawn = cp.spawn_pos
                    self.respawn_map_path = MAIN_WORLD_PATH
                    self.respawn_position = spawn
                else:
                    spawn = (140, 640)

                ret_trigger = MapTrigger(
                    rect=(0, 0, 0, 0),
                    target_map=MAIN_WORLD_PATH,
                    spawn_pos=spawn,
                )
                self.player.is_teleporting = True
                focus_screen = (
                    int(self.player.pos_x - self.camera_x),
                    int(self.player.hurtbox.centery - self.camera_y),
                )
                self.transition.start(
                    ret_trigger, mode="PORTAL", focus_screen_pos=focus_screen
                )
            return True

        self.victory_timer = 0.0
        return False

    def restart_game(self):
        if self.is_tutorial:
            self.new_game(map_path=TUTORIAL_PATH, is_tutorial=True)
        else:
            self.new_game(map_path=MAIN_WORLD_PATH, is_tutorial=False)
        self.state = State.PLAYING

    # ------------------------------------------------------------------
    # Perfect Parry: Bullet Time, 1.15x Camera Zoom & Speed Lines
    # ------------------------------------------------------------------
    def trigger_bullet_time(self, focus_x=None, focus_y=None):
        self.hitstop_timer = HITSTOP_DURATION
        self.screen_dim_timer = BULLET_TIME_DURATION + 0.15
        self.time_scale = BULLET_TIME_SCALE
        self.bullet_time_timer = BULLET_TIME_DURATION
        self.zoom_scale = PARRY_ZOOM_SCALE

        if focus_x is not None and focus_y is not None:
            self.zoom_focus_world = [float(focus_x), float(focus_y)]
        elif self.boss is not None and self.boss.alive():
            self.zoom_focus_world = [
                (self.player.pos_x + self.boss.pos_x) * 0.5,
                float(self.player.hurtbox.centery),
            ]
        else:
            self.zoom_focus_world = [
                float(self.player.pos_x),
                float(self.player.hurtbox.centery),
            ]

    def draw_text(self, text, font, color, center, surface=None):
        """Render crisp pixel text with antialias=False"""
        target = self.screen if surface is None else surface
        img = font.render(text, False, color)
        target.blit(img, img.get_rect(center=center))

    def draw_parry_speed_lines(self, target_surface):
        if self.time_scale >= 0.95 and self.hitstop_timer <= 0.0:
            return

        fx = self.zoom_focus_world[0] - self.camera_x
        fy = self.zoom_focus_world[1] - self.camera_y
        fx = max(WIDTH * 0.25, min(WIDTH * 0.75, fx))
        fy = max(HEIGHT * 0.25, min(HEIGHT * 0.75, fy))

        intensity = min(1.0, (1.0 - self.time_scale) / (1.0 - BULLET_TIME_SCALE))
        alpha = int(215 * intensity)
        if alpha <= 10:
            return

        line_surf = self.speed_line_surface
        line_surf.fill((0, 0, 0, 0))
        outer_r = math.hypot(WIDTH, HEIGHT) * 0.75
        clear_rx = WIDTH * 0.52
        clear_ry = HEIGHT * 0.50

        for ang, inner_ratio, thick in self.speed_line_specs:
            cos_a = math.cos(ang)
            sin_a = math.sin(ang)
            r_in = inner_ratio * min(clear_rx, clear_ry) * (1.12 - 0.12 * intensity)
            x1 = fx + cos_a * r_in
            y1 = fy + sin_a * (r_in * 0.78)
            x2 = fx + cos_a * outer_r
            y2 = fy + sin_a * outer_r

            pygame.draw.line(
                line_surf,
                (6, 10, 22, alpha),
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                thick,
            )

        target_surface.blit(line_surf, (0, 0))

    def _blit_world_with_zoom(self):
        if self.zoom_scale <= 1.001:
            self.screen.blit(self.world_surface, (0, 0))
            return

        crop_w = int(round(WIDTH / self.zoom_scale))
        crop_h = int(round(HEIGHT / self.zoom_scale))

        fx = self.zoom_focus_world[0] - self.camera_x
        fy = self.zoom_focus_world[1] - self.camera_y

        crop_x = max(0, min(WIDTH - crop_w, int(round(fx - crop_w * 0.5))))
        crop_y = max(0, min(HEIGHT - crop_h, int(round(fy - crop_h * 0.5))))

        sub_view = self.world_surface.subsurface((crop_x, crop_y, crop_w, crop_h))
        pygame.transform.scale(sub_view, (WIDTH, HEIGHT), self.screen)

    # ------------------------------------------------------------------
    # Main Loop: Events, Combat Collisions, Update, Draw
    # ------------------------------------------------------------------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            # ---------- 1. Main Menu ----------
            if self.state == State.MENU:
                choice = self.main_menu.handle_event(event)
                if choice == "START":
                    self.state = State.TUTORIAL_PROMPT
                    self.prompt_selection = 0
                elif choice == "QUIT":
                    self.running = False

            # ---------- 2. Guided Tutorial Prompt ----------
            elif self.state == State.TUTORIAL_PROMPT:
                if event.type == pygame.KEYDOWN:
                    if event.key in (
                        pygame.K_LEFT,
                        pygame.K_a,
                        pygame.K_UP,
                        pygame.K_w,
                    ):
                        self.prompt_selection = 0
                    elif event.key in (
                        pygame.K_RIGHT,
                        pygame.K_d,
                        pygame.K_DOWN,
                        pygame.K_s,
                    ):
                        self.prompt_selection = 1
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self.prompt_selection == 0:
                            self.new_game(map_path=TUTORIAL_PATH, is_tutorial=True)
                        else:
                            self.new_game(map_path=MAIN_WORLD_PATH, is_tutorial=False)
                        self.state = State.PLAYING
                    elif event.key == pygame.K_ESCAPE:
                        self.state = State.MENU

                elif event.type == pygame.MOUSEMOTION:
                    pos = event.pos
                    if self.prompt_buttons.get("YES") and self.prompt_buttons[
                        "YES"
                    ].collidepoint(pos):
                        self.prompt_selection = 0
                    elif self.prompt_buttons.get("NO") and self.prompt_buttons[
                        "NO"
                    ].collidepoint(pos):
                        self.prompt_selection = 1

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = event.pos
                    if self.prompt_buttons.get("YES") and self.prompt_buttons[
                        "YES"
                    ].collidepoint(pos):
                        self.new_game(map_path=TUTORIAL_PATH, is_tutorial=True)
                        self.state = State.PLAYING
                    elif self.prompt_buttons.get("NO") and self.prompt_buttons[
                        "NO"
                    ].collidepoint(pos):
                        self.new_game(map_path=MAIN_WORLD_PATH, is_tutorial=False)
                        self.state = State.PLAYING

            # ---------- 3. Pause Menu ----------
            elif self.state == State.PAUSED:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.state = State.PLAYING
                else:
                    choice = self.pause_menu.handle_event(event)
                    if choice == "BACK TO GAME":
                        self.state = State.PLAYING
                    elif choice == "RESTART":
                        self.restart_game()
                    elif choice == "MAIN MENU":
                        self.state = State.MENU
                    elif choice == "QUIT":
                        self.running = False

            # ---------- 4. Gameplay ----------
            elif self.state == State.PLAYING:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_F1, pygame.K_TAB):
                        self.debug_mode = not self.debug_mode
                        self.player.god_mode = self.debug_mode
                        state_str = (
                            "ON (God Mode Enabled)" if self.debug_mode else "OFF"
                        )
                        print(f"[DEBUG] Debug Mode: {state_str}")

                    # Debug shortcut: press K to defeat active Boss/enemies
                    if self.debug_mode and event.key == pygame.K_k:
                        for enemy in list(self.enemies):
                            if hasattr(enemy, "boss_health"):
                                enemy.boss_health = 0
                            enemy.kill()
                        print("[Debug] All enemies defeated")

                    if event.key == pygame.K_ESCAPE:
                        if not self.transition.is_transitioning:
                            self.player.stop_block()
                            self.pause_menu.selected = 0
                            self.state = State.PAUSED

                    elif (
                        not self.player.is_teleporting
                        and not self.transition.is_transitioning
                    ):
                        if event.key == pygame.K_e:
                            self.handle_interact_key()
                        elif event.key in (pygame.K_w, pygame.K_SPACE, pygame.K_UP):
                            keys = pygame.key.get_pressed()
                            down_held = bool(keys[pygame.K_s] or keys[pygame.K_DOWN])
                            self.player.jump(down_pressed=down_held)
                        elif event.key in (pygame.K_j, pygame.K_LSHIFT):
                            self.player.start_block()

                elif event.type == pygame.KEYUP:
                    if event.key in (pygame.K_j, pygame.K_LSHIFT):
                        self.player.stop_block()

                elif (
                    event.type == pygame.MOUSEBUTTONDOWN
                    and not self.player.is_teleporting
                    and not self.transition.is_transitioning
                ):
                    if event.button == 1:
                        keys = pygame.key.get_pressed()
                        down_held = bool(keys[pygame.K_s] or keys[pygame.K_DOWN])
                        self.player.attack(down_pressed=down_held)
                    elif event.button == 3:
                        self.player.start_block()

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:
                        self.player.stop_block()

            # ---------- 5. Game Over ----------
            elif self.state == State.GAME_OVER:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    self.state = State.MENU

    def resolve_combat_collisions(self):
        """Resolve active Hitbox collisions against Hurtboxes and ParryBoxes"""
        self.active_hitboxes = [hb for hb in self.active_hitboxes if hb.active]

        for hb in self.active_hitboxes:
            if not hb.active:
                continue

            if hb.owner == "player":
                for enemy in self.enemies:
                    if (
                        enemy.alive()
                        and hb.can_hit(enemy)
                        and hb.rect.colliderect(enemy.hurtbox)
                    ):
                        hb.register_hit(enemy)
                        enemy.be_attacked(hb.damage)
                        if hb.tag == "player_down_slash":
                            self.player.on_pogo_hit(vfx_group=self.vfx_group)

            elif hb.owner == "boss" and self.player.alive():
                if (
                    self.boss is None
                    or self.player.is_teleporting
                    or not hb.can_hit(self.player)
                ):
                    continue

                hit_parry_box = (
                    self.player.is_blocking
                    and hb.rect.colliderect(self.player.parry_box)
                )
                hit_hurtbox = hb.rect.colliderect(self.player.hurtbox)

                if hit_parry_box or hit_hurtbox:
                    hb.register_hit(self.player)
                    outcome = self.player.take_hit(
                        hb, attacker=self.boss, vfx_group=self.vfx_group
                    )
                    if outcome == "parry":
                        focus_x = (
                            self.player.parry_box.centerx * 0.65
                            + self.boss.hurtbox.centerx * 0.35
                        )
                        focus_y = self.player.hurtbox.centery
                        self.trigger_bullet_time(focus_x=focus_x, focus_y=focus_y)
                        if self.boss.alive():
                            self.boss.on_parried()

    def update(self, raw_dt):
        # 1. Update transition animation (Iris Wipe / Respawn Fade)
        was_transitioning = self.transition.is_transitioning
        self.transition.update(raw_dt, on_map_switch=self.handle_map_switch)

        if was_transitioning and not self.transition.is_transitioning:
            self.player.is_teleporting = False

        if self.state != State.PLAYING:
            return

        if self.transition.is_transitioning:
            for vfx in list(self.vfx_group):
                vfx.update(raw_dt)
            self.hud.update(raw_dt)
            return

        self.player.god_mode = self.debug_mode

        if self.transition_cooldown > 0.0:
            self.transition_cooldown = max(0.0, self.transition_cooldown - raw_dt)

        # 2. Update screen dimming timer
        if self.screen_dim_timer > 0.0:
            self.screen_dim_timer = max(0.0, self.screen_dim_timer - raw_dt)

        # 3. Hitstop freeze frame on Perfect Parry
        if self.hitstop_timer > 0.0:
            self.hitstop_timer = max(0.0, self.hitstop_timer - raw_dt)
            for vfx in list(self.vfx_group):
                vfx.update(raw_dt * 0.12)
            return

        # 4. Update Bullet Time & 1.15x Camera Zoom recovery
        if self.bullet_time_timer > 0.0:
            self.bullet_time_timer = max(0.0, self.bullet_time_timer - raw_dt)
            self.zoom_scale = PARRY_ZOOM_SCALE
            if self.bullet_time_timer <= 0.0:
                self.time_scale = min(
                    1.0,
                    self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt,
                )
        else:
            if self.time_scale < 1.0:
                self.time_scale = min(
                    1.0, self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt
                )
            if self.zoom_scale > 1.0:
                self.zoom_scale = max(
                    1.0, self.zoom_scale - PARRY_ZOOM_RECOVERY_SPEED * raw_dt
                )

        scaled_dt = raw_dt * self.time_scale

        # 5. Update Player
        self.player.update(
            dt=scaled_dt,
            raw_dt=raw_dt,
            active_hitboxes=self.active_hitboxes,
            vfx_group=self.vfx_group,
            map_width=self.game_map.width,
        )

        # 6. Update Checkpoints & Portals interaction zones
        self.update_checkpoints_and_portals(raw_dt)

        # 7. Update Boss / Guided Tutorial entities
        if self.boss is not None and self.boss.alive():
            self.boss.update(
                dt=scaled_dt,
                active_hitboxes=self.active_hitboxes,
                vfx_group=self.vfx_group,
                map_width=self.game_map.width,
            )

        if self.tutorial_manager is not None:
            self.tutorial_manager.update(scaled_dt)

        if self.is_main_world() and self.boss is not None and not self.boss.alive():
            self.main_boss_defeated = True

        # 8. Update VFX & Hitboxes
        for vfx in list(self.vfx_group):
            vfx.update(scaled_dt)
        for hb in list(self.active_hitboxes):
            hb.update(scaled_dt)

        # 9. Resolve combat collisions
        self.resolve_combat_collisions()

        # 10. Update HUD & Camera
        self.hud.update(raw_dt)
        self.update_camera()

        # 11. Handle Boss Arena outcome or Soul-like Death Respawn
        if self.is_boss_arena():
            self.handle_boss_arena_outcome(raw_dt)
        elif self.player.player_hp <= 0 and not self.debug_mode:
            self.start_death_respawn()

    def draw(self):
        if self.state == State.MENU:
            self.main_menu.draw(self.screen)
            self.hud.draw_text(
                self.screen,
                "A/D: Move | W/SPACE: Jump | LMB: Attack | Air S+LMB: Pogo | RMB/J: Parry | E: Interact | F1: Debug",
                self.hud.font_hud,
                (160, 190, 230),
                (WIDTH // 2, 650),
            )

        elif self.state == State.TUTORIAL_PROMPT:
            self.screen.fill((20, 20, 50))
            self.hud.draw_text(
                self.screen,
                "HOLLOW ACTION",
                self.hud.font_big,
                (80, 80, 120),
                (WIDTH // 2, 230),
            )
            self.prompt_buttons = self.hud.draw_tutorial_prompt(
                self.screen, self.prompt_selection
            )

        elif self.state in (State.PLAYING, State.PAUSED):
            # ==================== Pass 1: Render Game World onto self.world_surface ====================
            self.world_surface.blit(self.background, (0, 0))
            self.game_map.draw(self.world_surface, self.camera_x, self.camera_y)

            # 1. Draw Guided Tutorial world elements (gates, spikes, signposts, dummy/guardian UI)
            if self.tutorial_manager is not None:
                self.tutorial_manager.draw_world_elements(
                    self.world_surface, self.camera_x, self.camera_y
                )

            # 2. Draw Checkpoints & Portals (with floating '[E] Save & Heal' / '[E] Enter Portal' prompts)
            for cp in self.checkpoints:
                cp.draw(
                    self.world_surface,
                    self.camera_x,
                    self.camera_y,
                    self.font_prompt,
                    is_active=(cp is self.active_checkpoint),
                )
            for trigger in self.triggers:
                trigger.draw(
                    self.world_surface,
                    self.camera_x,
                    self.camera_y,
                    self.font_prompt,
                    boss=self.boss,
                )

            # 3. Perfect Parry background dimming layer
            if self.screen_dim_timer > 0.0 or self.time_scale < 0.95:
                dim_ratio = min(1.0, self.screen_dim_timer / 0.35)
                dim_alpha = (
                    int(130 * dim_ratio)
                    if self.hitstop_timer > 0.0
                    else int(95 * dim_ratio)
                )
                self.parry_dim_overlay.fill((10, 16, 36, max(25, dim_alpha)))
                self.world_surface.blit(self.parry_dim_overlay, (0, 0))

            # 4. Draw Player's pixel flame aura, afterimages, and 1.5s buff particles
            if self.player.alive():
                self.player.draw_extras(
                    self.world_surface, self.camera_x, self.camera_y
                )

            # 5. Draw all active sprites (Player, Boss, Tutorial Targets)
            for sprite in self.all_sprites:
                if sprite.alive():
                    self.world_surface.blit(
                        sprite.image,
                        sprite.rect.move(-self.camera_x, -self.camera_y),
                    )

            # 6. Draw all VFX (Slashes, Heal particles, Portal particles, Pixel Ink-Splash Parry)
            for vfx in self.vfx_group:
                vfx.draw(self.world_surface, self.camera_x, self.camera_y)

            # 7. Draw black radial manga speed lines during Perfect Parry
            self.draw_parry_speed_lines(self.world_surface)

            # 8. Floating combat feedback text above Player
            if self.player.status_timer > 0.0 and self.player.status_text:
                sx = int(self.player.pos_x - self.camera_x)
                sy = int(self.player.hurtbox.top - 18 - self.camera_y)
                color = (
                    (90, 250, 255)
                    if (
                        "PERFECT" in self.player.status_text
                        or "POGO" in self.player.status_text
                        or "SHATTERED" in self.player.status_text
                    )
                    else (255, 230, 120)
                )
                self.draw_text(
                    self.player.status_text,
                    self.font_hud,
                    color,
                    (sx, sy),
                    surface=self.world_surface,
                )

            # 9. Debug wireframes on world_surface
            if self.debug_mode:
                if hasattr(self.game_map, "draw_collision_debug"):
                    self.game_map.draw_collision_debug(
                        self.world_surface, self.camera_x, self.camera_y
                    )
                draw_debug_boxes(
                    self.world_surface,
                    self.camera_x,
                    self.camera_y,
                    self.player,
                    self.boss,
                    self.active_hitboxes,
                    self.vfx_group,
                )
                for trigger in self.triggers:
                    trigger.draw_debug(
                        self.world_surface, self.camera_x, self.camera_y, self.boss
                    )
                for cp in self.checkpoints:
                    cp.draw_debug(
                        self.world_surface,
                        self.camera_x,
                        self.camera_y,
                        self.hud.font_hud,
                        cp is self.active_checkpoint,
                    )

            # ==================== Pass 2: Apply 1.15x Camera Zoom onto self.screen ====================
            self._blit_world_with_zoom()

            # ==================== Pass 3: Render Fixed Top-Layer HUD & UI onto self.screen ====================
            self.hud.draw_gameplay_hud(self.screen)

            if self.tutorial_manager is not None:
                self.tutorial_manager.draw_hud_banner(self.screen, self.hud)

            if self.debug_mode:
                map_name = os.path.basename(self.current_map_path)
                mode_str = (
                    "TUTORIAL"
                    if self.is_tutorial
                    else ("BOSS ARENA" if self.is_boss_arena() else "WORLD")
                )
                cp_str = (
                    self.active_checkpoint.order if self.active_checkpoint else "-"
                )
                boss_ground = (
                    getattr(self.boss, "on_ground", "-") if self.boss else "-"
                )
                pos_info = (
                    f"[{mode_str}] Map: {map_name} | "
                    f"Player: ({int(self.player.pos_x)}, {int(self.player.pos_y)}) Grounded={self.player.on_ground} | "
                    f"Boss Grounded={boss_ground} | CP: {cp_str} | K: Kill Boss"
                )
                info_surf = self.hud.font_hud.render(
                    pos_info, False, (0, 255, 120)
                )
                self.screen.blit(info_surf, (24, HEIGHT - 36))

            if (
                not self.is_tutorial
                and self.boss is not None
                and not self.boss.alive()
            ):
                self.hud.draw_text(
                    self.screen,
                    "VICTORY! BOSS DEFEATED",
                    self.hud.font_big,
                    (255, 215, 80),
                    (WIDTH // 2, HEIGHT // 2 - 40),
                )

            if self.state == State.PAUSED:
                self.screen.blit(self.pause_overlay, (0, 0))
                self.pause_menu.draw(self.screen)

        elif self.state == State.GAME_OVER:
            self.screen.fill((80, 20, 20))
            self.hud.draw_text(
                self.screen,
                "GAME OVER",
                self.hud.font_big,
                (255, 255, 255),
                (WIDTH // 2, 280),
            )
            self.hud.draw_text(
                self.screen,
                "Press ENTER to return to menu",
                self.hud.font_small,
                (220, 220, 220),
                (WIDTH // 2, 420),
            )

        # Topmost transition overlay (Pixelated Iris Wipe or Respawn Fade)
        self.transition.draw(self.screen)

        pygame.display.flip()

    def run(self):
        while self.running:
            raw_dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(raw_dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
