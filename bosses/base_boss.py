import math
import pygame
from Animator import AnimatedSprite
from Settings import GROUND_Y, GRAVITY


class BossState:
    INTRO = "INTRO"
    IDLE = "IDLE"
    CHASE = "CHASE"
    ATTACK_1 = "ATTACK_1"
    ATTACK_2 = "ATTACK_2"
    ATTACK_3 = "ATTACK_3"
    ATTACK_4 = "ATTACK_4"
    ATTACK_5 = "ATTACK_5"
    ATTACK_6 = "ATTACK_6"
    PHASE_2_TRANSITION = "PHASE_2_TRANSITION"
    JUDGEMENT_CUT_END = "JUDGEMENT_CUT_END"
    SANS_ULTIMATE = "SANS_ULTIMATE"
    COOLDOWN = "COOLDOWN"


class AttackPhase:
    NONE = "NONE"
    WINDUP = "WINDUP"      # Telegraph phase (no Hitbox)
    ACTIVE = "ACTIVE"      # Active frames (spawns VFX & Hitboxes)
    RECOVERY = "RECOVERY"  # Recovery phase (clears melee Hitbox)


class BaseBoss(pygame.sprite.Sprite):
    """
    Common Base Class for all Stage Bosses (Sans, Vergil, etc.):
    1. Unconditional per-frame gravity, solid floor/wall/slope collision, and One-Way Platform landing.
    2. Shared Jump & Vertical Chase AI (elevation chase, drop-through chase, obstacle vaulting, gap jumping).
    3. Unified HP management (hp/max_hp), take_damage(), reset(), and midbottom anchor sync_boxes().
    4. Unified attack hitbox interface (get_active_hitboxes() / get_projectiles()) so the combat loop
       and Debug renderer always detect every melee slash, projectile, bone wave, and laser beam!
    """

    def __init__(
        self,
        target_player,
        boss_name="BOSS",
        start_x=640,
        ground_y=GROUND_Y,
        game_map=None,
        max_hp=100,
        move_speed=215.0,
        collision_size=(42, 100),
        hurtbox_size=(36, 94),
    ):
        super().__init__()

        self.boss_name = boss_name
        self.target = target_player
        self.game_map = game_map
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)
        self.boss_speed = float(move_speed)

        # Unified ground anchor (pos_x, pos_y = midbottom) + Jump & One-Way Platform physics
        self.spawn_x = float(start_x)
        self.spawn_y = float(ground_y)
        self.pos_x = float(start_x)
        self.pos_y = float(ground_y)
        self.ground_y = float(ground_y)
        self.velocity_y = 0.0
        self.gravity = GRAVITY
        self.jump_speed = -635.0
        self.jump_cooldown = 0.0
        self.on_ground = False
        self.on_one_way_platform = False
        self.drop_through_timer = 0.0
        self.flip = True

        # FSM state machine & Intro Cutscene state
        self.state = BossState.IDLE
        self.attack_phase = AttackPhase.NONE
        self.state_timer = 0.0
        self.cooldown_duration = 0.55
        self.combo_step = 0
        self.intro_duration = 1.75
        self.intro_progress = 1.0

        # Per-skill cooldowns (seconds)
        self.skill_cooldowns = {
            BossState.ATTACK_1: 0.0,
            BossState.ATTACK_2: 0.0,
            BossState.ATTACK_3: 0.0,
        }

        # Hit flash, invulnerability, death & camera shake request flags
        self.hit_flash_timer = 0.0
        self.hit_invuln_timer = 0.0
        self.invincible = False
        self.is_dead = False
        self.pending_screen_shake = 0.0

        # Owned attack VFX & Hitboxes (tracked for unified get_active_hitboxes() & cleanup)
        self.current_melee_hitbox = None
        self.owned_hitboxes = []
        self.owned_vfx = []

        # Animator & sprite offset compensation (populated by subclasses)
        self.animator = AnimatedSprite()
        self.animation_speed = {"idle": 0.10, "Run": 0.16}
        self.sprite_offsets = {"idle": (0.0, 0.0), "Run": (0.0, 0.0)}
        self.image = pygame.Surface(collision_size, pygame.SRCALPHA)

        # Separated Collision Box & Hurtbox
        self.collision_rect = pygame.Rect(0, 0, collision_size[0], collision_size[1])
        self.hurtbox = pygame.Rect(0, 0, hurtbox_size[0], hurtbox_size[1])
        self.hitbox = self.hurtbox
        self.rect = self.image.get_rect()

    # ---------- Backward-Compatible HP Properties ----------
    @property
    def max_health(self):
        return int(self.max_hp) if self.max_hp.is_integer() else self.max_hp

    @max_health.setter
    def max_health(self, val):
        self.max_hp = float(val)

    @property
    def boss_health(self):
        return self.hp

    @boss_health.setter
    def boss_health(self, val):
        self.hp = float(val)

    @property
    def facing_dir(self):
        return -1 if self.flip else 1

    # ---------- Unified Attack Registration & Query Interface ----------
    def register_hitbox(self, hb, active_hitboxes=None):
        """Register a boss Hitbox so both owned_hitboxes and active_hitboxes track it"""
        if hb is not None:
            self.owned_hitboxes.append(hb)
            if active_hitboxes is not None and hb not in active_hitboxes:
                active_hitboxes.append(hb)
        return hb

    def register_vfx(self, vfx, vfx_group=None):
        """Register a boss attack VFX / projectile so get_active_hitboxes() tracks its Hitboxes"""
        if vfx is not None:
            self.owned_vfx.append(vfx)
            if vfx_group is not None:
                vfx_group.add(vfx)
        return vfx

    def get_projectiles(self):
        """Return all live attack VFX / projectiles spawned by this Boss"""
        self.owned_vfx[:] = [v for v in self.owned_vfx if v.alive()]
        return list(self.owned_vfx)

    def get_active_hitboxes(self):
        """
        Unified Combat Interface:
        Collects every currently active Hitbox from this Boss (melee slashes, bone waves,
        homing bones, Gaster Blaster multi-segment laser beams, dimension waves, AoE fields).
        """
        self.owned_hitboxes[:] = [hb for hb in self.owned_hitboxes if hb.active]
        self.owned_vfx[:] = [v for v in self.owned_vfx if v.alive()]

        result = []
        seen = set()

        def _add(hb):
            if hb is not None and hb.active and id(hb) not in seen:
                seen.add(id(hb))
                result.append(hb)

        if self.current_melee_hitbox is not None:
            _add(self.current_melee_hitbox)

        for hb in self.owned_hitboxes:
            _add(hb)

        for vfx in self.owned_vfx:
            if getattr(vfx, "hitbox", None) is not None:
                _add(vfx.hitbox)
            for b_hb in getattr(vfx, "beam_hitboxes", ()):
                _add(b_hb)

        return result

    def _clear_melee_hitbox(self):
        if self.current_melee_hitbox is not None:
            self.current_melee_hitbox.destroy()
            self.current_melee_hitbox = None

    def clear_owned_attacks(self):
        """Destroy all melee hitboxes, projectiles, and beams owned by this Boss"""
        self._clear_melee_hitbox()
        for hb in self.owned_hitboxes:
            hb.destroy()
        self.owned_hitboxes.clear()
        for vfx in self.owned_vfx:
            vfx.destroy()
        self.owned_vfx.clear()

    # ---------- Shared Physics, Jump & Vertical Chase AI ----------
    def jump(self):
        """Jump upward when grounded and jump_cooldown <= 0"""
        if self.on_ground and self.jump_cooldown <= 0.0:
            self.velocity_y = self.jump_speed
            self.on_ground = False
            self.on_one_way_platform = False
            self.jump_cooldown = 1.05
            return True
        return False

    def face_target(self):
        if self.target and self.target.alive():
            self.flip = self.target.pos_x < self.pos_x

    def sync_boxes(self):
        """Align collision_rect, hurtbox, and sprite rect strictly to midbottom (pos_x, pos_y)"""
        anchor_x = int(round(self.pos_x))
        anchor_y = int(round(self.pos_y))
        f_dir = self.facing_dir

        self.collision_rect.midbottom = (anchor_x, anchor_y)
        self.hurtbox.midbottom = (anchor_x, anchor_y - 2)
        self.hitbox = self.hurtbox

        anim_state = self.animator.current_state or "idle"
        body_dx, bottom_pad = self.sprite_offsets.get(anim_state, (0.0, 0.0))
        self.rect = self.image.get_rect()
        self.rect.centerx = int(round(self.pos_x - f_dir * body_dx))
        self.rect.bottom = int(round(self.pos_y + bottom_pad))

    def update_vertical_chase_ai(self, distance, move_dir):
        """
        Shared Jump & Vertical Platform Chase Logic:
        - Elevation Chase: Jump up when player is on a higher platform
        - Drop-Through Chase: Drop down through one-way platforms when player is below
        - Gap Ahead Detection: Jump across floor gaps while chasing
        """
        if not (self.target and self.target.alive() and self.on_ground):
            return

        player_hb = getattr(self.target, "collision_rect", self.target.hurtbox)

        if (
            player_hb.bottom < self.collision_rect.top - 20
            and distance <= 340.0
            and self.jump_cooldown <= 0.0
        ):
            self.jump()
        elif (
            self.on_one_way_platform
            and player_hb.top > self.collision_rect.bottom + 16
            and distance <= 320.0
        ):
            self.drop_through_timer = 0.25
            self.on_ground = False
            self.on_one_way_platform = False
            self.velocity_y = 140.0
            self.pos_y += 3.0
        elif (
            self.jump_cooldown <= 0.0
            and distance > 85.0
            and self.game_map is not None
            and hasattr(self.game_map, "has_ground_ahead")
        ):
            if not self.game_map.has_ground_ahead(self.collision_rect, move_dir):
                self.jump()

    def apply_physics_and_collisions(self, dt, old_pos_x, map_width):
        """
        Unconditional per-frame gravity, solid wall/floor collision, One-Way Platform landing,
        and obstacle vaulting when blocked horizontally during CHASE.
        """
        intended_dx = self.pos_x - old_pos_x
        self.velocity_y = min(self.velocity_y + self.gravity * dt, 950.0)
        dy = self.velocity_y * dt

        has_map_geometry = bool(
            self.game_map
            and (
                getattr(self.game_map, "collisions", None)
                or getattr(self.game_map, "polygons", None)
                or getattr(self.game_map, "platforms", None)
            )
        )

        if has_map_geometry:
            self.collision_rect.midbottom = (round(old_pos_x), round(self.pos_y))
            on_ground_now, hit_ceiling = self.game_map.move_with_collisions(
                self.collision_rect,
                intended_dx,
                dy,
                drop_through=(self.drop_through_timer > 0.0),
            )
            self.on_one_way_platform = bool(
                getattr(self.game_map, "last_on_one_way", False)
            )

            if self.collision_rect.left < 40:
                self.collision_rect.left = 40
            elif self.collision_rect.right > map_width - 40:
                self.collision_rect.right = map_width - 40

            actual_dx = self.collision_rect.centerx - round(old_pos_x)
            self.pos_x = float(self.collision_rect.centerx)
            self.pos_y = float(self.collision_rect.bottom)

            if on_ground_now and self.velocity_y >= 0.0:
                self.velocity_y = 0.0
                self.on_ground = True
                self.ground_y = self.pos_y
            else:
                self.on_ground = on_ground_now
                if hit_ceiling and self.velocity_y < 0.0:
                    self.velocity_y = 0.0

            # Obstacle Vaulting: auto-jump when blocked by a step/wall while chasing
            if (
                self.state == BossState.CHASE
                and self.on_ground
                and self.jump_cooldown <= 0.0
                and abs(intended_dx) > 0.8
                and abs(actual_dx) < abs(intended_dx) * 0.25
            ):
                self.jump()
        else:
            self.pos_x = max(40.0, min(float(map_width - 40), self.pos_x))
            self.pos_y += dy
            self.on_one_way_platform = False
            if self.pos_y >= self.ground_y:
                self.pos_y = float(self.ground_y)
                self.velocity_y = 0.0
                self.on_ground = True
            else:
                self.on_ground = False

    # ---------- Shared Damage, Parry Reaction & Reset ----------
    def take_damage(self, damage=12):
        """Unified damage intake with brief invulnerability and red hit flash"""
        if self.invincible:
            return
        if self.hit_invuln_timer <= 0.0 and self.hp > 0:
            self.hp = max(0.0, round(self.hp - damage, 2))
            self.hit_flash_timer = 0.25
            self.hit_invuln_timer = 0.18
            if self.hp <= 0.0:
                self.is_dead = True
                self.clear_owned_attacks()
                self.kill()

    def be_attacked(self, damage=12):
        """Backward-compatible alias for take_damage()"""
        self.take_damage(damage)

    def on_parried(self):
        """Hook called when player lands a Perfect Parry against this Boss"""
        self._clear_melee_hitbox()

    def reset(self):
        """Soul-like full Boss reset (restores full HP, spawn coordinates, and IDLE state)"""
        self.clear_owned_attacks()
        self.hp = float(self.max_hp)
        self.pos_x = float(self.spawn_x)
        self.pos_y = float(self.spawn_y)
        self.velocity_y = 0.0
        self.jump_cooldown = 0.0
        self.drop_through_timer = 0.0
        self.on_ground = False
        self.on_one_way_platform = False
        self.state = BossState.IDLE
        self.attack_phase = AttackPhase.NONE
        self.state_timer = 0.0
        self.combo_step = 0
        self.hit_flash_timer = 0.0
        self.hit_invuln_timer = 0.0
        self.invincible = False
        self.is_dead = False
        self.pending_screen_shake = 0.0
        for k in self.skill_cooldowns:
            self.skill_cooldowns[k] = 0.0
        self.animator.play("idle", force_reset=True)
        self.image = self.animator.update_get_image(
            self.animation_speed.get("idle", 0.10), dt_scale=0.0
        )
        self.face_target()
        if self.flip:
            self.image = pygame.transform.flip(
                self.image, True, False
            ).convert_alpha()
        self.sync_boxes()

    def _tick_common_timers(self, dt):
        self.state_timer += dt
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)
        if self.hit_invuln_timer > 0.0:
            self.hit_invuln_timer = max(0.0, self.hit_invuln_timer - dt)
        if self.jump_cooldown > 0.0:
            self.jump_cooldown = max(0.0, self.jump_cooldown - dt)
        if self.drop_through_timer > 0.0:
            self.drop_through_timer = max(0.0, self.drop_through_timer - dt)
        for k in self.skill_cooldowns:
            if self.skill_cooldowns[k] > 0.0:
                self.skill_cooldowns[k] = max(0.0, self.skill_cooldowns[k] - dt)
