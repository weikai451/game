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
        self.jce_center = (float(start_x), float(ground_y - 75.0))
        self.jce_radius = 290
        self.skill_cooldowns[BossState.ATTACK_4] = 2.0
        self.skill_cooldowns[BossState.ATTACK_5] = 2.6
        self.skill_cooldowns[BossState.ATTACK_6] = 3.2
        self.skill_cooldowns[BossState.JUDGEMENT_CUT_END] = 0.0
        self.intro_duration = 2.0
        self.intro_progress = 0.0
        self.state = BossState.INTRO

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
            BossState.ATTACK_4,
            BossState.ATTACK_5,
            BossState.ATTACK_6,
            BossState.JUDGEMENT_CUT_END,
        ):
            self.face_target()
            self.attack_phase = AttackPhase.WINDUP
            if new_state in (BossState.ATTACK_1, BossState.ATTACK_4):
                self.animator.play("Attack1", force_reset=True)
            elif new_state == BossState.ATTACK_2:
                self.dash_dir = self.facing_dir
                self.dash_start_x = self.pos_x
                self.animator.play("Dash", force_reset=True)
            elif new_state in (
                BossState.ATTACK_3,
                BossState.ATTACK_5,
                BossState.ATTACK_6,
                BossState.JUDGEMENT_CUT_END,
            ):
                self.animator.play("Attack1", force_reset=True)

            # Phase 2 Dual-Skill Combo (60% chance, max 2 concurrent skills; Judgement Cut End stays solo!)
            if (
                self.phase >= 2
                and new_state != BossState.JUDGEMENT_CUT_END
                and self.pending_secondary_skill is None
                and random.random() < 0.60
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
            self.animator.play("idle", force_reset=True)
        elif new_state == BossState.PHASE_2_TRANSITION:
            self.attack_phase = AttackPhase.NONE
            self.invincible = True
            self.animator.play("idle", force_reset=True)
        else:
            self.attack_phase = AttackPhase.NONE
            self.invincible = False
            if new_state == BossState.COOLDOWN:
                cd_mult = 0.78 if self.phase >= 2 else 1.0
                self.cooldown_duration = cooldown_duration * cd_mult
                self.animator.play("idle")
            elif new_state == BossState.IDLE:
                self.animator.play("idle")
            elif new_state == BossState.CHASE:
                self.animator.play("Run")

    def decide_next_action(self, distance):
        # Phase 2 Ultimate: Judgement Cut End when off cooldown
        if (
            self.phase >= 2
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
        cd6 = self.skill_cooldowns.get(BossState.ATTACK_6, 0.0) <= 0.0

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
        get_audio().play_sfx("yamato_slash")

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
                    damage=13,
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
                    damage=17,
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
                    damage=19,
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
                    damage=15,
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
                        damage=17,
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
                    damage=14,
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
                    damage=12,
                    duration=0.18,
                    color_outer=(95, 195, 255),
                )

        elif self.state_timer < recovery_end:
            if self.attack_phase != AttackPhase.RECOVERY:
                self.attack_phase = AttackPhase.RECOVERY
                self._clear_melee_hitbox()
                self.animator.current_frames = 3.0
        else:
            self._clear_melee_hitbox()
            self.skill_cooldowns[BossState.ATTACK_4] = 3.2
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.60)

    def _update_attack_5_single_judgement_cut(self, active_hitboxes, vfx_group):
        """
        Attack B — Single Judgement Cut:
        Quick Yamato draw/sheathe spawning a blue-violet spatial slash sphere directly at the player.
        """
        windup_end = 0.34
        active_end = 0.78
        recovery_end = 1.05

        if self.state_timer < windup_end:
            self.attack_phase = AttackPhase.WINDUP
            self.face_target()
            self.animator.play("Attack1")
            self.animator.current_frames = 0.0
        elif self.state_timer < active_end:
            self.attack_phase = AttackPhase.ACTIVE
            if self.combo_step == 0:
                self.combo_step = 1
                self.animator.current_frames = 3.0
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
                    windup_time=0.46,
                    active_time=0.28,
                    damage=15,
                    hitbox_list=active_hitboxes,
                )
                self.register_vfx(vfx, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_5] = 3.4
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
                        damage=10,
                        hitbox_list=active_hitboxes,
                    )
                    self.register_vfx(sword, vfx_group)
        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
        else:
            self.skill_cooldowns[BossState.ATTACK_6] = 4.0
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.65)

    def _trigger_phase_2(self, vfx_group=None):
        """Force-interrupt current action into invincible Phase 2 awakening burst."""
        self.phase = 2
        self.phase2_triggered = True
        self.boss_speed = 270.0
        self.clear_owned_attacks()
        self.change_state(BossState.PHASE_2_TRANSITION)
        self.pending_screen_shake = max(self.pending_screen_shake, 0.45)
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
            # Immediately unleash Judgement Cut End as the Phase 2 opener!
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
                    active_hitboxes, damage=12, lifetime=0.22, tag="vergil_jce_slash"
                )
                self.pending_screen_shake = max(self.pending_screen_shake, 0.22)
            elif self.combo_step == 2 and self.state_timer >= 1.55:
                self.combo_step = 3
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=12, lifetime=0.22, tag="vergil_jce_slash"
                )
            elif self.combo_step == 3 and self.state_timer >= 1.95:
                self.combo_step = 4
                self._spawn_jce_sphere_hitbox(
                    active_hitboxes, damage=12, lifetime=0.22, tag="vergil_jce_slash"
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
                    active_hitboxes, damage=19, lifetime=0.24, tag="vergil_jce_finisher"
                )
                self.pending_screen_shake = max(self.pending_screen_shake, 0.55)

        elif self.state_timer < recovery_end:
            self.attack_phase = AttackPhase.RECOVERY
            self.animator.play("idle")
        else:
            self.skill_cooldowns[BossState.JUDGEMENT_CUT_END] = 11.0
            self.change_state(BossState.COOLDOWN, cooldown_duration=0.85)

    def reset(self):
        self.phase = 1
        self.phase2_triggered = False
        self.boss_speed = self.base_speed
        super().reset()
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
                    damage=10,
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
                damage=14,
                hitbox_list=active_hitboxes,
            )
            self.register_vfx(vfx, vfx_group)

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=1600):
        self._tick_common_timers(dt)
        self.tick_secondary_skill(dt, active_hitboxes, vfx_group, map_width)

        # Trigger Phase 2 awakening the moment HP drops to/below 50%
        if (
            not self.phase2_triggered
            and self.hp > 0.0
            and self.hp <= self.max_hp * 0.5
        ):
            self._trigger_phase_2(vfx_group=vfx_group)

        has_target = bool(self.target and self.target.alive())
        player_x = self.target.pos_x if has_target else self.pos_x
        distance = abs(self.pos_x - player_x)
        old_pos_x = self.pos_x

        if self.state == BossState.INTRO:
            if self.combo_step == 0:
                self.combo_step = 1
                self.face_target()
                if vfx_group is not None:
                    vfx_group.add(VergilIntroRiftVFX(self, duration=self.intro_duration))
            elif self.combo_step == 1 and self.state_timer >= 1.22:
                self.combo_step = 2
                self.animator.play("Attack1")
                self.animator.current_frames = 3.0
                get_audio().play_sfx("sheathe")
            self.intro_progress = min(1.0, self.state_timer / max(0.01, self.intro_duration))
            if self.state_timer >= self.intro_duration:
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

        # Phase 2 blue-violet Devil Trigger aura glow
        if self.phase >= 2:
            glow = int(38 + 26 * abs(math.sin(pygame.time.get_ticks() * 0.008)))
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
