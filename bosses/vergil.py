import math
import random
import pygame
from Settings import GROUND_Y
from VFX import (
    Hitbox,
    SlashVFX,
    DashSlashVFX,
    ProjectileWaveVFX,
    GroundShockwaveVFX,
    VergilAuraBurstVFX,
    JudgementCutEndVFX,
    VergilIntroRiftVFX,
    RisingSlashVFX,
    SingleJudgementCutVFX,
    SummonedSwordVFX,
)
from audio_manager import get_audio
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
            max_hp=200,
            move_speed=225.0,
            collision_size=(42, 104),
            hurtbox_size=(36, 98),
        )

        self.dash_dir = -1
        self.dash_start_x = 0.0
        self.base_speed = 225.0
        self.phase = 1
        self.phase2_triggered = False
        self.phase3_triggered = False
        self.jce_center = (float(start_x), float(ground_y - 75.0))
        self.jce_radius = 290
        self.afterimages = []
        self.trick_ripples = []
        self._last_vfx_group = None
        self._trick_step_timer = 0.0
        self._trick_slashes_left = 0
        self.title_card_active = False
        self.title_card_timer = 0.0
        self._death_alpha = 255.0
        self._death_slide_vx = 0.0
        self._death_exit_dir = 1
        self._death_rift_x = float(start_x)
        self._death_rift_scale = 0.0
        self._sheathe_glint_timer = 0.0
        self.skill_cooldowns[BossState.ATTACK_4] = 2.0
        self.skill_cooldowns[BossState.ATTACK_5] = 2.6
        self.skill_cooldowns[BossState.ATTACK_6] = 3.0
        self.skill_cooldowns[BossState.ATTACK_7] = 3.5
        self.skill_cooldowns[BossState.JUDGEMENT_CUT_END] = 0.0
        self.intro_duration = 4.10  # 2.00s rift step-out & sheathe + 2.10s Dimension-Slash Title Card
        self.intro_progress = 0.0
        self.title_card_active = False
        self.title_card_timer = 0.0
        self.title_card_style = "vergil"
        self.state = BossState.INTRO

        self.animation_speed = {
            "idle": 0.085,
            "Run": 0.13,
            "Dash": 0.24,
            "Attack1": 0.16,
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
            BossState.ATTACK_4,
            BossState.ATTACK_5,
            BossState.ATTACK_6,
            BossState.ATTACK_7,
            BossState.JUDGEMENT_CUT_END,
        ):
            self.face_target()
            self.attack_phase = AttackPhase.WINDUP
            if new_state in (BossState.ATTACK_1, BossState.ATTACK_4):
                self.animator.play("Attack1", force_reset=True)
            elif new_state in (BossState.ATTACK_2, BossState.ATTACK_7):
                self.dash_dir = self.facing_dir
                self.dash_start_x = self.pos_x
                self.animator.play("Dash", force_reset=True)
                if new_state == BossState.ATTACK_7:
                    self._trick_slashes_left = 3
                    self._trick_step_timer = 0.24
            elif new_state in (
                BossState.ATTACK_3,
                BossState.ATTACK_5,
                BossState.ATTACK_6,
                BossState.JUDGEMENT_CUT_END,
            ):
                self.animator.play("Attack1", force_reset=True)

            # Phase 2 & Phase 3 Dual-Skill Combo (max 2 concurrent skills; JCE & Rapid Trick stay solo!)
            dual_chance = 0.70 if self.phase >= 3 else 0.55
            if (
                self.phase >= 2
                and new_state not in (BossState.JUDGEMENT_CUT_END, BossState.ATTACK_7)
                and self.pending_secondary_skill is None
                and random.random() < dual_chance
            ):
                pair_map = {
                    BossState.ATTACK_1: ("mirage_blades", "single_jc"),
                    BossState.ATTACK_2: ("mirage_blades", "single_jc"),
                    BossState.ATTACK_3: ("mirage_blades",),
                    BossState.ATTACK_4: ("mirage_blades", "single_jc"),
                    BossState.ATTACK_5: ("mirage_blades",),
                    BossState.ATTACK_6: ("single_jc",),
                }
                choices = pair_map.get(new_state)
                if choices:
                    self.schedule_secondary_skill(
                        random.choice(choices), delay=random.uniform(0.16, 0.28)
                    )
        elif new_state == BossState.INTRO:
            self.attack_phase = AttackPhase.NONE
            self.intro_progress = 0.0
            self.title_card_active = False
            self.title_card_timer = 0.0
            self.animator.play("idle", force_reset=True)
        elif new_state == BossState.PHASE_2_TRANSITION:
            self.attack_phase = AttackPhase.NONE
            self.invincible = True
            self.animator.play("idle", force_reset=True)
        else:
            self.attack_phase = AttackPhase.NONE
            self.invincible = False
            if new_state == BossState.COOLDOWN:
                cd_mult = 0.68 if self.phase >= 3 else (0.84 if self.phase == 2 else 1.0)
                self.cooldown_duration = cooldown_duration * cd_mult
                self.animator.play("idle")
            elif new_state == BossState.IDLE:
                self.animator.play("idle")
            elif new_state == BossState.CHASE:
                self.animator.play("Run")

    def decide_next_action(self, distance):
        # Phase 3 Ultimate (<= 1/3 HP): Judgement Cut End in rotation!
        if (
            self.phase >= 3
            and self.skill_cooldowns.get(BossState.JUDGEMENT_CUT_END, 0.0) <= 0.0
        ):
            self.change_state(BossState.JUDGEMENT_CUT_END)
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
        # Phase 2+ unlocks Mirage Blades (ATTACK_6) and Rapid Trick Slash (ATTACK_7)!
        cd6 = self.phase >= 2 and self.skill_cooldowns.get(BossState.ATTACK_6, 0.0) <= 0.0
        cd7 = self.phase >= 2 and self.skill_cooldowns.get(BossState.ATTACK_7, 0.0) <= 0.0

        if cd7 and distance >= 130.0:
            self.change_state(BossState.ATTACK_7)
            return

        if vertical_diff > 65.0:
            if cd6 and distance >= 140.0:
                self.change_state(BossState.ATTACK_6)
                return
            if cd5 and distance >= 150.0:
                self.change_state(BossState.ATTACK_5)
                return
            if cd3 and distance >= 180.0:
                self.change_state(BossState.ATTACK_3)
                return
            self.change_state(BossState.CHASE)
            return

        if distance <= 105:
            if cd4:
                self.change_state(BossState.ATTACK_4)
                return
            if cd1:
                self.change_state(BossState.ATTACK_1)
                return
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return

        elif distance <= 285:
            if cd5:
                self.change_state(BossState.ATTACK_5)
                return
            if cd2:
                self.change_state(BossState.ATTACK_2)
                return
            if cd6:
                self.change_state(BossState.ATTACK_6)
                return
            if cd3 and distance >= 165:
                self.change_state(BossState.ATTACK_3)
                return

        else:
            if cd6:
                self.change_state(BossState.ATTACK_6)
                return
            if cd5:
                self.change_state(BossState.ATTACK_5)
                return
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

    def _spawn_afterimage(self, color=(55, 195, 255), alpha=180.0):
        if self.image is None:
            return
        ghost = self.image.copy()
        ghost.fill(color, special_flags=pygame.BLEND_RGB_ADD)
        self.afterimages.append([ghost, self.rect.copy(), float(alpha)])
        if len(self.afterimages) > 14:
            self.afterimages = self.afterimages[-14:]

    def _spawn_trick_ripple(self, x=None, y=None):
        rx = float(self.pos_x if x is None else x)
        ry = float((self.pos_y - 52.0) if y is None else y)
        self.trick_ripples.append([rx, ry, 14.0, 210.0])

    # ---------- Vergil Signature Sword Attacks ----------

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
        self._spawn_afterimage(color=(70, 200, 255), alpha=170.0)
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
        get_audio().play_sfx("yamato_slash")

        # Multi-layered Arc Slash: deep blue-violet outer halo + blazing cyan-white core!
        outer_halo = SlashVFX(
            anchor_entity=self,
            forward_offset=forward_offset + 4.0,
            vertical_offset=vertical_offset,
            width=int(width * 1.18),
            height=int(height * 1.15),
            flip=self.flip,
            duration=duration + 0.04,
            color_outer=(115, 70, 245),
            color_inner=color_outer,
            hitbox=None,
        )
        self.register_vfx(outer_halo, vfx_group)

        slash_vfx = SlashVFX(
            anchor_entity=self,
            forward_offset=forward_offset,
            vertical_offset=vertical_offset,
            width=width,
            height=height,
            flip=self.flip,
            duration=duration,
            color_outer=color_outer,
            color_inner=(240, 252, 255),
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
                    damage=9,
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
                    damage=12,
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
                    damage=13,
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
                    damage=11,
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
                        damage=12,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(aoe_vfx, vfx_group)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
            self.animator.current_frames = 3.0
        else:
            self.skill_cooldowns[BossState.ATTACK_3] = 3.2
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.75)

    def _update_attack_4_rising_slash(self, dt, active_hitboxes, vfx_group, map_width):
        """
        Attack A — Rising Slash (High Time Launcher + Airborne Follow-up):
        Slides in and sweeps upward with knockback_y = -650 to launch unblocked players high
        into the air, then leaps up for a quick airborne chase slash!
        """
        windup_end = 0.30
        followup_time = 0.54
        active_end = 0.76
        recovery_end = 1.08

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.pos_x += self.facing_dir * 260.0 * dt
            self.pos_x = max(60.0, min(float(map_width - 60), self.pos_x))
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0

        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self.face_target()
                self.animator.current_frames = 1.0
                # Upward Rising Slash with vertical launch knockback_y = -650!
                cx = int(round(self.pos_x + self.facing_dir * 40.0))
                cy = int(round(self.pos_y - 58.0))
                hb_rect = pygame.Rect(0, 0, 92, 108)
                hb_rect.center = (cx, cy)
                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=10,
                    knockback_x=self.facing_dir * 165.0,
                    knockback_y=-650.0,
                    lifetime=0.20,
                    tag="vergil_rising_slash",
                )
                self.current_melee_hitbox = hb
                self.register_hitbox(hb, active_hitboxes)
                vfx = RisingSlashVFX(
                    anchor_entity=self,
                    forward_offset=40.0,
                    vertical_offset=-58.0,
                    flip=self.flip,
                    duration=0.22,
                    hitbox=hb,
                )
                self.register_vfx(vfx, vfx_group)

            elif self.combo_step == 1 and self.state_timer >= followup_time:
                self.combo_step = 2
                self._clear_melee_hitbox()
                self.face_target()
                # Leap upward to pursue launched player with an aerial slash!
                if self.on_ground:
                    self.velocity_y = -520.0
                    self.on_ground = False
                self.pos_x += self.facing_dir * 28.0
                self.animator.current_frames = 2.0
                self._spawn_melee_slash(
                    active_hitboxes,
                    vfx_group,
                    forward_offset=44.0,
                    vertical_offset=-56.0,
                    width=106,
                    height=88,
                    damage=8,
                    duration=0.18,
                    color_outer=(95, 195, 255),
                )
                # Phase 3 enhanced aerial combo: fire 3 Mirage Blades during airborne follow-up!
                if self.phase >= 3:
                    self._execute_secondary_skill("mirage_blades", active_hitboxes, vfx_group, map_width)

        elif self.state_timer < recovery_end:
            if self.attack_phase != AttackPhase.RECOVERY:
                self.attack_phase = AttackPhase.RECOVERY
                self._clear_melee_hitbox()
                self.animator.current_frames = 3.0
        else:
            self._clear_melee_hitbox()
            self.skill_cooldowns[BossState.ATTACK_4] = 3.2 * (0.75 if self.phase >= 3 else 1.0)
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.60)

    def _update_attack_5_single_judgement_cut(self, active_hitboxes, vfx_group):
        """
        Attack B — Single Judgement Cut (Phase 1 & 2: 1 sphere; Phase 3: 3 consecutive rapid spheres!):
        Quick Yamato draw/sheathe spawning blue-violet spatial slash spheres directly at the player.
        """
        is_triple = self.phase >= 3
        windup_end = 0.30
        active_end = 1.25 if is_triple else 0.78
        recovery_end = 1.50 if is_triple else 1.05

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0
        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            fire_times = (0.30, 0.62, 0.94) if is_triple else (0.30,)
            if self.combo_step < len(fire_times) and self.state_timer >= fire_times[self.combo_step]:
                self.combo_step += 1
                self.face_target()
                self.animator.current_frames = 3.0
                self._sheathe_glint_timer = 0.16
                get_audio().play_sfx("sheathe")
                tx = (
                    self.target.hurtbox.centerx
                    if (self.target and self.target.alive())
                    else self.pos_x + self.facing_dir * 220.0
                )
                ty = (
                    self.target.hurtbox.centery
                    if (self.target and self.target.alive())
                    else self.pos_y - 45.0
                )
                vfx = SingleJudgementCutVFX(
                    x=tx,
                    y=ty,
                    radius=88,
                    windup_time=0.44,
                    active_time=0.26,
                    damage=10 if is_triple else 11,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(vfx, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_5] = 3.4 * (0.76 if self.phase >= 3 else 1.0)
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.60)

    def _update_attack_6_summoned_swords(self, active_hitboxes, vfx_group):
        """
        Attack C — Summoned Swords (Mirage Blades):
        Summons 4 glowing cyan Mirage Blades beside Vergil / above the player that fire sequentially.
        """
        windup_end = 0.30
        active_end = 0.85
        recovery_end = 1.15

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0
        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self.animator.current_frames = 2.0
                tx = (
                    self.target.hurtbox.centerx
                    if (self.target and self.target.alive())
                    else self.pos_x + self.facing_dir * 220.0
                )
                ty = (
                    self.target.hurtbox.centery
                    if (self.target and self.target.alive())
                    else self.pos_y - 45.0
                )
                f_dir = self.facing_dir
                spawns = [
                    (self.pos_x - f_dir * 28.0, self.pos_y - 108.0),
                    (self.pos_x + f_dir * 22.0, self.pos_y - 130.0),
                    (tx - f_dir * 120.0, ty - 155.0),
                    (tx + f_dir * 40.0, ty - 175.0),
                ]
                for i, (sx, sy) in enumerate(spawns):
                    sword = SummonedSwordVFX(
                        x=sx,
                        y=sy,
                        target_x=tx,
                        target_y=ty,
                        windup=0.38 + i * 0.14,
                        speed=680.0,
                        duration=1.25,
                        damage=7,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(sword, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_6] = 4.0
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.65)

    def _update_attack_7_rapid_trick_slash(self, dt, active_hitboxes, vfx_group, map_width):
        """
        Phase 2+ Signature — Rapid Dark Slayer Trick Slash (高速連續瞬移斬):
        Teleports behind/beside the player 3 times with cyan afterimages & spatial ripples,
        delivering crisp Iaido arc slashes from alternating angles!
        """
        self._trick_step_timer -= dt
        if self._trick_slashes_left > 0:
            self.attack_phase = AttackPhase.ACTIVE
            if self._trick_step_timer <= 0.0:
                self._trick_slashes_left -= 1
                self._trick_step_timer = 0.36 if self.phase >= 3 else 0.44
                self._clear_melee_hitbox()

                # Leave Dark Slayer afterimage + ripple at old location
                self._spawn_afterimage(color=(55, 195, 255), alpha=210.0)
                self._spawn_trick_ripple(self.pos_x, self.pos_y - 52.0)
                get_audio().play_sfx("vergil_teleport")

                px = self.target.pos_x if (self.target and self.target.alive()) else self.pos_x
                side = -1 if (self._trick_slashes_left % 2 == 0) else 1
                nx = max(90.0, min(float(map_width - 90), px + side * 86.0))
                self.pos_x = nx
                self.velocity_y = 0.0
                self.face_target()
                self.sync_boxes()
                self._spawn_trick_ripple(self.pos_x, self.pos_y - 52.0)

                self.animator.play("Attack1", force_reset=True)
                self.animator.current_frames = 1.0 if (self._trick_slashes_left % 2 == 1) else 2.0
                self._spawn_melee_slash(
                    active_hitboxes,
                    vfx_group,
                    forward_offset=46.0,
                    vertical_offset=-52.0,
                    width=108,
                    height=84,
                    damage=9,
                    duration=0.16,
                    color_outer=(80, 185, 255) if self._trick_slashes_left > 0 else (140, 85, 255),
                )
        else:
            self.attack_phase = AttackPhase.RECOVERY
            if self._trick_step_timer <= 0.0:
                self._clear_melee_hitbox()
                self.skill_cooldowns[BossState.ATTACK_7] = 5.4 * (0.76 if self.phase >= 3 else 1.0)
                self.change_state(BossState.COOLDOWN, cooldown_duration=0.60)

    def _trigger_phase_2(self, vfx_group=None):
        """Phase 2 (<= 2/3 HP, <= 133): Blue-violet aura burst, unlocks Mirage Blades, Rapid Trick Slash & Dual-Skills!"""
        self.phase = 2
        self.phase2_triggered = True
        self.boss_speed = 255.0
        self.pending_screen_shake = max(self.pending_screen_shake, 0.35)
        get_audio().play_sfx("vergil_teleport")
        if vfx_group is not None:
            vfx_group.add(
                VergilAuraBurstVFX(self.pos_x, self.pos_y - 52.0, duration=0.85)
            )
        self.change_state(BossState.ATTACK_7)

    def _trigger_phase_3(self, vfx_group=None):
        """Phase 3 (<= 1/3 HP, <= 66 — Sin Devil Trigger): Force-interrupts into invincible awakening -> Judgement Cut End!"""
        self.phase = 3
        self.phase2_triggered = True
        self.phase3_triggered = True
        self.boss_speed = 285.0
        self.clear_owned_attacks()
        self.change_state(BossState.PHASE_2_TRANSITION)
        self.pending_screen_shake = max(self.pending_screen_shake, 0.50)
        if vfx_group is not None:
            vfx_group.add(
                VergilAuraBurstVFX(self.pos_x, self.pos_y - 52.0, duration=1.0)
            )

    def _update_phase_2_transition(self, dt, vfx_group):
        self.invincible = True
        self.velocity_y = 0.0
        if self.combo_step == 0:
            self.combo_step = 1
            if vfx_group is not None:
                vfx_group.add(
                    VergilAuraBurstVFX(self.pos_x, self.pos_y - 52.0, duration=1.0)
                )
        if self.state_timer >= 1.0:
            self.invincible = False
            # Immediately unleash Judgement Cut End as the Phase 3 Sin Devil Trigger opener!
            self.change_state(BossState.JUDGEMENT_CUT_END)

    def _spawn_jce_sphere_hitbox(self, active_hitboxes, damage, lifetime, tag):
        cx, cy = self.jce_center
        hb_w = int(self.jce_radius * 1.65)
        hb_h = int(self.jce_radius * 1.50)
        hb_rect = pygame.Rect(0, 0, hb_w, hb_h)
        hb_rect.center = (int(round(cx)), int(round(cy)))
        kb = 260.0 if (self.target and self.target.pos_x >= cx) else -260.0
        hb = Hitbox(
            owner="boss",
            rect=hb_rect,
            damage=damage,
            knockback_x=kb,
            lifetime=lifetime,
            tag=tag,
        )
        self.register_hitbox(hb, active_hitboxes)

    def _update_judgement_cut_end(self, dt, active_hitboxes, vfx_group, map_width):
        """
        DMC5 Judgement Cut End:
        - 0.00 .. 1.15s: Teleport to arena center, Yamato sheathe charge + Dimensional Sphere warning.
        - 1.15 .. 2.35s: Full-screen space shatter + 3 rhythmic parryable Dimensional Sphere slash waves.
        - 2.35 .. 2.75s: Yamato sheathe click + Final Spatial Shatter detonation + heavy screen shake.
        - 2.75 .. 3.45s: Recovery window.
        """
        windup_end = 1.15
        slash_end = 2.35
        shatter_end = 2.75
        recovery_end = 3.45

        if self.combo_step == 0:
            self.combo_step = 1
            # Teleport to arena center for dramatic full-stage Dimensional Sphere
            center_x = max(240.0, min(float(map_width - 240), float(map_width) * 0.5))
            self.pos_x = center_x
            self.velocity_y = 0.0
            self.face_target()
            self.jce_center = (self.pos_x, self.pos_y - 80.0)
            self.pending_screen_shake = max(self.pending_screen_shake, 0.18)
            get_audio().play_sfx("vergil_teleport")

            jce_vfx = JudgementCutEndVFX(
                center_x=self.jce_center[0],
                center_y=self.jce_center[1],
                radius=self.jce_radius,
                windup_time=windup_end,
                slash_duration=slash_end - windup_end,
                shatter_duration=shatter_end - slash_end,
            )
            self.register_vfx(jce_vfx, vfx_group)

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0

        elif self.state_timer < slash_end:
            self.attack_phase = AttackPhase.ACTIVE
            self.animator.play("Attack1")
            self.animator.current_frames = 2.0

            # 3 rhythmic slash waves inside the Dimensional Sphere (each parryable!)
            if self.combo_step == 1 and self.state_timer >= 1.15:
                self.combo_step = 2
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=8, lifetime=0.22, tag="vergil_jce_slash"
                )
                self.pending_screen_shake = max(self.pending_screen_shake, 0.22)
            elif self.combo_step == 2 and self.state_timer >= 1.55:
                self.combo_step = 3
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=8, lifetime=0.22, tag="vergil_jce_slash"
                )
            elif self.combo_step == 3 and self.state_timer >= 1.95:
                self.combo_step = 4
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=8, lifetime=0.22, tag="vergil_jce_slash"
                )

        elif self.state_timer < shatter_end:
            self.attack_phase = AttackPhase.ACTIVE
            self.animator.play("Attack1")
            self.animator.current_frames = 3.0
            if self.combo_step < 5:
                self.combo_step = 5
                # Yamato sheathe-click final spatial shatter detonation!
                get_audio().play_sfx("sheathe")
                get_audio().play_sfx("jce_shatter")
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=13, lifetime=0.24, tag="vergil_jce_finisher"
                )
                self.pending_screen_shake = max(self.pending_screen_shake, 0.55)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
            self.animator.play("idle")
        else:
            self.skill_cooldowns[BossState.JUDGEMENT_CUT_END] = 11.0
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.85)

    def begin_death_sequence(self):
        """DMC5-authentic Vergil defeat: knockback kneel on Yamato -> sheathe click -> walk into blue-violet rift."""
        super().begin_death_sequence()
        self.pending_death_hitstop = 0.16
        self.pending_screen_shake = max(self.pending_screen_shake, 0.35)
        self.title_card_active = False
        self.title_card_timer = 0.0
        self._death_alpha = 255.0
        p_x = self.target.pos_x if (self.target and self.target.alive()) else self.pos_x - 100.0
        push_dir = 1 if self.pos_x >= p_x else -1
        self._death_slide_vx = push_dir * 260.0
        self._death_exit_dir = push_dir
        self._death_rift_x = self.pos_x + push_dir * 96.0
        self._death_rift_scale = 0.0
        self.animator.play("idle", force_reset=True)
        get_audio().play_sfx("jce_shatter")
        if self._last_vfx_group is not None:
            self._last_vfx_group.add(VergilAuraBurstVFX(self.pos_x, self.pos_y - 52.0, duration=0.85))

    def _update_dying(self, dt, vfx_group, map_width):
        """
        4.40s DMC5 Vergil Defeat Cutscene:
        - 0.00 .. 0.55s: Knockback slide with cyan afterimages.
        - 0.55 .. 1.95s: Drops to one knee supported by Yamato planted in ground.
        - 1.95 .. 2.75s: Rises calmly, plays crisp Yamato sheathe-click + white hilt glint.
        - 2.75 .. 4.40s: Turns away, opens blue-violet vertical rift, walks inside & fades out as rift snaps shut.
        """
        t = self.state_timer
        old_x = self.pos_x

        if t < 0.55:
            self.pos_x += self._death_slide_vx * dt
            self._death_slide_vx *= max(0.0, 1.0 - 4.5 * dt)
            if int(t * 25.0) % 2 == 0:
                self._spawn_afterimage(color=(65, 195, 255), alpha=150.0)
        elif t < 1.95:
            self.face_target()
            self._death_rift_x = max(110.0, min(float(map_width - 110), self.pos_x + self._death_exit_dir * 78.0))
        elif t < 2.75:
            self.face_target()
            if self.combo_step == 0 and t >= 2.15:
                self.combo_step = 1
                self._sheathe_glint_timer = 0.28
                self.animator.play("Attack1")
                self.animator.current_frames = 3.0
                get_audio().play_sfx("sheathe")
        elif t < 4.40:
            if self.combo_step < 2:
                self.combo_step = 2
                self.flip = self._death_exit_dir < 0
                self.animator.play("Run", force_reset=True)
                get_audio().play_sfx("vergil_teleport")
            if t < 3.90:
                open_p = min(1.0, (t - 2.75) / 0.35)
                self._death_rift_scale = open_p
                walk_dx = self._death_exit_dir * 72.0 * dt
                if abs(self._death_rift_x - self.pos_x) > 8.0:
                    self.pos_x += walk_dx
                fade_p = max(0.0, min(1.0, (t - 3.15) / 0.70))
                self._death_alpha = max(0.0, 255.0 * (1.0 - fade_p))
            else:
                if self.combo_step < 3:
                    self.combo_step = 3
                    get_audio().play_sfx("portal_warp")
                self._death_alpha = 0.0
                close_p = min(1.0, (t - 3.90) / 0.45)
                self._death_rift_scale = max(0.0, 1.0 - close_p)
        else:
            self.finish_death_sequence()
            return

        self.apply_physics_and_collisions(dt, old_x, map_width)
        anim_name = "Run" if (t >= 2.75 and t < 3.90) else "idle"
        self.image = self.animator.update_get_image(
            self.animation_speed.get(anim_name, 0.085) * (0.60 if anim_name == "Run" else 0.45),
            dt_scale=dt * 60.0,
        )
        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False).convert_alpha()
        if self._death_alpha < 254.0:
            self.image = self.image.copy()
            self.image.set_alpha(int(self._death_alpha))
        self.sync_boxes()
        # One-knee kneel offset (0.55..1.95s) smoothly rising back up (1.95..2.20s)
        if 0.55 <= t < 1.95:
            self.rect.y += 14
        elif 1.95 <= t < 2.20:
            self.rect.y += int(14 * (1.0 - (t - 1.95) / 0.25))

    def draw_extras(self, surface, camera_x=0, camera_y=0):
        """Render Dark Slayer afterimages, trick ripples, Phase 2 spiral guard blades, Phase 3 Sin Devil Trigger aura & DYING visuals."""
        # 1. Decaying Dark Slayer cyan/violet afterimages
        for ghost, rect, alpha in self.afterimages:
            if alpha > 8:
                img = ghost.copy()
                img.set_alpha(int(alpha))
                surface.blit(img, rect.move(-camera_x, -camera_y))

        # 2. Expanding spatial trick ripple rings
        for rx, ry, rad, alpha in self.trick_ripples:
            if alpha > 10:
                sx, sy = int(round(rx - camera_x)), int(round(ry - camera_y))
                pygame.draw.circle(surface, (85, 220, 255), (sx, sy), int(rad), 2)

        if not self.alive():
            return

        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        t = pygame.time.get_ticks() * 0.001

        # 3. DYING Cutscene props: planted Yamato support blade & vertical Blue-Violet Exit Rift
        if self.state == BossState.DYING:
            if 0.55 <= self.state_timer < 1.95:
                kx = sx + self.facing_dir * 14
                pygame.draw.line(surface, (200, 235, 255), (kx, sy - 58), (kx, sy), 3)
                pygame.draw.rect(surface, (45, 70, 155), (kx - 5, sy - 60, 10, 4))
            if self._death_rift_scale > 0.03:
                rx = int(round(self._death_rift_x - camera_x))
                ry = sy - 64
                rw = max(4, int(30 * self._death_rift_scale))
                rh = max(12, int(118 * self._death_rift_scale))
                pts_out = [(rx, ry - rh // 2), (rx + rw, ry), (rx, ry + rh // 2), (rx - rw, ry)]
                pts_in = [(rx, ry - int(rh * 0.42)), (rx + int(rw * 0.55), ry), (rx, ry + int(rh * 0.42)), (rx - int(rw * 0.55), ry)]
                pygame.draw.polygon(surface, (95, 65, 245), pts_out)
                pygame.draw.polygon(surface, (75, 230, 255), pts_out, 2)
                pygame.draw.polygon(surface, (10, 8, 22), pts_in)
            if self._sheathe_glint_timer > 0.0:
                gx, gy = sx - self.facing_dir * 8, sy - 54
                pygame.draw.line(surface, (255, 255, 255), (gx - 18, gy), (gx + 18, gy), 2)
                pygame.draw.line(surface, (120, 235, 255), (gx, gy - 14), (gx, gy + 14), 2)
            return

        # 4. Phase 3 Sin Devil Trigger burning blue-violet flame aura
        if self.phase >= 3:
            for i in range(6):
                ang = t * 5.0 + i * (math.tau / 6.0)
                fx = sx + int(math.cos(ang) * 24)
                fy = sy - 14 - int(abs(math.sin(t * 7.0 + i)) * 56)
                col = (95, 70, 255) if i % 2 == 0 else (65, 220, 255)
                pygame.draw.polygon(surface, col, [(fx - 4, fy + 8), (fx, fy - 12), (fx + 4, fy + 8)])

        # 5. Phase 2+ orbiting Spiral Guard Mirage Blades around Vergil
        if self.phase >= 2:
            for i in range(3):
                ang = t * 3.4 + i * (math.tau / 3.0)
                bx = sx + int(math.cos(ang) * 38)
                by = sy - 56 + int(math.sin(ang) * 14)
                pygame.draw.line(surface, (75, 235, 255), (bx - 8, by), (bx + 8, by), 2)
                pygame.draw.circle(surface, (235, 252, 255), (bx + 6, by), 2)

        # 6. Iaido Windup / Sheathe Hilt Glint star
        if self.attack_phase == AttackPhase.WINDUP or self._sheathe_glint_timer > 0.0:
            gx = sx - self.facing_dir * 6
            gy = sy - 54
            sz = 14 if self._sheathe_glint_timer > 0.0 else 9
            pygame.draw.line(surface, (235, 252, 255), (gx - sz, gy), (gx + sz, gy), 2)
            pygame.draw.line(surface, (85, 215, 255), (gx, gy - sz), (gx, gy + sz), 2)

    def reset(self):
        self.phase = 1
        self.phase2_triggered = False
        self.phase3_triggered = False
        self.boss_speed = self.base_speed
        self.afterimages.clear()
        self.trick_ripples.clear()
        self.title_card_active = False
        self.title_card_timer = 0.0
        self._death_alpha = 255.0
        self._death_rift_scale = 0.0
        self._sheathe_glint_timer = 0.0
        super().reset()
        self.skill_cooldowns[BossState.ATTACK_7] = 2.5
        self.skill_cooldowns[BossState.JUDGEMENT_CUT_END] = 0.0

    def on_parried(self):
        super().on_parried()
        if self.state in (BossState.ATTACK_1, BossState.ATTACK_2):
            self.attack_phase = AttackPhase.RECOVERY
            self.state_timer = 0.68

    def _execute_secondary_skill(self, skill_id, active_hitboxes, vfx_group, map_width):
        """Phase 2 concurrent secondary ranged skill (Mirage Blades or Single Judgement Cut)."""
        if not self.alive() or self.state in (
            BossState.INTRO,
            BossState.PHASE_2_TRANSITION,
            BossState.JUDGEMENT_CUT_END,
        ):
            return
        tx = (
            float(self.target.hurtbox.centerx)
            if (self.target and self.target.alive())
            else self.pos_x + self.facing_dir * 220.0
        )
        ty = (
            float(self.target.hurtbox.centery)
            if (self.target and self.target.alive())
            else self.pos_y - 45.0
        )
        f_dir = self.facing_dir

        if skill_id == "mirage_blades":
            spawns = [
                (self.pos_x - f_dir * 26.0, self.pos_y - 110.0),
                (tx - f_dir * 105.0, ty - 150.0),
                (tx + f_dir * 35.0, ty - 168.0),
            ]
            for i, (sx, sy) in enumerate(spawns):
                sword = SummonedSwordVFX(
                    x=sx,
                    y=sy,
                    target_x=tx,
                    target_y=ty,
                    windup=0.36 + i * 0.14,
                    speed=680.0,
                    duration=1.20,
                    damage=7,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(sword, vfx_group)

        elif skill_id == "single_jc":
            get_audio().play_sfx("sheathe")
            vfx = SingleJudgementCutVFX(
                x=tx,
                y=ty,
                radius=84,
                windup_time=0.46,
                active_time=0.26,
                damage=10,
                hitbox_list=active_hitboxes,
            )
            self.register_vfx(vfx, vfx_group)

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        self._last_vfx_group = vfx_group
        self._tick_common_timers(dt)
        if self._sheathe_glint_timer > 0.0:
            self._sheathe_glint_timer = max(0.0, self._sheathe_glint_timer - dt)

        # Decay Dark Slayer afterimages & spatial ripple rings
        self.afterimages = [
            [g, r, a - 460.0 * dt]
            for (g, r, a) in self.afterimages
            if a - 460.0 * dt > 10.0
        ]
        self.trick_ripples = [
            [x, y, rad + 165.0 * dt, a - 480.0 * dt]
            for (x, y, rad, a) in self.trick_ripples
            if a - 480.0 * dt > 12.0
        ]

        if self.state == BossState.DYING:
            self._update_dying(dt, vfx_group, map_width)
            return

        self.tick_secondary_skill(dt, active_hitboxes, vfx_group, map_width)

        # Phase 2 Trigger (<= 2/3 HP, <= 133): Aura Burst + Mirage Blades & Rapid Trick Slash!
        if (
            not self.phase2_triggered
            and self.state != BossState.INTRO
            and self.hp > 0.0
            and self.hp <= 133.0
        ):
            self._trigger_phase_2(vfx_group=vfx_group)

        # Phase 3 Trigger (<= 1/3 HP, <= 66): Sin Devil Trigger Awakening -> Immediate Judgement Cut End!
        if (
            not self.phase3_triggered
            and self.state != BossState.INTRO
            and self.hp > 0.0
            and self.hp <= 66.0
        ):
            self._trigger_phase_3(vfx_group=vfx_group)

        has_target = bool(self.target and self.target.alive())
        player_x = self.target.pos_x if has_target else self.pos_x
        distance = abs(self.pos_x - player_x)
        old_pos_x = self.pos_x

        if self.state == BossState.INTRO:
            cutscene_end = 2.00
            if self.combo_step == 0:
                self.combo_step = 1
                self.face_target()
                if vfx_group is not None:
                    vfx_group.add(VergilIntroRiftVFX(self, duration=cutscene_end))
            elif self.combo_step == 1 and self.state_timer >= 1.22:
                self.combo_step = 2
                self.animator.play("Attack1")
                self.animator.current_frames = 3.0
                self._sheathe_glint_timer = 0.24
                get_audio().play_sfx("sheathe")
            elif self.combo_step == 2 and self.state_timer >= cutscene_end:
                # Launch Vergil Dimension-Slash Title Card ('The Alpha and the Omega' / 'VERGIL')
                self.combo_step = 3
                self.title_card_active = True
                self.title_card_timer = 0.0
                get_audio().play_sfx("yamato_slash")
            elif self.combo_step == 3 and self.state_timer >= cutscene_end + 0.72:
                # Yamato click SFX + subtle camera shake as huge 'VERGIL' reveals!
                self.combo_step = 4
                self.pending_screen_shake = max(self.pending_screen_shake, 0.18)
                get_audio().play_sfx("sheathe")

            if self.state_timer < cutscene_end:
                self.intro_progress = 0.0
                self.title_card_timer = 0.0
            else:
                self.title_card_timer = self.state_timer - cutscene_end
                # Smoothly expand VERGIL HP bar as Title Card closes (1.75 .. 2.10s)
                if self.title_card_timer >= 1.75:
                    self.intro_progress = min(1.0, (self.title_card_timer - 1.75) / 0.35)
                else:
                    self.intro_progress = 0.0

            if self.state_timer >= self.intro_duration:
                self.title_card_active = False
                self.title_card_timer = 0.0
                self.intro_progress = 1.0
                self.change_state(BossState.IDLE)

        elif self.state == BossState.PHASE_2_TRANSITION:
            self._update_phase_2_transition(dt, vfx_group)

        elif self.state == BossState.JUDGEMENT_CUT_END:
            self._update_judgement_cut_end(dt, active_hitboxes, vfx_group, map_width)

        elif self.state == BossState.COOLDOWN:
            if self.state_timer >= self.cooldown_duration:
                self.change_state(BossState.IDLE)

        elif self.state == BossState.IDLE:
            self.face_target()
            if self.state_timer >= (0.10 if self.phase >= 2 else 0.15):
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

        elif self.state == BossState.ATTACK_4:
            self._update_attack_4_rising_slash(dt, active_hitboxes, vfx_group, map_width)

        elif self.state == BossState.ATTACK_5:
            self._update_attack_5_single_judgement_cut(active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_6:
            self._update_attack_6_summoned_swords(active_hitboxes, vfx_group)

        elif self.state == BossState.ATTACK_7:
            self._update_attack_7_rapid_trick_slash(dt, active_hitboxes, vfx_group, map_width)

        # Unconditional gravity, map collisions, One-Way Platforms & obstacle vaulting
        self.apply_physics_and_collisions(dt, old_pos_x, map_width)

        # Animation frame update
        anim_state = self.animator.current_state or "idle"
        current_fspeed = self.animation_speed.get(anim_state, 0.12)
        dt_scale = (
            0.0
            if (
                self.attack_phase == AttackPhase.WINDUP
                or self.state == BossState.JUDGEMENT_CUT_END
            )
            else (dt * 60.0)
        )
        self.image = self.animator.update_get_image(current_fspeed, dt_scale=dt_scale)

        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False).convert_alpha()

        # Phase 2/3 blue-violet Devil Trigger aura glow
        if self.phase >= 2:
            base_g = 46 if self.phase >= 3 else 28
            glow = int(base_g + 26 * abs(math.sin(pygame.time.get_ticks() * 0.008)))
            self.image = self.image.copy()
            self.image.fill(
                (int(glow * 0.45), int(glow * 0.55), min(255, glow * 2)),
                special_flags=pygame.BLEND_RGB_ADD,
            )

        # Wind-up telegraph & Hit Flash overlays
        if self.attack_phase == AttackPhase.WINDUP:
            pulse = int(abs(math.sin(self.state_timer * 22.0)) * 110)
            self.image = self.image.copy()
            if self.state == BossState.ATTACK_2:
                self.image.fill(
                    (pulse, int(pulse * 0.4), 0), special_flags=pygame.BLEND_RGB_ADD
                )
            elif self.state in (BossState.ATTACK_3, BossState.JUDGEMENT_CUT_END):
                self.image.fill(
                    (int(pulse * 0.65), int(pulse * 0.3), min(255, pulse + 40)),
                    special_flags=pygame.BLEND_RGB_ADD,
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
