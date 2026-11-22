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

        # Undertale Sans 30-Dodge Stamina System & Afterimages
        # (< 20 triggers Teleport Bone Assault phase; <= 15 triggers 360° Gaster Blaster Ultimate!)
        self.max_stamina = 30
        self.stamina = 30
        self.dodge_timer = 0.0
        self.dodge_vel_x = 0.0
        self.dodge_afterimages = []
        self._afterimage_timer = 0.0
        self._last_vfx_group = None
        self._last_map_width = 1664
        self._wave_cycle = 0
        self._blaster_pattern_cycle = 0
        self.cooldown_scale = 0.85  # 15% shorter attack intervals (0.78 at <20, 0.70 at <=15!)
        self.phase = 1
        self.teleport_phase_unlocked = False
        self.phase2_triggered = False
        self.screen_blackout_timer = 0.0
        self._chain_tp_total = 4
        self._chain_tp_done = 0
        self._chain_tp_timer = 0.0
        self._chain_tp_interval = 0.85
        self._chain_tp_hover = False
        self.title_card_active = False
        self.title_card_timer = 0.0
        self.skill_cooldowns[BossState.ATTACK_4] = 2.0
        self.skill_cooldowns[BossState.ATTACK_5] = 3.2
        self.skill_cooldowns[BossState.ATTACK_6] = 0.0
        self.skill_cooldowns[BossState.SANS_ULTIMATE] = 0.0
        self.intro_duration = 4.0  # 2.0s zoom-in cutscene + 2.0s smooth pixel Title Card
        self.intro_progress = 0.0
        self.waiting_for_dialogue = False
        self.state = BossState.INTRO
        # Explicit arena horizontal bounds (prevent Telekinesis Slam / Dodge leaving Boss Arena!)
        default_w = float(getattr(game_map, "width", 1664)) if game_map is not None else 1664.0
        self.arena_left_x = 120.0
        self.arena_right_x = max(320.0, default_w - 120.0)

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
            BossState.ATTACK_6,
            BossState.SANS_ULTIMATE,
        ):
            self.face_target()
            self.attack_phase = AttackPhase.WINDUP
            self.animator.play("Cast", force_reset=True)
            if new_state == BossState.ATTACK_6:
                self._chain_tp_total = random.choice((3, 4))
                self._chain_tp_done = 0
                self._chain_tp_timer = 0.0
                self._chain_tp_interval = random.uniform(0.775, 0.925)
                self._chain_tp_hover = False
            # Phase 2 Dual-Skill Combo (60% chance, max 2 concurrent skills; Ultimate & Chain Teleport stay solo!)
            if (
                self.phase >= 2
                and new_state not in (BossState.SANS_ULTIMATE, BossState.ATTACK_6)
                and self.pending_secondary_skill is None
                and random.random() < 0.60
            ):
                pair_map = {
                    BossState.ATTACK_1: ("bone_barrage", "blaster_pair"),
                    BossState.ATTACK_2: ("bone_wave",),
                    BossState.ATTACK_3: ("bone_wave",),
                    BossState.ATTACK_4: ("x_blasters",),
                    BossState.ATTACK_5: ("bone_wave",),
                }
                choices = pair_map.get(new_state)
                if choices:
                    self.schedule_secondary_skill(
                        random.choice(choices), delay=random.uniform(0.22, 0.36)
                    )
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
        # Tier 2 Ultimate (<= 1/2 stamina): 360-Degree Gaster Blaster Ring when off cooldown
        if (
            self.phase2_triggered
            and self.skill_cooldowns.get(BossState.SANS_ULTIMATE, 0.0) <= 0.0
        ):
            self.change_state(BossState.SANS_ULTIMATE)
            return

        # Tier 1 Signature (< 2/3 stamina): Rapid Chain Teleportation & Bone Assault
        if (
            self.teleport_phase_unlocked
            and self.skill_cooldowns.get(BossState.ATTACK_6, 0.0) <= 0.0
        ):
            self.change_state(BossState.ATTACK_6)
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
        Choose a guaranteed-safe landing coordinate (land_x, land_y) strictly INSIDE
        the Boss Arena bounds ([arena_left_x, arena_right_x]) on either a Judgement Hall
        One-Way Platform or a clear segment of the arena floor.
        """
        left_bound = float(getattr(self, "arena_left_x", 120.0))
        right_bound = min(float(map_width) - 80.0, float(getattr(self, "arena_right_x", map_width - 120.0)))
        if right_bound - left_bound < 240.0:
            left_bound = max(120.0, self.pos_x - 360.0)
            right_bound = min(float(map_width) - 120.0, self.pos_x + 360.0)

        candidates = []
        if self.game_map is not None:
            for plat in getattr(self.game_map, "platforms", ()):
                if (
                    plat.width >= 160
                    and plat.left >= left_bound + 40.0
                    and plat.right <= right_bound - 40.0
                ):
                    candidates.append((float(plat.centerx), float(plat.top)))

        floor_y = float(self.ground_y)
        min_x = left_bound + 120.0
        max_x = max(min_x + 80.0, right_bound - 120.0)
        candidates.append((random.uniform(min_x, max_x), floor_y))
        candidates.append((random.uniform(min_x, max_x), floor_y))
        land_x, land_y = random.choice(candidates)
        land_x = max(left_bound + 80.0, min(right_bound - 80.0, land_x))
        return (land_x, land_y)

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

    def _trigger_teleport_phase(self, vfx_group=None):
        """
        Tier 1 Awakening when Stamina drops below 2/3 (< 20 out of 30):
        Intensifies cyan-gold eye flame, unlocks Dual-Skill Combos & Rapid Teleportation Bone Assault!
        """
        self.teleport_phase_unlocked = True
        self.phase = max(self.phase, 2)
        self.cooldown_scale = min(self.cooldown_scale, 0.78)
        self.screen_blackout_timer = max(self.screen_blackout_timer, 0.07)
        self.pending_screen_shake = max(self.pending_screen_shake, 0.30)
        get_audio().play_sfx("blaster_charge")
        if vfx_group is not None:
            vfx_group.add(
                FloatingTextVFX(
                    self.pos_x,
                    self.hurtbox.top - 22,
                    text="READY FOR THIS?",
                    color=(85, 240, 255),
                    outline_color=(10, 15, 35),
                    font_size=24,
                    duration=1.0,
                    rise_speed=44.0,
                )
            )
        self.change_state(BossState.ATTACK_6)

    def _pick_tactical_teleport_spot(self, step_idx, map_width):
        """Pick an in-arena tactical teleport position (behind player, platform, or mid-air)."""
        left_b = float(getattr(self, "arena_left_x", 120.0)) + 90.0
        right_b = min(float(map_width) - 90.0, float(getattr(self, "arena_right_x", map_width - 120.0)) - 90.0)
        if right_b <= left_b + 80.0:
            left_b, right_b = 140.0, max(260.0, float(map_width) - 140.0)

        px = self.target.pos_x if (self.target and self.target.alive()) else (left_b + right_b) * 0.5
        floor_y = float(self.ground_y)

        # Alternate: 0 -> behind player on ground, 1 -> elevated arena platform, 2 -> mid-air hover, 3 -> opposite flank
        mode = step_idx % 4
        if mode == 1 and self.game_map is not None:
            valid_plats = [
                p for p in getattr(self.game_map, "platforms", ())
                if p.width >= 140 and p.left >= left_b - 20.0 and p.right <= right_b + 20.0
            ]
            if valid_plats:
                plat = random.choice(valid_plats)
                return (float(plat.centerx), float(plat.top), False)

        if mode == 2:
            side = -1 if px > (left_b + right_b) * 0.5 else 1
            tx = max(left_b, min(right_b, px + side * random.uniform(210.0, 310.0)))
            return (tx, max(220.0, floor_y - 145.0), True)

        if mode == 0:
            p_face = 1 if getattr(self.target, "facing_right", True) else -1
            tx = px - p_face * random.uniform(170.0, 250.0)
            if tx < left_b or tx > right_b:
                tx = px + p_face * random.uniform(190.0, 270.0)
            return (max(left_b, min(right_b, tx)), floor_y, False)

        side = 1 if self.pos_x < px else -1
        tx = max(left_b, min(right_b, px + side * random.uniform(220.0, 320.0)))
        return (tx, floor_y, False)

    def _update_attack_6_chain_teleport_bones(self, dt, active_hitboxes, vfx_group, map_width):
        """
        Attack 6 — Rapid Teleportation & Bone Assault (連續傳送骨陣突襲):
        Executes 3~4 rapid blinks (0.62~0.74s apart) with brief 0.07s Undertale blackout cuts
        and synchronized high-density Bone Barrage / Blue-White Bone Wave / Ground Bone Wall!
        """
        if self._chain_tp_done < self._chain_tp_total:
            self.attack_phase = AttackPhase.ACTIVE
            self._chain_tp_timer -= dt
            if self._chain_tp_timer <= 0.0:
                step = self._chain_tp_done
                self._chain_tp_done += 1
                self._chain_tp_timer = self._chain_tp_interval

                # Leave cyan ghost at old spot & fire 0.07s Undertale-style instant black-frame cut!
                self._spawn_dodge_afterimage(alpha=205.0)
                self.screen_blackout_timer = 0.07
                self.pending_screen_shake = max(self.pending_screen_shake, 0.12)
                get_audio().play_sfx("sans_dodge")
                get_audio().play_sfx("vergil_teleport")

                nx, ny, hover = self._pick_tactical_teleport_spot(step, map_width)
                self.pos_x = nx
                self.pos_y = ny
                self.velocity_y = 0.0
                self._chain_tp_hover = hover
                self.face_target()
                self.sync_boxes()
                self.animator.play("Cast", force_reset=True)

                tx = float(self.target.hurtbox.centerx) if (self.target and self.target.alive()) else self.pos_x + self.facing_dir * 200.0
                ty = float(self.target.hurtbox.centery) if (self.target and self.target.alive()) else self.pos_y - 40.0
                f_dir = self.facing_dir

                # Synchronized high-density bone assault per blink
                pattern = step % 3
                if pattern == 0:
                    # 4-bone mixed cyan/white homing fan
                    offsets = [(-f_dir * 32, -108), (f_dir * 16, -124), (f_dir * 54, -84), (-f_dir * 12, -62)]
                    for idx, (ox, oy) in enumerate(offsets):
                        vfx = HomingBoneVFX(
                            x=self.pos_x + ox,
                            y=self.pos_y + oy,
                            target_x=tx,
                            target_y=ty,
                            windup=0.22 + idx * 0.09,
                            speed=610.0,
                            duration=1.25,
                            cyan=(idx % 2 == 1),
                            damage=1,
                            hitbox_list=active_hitboxes,
                        )
                        self.register_vfx(vfx, vfx_group)
                elif pattern == 1:
                    # Mixed Blue + White bone wave pincer across arena floor
                    get_audio().play_sfx("bone_shoot")
                    floor_y = float(self.ground_y)
                    for i, bh in enumerate((58, 78, 92, 76, 60)):
                        bx = self.pos_x + f_dir * (38.0 + i * 28.0)
                        vfx = BoneWaveVFX(
                            x=bx,
                            ground_y=floor_y,
                            height=bh,
                            direction=f_dir,
                            speed=275.0,
                            delay=i * 0.045,
                            duration=0.80,
                            cyan=(i % 2 == 1),
                            damage=1,
                            hitbox_list=active_hitboxes,
                        )
                        self.register_vfx(vfx, vfx_group)
                else:
                    # Vertical Ground Bone Wall erupting at player's feet + 2 aimed follow-up bones
                    get_audio().play_sfx("bone_shoot")
                    trap = GroundBoneTrapVFX(
                        center_x=tx,
                        ground_y=float(self.ground_y),
                        width=148,
                        bone_height=96,
                        warning_time=0.40,
                        active_time=0.42,
                        retract_time=0.18,
                        damage=1,
                        blue=False,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(trap, vfx_group)
                    for idx, (ox, oy) in enumerate(((f_dir * 40, -110), (-f_dir * 24, -85))):
                        vfx = HomingBoneVFX(
                            x=self.pos_x + ox,
                            y=self.pos_y + oy,
                            target_x=tx,
                            target_y=ty,
                            windup=0.26 + idx * 0.12,
                            speed=590.0,
                            duration=1.20,
                            cyan=(idx == 0),
                            damage=1,
                            hitbox_list=active_hitboxes,
                        )
                        self.register_vfx(vfx, vfx_group)
        else:
            self._chain_tp_timer -= dt
            self.attack_phase = AttackPhase.RECOVERY
            if self._chain_tp_timer <= 0.15:
                self._chain_tp_hover = False
            if self._chain_tp_timer <= 0.0:
                self._chain_tp_hover = False
                self.skill_cooldowns[BossState.ATTACK_6] = 6.5 * self.cooldown_scale
                self.change_state(BossState.COOLDOWN, cooldown_duration=0.65)

    def _trigger_phase_2(self, vfx_group=None):
        """Trigger Sans Phase 3 Final Awakening when Stamina drops to/below 1/3 (<= 10 out of 30)."""
        self.phase = 3
        self.teleport_phase_unlocked = True
        self.phase2_triggered = True
        self.cooldown_scale = 0.68
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
        self.teleport_phase_unlocked = False
        self.phase2_triggered = False
        self.screen_blackout_timer = 0.0
        self._chain_tp_hover = False
        self.cooldown_scale = 0.85
        self.title_card_active = False
        self.dodge_timer = 0.0
        self.dodge_vel_x = 0.0
        self.dodge_afterimages.clear()
        super().reset()
        self.skill_cooldowns[BossState.ATTACK_6] = 0.0
        self.skill_cooldowns[BossState.SANS_ULTIMATE] = 0.0

    def draw_extras(self, surface, camera_x=0, camera_y=0):
        """Render translucent cyan dodge afterimages + intensified cyan/gold eye flame (<20 stamina)."""
        for ghost, rect, alpha in self.dodge_afterimages:
            if alpha > 8:
                img = ghost.copy()
                img.set_alpha(int(alpha))
                surface.blit(img, rect.move(-camera_x, -camera_y))

        if (self.teleport_phase_unlocked or self.phase >= 2) and self.alive():
            t = pygame.time.get_ticks() * 0.001
            ex = int(round(self.pos_x + self.facing_dir * 6.0 - camera_x))
            ey = int(round(self.pos_y - 74.0 - camera_y))
            intense = self.phase2_triggered
            col = (55, 235, 255) if int(t * 18.0) % 2 == 0 else (255, 225, 55)
            outer_col = (255, 215, 65) if col[0] < 100 else (45, 225, 255)
            flame_h = int((18 if intense else 14) + 8 * abs(math.sin(t * 24.0)))
            # Multi-layered blazing cyan/gold eye trail
            pygame.draw.circle(surface, outer_col, (ex, ey), 7 if intense else 6)
            pygame.draw.line(
                surface, outer_col, (ex, ey), (ex - self.facing_dir * 13, ey - flame_h - 4), 4
            )
            pygame.draw.line(
                surface, col, (ex, ey), (ex - self.facing_dir * 9, ey - flame_h), 3
            )
            pygame.draw.circle(surface, (250, 255, 255), (ex, ey), 3)

    def on_parried(self):
        super().on_parried()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2, BossState.ATTACK_3):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = max(self.state_timer, 0.95)

    def _execute_secondary_skill(self, skill_id, active_hitboxes, vfx_group, map_width):
        """Phase 2 concurrent secondary skill launcher (runs alongside primary attack)."""
        if not self.alive() or self.state in (BossState.INTRO, BossState.PHASE_2_TRANSITION):
            return
        tx = (
            float(self.target.hurtbox.centerx)
            if (self.target and self.target.alive())
            else self.pos_x + self.facing_dir * 200.0
        )
        ty = (
            float(self.target.hurtbox.centery)
            if (self.target and self.target.alive())
            else self.pos_y - 40.0
        )
        f_dir = self.facing_dir

        if skill_id == "bone_wave":
            self._wave_cycle += 1
            is_blue = (self._wave_cycle % 2 == 0)
            get_audio().play_sfx("bone_shoot")
            for i, bh in enumerate((56, 74, 88, 72, 56)):
                bx = self.pos_x + f_dir * (40.0 + i * 30.0)
                vfx = BoneWaveVFX(
                    x=bx,
                    ground_y=self.pos_y,
                    height=bh,
                    direction=f_dir,
                    speed=255.0,
                    delay=i * 0.055,
                    duration=0.78,
                    cyan=is_blue,
                    damage=1,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(vfx, vfx_group)

        elif skill_id == "bone_barrage":
            offsets = [(-f_dir * 34, -108), (f_dir * 16, -126), (f_dir * 52, -92)]
            for idx, (ox, oy) in enumerate(offsets):
                vfx = HomingBoneVFX(
                    x=self.pos_x + ox,
                    y=self.pos_y + oy,
                    target_x=tx,
                    target_y=ty,
                    windup=0.34 + idx * 0.14,
                    speed=590.0,
                    duration=1.30,
                    cyan=(idx == 1),
                    damage=1,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(vfx, vfx_group)

        elif skill_id == "blaster_pair":
            for ox, oy, wu in ((f_dir * 72.0, -34.0, 0.62), (-f_dir * 150.0, -165.0, 0.88)):
                b = GasterBlasterVFX(
                    x=tx + ox,
                    y=ty + oy,
                    target_x=tx,
                    target_y=ty,
                    windup=wu,
                    active_time=0.42,
                    recovery_time=0.22,
                    beam_length=600.0,
                    beam_width=36,
                    damage=1,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(b, vfx_group)

        elif skill_id == "x_blasters":
            radius = 275.0
            for deg in (45, 135, 225, 315):
                rad = math.radians(deg)
                b = GasterBlasterVFX(
                    x=tx + math.cos(rad) * radius,
                    y=ty + math.sin(rad) * radius,
                    target_x=tx,
                    target_y=ty,
                    windup=0.74,
                    active_time=0.42,
                    recovery_time=0.22,
                    beam_length=580.0,
                    beam_width=34,
                    damage=1,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(b, vfx_group)

    def can_talk(self, player):
        """True when Sans is peacefully waiting and Player is close enough to press [E] Talk."""
        if not self.waiting_for_dialogue or not self.alive() or player is None or not player.alive():
            return False
        dx = abs(player.pos_x - self.pos_x)
        dy = abs(player.pos_y - self.pos_y)
        return dx <= 115.0 and dy <= 120.0

    def start_pre_battle_wait(self):
        """Hold Sans calmly in IDLE facing the player while waiting for [E] Talk or Pre-Boss Dialogue."""
        self.waiting_for_dialogue = True
        self.intro_progress = 0.0
        self.title_card_active = False
        self.state = BossState.IDLE
        self.state_timer = 0.0
        self.animator.play("idle", force_reset=True)

    def begin_intro_cutscene(self):
        """Immediately launch Sans's 1.40x Intro Cutscene -> Pixel Title Card -> Battle!"""
        self.waiting_for_dialogue = False
        self.change_state(BossState.INTRO)

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        self._last_vfx_group = vfx_group
        self._last_map_width = map_width
        self._tick_common_timers(dt)
        if self.waiting_for_dialogue:
            self.face_target()
            self.apply_physics_and_collisions(dt, self.pos_x, map_width)
            self.image = self.animator.update_get_image(
                self.animation_speed.get("idle", 0.09), dt_scale=dt * 60.0
            )
            if self.flip:
                self.image = pygame.transform.flip(self.image, True, False).convert_alpha()
            self.sync_boxes()
            return
        self.tick_secondary_skill(dt, active_hitboxes, vfx_group, map_width)

        # Fade out dodge afterimages
        self.dodge_afterimages = [
            [g, r, a - 460.0 * dt]
            for (g, r, a) in self.dodge_afterimages
            if a - 460.0 * dt > 10.0
        ]

        if self.screen_blackout_timer > 0.0:
            self.screen_blackout_timer = max(0.0, self.screen_blackout_timer - dt)

        # Tier 2 (Phase 2): Stamina <= 2/3 (<= 20 out of 30) -> Rapid Teleport Bone Assault & Dual-Skills!
        if (
            not self.teleport_phase_unlocked
            and self.state != BossState.INTRO
            and self.hp > 0.0
            and self.stamina <= 20
        ):
            self._trigger_teleport_phase(vfx_group=vfx_group)

        # Tier 3 (Phase 3 Final): Stamina <= 1/3 (<= 10 out of 30) -> 360° Gaster Blaster Ultimate!
        if (
            not self.phase2_triggered
            and self.state not in (BossState.INTRO, BossState.ATTACK_6)
            and self.hp > 0.0
            and self.stamina <= (self.max_stamina / 3.0)
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
            min_bx = max(120.0, float(getattr(self, "arena_left_x", 120.0)) + 40.0)
            max_bx = min(float(map_width - 120), float(getattr(self, "arena_right_x", map_width - 120)) - 40.0)
            self.pos_x = max(min_bx, min(max_bx, self.pos_x))
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
            min_bx = max(40.0, float(getattr(self, "arena_left_x", 40.0)) + 40.0)
            max_bx = min(float(map_width - 40), float(getattr(self, "arena_right_x", map_width - 40)) - 40.0)
            self.pos_x = max(min_bx, min(max_bx, self.pos_x))
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

        elif self.state == BossState.ATTACK_6:
            self._update_attack_6_chain_teleport_bones(
                dt, active_hitboxes, vfx_group, map_width
            )

        # Unconditional gravity, map collisions, One-Way Platforms & obstacle vaulting
        # (Suspend downward gravity while hovering mid-air during Chain Teleport Assault)
        if self.state == BossState.ATTACK_6 and self._chain_tp_hover:
            self.velocity_y = 0.0
        else:
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
