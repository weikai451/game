import math
import random
import pygame
from Settings import GROUND_Y
from VFX import (
    BoneWaveVFX,
    HomingBoneVFX,
    GasterBlasterVFX,
    FloatingTextVFX,
    BlueSoulHeartVFX,
    GroundBoneTrapVFX,
    SansIntroVFX,
)
from audio_manager import get_audio
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
            max_hp=1,
            move_speed=215.0,
            collision_size=(42, 94),
            hurtbox_size=(38, 90),
        )

        self.animation_speed = {
            "idle": 0.09,
            "Run": 0.15,
            "Cast": 0.20,
            "Dodge": 0.28,
        }
        self.sprite_offsets = {
            "idle": (0.0, 0.0),
            "Run": (0.0, 0.0),
            "Cast": (0.0, 0.0),
            "Dodge": (0.0, 0.0),
        }

        # Undertale Sans 10-Dodge Stamina System & Afterimages
        self.max_stamina = 10
        self.stamina = 10
        self.dodge_timer = 0.0
        self.dodge_vel_x = 0.0
        self.dodge_afterimages = []
        self._afterimage_timer = 0.0
        self._last_vfx_group = None
        self._last_map_width = 1664
        self._wave_cycle = 0
        self._blaster_pattern_cycle = 0
        self.cooldown_scale = 0.85  # 15% shorter attack intervals (0.72 in Phase 2!)
        self.phase = 1
        self.phase2_triggered = False
        self.title_card_active = False
        self.title_card_timer = 0.0
        self.skill_cooldowns[BossState.ATTACK_4] = 2.0
        self.skill_cooldowns[BossState.ATTACK_5] = 3.2
        self.skill_cooldowns[BossState.SANS_ULTIMATE] = 0.0
        self.intro_duration = 4.0  # 2.0s zoom-in cutscene + 2.0s smooth pixel Title Card
        self.intro_progress = 0.0
        self.state = BossState.INTRO

        self.animator.load_animation("idle", "assets/sprites/sans/sans_idle.png", 4, 1.0)
        self.animator.load_animation("Run", "assets/sprites/sans/sans_move.png", 4, 1.0)
        self.animator.load_animation("Cast", "assets/sprites/sans/sans_cast.png", 4, 1.0)
        self.animator.load_animation(
            "Dodge", "assets/sprites/sans/sans_dodge.png", 4, 1.0
        )

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
            BossState.ATTACK_4,
            BossState.ATTACK_5,
            BossState.SANS_ULTIMATE,
        ):
            self.face_target()
            self.attack_phase = AttackPhase.WINDUP
            self.animator.play("Cast", force_reset=True)
        elif new_state == BossState.PHASE_2_TRANSITION:
            self.attack_phase = AttackPhase.NONE
            self.invincible = True
            self.animator.play("Cast", force_reset=True)
        elif new_state == BossState.INTRO:
            self.attack_phase = AttackPhase.NONE
            self.intro_progress = 0.0
            self.title_card_active = False
            self.animator.play("idle", force_reset=True)
        else:
            self.attack_phase = AttackPhase.NONE
            self.invincible = False
            if new_state == BossState.COOLDOWN:
                self.cooldown_duration = cooldown_duration * self.cooldown_scale
                self.animator.play("idle")
            elif new_state == BossState.IDLE:
                self.animator.play("idle")
            elif new_state == BossState.CHASE:
                self.animator.play("Run")

    def decide_next_action(self, distance):
        # Phase 2 Ultimate: 360-Degree Gaster Blaster Ring when off cooldown
        if (
            self.phase >= 2
            and self.skill_cooldowns.get(BossState.SANS_ULTIMATE, 0.0) <= 0.0
        ):
            self.change_state(BossState.SANS_ULTIMATE)
            return

        vertical_diff = (
            abs(self.target.pos_y - self.pos_y)
            if (self.target and self.target.alive())
            else 0.0
        )
        cd1 = self.skill_cooldowns[BossState.ATTACK_1] <= 0.0
        cd2 = self.skill_cooldowns[BossState.ATTACK_2] <= 0.0
        cd3 = self.skill_cooldowns[BossState.ATTACK_3] <= 0.0
        cd4 = self.skill_cooldowns.get(BossState.ATTACK_4, 0.0) <= 0.0
        cd5 = self.skill_cooldowns.get(BossState.ATTACK_5, 0.0) <= 0.0

        # Cross (+) / Diagonal (X) 4-Blaster Formation
        if cd5:
            self.change_state(BossState.ATTACK_5)
            return

        # Telekinesis Slam & Ground Bone Trap (works from any range when off cooldown)
        if cd4 and distance >= 120.0:
            self.change_state(BossState.ATTACK_4)
            return

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
                self._wave_cycle += 1
                is_blue_wave = (self._wave_cycle % 2 == 0)
                get_audio().play_sfx("bone_shoot")
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
                        cyan=is_blue_wave,
                        damage=1,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_1] = 2.0 * self.cooldown_scale
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
                        damage=1,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_2] = 2.6 * self.cooldown_scale
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
                    damage=1,
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
                    damage=1,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(b2, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_3] = 3.6 * self.cooldown_scale
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.80)

    def _pick_safe_telekinesis_landing(self, map_width):
        """
        Choose a guaranteed-safe landing coordinate (land_x, land_y) on either a
        One-Way Platform or a clear segment of the solid arena floor.
        """
        candidates = []
        if self.game_map is not None:
            for plat in getattr(self.game_map, "platforms", ()):
                if plat.width >= 160:
                    candidates.append((float(plat.centerx), float(plat.top)))

        floor_y = float(self.ground_y)
        min_x = 260.0
        max_x = max(min_x + 100.0, float(map_width) - 260.0)
        candidates.append((random.uniform(min_x, max_x), floor_y))
        candidates.append((random.uniform(min_x, max_x), floor_y))
        return random.choice(candidates)

    def _update_attack_4_telekinesis_slam(self, active_hitboxes, vfx_group, map_width):
        """
        Attack 4 — Telekinesis Slam & Ground Bone Trap (念力傳送摔落＋地面突刺骨頭):
        - WINDUP (0.0 .. 0.35s): Sans raises hand with blue eye flare.
        - ACTIVE (0.35s): Overlays Blue Soul Heart on Player, teleports Player above a safe
          floor/platform, slams them downward (vel_y = 680), and spawns a 0.52s Warning Zone
          followed by erupting sharp ground bones!
        """
        windup_end = 0.35
        active_end = 1.45
        recovery_end = 1.85

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                if self.target is not None and self.target.alive():
                    land_x, land_y = self._pick_safe_telekinesis_landing(map_width)

                    # Teleport player cleanly above the chosen safe surface & slam downward!
                    self.target.pos_x = float(land_x)
                    self.target.pos_y = max(140.0, float(land_y) - 125.0)
                    self.target.velocity_y = 680.0
                    self.target.on_ground = False
                    self.target.on_one_way_platform = False
                    self.target.sync_boxes()

                    self.pending_screen_shake = max(self.pending_screen_shake, 0.22)
                    get_audio().play_sfx("blue_soul_slam")

                    # Blue Soul Heart overlay on Player
                    heart_vfx = BlueSoulHeartVFX(self.target, duration=0.95)
                    self.register_vfx(heart_vfx, vfx_group)

                    # Warning Zone (0.52s) -> Sharp Ground Bone Trap (0.52s)
                    trap_vfx = GroundBoneTrapVFX(
                        center_x=land_x,
                        ground_y=land_y,
                        width=224,
                        bone_height=76,
                        warning_time=0.52,
                        active_time=0.52,
                        retract_time=0.18,
                        damage=1,
                        blue=False,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(trap_vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_4] = 5.4 * self.cooldown_scale
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def _update_attack_5_blaster_formation(self, active_hitboxes, vfx_group):
        """
        Attack 5 — Cross (+) & Diagonal (X) 4-Blaster Formations:
        Alternates between orthogonal Cross (+) and 45-degree Diagonal (X) 4-Blaster volleys
        converging through the player's position with synced rotated multi-segment Hitboxes!
        """
        windup_end = 0.36
        active_end = 1.25
        recovery_end = 1.60

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self._blaster_pattern_cycle += 1
                is_x_pattern = (self._blaster_pattern_cycle % 2 == 0)

                cx = (
                    float(self.target.hurtbox.centerx)
                    if (self.target and self.target.alive())
                    else self.pos_x + self.facing_dir * 200.0
                )
                cy = (
                    float(self.target.hurtbox.centery)
                    if (self.target and self.target.alive())
                    else self.pos_y - 40.0
                )

                angles_deg = (45, 135, 225, 315) if is_x_pattern else (0, 90, 180, 270)
                radius = 270.0
                for deg in angles_deg:
                    rad = math.radians(deg)
                    bx = cx + math.cos(rad) * radius
                    by = cy + math.sin(rad) * radius
                    blaster = GasterBlasterVFX(
                        x=bx,
                        y=by,
                        target_x=cx,
                        target_y=cy,
                        windup=0.70,
                        active_time=0.45,
                        recovery_time=0.25,
                        beam_length=580.0,
                        beam_width=36,
                        damage=1,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(blaster, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_5] = 4.8 * self.cooldown_scale
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def _trigger_phase_2(self, vfx_group=None):
        """Trigger Sans Phase 2 Awakening when Stamina drops to/below 50% (<= 5)."""
        self.phase = 2
        self.phase2_triggered = True
        self.cooldown_scale = 0.72
        self.clear_owned_attacks()
        self.change_state(BossState.PHASE_2_TRANSITION)
        self.pending_screen_shake = max(self.pending_screen_shake, 0.45)
        get_audio().play_sfx("blaster_charge")
        if vfx_group is not None:
            vfx_group.add(
                FloatingTextVFX(
                    self.pos_x,
                    self.hurtbox.top - 22,
                    text="GET DUNKED ON!",
                    color=(80, 235, 255),
                    outline_color=(10, 15, 35),
                    font_size=24,
                    duration=1.05,
                    rise_speed=42.0,
                )
            )

    def _update_phase_2_transition(self, dt, vfx_group):
        self.invincible = True
        self.velocity_y = 0.0
        if self.state_timer >= 0.95:
            self.invincible = False
            # Immediately unleash 360-Degree Gaster Blaster Ring as Phase 2 opener!
            self.change_state(BossState.SANS_ULTIMATE)

    def _update_sans_ultimate_360_blasters(self, active_hitboxes, vfx_group):
        """
        Sans Phase 2 Ultimate — 360-Degree Gaster Blaster Ring:
        Summons 10 Gaster Blasters in a 360-degree circle around the player in 2 staggered
        5-blaster waves (72-degree spacing, offset by 36 degrees) for intense weaving & parrying!
        """
        windup_end = 0.35
        active_end = 1.95
        recovery_end = 2.35

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self.pending_screen_shake = max(self.pending_screen_shake, 0.35)
                cx = (
                    float(self.target.hurtbox.centerx)
                    if (self.target and self.target.alive())
                    else self.pos_x
                )
                cy = (
                    float(self.target.hurtbox.centery)
                    if (self.target and self.target.alive())
                    else self.pos_y - 45.0
                )
                radius = 310.0

                # Wave A: 5 Blasters at 0, 72, 144, 216, 288 deg
                for i in range(5):
                    rad = math.radians(i * 72.0)
                    b = GasterBlasterVFX(
                        x=cx + math.cos(rad) * radius,
                        y=cy + math.sin(rad) * radius,
                        target_x=cx,
                        target_y=cy,
                        windup=0.68,
                        active_time=0.42,
                        recovery_time=0.25,
                        beam_length=640.0,
                        beam_width=34,
                        damage=1,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(b, vfx_group)

                # Wave B: 5 staggered Blasters at 36, 108, 180, 252, 324 deg (delayed 0.58s)
                for i in range(5):
                    rad = math.radians(36.0 + i * 72.0)
                    b = GasterBlasterVFX(
                        x=cx + math.cos(rad) * radius,
                        y=cy + math.sin(rad) * radius,
                        target_x=cx,
                        target_y=cy,
                        windup=1.26,
                        active_time=0.42,
                        recovery_time=0.25,
                        beam_length=640.0,
                        beam_width=34,
                        damage=1,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(b, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.SANS_ULTIMATE] = 9.5 * self.cooldown_scale
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def _spawn_dodge_afterimage(self, alpha=165.0):
        if self.image is None:
            return
        ghost = self.image.copy()
        ghost.fill((40, 215, 255), special_flags=pygame.BLEND_RGB_ADD)
        self.dodge_afterimages.append([ghost, self.rect.copy(), float(alpha)])

    def take_damage(self, damage=12):
        """
        Undertale Sans 10-Dodge Stamina Mechanic:
        - While stamina > 0: dodges the attack with zero HP loss, consumes 1 stamina,
          slides sideways with cyan afterimages, and floats pixel-art 'MISS' above head.
        - Once stamina == 0: the very next hit lands fatally on Sans's 1 HP!
        """
        if self.invincible or self.hit_invuln_timer > 0.0 or self.hp <= 0.0:
            return

        if self.stamina > 0:
            self.stamina = max(0, self.stamina - 1)
            self.hit_invuln_timer = 0.24
            self.dodge_timer = 0.34
            self._afterimage_timer = 0.0

            # Dodge away from player; reverse direction if near arena boundary walls
            if self.target is not None:
                dodge_dir = 1 if self.pos_x >= self.target.pos_x else -1
            else:
                dodge_dir = -self.facing_dir

            if dodge_dir < 0 and self.pos_x < 220.0:
                dodge_dir = 1
            elif dodge_dir > 0 and self.pos_x > self._last_map_width - 220.0:
                dodge_dir = -1

            self.dodge_vel_x = dodge_dir * 490.0
            self._spawn_dodge_afterimage(alpha=185.0)
            self.animator.play("Dodge", force_reset=True)
            get_audio().play_sfx("sans_dodge")

            if self._last_vfx_group is not None:
                self._last_vfx_group.add(
                    FloatingTextVFX(
                        self.pos_x,
                        self.hurtbox.top - 12,
                        text="MISS",
                        color=(255, 255, 255),
                        outline_color=(15, 15, 28),
                        font_size=26,
                        duration=0.85,
                        rise_speed=58.0,
                    )
                )
            return

        # Stamina exhausted (0/10): fatal hit on 1 HP!
        super().take_damage(damage)

    def reset(self):
        self.stamina = self.max_stamina
        self.phase = 1
        self.phase2_triggered = False
        self.cooldown_scale = 0.85
        self.title_card_active = False
        self.dodge_timer = 0.0
        self.dodge_vel_x = 0.0
        self.dodge_afterimages.clear()
        super().reset()
        self.skill_cooldowns[BossState.SANS_ULTIMATE] = 0.0

    def draw_extras(self, surface, camera_x=0, camera_y=0):
        """Render translucent cyan dodge afterimages + persistent Phase 2 cyan/gold eye flame."""
        for ghost, rect, alpha in self.dodge_afterimages:
            if alpha > 8:
                img = ghost.copy()
                img.set_alpha(int(alpha))
                surface.blit(img, rect.move(-camera_x, -camera_y))

        if self.phase >= 2 and self.alive():
            t = pygame.time.get_ticks() * 0.001
            ex = int(round(self.pos_x + self.facing_dir * 6.0 - camera_x))
            ey = int(round(self.pos_y - 74.0 - camera_y))
            col = (55, 235, 255) if int(t * 16.0) % 2 == 0 else (255, 225, 55)
            flame_h = int(12 + 6 * abs(math.sin(t * 22.0)))
            pygame.draw.circle(surface, col, (ex, ey), 5)
            pygame.draw.line(surface, col, (ex, ey), (ex - self.facing_dir * 8, ey - flame_h), 3)
            pygame.draw.circle(surface, (245, 255, 255), (ex, ey), 2)

    def on_parried(self):
        super().on_parried()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2, BossState.ATTACK_3):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = max(self.state_timer, 0.95)

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        self._last_vfx_group = vfx_group
        self._last_map_width = map_width
        self._tick_common_timers(dt)

        # Fade out dodge afterimages
        self.dodge_afterimages = [
            [g, r, a - 460.0 * dt]
            for (g, r, a) in self.dodge_afterimages
            if a - 460.0 * dt > 10.0
        ]

        # Trigger Phase 2 awakening once dodge stamina drops to/below 50% (<= 5)
        if (
            not self.phase2_triggered
            and self.state != BossState.INTRO
            and self.hp > 0.0
            and self.stamina <= self.max_stamina * 0.5
        ):
            self._trigger_phase_2(vfx_group=vfx_group)

        has_target = bool(self.target and self.target.alive())
        player_x = self.target.pos_x if has_target else self.pos_x
        distance = abs(self.pos_x - player_x)
        old_pos_x = self.pos_x

        if self.state == BossState.INTRO:
            cutscene_end = 2.0
            if self.combo_step == 0:
                self.combo_step = 1
                self.face_target()
                get_audio().play_sfx("encounter")
                if vfx_group is not None:
                    vfx_group.add(SansIntroVFX(self, duration=cutscene_end))
            elif self.combo_step == 1 and self.state_timer >= cutscene_end:
                # Begin smooth 2.0s pixel Title Card fade-in ('The weakest ?' -> 'Sans')
                self.combo_step = 2
                self.title_card_active = True
                self.title_card_timer = 0.0
            elif self.combo_step == 2 and self.state_timer >= cutscene_end + 0.60:
                # Heavy impact SFX + micro screen shake when huge 'Sans' reveals!
                self.combo_step = 3
                self.pending_screen_shake = max(self.pending_screen_shake, 0.18)
                get_audio().play_sfx("jce_shatter")

            if self.state_timer < cutscene_end:
                self.intro_progress = min(0.85, (self.state_timer / cutscene_end) * 0.85)
                self.title_card_timer = 0.0
            else:
                self.title_card_timer = self.state_timer - cutscene_end
                # Smoothly expand Boss HP/Stamina bar as the white card fades out (1.70..2.00s)
                if self.title_card_timer >= 1.70:
                    self.intro_progress = min(1.0, (self.title_card_timer - 1.70) / 0.30)
                else:
                    self.intro_progress = 0.0

            if self.state_timer >= self.intro_duration:
                self.title_card_active = False
                self.title_card_timer = 0.0
                self.intro_progress = 1.0
                self.change_state(BossState.IDLE)
        elif self.state == BossState.PHASE_2_TRANSITION:
            self._update_phase_2_transition(dt, vfx_group)
        elif self.state == BossState.SANS_ULTIMATE:
            self._update_sans_ultimate_360_blasters(active_hitboxes, vfx_group)
        elif self.dodge_timer > 0.0:
            self.dodge_timer = max(0.0, self.dodge_timer - dt)
            self.pos_x += self.dodge_vel_x * dt
            self.pos_x = max(120.0, min(float(map_width - 120), self.pos_x))
            self.dodge_vel_x *= max(0.0, 1.0 - 7.0 * dt)
            self._afterimage_timer += dt
            if self._afterimage_timer >= 0.08:
                self._afterimage_timer = 0.0
                self._spawn_dodge_afterimage(alpha=155.0)
            if self.dodge_timer <= 0.0:
                self.dodge_vel_x = 0.0
                self.animator.play(
                    "Cast"
                    if self.state in (BossState.ATTACK_1, BossState.ATTACK_2, BossState.ATTACK_3)
                    else ("Run" if self.state == BossState.CHASE else "idle")
                )
        elif self.state == BossState.COOLDOWN:
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

        elif self.state == BossState.ATTACK_4:
            self._update_attack_4_telekinesis_slam(
                active_hitboxes, vfx_group, map_width
            )

        elif self.state == BossState.ATTACK_5:
            self._update_attack_5_blaster_formation(active_hitboxes, vfx_group)

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
