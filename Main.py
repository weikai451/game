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
from checkpoint import load_checkpoints, Checkpoint
from menu import Menu
from tutorial_system import GuidedTutorialManager
import Player
from bosses import Sans, Vergil
from enemies import Slimer
from audio_manager import get_audio
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
        self.audio = get_audio()

        # Global pixel fonts (rendered with antialias=False)
        self.font_big = get_pixel_font(55)
        self.font_small = get_pixel_font(22)
        self.font_hud = get_pixel_font(16)
        self.font_prompt = get_pixel_font(16)
        # Crisp pixel fonts (antialias=False) for programmatic Boss Title Card ('The weakest ?' / 'Sans')
        self.font_title_sub = get_pixel_font(40)
        self.font_title_main = get_pixel_font(96)
        self.title_card_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # Load default & dedicated Sans Judgement Hall background images
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

        try:
            if os.path.exists("assets/backgrounds/sans_bg.png"):
                sans_raw = pygame.image.load("assets/backgrounds/sans_bg.png").convert()
                self.sans_background = pygame.transform.scale(sans_raw, (WIDTH, HEIGHT))
            else:
                self.sans_background = self.background
        except Exception:
            self.sans_background = self.background

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

        # Main Menu & Pause Menu (100% English Pixel UI + Categorized Volume Sliders)
        self.main_menu = Menu("HOLLOW ACTION", ["START", "QUIT"])
        self.pause_menu = Menu(
            "PAUSED",
            ["BACK TO GAME", "RESTART", "MAIN MENU", "QUIT"],
            fill_background=False,
            sliders=[
                {"key": "master", "label": "MASTER VOLUME"},
                {"key": "bgm", "label": "BGM / MUSIC"},
                {"key": "sfx", "label": "SFX / COMBAT"},
            ],
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

        # Bullet Time, Hitstop, Screen Dimming, Screen Shake & Stage Clear timers
        self.time_scale = 1.0
        self.bullet_time_timer = 0.0
        self.hitstop_timer = 0.0
        self.screen_dim_timer = 0.0
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 7.0
        self.intro_letterbox_ratio = 0.0
        self.boss_defeated = {"sans": False, "vergil": False}
        self.cleared_stages = {}
        self.level_cleared = False
        self.stage_cleared = False
        self.portal_unlock_banner_timer = 0.0

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

    def is_sans_arena(self):
        return "sans_arena" in self.map_name()

    def is_vergil_arena(self):
        name = self.map_name()
        return any(k in name for k in BOSS_ARENA_KEYWORDS)

    def is_boss_arena(self):
        return self.is_sans_arena() or self.is_vergil_arena()

    def is_boss_intro_active(self):
        """True while the current Boss is playing its opening INTRO cutscene."""
        return bool(
            self.boss is not None
            and self.boss.alive()
            and getattr(self.boss, "state", "") == "INTRO"
        )

    def is_main_world(self):
        return "main_world" in self.map_name()

    def check_stage_clear_condition(self):
        """
        Evaluate the current stage's Portal unlock condition:
        - Tutorial: Gate 2 open (Parry Guardian defeated & all tutorial stages cleared)
        - Stage 1 (Slime Exploration): All Slimer enemies defeated
        - Stage 2 (Sans) & Stage 3 (Vergil): Boss defeated (is_dead == True)
        """
        if self.is_tutorial:
            return bool(
                self.tutorial_manager is not None
                and getattr(self.tutorial_manager, "gate2_open", False)
            )
        if self.is_main_world():
            return len(self.regular_enemies) == 0
        if self.is_boss_arena():
            return self.boss is not None and (
                getattr(self.boss, "is_dead", False) or not self.boss.alive()
            )
        return True

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

    def _rebuild_sprite_groups(self):
        """
        Keep self.enemies and self.all_sprites cleanly synced across Player, Boss, and Slimers.
        NOTE: Check HP (> 0) rather than pygame.sprite.Sprite.alive(), because a newly
        instantiated Sprite has alive() == False until it is added to a Sprite Group!
        """
        self.enemies = pygame.sprite.Group()
        self.all_sprites = pygame.sprite.Group(self.player)
        if self.boss is not None and getattr(self.boss, "boss_health", 0) > 0:
            self.enemies.add(self.boss)
            self.all_sprites.add(self.boss)
        for mob in self.regular_enemies:
            if getattr(mob, "hp", 0) > 0:
                self.enemies.add(mob)
                self.all_sprites.add(mob)

    def spawn_boss(self, boss_cls=Sans, floor_y=None, start_x=1520):
        """Spawn the specified Boss class (Sans for Level 1, Vergil for Level 2) with map collision binding."""
        if floor_y is None:
            floor_y = self.get_floor_y_at(start_x, default=640)
        self.boss = boss_cls(
            self.player,
            start_x=start_x,
            ground_y=floor_y,
            game_map=self.game_map,
        )
        self._rebuild_sprite_groups()
        if self.hud is not None:
            self.hud.boss = self.boss
            self.hud.boss_display_hp = float(self.boss.boss_health)

    def _get_regular_enemy_spawn_specs(self):
        """
        Return regular enemy (Slimer) spawn specs for the current map:
        - Main World Practice Zone 1 (before Checkpoint 1 & Sans): 2 Slimers spaced 170px apart
          below the y=560 / y=496 one-way platforms for 2x Pogo bounce practice.
        - Main World Practice Zone 2 (between Checkpoint 2 & Level 2 Vergil Portal): 2 Slimers
          spaced 155px apart below the y=584 / y=488 one-way shortcut platforms.
        """
        if self.is_main_world():
            return [
                (Slimer, 560.0, 640.0, 95.0),
                (Slimer, 730.0, 640.0, 95.0),
                (Slimer, 2290.0, 688.0, 80.0),
                (Slimer, 2445.0, 688.0, 80.0),
            ]
        return []

    def respawn_regular_enemies(self):
        """
        Respawn ONLY regular enemies (Slimers) at their initial spawn_pos with full HP & PATROL state.
        NEVER resets or alters the current Boss (Sans / Vergil) — used by Checkpoint [E] Save & Heal!
        """
        for mob in list(self.regular_enemies):
            if hasattr(mob, "_clear_contact_hitbox"):
                mob._clear_contact_hitbox()
            mob.kill()
        self.regular_enemies.empty()

        self.regular_enemy_spawns = self._get_regular_enemy_spawn_specs()
        for enemy_cls, sx, default_y, patrol_range in self.regular_enemy_spawns:
            floor_y = self.get_floor_y_at(sx, default=int(default_y))
            mob = enemy_cls(
                self.player,
                start_x=sx,
                ground_y=floor_y,
                game_map=self.game_map,
                patrol_range=patrol_range,
            )
            self.regular_enemies.add(mob)

        self._rebuild_sprite_groups()

    def reset_level_enemies(self, include_boss=True):
        """
        Enemy & Boss State Reset:
        - Always respawns regular enemies (Slimers) at their spawn_pos.
        - Only resets Boss when include_boss=True (used on Player Death Respawn).
        """
        if not include_boss:
            self.respawn_regular_enemies()
            return

        self.active_hitboxes.clear()
        for vfx in list(self.vfx_group):
            if not isinstance(vfx, (HealVFX, PortalTeleportVFX)):
                vfx.destroy()

        if self.is_tutorial:
            return

        self.respawn_regular_enemies()

        if self.is_sans_arena():
            if self.boss_defeated.get("sans", False):
                # Sans is already defeated — NEVER resurrect him on Checkpoint respawn!
                self.boss = None
                self.spawn_boss_victory_checkpoint()
                self.audio.stop_bgm(fadeout_ms=400)
            else:
                boss_x = 1180.0
                floor_y = self.get_floor_y_at(boss_x, default=784)
                if (
                    self.boss is not None
                    and isinstance(self.boss, Sans)
                    and self.boss.alive()
                ):
                    self.boss.game_map = self.game_map
                    self.boss.spawn_x = float(boss_x)
                    self.boss.spawn_y = float(floor_y)
                    self.boss.reset()
                else:
                    self.spawn_boss(boss_cls=Sans, floor_y=floor_y, start_x=boss_x)
        elif self.is_vergil_arena():
            if self.boss_defeated.get("vergil", False):
                # Vergil is already defeated — NEVER resurrect him on Checkpoint respawn!
                self.boss = None
                self.spawn_boss_victory_checkpoint()
                self.audio.stop_bgm(fadeout_ms=400)
            else:
                px = getattr(self.player, "pos_x", 280.0)
                boss_x = min(float(self.game_map.width - 260), max(860.0, px + 420.0))
                floor_y = self.get_floor_y_at(boss_x, default=656)
                if (
                    self.boss is not None
                    and isinstance(self.boss, Vergil)
                    and self.boss.alive()
                ):
                    self.boss.game_map = self.game_map
                    self.boss.spawn_x = float(boss_x)
                    self.boss.spawn_y = float(floor_y)
                    self.boss.reset()
                else:
                    self.spawn_boss(boss_cls=Vergil, floor_y=floor_y, start_x=boss_x)
        elif self.is_main_world():
            # Stage 1 is dedicated to Slimer exploration & Pogo practice (no Boss)
            self.boss = None

        self._rebuild_sprite_groups()

        if self.hud is not None:
            self.hud.boss = self.boss
            self.hud.boss_display_hp = (
                float(self.boss.boss_health) if self.boss is not None else 0.0
            )

    def update_camera(self):
        # Stage 3 (Vergil 1376x768) uses fixed centered camera;
        # Stage 2 (Sans 1.2x expanded 1664x928) & Stage 1 smoothly follow player within map bounds!
        if self.is_vergil_arena():
            self.camera_x = (self.game_map.width - WIDTH) // 2
            self.camera_y = (self.game_map.height - HEIGHT) // 2
        else:
            player_rect = getattr(self.player, "collision_rect", self.player.rect)
            self.camera_x, self.camera_y = self.game_map.get_camera_offset(
                player_rect, WIDTH, HEIGHT
            )

    def spawn_boss_victory_checkpoint(self):
        """
        Dynamically spawn an interactive Checkpoint ([E] Save & Heal) on safe ground
        beside the Arena Exit Portal after defeating a Boss (Sans / Vergil).
        """
        # Avoid spawning duplicate dynamic victory checkpoints
        if any(getattr(cp, "is_boss_victory_cp", False) for cp in self.checkpoints):
            return

        if self.triggers:
            portal_cx = self.triggers[0].rect.centerx
            cp_x = max(160.0, float(portal_cx - 150))
        else:
            cp_x = float(self.game_map.width * 0.5)

        default_y = 784 if self.is_sans_arena() else 656
        floor_y = self.get_floor_y_at(cp_x, default=default_y)
        cp_rect = pygame.Rect(0, 0, 56, 96)
        cp_rect.midbottom = (int(round(cp_x)), int(floor_y))

        next_order = max((cp.order for cp in self.checkpoints), default=10) + 1
        cp = Checkpoint(order=next_order, rect=cp_rect, name="Victory Checkpoint")
        cp.is_boss_victory_cp = True
        self.checkpoints.append(cp)

        if self.vfx_group is not None:
            self.vfx_group.add(HealVFX(cp.spawn_pos[0], cp.spawn_pos[1], duration=0.95))
        print(f"[Boss Victory] Dynamic Checkpoint spawned at {cp.spawn_pos}")

    def setup_map_state(self):
        """Configure Stage (Tutorial / Stage 1 Slime / Stage 2 Sans / Stage 3 Vergil), Checkpoints, Portals & HUD"""
        map_key = self.map_name()
        self.is_tutorial = "tutorial" in map_key
        self.victory_timer = 0.0
        # Persist per-stage level_cleared flag across Checkpoint refreshes & death respawns!
        self.level_cleared = bool(self.cleared_stages.get(map_key, False))
        self.stage_cleared = self.level_cleared
        self.portal_unlock_banner_timer = 0.0
        self.tutorial_manager = None

        # Load checkpoints from the current .tmx map
        self.checkpoints = load_checkpoints(
            self.resolve_map_path(self.current_map_path)
        )

        if self.is_tutorial:
            self.boss = None
            self.regular_enemies.empty()
            self.enemies = pygame.sprite.Group()
            self.all_sprites = pygame.sprite.Group(self.player)
            self.tutorial_manager = GuidedTutorialManager(self)
        elif self.is_sans_arena():
            # Stage 2 Dedicated 1.2x Sans Boss Arena: Spawn SANS only if not yet defeated
            self.regular_enemies.empty()
            if not self.boss_defeated.get("sans", False) and not self.level_cleared:
                boss_x = 1180.0
                floor_y = self.get_floor_y_at(boss_x, default=784)
                self.spawn_boss(boss_cls=Sans, floor_y=floor_y, start_x=boss_x)
            else:
                self.boss = None
                self.level_cleared = True
                self.stage_cleared = True
                self._rebuild_sprite_groups()
        elif self.is_vergil_arena():
            # Stage 3 Final Boss Arena: Spawn VERGIL only if not yet defeated
            self.regular_enemies.empty()
            if not self.boss_defeated.get("vergil", False) and not self.level_cleared:
                px = getattr(self.player, "pos_x", 280.0)
                boss_x = min(float(self.game_map.width - 260), max(860.0, px + 420.0))
                floor_y = self.get_floor_y_at(boss_x, default=656)
                self.spawn_boss(boss_cls=Vergil, floor_y=floor_y, start_x=boss_x)
            else:
                self.boss = None
                self.level_cleared = True
                self.stage_cleared = True
                self._rebuild_sprite_groups()
        elif self.is_main_world():
            # Stage 1: Slime Exploration & Pogo Practice (NO Sans here!)
            self.boss = None
            self.respawn_regular_enemies()
        else:
            self.boss = None
            self.regular_enemies.empty()
            self.enemies = pygame.sprite.Group()
            self.all_sprites = pygame.sprite.Group(self.player)

        self.triggers = self._convert_tiled_portals_to_triggers()

        # If this stage was already cleared earlier, keep all Portals permanently unlocked!
        if self.level_cleared:
            for trigger in self.triggers:
                trigger.unlocked = True
                trigger.unlock_anim_timer = 0.65
            if self.is_boss_arena():
                self.spawn_boss_victory_checkpoint()
                self.audio.stop_bgm(fadeout_ms=1100)

        # Manage Boss Arena BGM (Sans Megalovania at 20% lower base vol 0.32 / Vergil Theme 0.40)
        if self.is_sans_arena() and not self.boss_defeated.get("sans", False) and not self.level_cleared:
            self.audio.play_bgm("sans_theme", volume=0.32)
        elif self.is_vergil_arena() and not self.boss_defeated.get("vergil", False) and not self.level_cleared:
            self.audio.play_bgm("vergil_theme", volume=0.40)
        else:
            self.audio.stop_bgm(fadeout_ms=900)

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
            self.boss_defeated = {"sans": False, "vergil": False}
            self.cleared_stages = {}
            self.level_cleared = False
            self.respawn_map_path = map_path
            self.respawn_position = (spawn_x, spawn_y)
        self.checkpoint_msg_timer = 0.0

        self.player = Player.Player(start_x=spawn_x, ground_y=spawn_y)
        self.player.god_mode = self.debug_mode
        self.player.game_map = self.game_map
        self.player.pos_y = float(spawn_y)
        self.player.sync_boxes()

        self.boss = None
        self.regular_enemies = pygame.sprite.Group()
        self.regular_enemy_spawns = []
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
                self.audio.play_sfx("checkpoint_heal")

                self.vfx_group.add(
                    HealVFX(self.player.pos_x, self.player.pos_y, duration=0.90)
                )
                self.vfx_group.add(
                    HealVFX(cp.spawn_pos[0], cp.spawn_pos[1], duration=0.90)
                )

                # Checkpoint [E] Save & Heal ONLY respawns regular enemies (Slimers),
                # preserving Boss HP, position, and defeated state!
                self.respawn_regular_enemies()
                print(
                    f"[Checkpoint] Saved & Healed at {cp.name} {cp.spawn_pos}, Regular Enemies Respawned (Boss Preserved)."
                )
                return

        # 2. Portal Interaction ([E] Enter Portal)
        if self.transition_cooldown <= 0.0:
            portal_trigger = find_interactable_portal(
                self.player, self.triggers, self.boss
            )
            if portal_trigger is not None:
                self.player.is_teleporting = True
                self.audio.play_sfx("portal_warp")
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
            was_in = cp.can_interact
            cp.update(raw_dt, player_rect)
            if not was_in and cp.can_interact:
                self.audio.play_sfx("prompt_pop")

        for trigger in self.triggers:
            was_in = trigger.can_interact
            trigger.update(raw_dt, player_rect)
            if not was_in and trigger.can_interact and trigger.unlocked:
                self.audio.play_sfx("prompt_pop")

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
        """
        In Boss Arenas (Stage 2 Sans / Stage 3 Vergil):
        - Player death triggers Soul-like respawn at last Checkpoint.
        - Boss defeat unlocks the Arena Exit Portal (no abrupt auto-teleport).
        """
        if self.player.player_hp <= 0 and not self.debug_mode:
            self.start_death_respawn()
            return True
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
                        self.audio.stop_bgm(fadeout_ms=600)
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
                            if hasattr(enemy, "is_dead"):
                                enemy.is_dead = True
                            if hasattr(enemy, "clear_owned_attacks"):
                                enemy.clear_owned_attacks()
                            if hasattr(enemy, "_clear_contact_hitbox"):
                                enemy._clear_contact_hitbox()
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
                        and not self.is_boss_intro_active()
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
                    and not self.is_boss_intro_active()
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

    def get_all_active_hitboxes(self):
        """
        Collect all active hitboxes from the shared list, the current Boss,
        AND all regular enemies (Slimers) via their unified `get_active_hitboxes()` interface.
        """
        combined = []
        seen = set()
        for hb in self.active_hitboxes:
            if hb.active and id(hb) not in seen:
                seen.add(id(hb))
                combined.append(hb)
        if self.boss is not None and hasattr(self.boss, "get_active_hitboxes"):
            for hb in self.boss.get_active_hitboxes():
                if hb.active and id(hb) not in seen:
                    seen.add(id(hb))
                    combined.append(hb)
        for mob in self.regular_enemies:
            if mob.alive() and hasattr(mob, "get_active_hitboxes"):
                for hb in mob.get_active_hitboxes():
                    if hb.active and id(hb) not in seen:
                        seen.add(id(hb))
                        combined.append(hb)
        return combined

    def resolve_combat_collisions(self):
        """Resolve active Hitbox collisions against Hurtboxes and ParryBoxes"""
        # Filter in-place so delayed projectile VFX holding a reference to
        # `self.active_hitboxes` never append to an orphaned list!
        self.active_hitboxes[:] = [hb for hb in self.active_hitboxes if hb.active]

        for hb in self.get_all_active_hitboxes():
            if not hb.active:
                continue

            if hb.owner == "player":
                for enemy in list(self.enemies):
                    if (
                        enemy.alive()
                        and hb.can_hit(enemy)
                        and hb.rect.colliderect(enemy.hurtbox)
                    ):
                        hb.register_hit(enemy)
                        prev_stamina = getattr(enemy, "stamina", 0)
                        enemy.be_attacked(hb.damage)
                        dodged = (
                            prev_stamina > 0
                            and getattr(enemy, "stamina", 0) < prev_stamina
                        )
                        if not dodged:
                            self.audio.play_sfx("hit")
                        if hb.tag == "player_down_slash" and not dodged:
                            self.player.on_pogo_hit(vfx_group=self.vfx_group)

            elif hb.owner in ("boss", "enemy") and self.player.alive():
                attacker = getattr(hb, "source_entity", None)
                if attacker is None and hb.owner == "boss":
                    attacker = self.boss

                if (
                    attacker is None
                    or not attacker.alive()
                    or self.player.is_teleporting
                ):
                    continue

                is_sans_attack = getattr(hb, "tag", "").startswith("sans_")
                if not hb.can_hit(self.player):
                    continue

                hit_parry_box = (
                    self.player.is_blocking
                    and hb.rect.colliderect(self.player.parry_box)
                )
                hit_hurtbox = hb.rect.colliderect(self.player.hurtbox)

                if hit_parry_box or hit_hurtbox:
                    # Undertale Blue Attack rule: if NOT blocking and completely still on ground,
                    # Sky-Blue attacks pass harmlessly through the player!
                    if (
                        getattr(hb, "attack_type", "white") == "blue"
                        and not self.player.is_blocking
                        and self.player.is_completely_still()
                    ):
                        continue

                    outcome = self.player.take_hit(
                        hb, attacker=attacker, vfx_group=self.vfx_group
                    )
                    # For Sans attacks: unblocked hits ("kr_hit") do NOT add player to hit_targets
                    # so overlapping bones / Gaster Blaster beams keep draining 1 HP continuously!
                    if not is_sans_attack or outcome in ("parry", "block"):
                        hb.register_hit(self.player)

                    if outcome == "parry":
                        focus_x = (
                            self.player.parry_box.centerx * 0.65
                            + attacker.hurtbox.centerx * 0.35
                        )
                        focus_y = self.player.hurtbox.centery
                        self.trigger_bullet_time(focus_x=focus_x, focus_y=focus_y)
                        if attacker.alive() and hasattr(attacker, "on_parried"):
                            attacker.on_parried()

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

        # 2. Update screen dimming, screen shake & portal unlock banner timers
        if self.screen_dim_timer > 0.0:
            self.screen_dim_timer = max(0.0, self.screen_dim_timer - raw_dt)
        if self.screen_shake_timer > 0.0:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - raw_dt)
        if self.portal_unlock_banner_timer > 0.0:
            self.portal_unlock_banner_timer = max(
                0.0, self.portal_unlock_banner_timer - raw_dt
            )

        # 3. Hitstop freeze frame on Perfect Parry
        if self.hitstop_timer > 0.0:
            self.hitstop_timer = max(0.0, self.hitstop_timer - raw_dt)
            for vfx in list(self.vfx_group):
                vfx.update(raw_dt * 0.12)
            return

        # 4. Update Bullet Time, Boss Intro 1.40x Camera Pan/Zoom & Recovery
        if self.is_boss_intro_active():
            intro_p = getattr(self.boss, "intro_progress", 0.0)
            target_fx = float(self.boss.pos_x)
            target_fy = float(self.boss.pos_y - 54.0)
            lerp_k = min(1.0, raw_dt * 7.5)
            self.zoom_focus_world[0] += (target_fx - self.zoom_focus_world[0]) * lerp_k
            self.zoom_focus_world[1] += (target_fy - self.zoom_focus_world[1]) * lerp_k

            # Smoothly zoom in to 1.40x during intro, then ease back to 1.0x as battle starts
            if intro_p < 0.22:
                z_t = intro_p / 0.22
                self.zoom_scale = 1.0 + 0.40 * (1.0 - (1.0 - z_t) ** 3)
                self.intro_letterbox_ratio = z_t
            elif intro_p < 0.80:
                self.zoom_scale = 1.40
                self.intro_letterbox_ratio = 1.0
            else:
                z_t = (intro_p - 0.80) / 0.20
                self.zoom_scale = 1.40 - 0.40 * (z_t * z_t)
                self.intro_letterbox_ratio = max(0.0, 1.0 - z_t)
        elif self.bullet_time_timer > 0.0:
            self.intro_letterbox_ratio = max(0.0, self.intro_letterbox_ratio - raw_dt * 4.0)
            self.bullet_time_timer = max(0.0, self.bullet_time_timer - raw_dt)
            self.zoom_scale = PARRY_ZOOM_SCALE
            if self.bullet_time_timer <= 0.0:
                self.time_scale = min(
                    1.0,
                    self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt,
                )
        else:
            if self.intro_letterbox_ratio > 0.0:
                self.intro_letterbox_ratio = max(
                    0.0, self.intro_letterbox_ratio - raw_dt * 4.5
                )
            if self.time_scale < 1.0:
                self.time_scale = min(
                    1.0, self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt
                )
            if self.zoom_scale > 1.0:
                self.zoom_scale = max(
                    1.0, self.zoom_scale - PARRY_ZOOM_RECOVERY_SPEED * raw_dt
                )

        scaled_dt = raw_dt * self.time_scale

        # 5. Update Player (lock player controls during Boss INTRO cutscene)
        if self.is_boss_intro_active():
            self.player.velocity_x = 0.0
            self.player.holding_move_key = False
            self.player.is_attacking = False
            self.player.is_blocking = False
            self.player.sync_boxes()
        else:
            self.player.update(
                dt=scaled_dt,
                raw_dt=raw_dt,
                active_hitboxes=self.active_hitboxes,
                vfx_group=self.vfx_group,
                map_width=self.game_map.width,
            )

        # 6. Update Checkpoints & Portals interaction zones
        self.update_checkpoints_and_portals(raw_dt)

        # 7. Update Boss, Regular Enemies (Slimers) & Guided Tutorial entities
        if self.boss is not None and self.boss.alive():
            self.boss.update(
                dt=scaled_dt,
                active_hitboxes=self.active_hitboxes,
                vfx_group=self.vfx_group,
                map_width=self.game_map.width,
            )
            shake_req = getattr(self.boss, "pending_screen_shake", 0.0)
            if shake_req > 0.0:
                self.screen_shake_timer = max(self.screen_shake_timer, shake_req)
                self.boss.pending_screen_shake = 0.0

        for mob in list(self.regular_enemies):
            if mob.alive():
                mob.update(
                    dt=scaled_dt,
                    vfx_group=self.vfx_group,
                    map_width=self.game_map.width,
                )

        if self.tutorial_manager is not None:
            self.tutorial_manager.update(scaled_dt)

        # Check Stage Clear Condition -> Persist boss_defeated & level_cleared, Unlock Portals & Spawn Victory Checkpoint!
        if not self.stage_cleared and self.check_stage_clear_condition():
            self.stage_cleared = True
            self.level_cleared = True
            self.cleared_stages[self.map_name()] = True
            if self.is_sans_arena():
                self.boss_defeated["sans"] = True
            elif self.is_vergil_arena():
                self.boss_defeated["vergil"] = True
            unlocked_any = False
            for trigger in self.triggers:
                if trigger.unlock(vfx_group=self.vfx_group):
                    unlocked_any = True
            if self.is_boss_arena():
                self.spawn_boss_victory_checkpoint()
                self.audio.stop_bgm(fadeout_ms=1100)
            if unlocked_any:
                self.portal_unlock_banner_timer = 3.4
                self.audio.play_sfx("level_clear")
                print(f"[Stage Clear] '{self.map_name()}' Cleared! Portal Unlocked.")

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
            shake_dx = 0
            shake_dy = 0
            if self.screen_shake_timer > 0.0:
                mag = int(round(self.screen_shake_intensity * min(1.0, self.screen_shake_timer * 2.5)))
                if mag > 0:
                    shake_dx = random.randint(-mag, mag)
                    shake_dy = random.randint(-mag, mag)

            active_bg = self.sans_background if self.is_sans_arena() else self.background
            self.world_surface.blit(active_bg, (shake_dx, shake_dy))
            self.game_map.draw(
                self.world_surface, self.camera_x - shake_dx, self.camera_y - shake_dy
            )

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

            # 3b. Layer 1 Background Distortion VFX (behind characters, e.g. Vergil Judgement Cut End)
            for vfx in self.vfx_group:
                if hasattr(vfx, "draw_background_layer"):
                    vfx.draw_background_layer(
                        self.world_surface, self.camera_x, self.camera_y
                    )

            # 4. Draw Player & Boss extras (flame aura, afterimages, Sans dodge afterimages)
            if self.player.alive():
                self.player.draw_extras(
                    self.world_surface, self.camera_x, self.camera_y
                )
            if self.boss is not None and self.boss.alive() and hasattr(self.boss, "draw_extras"):
                self.boss.draw_extras(
                    self.world_surface, self.camera_x, self.camera_y
                )

            # 5. Draw all active sprites (Player, Boss, Slimers, Tutorial Targets)
            for sprite in self.all_sprites:
                if sprite.alive():
                    self.world_surface.blit(
                        sprite.image,
                        sprite.rect.move(-self.camera_x, -self.camera_y),
                    )
            for mob in self.regular_enemies:
                if mob.alive() and hasattr(mob, "draw_hp_bar"):
                    mob.draw_hp_bar(self.world_surface, self.camera_x, self.camera_y)

            # 6. Draw all VFX (Midground Slashes, Heal particles, Portal particles, Pixel Ink-Splash Parry)
            for vfx in self.vfx_group:
                vfx.draw(self.world_surface, self.camera_x, self.camera_y)

            # 7. Draw black radial manga speed lines during Perfect Parry
            self.draw_parry_speed_lines(self.world_surface)

            # 8. Floating combat feedback text above Player
            if self.player.status_timer > 0.0 and self.player.status_text:
                sx = int(self.player.pos_x - self.camera_x)
                sy = int(self.player.hurtbox.top - 18 - self.camera_y)
                if "KR" in self.player.status_text:
                    color = (225, 95, 255)
                elif (
                    "PERFECT" in self.player.status_text
                    or "POGO" in self.player.status_text
                    or "SHATTERED" in self.player.status_text
                ):
                    color = (90, 250, 255)
                else:
                    color = (255, 230, 120)
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
                    self.get_all_active_hitboxes(),
                    self.vfx_group,
                    regular_enemies=self.regular_enemies,
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

            # ==================== Pass 2: Apply Dynamic Camera Zoom (1.40x Boss Intro / 1.15x Parry) onto self.screen ====================
            self._blit_world_with_zoom()

            # Cinema Letterbox black bars during Boss Intro Cutscene
            if self.intro_letterbox_ratio > 0.01:
                bar_h = int(round(56 * self.intro_letterbox_ratio))
                if bar_h > 0:
                    pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, WIDTH, bar_h))
                    pygame.draw.rect(
                        self.screen, (0, 0, 0), (0, HEIGHT - bar_h, WIDTH, bar_h)
                    )

            # ==================== Pass 3: Render Fixed Top-Layer HUD & UI onto self.screen ====================
            self.hud.draw_gameplay_hud(self.screen)

            if self.tutorial_manager is not None:
                self.tutorial_manager.draw_hud_banner(self.screen, self.hud)

            if self.debug_mode:
                # Top-left Boss Debug Status Panel (below Player HP & God Mode badge)
                if self.boss is not None:
                    b_cls = self.boss.__class__.__name__
                    b_pos = f"({int(self.boss.pos_x)}, {int(self.boss.pos_y)})"
                    b_alive = self.boss.alive()
                    b_hp = f"{int(round(self.boss.boss_health))}/{int(self.boss.max_health)}"
                    b_state = getattr(self.boss, "state", "-")
                    b_ground = getattr(self.boss, "on_ground", False)
                    debug_lines = [
                        f"BOSS: {b_cls} | Alive={b_alive} | HP={b_hp} | State={b_state}",
                        f"BOSS POS: {b_pos} | Grounded={b_ground} | Slimers={len(self.regular_enemies)}",
                    ]
                else:
                    debug_lines = [
                        f"BOSS: None | Slimers={len(self.regular_enemies)}",
                    ]

                panel_x, panel_y = 24, 114
                line_surfs = [
                    self.hud.font_hud.render(line, False, (120, 255, 220))
                    for line in debug_lines
                ]
                panel_w = max(s.get_width() for s in line_surfs) + 16
                panel_h = sum(s.get_height() + 4 for s in line_surfs) + 10
                panel_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
                panel_bg.fill((12, 18, 28, 200))
                self.screen.blit(panel_bg, (panel_x, panel_y))
                pygame.draw.rect(
                    self.screen,
                    (80, 220, 200),
                    (panel_x, panel_y, panel_w, panel_h),
                    1,
                    border_radius=3,
                )
                cur_y = panel_y + 6
                for s in line_surfs:
                    self.screen.blit(s, (panel_x + 8, cur_y))
                    cur_y += s.get_height() + 4

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

            if self.is_main_world():
                total_slimes = max(1, len(self.regular_enemy_spawns))
                rem_slimes = len(self.regular_enemies)
                if not self.level_cleared and rem_slimes > 0:
                    obj_text = f"STAGE 1: DEFEAT ALL SLIMERS ({total_slimes - rem_slimes} / {total_slimes})"
                    obj_col = (195, 245, 210)
                    border_col = (90, 210, 125)
                else:
                    obj_text = "STAGE 1 CLEAR! PORTAL OPEN — ENTER TO FACE SANS"
                    obj_col = (120, 245, 255)
                    border_col = (90, 225, 255)
                obj_surf = self.hud.font_hud.render(obj_text, False, obj_col)
                ow = obj_surf.get_width() + 24
                oh = obj_surf.get_height() + 12
                ox = (WIDTH - ow) // 2
                oy = 22
                pill = pygame.Surface((ow, oh), pygame.SRCALPHA)
                pill.fill((14, 18, 30, 195))
                self.screen.blit(pill, (ox, oy))
                pygame.draw.rect(
                    self.screen, border_col, (ox, oy, ow, oh), 2, border_radius=4
                )
                self.screen.blit(obj_surf, (ox + 12, oy + 6))

            if self.portal_unlock_banner_timer > 0.0:
                self.hud.draw_text(
                    self.screen,
                    "PORTAL UNLOCKED!",
                    self.hud.font_small,
                    (110, 245, 255),
                    (WIDTH // 2, 86),
                )

            if (
                not self.is_tutorial
                and self.boss is not None
                and not self.boss.alive()
            ):
                boss_label = getattr(self.boss, "boss_name", "BOSS")
                if self.is_sans_arena():
                    self.hud.draw_text(
                        self.screen,
                        f"STAGE 2 CLEAR! {boss_label} DEFEATED",
                        self.hud.font_big,
                        (255, 215, 80),
                        (WIDTH // 2, HEIGHT // 2 - 48),
                    )
                    self.hud.draw_text(
                        self.screen,
                        "Enter the Portal to challenge VERGIL in Stage 3",
                        self.hud.font_small,
                        (180, 235, 255),
                        (WIDTH // 2, HEIGHT // 2 + 12),
                    )
                else:
                    self.hud.draw_text(
                        self.screen,
                        f"VICTORY! {boss_label} DEFEATED",
                        self.hud.font_big,
                        (255, 215, 80),
                        (WIDTH // 2, HEIGHT // 2 - 48),
                    )
                    self.hud.draw_text(
                        self.screen,
                        "Enter the Portal to return to Stage 1",
                        self.hud.font_small,
                        (180, 235, 255),
                        (WIDTH // 2, HEIGHT // 2 + 12),
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

        # Layer 3 Foreground Screen-Breaking VFX Overlay (above ALL entities, camera zoom, and HUD!)
        if self.state in (State.PLAYING, State.PAUSED):
            for vfx in self.vfx_group:
                if hasattr(vfx, "draw_screen_overlay"):
                    vfx.draw_screen_overlay(self.screen)

            # Programmatic Pixel-Font Boss Title Card ('The weakest ?' / 'Sans') with smooth 2.0s pacing
            if self.boss is not None and getattr(self.boss, "title_card_active", False):
                tc_t = getattr(self.boss, "title_card_timer", 0.0)
                if tc_t < 0.25:
                    bg_alpha = int(255 * (tc_t / 0.25))
                elif tc_t > 1.70:
                    bg_alpha = int(255 * max(0.0, 1.0 - (tc_t - 1.70) / 0.30))
                else:
                    bg_alpha = 255

                self.title_card_surf.fill((255, 255, 255, max(0, min(255, bg_alpha))))
                if tc_t >= 0.25:
                    sub_a = min(255, int(255 * min(1.0, (tc_t - 0.25) / 0.15)))
                    sub_a = min(sub_a, bg_alpha)
                    sub_surf = self.font_title_sub.render("The weakest ?", False, (0, 0, 0))
                    sub_surf.set_alpha(sub_a)
                    self.title_card_surf.blit(
                        sub_surf, sub_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 65))
                    )
                if tc_t >= 0.60:
                    main_a = min(255, int(255 * min(1.0, (tc_t - 0.60) / 0.10)))
                    main_a = min(main_a, bg_alpha)
                    main_surf = self.font_title_main.render("Sans", False, (0, 0, 0))
                    main_surf.set_alpha(main_a)
                    self.title_card_surf.blit(
                        main_surf, main_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30))
                    )
                self.screen.blit(self.title_card_surf, (0, 0))

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
