import math
import pygame
from Settings import GROUND_Y
from VFX import BoneWaveVFX, HomingBoneVFX, GasterBlasterVFX
from bosses.base_boss import BaseBoss, BossState, AttackPhase


class Sans(BaseBoss):
    """
    Level 1 Boss — Sans (Undertale Style):
    - Inherits full gravity, One-Way Platform landing/drop-through, Jump & Vertical Chase AI
      from BaseBoss.
    - Registers all Bone Wave, Homing Bone Barrage, and Gaster Blaster VFX through
      self.register_vfx() so every active Hitbox is seamlessly exposed via get_active_hitboxes()!
    """

    def __init__(self, target_player, start_x=640, ground_y=GROUND_Y, game_map=None):
        super().__init__(
            target_player=target_player,
            boss_name="SANS",
            start_x=start_x,
            ground_y=ground_y,
            game_map=game_map,
            max_hp=100,
            move_speed=215.0,
            collision_size=(42, 94),
            hurtbox_size=(38, 90),
        )

        self.animation_speed = {
            "idle": 0.09,
            "Run": 0.15,
            "Cast": 0.20,
        }
        self.sprite_offsets = {
            "idle": (0.0, 0.0),
            "Run": (0.0, 0.0),
            "Cast": (0.0, 0.0),
        }

        self.animator.load_animation("idle", "assets/sprites/sans/sans_idle.png", 4, 1.0)
        self.animator.load_animation("Run", "assets/sprites/sans/sans_move.png", 4, 1.0)
        self.animator.load_animation("Cast", "assets/sprites/sans/sans_cast.png", 4, 1.0)

        self.animator.play("idle")
        self.image = self.animator.update_get_image(self.animation_speed["idle"])
        self.sync_boxes()

    def change_state(self, new_state, cooldown_duration=0.60):
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
            self.animator.play("Cast", force_reset=True)
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
            if cd3 and distance >= 160.0:
                self.change_state(BossState.ATTACK_3)
                return
            if cd2 and distance >= 120.0:
                self.change_state(BossState.ATTACK_2)
                return
            self.change_state(BossState.CHASE)
            return

        if distance <= 210:
            if cd1:
                self.change_state(BossState.ATTACK_1)
                return
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return
            if cd3:
                self.change_state(BossState.ATTACK_3)
                return

        elif distance <= 380:
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return
            if cd3:
                self.change_state(BossState.ATTACK_3)
                return
            if cd1:
                self.change_state(BossState.ATTACK_1)
                return

        else:
            if cd3:
                self.change_state(BossState.ATTACK_3)
                return
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return

        if distance > 110 or vertical_diff > 30.0:
            self.change_state(BossState.CHASE)
        else:
            self.change_state(BossState.IDLE)

    # ---------- Sans 3 Signature Attacks (All Hitboxes Registered via register_vfx) ----------

    def _update_attack_1_bone_wave(self, active_hitboxes, vfx_group):
        """Attack 1 — Bone Wave (骨浪突襲)"""
        windup_end = 0.35
        active_end = 0.90
        recovery_end = 1.25

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                direction = self.facing_dir
                floor_y = self.pos_y
                heights = (52, 70, 86, 96, 82, 66, 54)
                for i, bh in enumerate(heights):
                    bx = self.pos_x + direction * (44.0 + i * 28.0)
                    vfx = BoneWaveVFX(
                        x=bx,
                        ground_y=floor_y,
                        height=bh,
                        direction=direction,
                        speed=245.0,
                        delay=i * 0.06,
                        duration=0.82,
                        cyan=(i % 3 == 1),
                        damage=14,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_1] = 2.0
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.60)

    def _update_attack_2_bone_barrage(self, active_hitboxes, vfx_group):
        """Attack 2 — Homing Bone Barrage (懸空骨頭齊射)"""
        windup_end = 0.38
        active_end = 0.95
        recovery_end = 1.30

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                tx = (
                    self.target.hurtbox.centerx
                    if (self.target and self.target.alive())
                    else self.pos_x + self.facing_dir * 200
                )
                ty = (
                    self.target.hurtbox.centery
                    if (self.target and self.target.alive())
                    else self.pos_y - 36
                )
                f_dir = self.facing_dir
                offsets = [
                    (-f_dir * 38, -110),
                    (f_dir * 12, -130),
                    (f_dir * 52, -96),
                    (-f_dir * 18, -72),
                ]
                for idx, (ox, oy) in enumerate(offsets):
                    vfx = HomingBoneVFX(
                        x=self.pos_x + ox,
                        y=self.pos_y + oy,
                        target_x=tx,
                        target_y=ty,
                        windup=0.35 + idx * 0.14,
                        speed=580.0,
                        duration=1.35,
                        cyan=(idx % 2 == 1),
                        damage=15,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_2] = 2.6
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.65)

    def _update_attack_3_gaster_blaster(self, active_hitboxes, vfx_group):
        """Attack 3 — Gaster Blaster Laser Beam (龍骨砲高能光束)"""
        windup_end = 0.40
        active_end = 1.15
        recovery_end = 1.55

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                tx = (
                    self.target.hurtbox.centerx
                    if (self.target and self.target.alive())
                    else self.pos_x + self.facing_dir * 220
                )
                ty = (
                    self.target.hurtbox.centery
                    if (self.target and self.target.alive())
                    else self.pos_y - 36
                )
                f_dir = self.facing_dir

                # Blaster 1: Horizontal/side-angled beam toward player
                b1 = GasterBlasterVFX(
                    x=self.pos_x + f_dir * 68.0,
                    y=ty - 28.0,
                    target_x=tx,
                    target_y=ty,
                    windup=0.62,
                    active_time=0.45,
                    recovery_time=0.25,
                    beam_length=640.0,
                    beam_width=40,
                    damage=22,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(b1, vfx_group)

                # Blaster 2: High overhead angled beam slightly delayed
                b2 = GasterBlasterVFX(
                    x=tx - f_dir * 160.0,
                    y=ty - 175.0,
                    target_x=tx,
                    target_y=ty,
                    windup=0.92,
                    active_time=0.45,
                    recovery_time=0.25,
                    beam_length=640.0,
                    beam_width=38,
                    damage=22,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(b2, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_3] = 3.6
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.80)

    def on_parried(self):
        super().on_parried()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2, BossState.ATTACK_3):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = max(self.state_timer, 0.95)

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
            self._update_attack_1_bone_wave(active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_2:
            self._update_attack_2_bone_barrage(active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_3:
            self._update_attack_3_gaster_blaster(active_hitboxes, vfx_group)

        # Unconditional gravity, map collisions, One-Way Platforms & obstacle vaulting
        self.apply_physics_and_collisions(dt, old_pos_x, map_width)

        # Animation frame update
        anim_state = self.animator.current_state or "idle"
        current_fspeed = self.animation_speed.get(anim_state, 0.10)
        self.image = self.animator.update_get_image(current_fspeed, dt_scale=dt * 60.0)
        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False).convert_alpha()

        # Telegraph & Hit Flash overlays
        if self.attack_phase == AttackPhase.WINDUP:
            pulse = int(abs(math.sin(self.state_timer * 24.0)) * 90)
            self.image = self.image.copy()
            self.image.fill(
                (0, int(pulse * 0.85), pulse), special_flags=pygame.BLEND_RGB_ADD
            )

        if self.hit_flash_timer > 0.0:
            if int(self.hit_flash_timer * 25) % 2 == 0:
                self.image = self.image.copy()
                self.image.fill((255, 40, 40), special_flags=pygame.BLEND_RGB_ADD)

        self.sync_boxes()
