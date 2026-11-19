import math
import pygame
from Settings import GROUND_Y
from VFX import (
    Hitbox,
    SlashVFX,
    DashSlashVFX,
    ProjectileWaveVFX,
    GroundShockwaveVFX,
)
from bosses.base_boss import BaseBoss, BossState, AttackPhase


class Vergil(BaseBoss):
    """
    Level 2 Boss — Vergil (Restored & Modularized):
    - Inherits full gravity, One-Way Platform landing/drop-through, Jump & Vertical Chase AI
      from BaseBoss.
    - Features 3 signature parryable sword attacks:
      1. ATTACK_1: Close-range 2-hit Iai Slash combo
      2. ATTACK_2: Mid-range High-Speed Dash Slash
      3. ATTACK_3: Ranged Dimension Wave + Ground Judgment Cut AoE
    """

    def __init__(self, target_player, start_x=640, ground_y=GROUND_Y, game_map=None):
        super().__init__(
            target_player=target_player,
            boss_name="VERGIL",
            start_x=start_x,
            ground_y=ground_y,
            game_map=game_map,
            max_hp=120,
            move_speed=225.0,
            collision_size=(42, 104),
            hurtbox_size=(36, 98),
        )

        self.dash_dir = -1
        self.dash_start_x = 0.0

        self.animation_speed = {
            "idle": 0.10,
            "Run": 0.165,
            "Dash": 0.22,
            "Attack1": 0.14,
        }
        self.sprite_offsets = {
            "idle": (9.5, 0.0),
            "Run": (14.0, 9.0),
            "Dash": (10.0, 1.0),
            "Attack1": (1.0, 0.0),
        }

        self.animator.load_animation("idle", "asset/Vergil/vergil_idle.png", 4, 0.11)
        self.animator.load_animation("Run", "asset/Vergil/vergil_run.png", 6, 0.12)
        self.animator.load_animation("Dash", "asset/Vergil/vergil_dash.png", 5, 0.58)
        self.animator.load_animation(
            "Attack1", "asset/Vergil/vergil_attack1.png", 4, 0.12
        )

        self.animator.play("idle")
        self.image = self.animator.update_get_image(self.animation_speed["idle"])
        self.sync_boxes()

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
        vertical_diff = (
            abs(self.target.pos_y - self.pos_y)
            if (self.target and self.target.alive())
            else 0.0
        )
        cd1 = self.skill_cooldowns[BossState.ATTACK_1] <= 0.0
        cd2 = self.skill_cooldowns[BossState.ATTACK_2] <= 0.0
        cd3 = self.skill_cooldowns[BossState.ATTACK_3] <= 0.0

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

    # ---------- Vergil 3 Signature Sword Attacks ----------

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
            tag="vergil_melee",
        )
        self.current_melee_hitbox = hb
        self.register_hitbox(hb, active_hitboxes)

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
        self.register_vfx(slash_vfx, vfx_group)

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
                    tag="vergil_dash",
                )
                self.current_melee_hitbox = hb
                self.register_hitbox(hb, active_hitboxes)

                dash_vfx = DashSlashVFX(
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
                self.register_vfx(dash_vfx, vfx_group)

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
                    tag="vergil_projectile",
                )
                self.register_hitbox(wave_hb, active_hitboxes)

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
                self.register_vfx(wave_vfx, vfx_group)

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
                    self.register_vfx(aoe_vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
            self.animator.current_frames = 3.0
        else:
            self.skill_cooldowns[BossState.ATTACK_3] = 3.2
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def on_parried(self):
        super().on_parried()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = 0.68

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        self._tick_common_timers(dt)

        has_target = bool(self.target and self.target.alive())
        player_x = self.target.pos_x if has_target else self.pos_x
        distance = abs(self.pos_x - player_x)
        old_pos_x = self.pos_x

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
            self.update_vertical_chase_ai(distance, move_dir)
            self.decide_next_action(distance)

        elif self.state == BossState.ATTACK_1:
            self._update_attack_1(dt, active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_2:
            self._update_attack_2(dt, active_hitboxes, vfx_group, map_width)

        elif self.state == BossState.ATTACK_3:
            self._update_attack_3(dt, active_hitboxes, vfx_group)

        # Unconditional gravity, map collisions, One-Way Platforms & obstacle vaulting
        self.apply_physics_and_collisions(dt, old_pos_x, map_width)

        # Animation frame update
        anim_state = self.animator.current_state or "idle"
        current_fspeed = self.animation_speed.get(anim_state, 0.12)
        dt_scale = 0.0 if self.attack_phase == AttackPhase.WINDUP else (dt * 60.0)
        self.image = self.animator.update_get_image(current_fspeed, dt_scale=dt_scale)

        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False).convert_alpha()

        # Wind-up telegraph & Hit Flash overlays
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
