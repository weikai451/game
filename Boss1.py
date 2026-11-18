import math
import pygame
from Animator import AnimatedSprite
from Settings import GROUND_Y, GRAVITY
from VFX import (
    Hitbox,
    SlashVFX,
    DashSlashVFX,
    ProjectileWaveVFX,
    GroundShockwaveVFX,
)


class BossState:
    IDLE = "IDLE"
    CHASE = "CHASE"
    ATTACK_1 = "ATTACK_1"  # Close-range 2-hit Iai combo
    ATTACK_2 = "ATTACK_2"  # Mid-range Dash Slash
    ATTACK_3 = "ATTACK_3"  # Ranged Dimension Wave + Judgment Cut AoE
    COOLDOWN = "COOLDOWN"


class AttackPhase:
    NONE = "NONE"
    WINDUP = "WINDUP"      # Telegraph phase (no Hitbox)
    ACTIVE = "ACTIVE"      # Active frames (spawns VFX & Hitbox)
    RECOVERY = "RECOVERY"  # Recovery phase (destroys melee Hitbox)


class Vergil(pygame.sprite.Sprite):
    def __init__(self, target_player, start_x=640, ground_y=GROUND_Y, game_map=None):
        super().__init__()

        self.target = target_player
        self.game_map = game_map
        self.max_health = 100
        self.boss_health = 100
        self.boss_speed = 215.0  # px / s

        # Unified ground anchor (pos_x, pos_y) + Jump & One-Way Platform capabilities
        self.spawn_x = float(start_x)
        self.spawn_y = float(ground_y)
        self.pos_x = float(start_x)
        self.pos_y = float(ground_y)
        self.ground_y = ground_y
        self.velocity_y = 0.0
        self.gravity = GRAVITY
        self.jump_speed = -635.0       # Negative upward jump velocity (~134px jump height)
        self.jump_cooldown = 0.0       # Cooldown timer between Boss jumps
        self.on_ground = False
        self.on_one_way_platform = False
        self.drop_through_timer = 0.0  # > 0 allows Boss to drop through one-way platforms to chase player below
        self.flip = True

        # FSM attributes
        self.state = BossState.IDLE
        self.attack_phase = AttackPhase.NONE
        self.state_timer = 0.0
        self.cooldown_duration = 0.55

        # Per-skill cooldowns (seconds)
        self.skill_cooldowns = {
            BossState.ATTACK_1: 0.0,
            BossState.ATTACK_2: 0.0,
            BossState.ATTACK_3: 0.0,
        }

        # Hit flash & invulnerability timers
        self.hit_flash_timer = 0.0
        self.hit_invuln_timer = 0.0

        # Attack helper flags
        self.combo_step = 0
        self.dash_dir = -1
        self.dash_start_x = 0.0
        self.current_melee_hitbox = None

        # Animation speeds
        self.animation_speed = {
            "idle": 0.10,
            "Run": 0.165,
            "Dash": 0.22,
            "Attack1": 0.14,
        }

        # Non-transparent pixel bounding box offsets
        self.sprite_offsets = {
            "idle": (9.5, 0.0),
            "Run": (14.0, 9.0),
            "Dash": (10.0, 1.0),
            "Attack1": (1.0, 0.0),
        }

        self.animator = AnimatedSprite()
        self.animator.load_animation("idle", "asset/Vergil/vergil_idle.png", 4, 0.11)
        self.animator.load_animation("Run", "asset/Vergil/vergil_run.png", 6, 0.12)
        self.animator.load_animation("Dash", "asset/Vergil/vergil_dash.png", 5, 0.58)
        self.animator.load_animation(
            "Attack1", "asset/Vergil/vergil_attack1.png", 4, 0.12
        )

        self.animator.play("idle")
        self.image = self.animator.update_get_image(self.animation_speed["idle"])

        # Separated Collision Box & Hurtbox
        self.collision_rect = pygame.Rect(0, 0, 42, 104)
        self.hurtbox = pygame.Rect(0, 0, 36, 98)
        self.hitbox = self.hurtbox

        self.rect = self.image.get_rect()
        self.sync_boxes()

    @property
    def facing_dir(self):
        return -1 if self.flip else 1

    def jump(self):
        """
        Boss Jump Mechanism:
        When standing on ground and jump_cooldown <= 0, applies upward velocity self.jump_speed
        and sets self.on_ground = False.
        """
        if self.on_ground and self.jump_cooldown <= 0.0:
            self.velocity_y = self.jump_speed
            self.on_ground = False
            self.on_one_way_platform = False
            self.jump_cooldown = 1.05
            return True
        return False

    def sync_boxes(self):
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

    def _clear_melee_hitbox(self):
        if self.current_melee_hitbox is not None:
            self.current_melee_hitbox.destroy()
            self.current_melee_hitbox = None

    def reset(self):
        """
        Soul-like Reset:
        Restores Boss to full HP, initial spawn position, and IDLE state.
        """
        self._clear_melee_hitbox()
        self.boss_health = self.max_health
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
        for k in self.skill_cooldowns:
            self.skill_cooldowns[k] = 0.0
        self.animator.play("idle", force_reset=True)
        self.image = self.animator.update_get_image(
            self.animation_speed["idle"], dt_scale=0.0
        )
        self.face_target()
        if self.flip:
            self.image = pygame.transform.flip(
                self.image, True, False
            ).convert_alpha()
        self.sync_boxes()

    def face_target(self):
        if self.target and self.target.alive():
            self.flip = self.target.pos_x < self.pos_x

    def change_state(self, new_state, cooldown_duration=0.55):
        self._clear_melee_hitbox()
        self.state = new_state
        self.state_timer = 0.0
        self.combo_step = 0

        if new_state in (
            BossState.ATTACK_1,
            BossState.ATTACK_2,
            BossState.ATTACK_3,
        ):
            self.face_target()
            self.attack_phase = AttackPhase.WINDUP
            if new_state == BossState.ATTACK_1:
                self.animator.play("Attack1", force_reset=True)
            elif new_state == BossState.ATTACK_2:
                self.dash_dir = self.facing_dir
                self.dash_start_x = self.pos_x
                self.animator.play("Dash", force_reset=True)
            elif new_state == BossState.ATTACK_3:
                self.animator.play("Attack1", force_reset=True)
        else:
            self.attack_phase = AttackPhase.NONE
            if new_state == BossState.COOLDOWN:
                self.cooldown_duration = cooldown_duration
                self.animator.play("idle")
            elif new_state == BossState.IDLE:
                self.animator.play("idle")
            elif new_state == BossState.CHASE:
                self.animator.play("Run")

    def decide_next_action(self, distance):
        """
        Decide next FSM state based on horizontal & vertical distance to the player:
        - If player is significantly higher or lower on a platform, prioritize CHASE (with jump / drop-through)
          instead of whiffing ground melee attacks.
        """
        vertical_diff = (
            abs(self.target.pos_y - self.pos_y)
            if (self.target and self.target.alive())
            else 0.0
        )
        cd1 = self.skill_cooldowns[BossState.ATTACK_1] <= 0.0
        cd2 = self.skill_cooldowns[BossState.ATTACK_2] <= 0.0
        cd3 = self.skill_cooldowns[BossState.ATTACK_3] <= 0.0

        # If player is on a higher/lower platform (vertical difference > 65px), chase vertically first
        if vertical_diff > 65.0:
            if cd3 and distance >= 180.0:
                self.change_state(BossState.ATTACK_3)
                return
            self.change_state(BossState.CHASE)
            return

        if distance <= 95:
            if cd1:
                self.change_state(BossState.ATTACK_1)
                return
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return

        elif distance <= 280:
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return
            if cd3 and distance >= 165:
                self.change_state(BossState.ATTACK_3)
                return

        else:
            if cd3:
                self.change_state(BossState.ATTACK_3)
                return
            if cd2 and distance <= 360:
                self.change_state(BossState.ATTACK_2)
                return

        if distance > 75 or vertical_diff > 30.0:
            self.change_state(BossState.CHASE)
        else:
            self.change_state(BossState.IDLE)

    # ---------- 3 Attack States (WINDUP -> ACTIVE -> RECOVERY) ----------

    def _update_attack_1(self, dt, active_hitboxes, vfx_group):
        windup_end = 0.32
        slash2_time = 0.50
        active_end = 0.68
        recovery_end = 0.98

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self.face_target()
                self.pos_x += self.facing_dir * 18.0
                self.animator.current_frames = 1.0
                self._spawn_melee_slash(
                    active_hitboxes,
                    vfx_group,
                    forward_offset=42.0,
                    vertical_offset=-50.0,
                    width=96,
                    height=78,
                    damage=15,
                    duration=0.16,
                    color_outer=(50, 160, 255),
                )

            elif self.combo_step == 1 and self.state_timer >= slash2_time:
                self.combo_step = 2
                self._clear_melee_hitbox()
                self.face_target()
                self.pos_x += self.facing_dir * 24.0
                self.animator.current_frames = 2.0
                self._spawn_melee_slash(
                    active_hitboxes,
                    vfx_group,
                    forward_offset=48.0,
                    vertical_offset=-52.0,
                    width=112,
                    height=86,
                    damage=20,
                    duration=0.17,
                    color_outer=(120, 90, 255),
                )

        elif self.state_timer < recovery_end:
            if self.attack_phase != AttackPhase.RECOVERY:
                self.attack_phase = AttackPhase.RECOVERY
                self._clear_melee_hitbox()
                self.animator.current_frames = 3.0
        else:
            self._clear_melee_hitbox()
            self.skill_cooldowns[BossState.ATTACK_1] = 1.4
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.55)

    def _update_attack_2(self, dt, active_hitboxes, vfx_group, map_width):
        windup_end = 0.38
        active_end = 0.64
        recovery_end = 1.00
        dash_speed = 760.0

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.dash_dir = self.facing_dir
            self.dash_start_x = self.pos_x
            self.animator.play("Dash")
            self.animator.current_frames = 0.0

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                hb_w, hb_h = 116, 72
                hb_cx = int(round(self.pos_x + self.dash_dir * 28.0))
                hb_cy = int(round(self.pos_y - 50.0))
                hb_rect = pygame.Rect(0, 0, hb_w, hb_h)
                hb_rect.center = (hb_cx, hb_cy)

                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=22,
                    knockback_x=self.dash_dir * 300.0,
                    lifetime=active_end - windup_end,
                    tag="boss_dash",
                )
                self.current_melee_hitbox = hb
                if active_hitboxes is not None:
                    active_hitboxes.append(hb)

                if vfx_group is not None:
                    vfx_group.add(
                        DashSlashVFX(
                            anchor_entity=self,
                            start_x=self.dash_start_x,
                            vertical_offset=-50.0,
                            forward_offset=28.0,
                            hitbox_w=hb_w,
                            hitbox_h=hb_h,
                            flip=self.flip,
                            duration=active_end - windup_end,
                            hitbox=hb,
                        )
                    )

            self.pos_x += self.dash_dir * dash_speed * dt
            self.pos_x = max(40.0, min(float(map_width - 40), self.pos_x))

        elif self.state_timer < recovery_end:
            if self.attack_phase != AttackPhase.RECOVERY:
                self.attack_phase = AttackPhase.RECOVERY
                self._clear_melee_hitbox()
                self.animator.play("Attack1")
                self.animator.current_frames = 3.0
        else:
            self._clear_melee_hitbox()
            self.skill_cooldowns[BossState.ATTACK_2] = 2.4
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.65)

    def _update_attack_3(self, dt, active_hitboxes, vfx_group):
        windup_end = 0.42
        active_end = 0.72
        recovery_end = 1.10

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                direction = self.facing_dir
                spawn_x = self.pos_x + direction * 44.0
                spawn_y = self.pos_y - 50.0
                self.animator.current_frames = 2.0

                wave_w, wave_h = 56, 92
                hb_rect = pygame.Rect(0, 0, wave_w - 8, wave_h - 10)
                hb_rect.center = (int(round(spawn_x)), int(round(spawn_y)))
                wave_hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=18,
                    knockback_x=direction * 240.0,
                    lifetime=1.35,
                    tag="boss_projectile",
                )
                if active_hitboxes is not None:
                    active_hitboxes.append(wave_hb)

                if vfx_group is not None:
                    wave_vfx = ProjectileWaveVFX(
                        x=spawn_x,
                        y=spawn_y,
                        direction=direction,
                        speed=540.0,
                        width=wave_w,
                        height=wave_h,
                        duration=1.35,
                        hitbox=wave_hb,
                    )
                    vfx_group.add(wave_vfx)

                    if self.target and self.target.alive():
                        target_ground_y = int(round(self.target.pos_y))
                        aoe_vfx = GroundShockwaveVFX(
                            target_x=self.target.pos_x,
                            ground_y=target_ground_y,
                            radius=64,
                            windup_time=0.45,
                            active_time=0.26,
                            recovery_time=0.18,
                            damage=20,
                            hitbox_list=active_hitboxes,
                        )
                        vfx_group.add(aoe_vfx)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
            self.animator.current_frames = 3.0
        else:
            self.skill_cooldowns[BossState.ATTACK_3] = 3.2
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def _spawn_melee_slash(
        self,
        active_hitboxes,
        vfx_group,
        forward_offset=44.0,
        vertical_offset=-52.0,
        width=96,
        height=78,
        damage=15,
        duration=0.16,
        color_outer=(50, 160, 255),
    ):
        cx = int(round(self.pos_x + self.facing_dir * forward_offset))
        cy = int(round(self.pos_y + vertical_offset))
        hb_rect = pygame.Rect(0, 0, width - 8, height - 8)
        hb_rect.center = (cx, cy)

        kb = self.facing_dir * 240.0
        hb = Hitbox(
            owner="boss",
            rect=hb_rect,
            damage=damage,
            knockback_x=kb,
            lifetime=duration,
            tag="boss_melee",
        )
        self.current_melee_hitbox = hb
        if active_hitboxes is not None:
            active_hitboxes.append(hb)

        if vfx_group is not None:
            slash_vfx = SlashVFX(
                anchor_entity=self,
                forward_offset=forward_offset,
                vertical_offset=vertical_offset,
                width=width,
                height=height,
                flip=self.flip,
                duration=duration,
                color_outer=color_outer,
                color_inner=(230, 250, 255),
                hitbox=hb,
            )
            vfx_group.add(slash_vfx)

    def on_parried(self):
        self._clear_melee_hitbox()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = 0.68

    def be_attacked(self, damage=12):
        if self.hit_invuln_timer <= 0.0 and self.boss_health > 0:
            self.boss_health = max(0, round(self.boss_health - damage, 2))
            self.hit_flash_timer = 0.25
            self.hit_invuln_timer = 0.18
            if self.boss_health <= 0:
                self._clear_melee_hitbox()
                self.kill()

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        # 1. Update timers
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

        has_target = bool(self.target and self.target.alive())
        player_x = self.target.pos_x if has_target else self.pos_x
        distance = abs(self.pos_x - player_x)

        old_pos_x = self.pos_x

        # 2. FSM State Behavior & Vertical Chase AI
        if self.state == BossState.COOLDOWN:
            if self.state_timer >= self.cooldown_duration:
                self.change_state(BossState.IDLE)

        elif self.state == BossState.IDLE:
            self.face_target()
            if self.state_timer >= 0.15:
                self.decide_next_action(distance)

        elif self.state == BossState.CHASE:
            self.face_target()
            move_dir = -1 if self.pos_x > player_x else 1
            self.pos_x += move_dir * self.boss_speed * dt
            self.pos_x = max(40.0, min(float(map_width - 40), self.pos_x))

            # AI Jump & Platform Chase Conditions:
            if has_target and self.on_ground:
                player_hb = getattr(
                    self.target, "collision_rect", self.target.hurtbox
                )
                # (a) Elevation Chase: Player is significantly higher than Boss
                if (
                    player_hb.bottom < self.collision_rect.top - 20
                    and distance <= 340.0
                    and self.jump_cooldown <= 0.0
                ):
                    self.jump()

                # (b) Drop-Through Chase: Boss is on a one-way platform and Player is below
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

                # (c) Gap Ahead Detection: Jump across floor gaps while chasing
                elif (
                    self.jump_cooldown <= 0.0
                    and distance > 85.0
                    and self.game_map is not None
                    and hasattr(self.game_map, "has_ground_ahead")
                ):
                    if not self.game_map.has_ground_ahead(
                        self.collision_rect, move_dir
                    ):
                        self.jump()

            self.decide_next_action(distance)

        elif self.state == BossState.ATTACK_1:
            self._update_attack_1(dt, active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_2:
            self._update_attack_2(dt, active_hitboxes, vfx_group, map_width)

        elif self.state == BossState.ATTACK_3:
            self._update_attack_3(dt, active_hitboxes, vfx_group)

        # 3. Unconditional Per-Frame Gravity & Map Collision Resolution
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

            # (d) Obstacle Vaulting: If blocked horizontally by a wall/step while chasing on ground, jump over it!
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

        # 4. Animation Frame Update
        anim_state = self.animator.current_state or "idle"
        current_fspeed = self.animation_speed.get(anim_state, 0.12)
        dt_scale = dt * 60.0
        if self.attack_phase == AttackPhase.WINDUP:
            dt_scale = 0.0

        self.image = self.animator.update_get_image(current_fspeed, dt_scale=dt_scale)

        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False).convert_alpha()

        # 5. Visual overlays (Wind-up telegraph & hit flash)
        if self.attack_phase == AttackPhase.WINDUP:
            pulse = int(abs(math.sin(self.state_timer * 22.0)) * 110)
            self.image = self.image.copy()
            if self.state == BossState.ATTACK_2:
                self.image.fill(
                    (pulse, int(pulse * 0.4), 0), special_flags=pygame.BLEND_RGB_ADD
                )
            elif self.state == BossState.ATTACK_3:
                self.image.fill(
                    (int(pulse * 0.6), 0, pulse), special_flags=pygame.BLEND_RGB_ADD
                )
            else:
                self.image.fill(
                    (0, int(pulse * 0.7), pulse), special_flags=pygame.BLEND_RGB_ADD
                )

        if self.hit_flash_timer > 0.0:
            if int(self.hit_flash_timer * 25) % 2 == 0:
                self.image = self.image.copy()
                self.image.fill((255, 40, 40), special_flags=pygame.BLEND_RGB_ADD)

        self.sync_boxes()
