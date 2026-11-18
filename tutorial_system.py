import math
import pygame
from Settings import get_pixel_font
from VFX import Hitbox, SlashVFX, draw_floating_prompt_box


class TrainingDummy(pygame.sprite.Sprite):
    """
    Stage 2 Interactive Target:
    A harmless wooden training dummy blocking Gate 1.
    Takes basic melee attacks from the player, flashes/wobbles when struck,
    and opens Gate 1 when destroyed.
    """

    def __init__(self, x, ground_y):
        super().__init__()
        self.pos_x = float(x)
        self.pos_y = float(ground_y)
        self.max_health = 36
        self.boss_health = 36
        self.hit_flash_timer = 0.0
        self.wobble_timer = 0.0

        self.collision_rect = pygame.Rect(0, 0, 34, 68)
        self.collision_rect.midbottom = (int(x), int(ground_y))
        self.hurtbox = self.collision_rect.inflate(6, 4)
        self.rect = pygame.Rect(0, 0, 56, 80)
        self.rect.midbottom = (int(x), int(ground_y))
        self.image = pygame.Surface((56, 80), pygame.SRCALPHA)
        self._render_sprite()

    def be_attacked(self, damage=12):
        if self.boss_health <= 0:
            return
        self.boss_health = max(0, self.boss_health - damage)
        self.hit_flash_timer = 0.22
        self.wobble_timer = 0.35
        if self.boss_health <= 0:
            self.kill()

    def _render_sprite(self):
        self.image.fill((0, 0, 0, 0))
        cx = 28
        wobble_dx = (
            int(math.sin(self.wobble_timer * 38.0) * 4)
            if self.wobble_timer > 0.0
            else 0
        )

        # Base & wooden post
        pygame.draw.rect(self.image, (75, 52, 34), (cx - 16, 72, 32, 8))
        pygame.draw.rect(self.image, (110, 76, 46), (cx - 4 + wobble_dx // 2, 18, 8, 56))
        # Crossbar arms
        pygame.draw.rect(self.image, (130, 90, 54), (cx - 22 + wobble_dx, 30, 44, 8))
        # Straw/wood torso & head
        pygame.draw.rect(
            self.image, (175, 132, 76), (cx - 12 + wobble_dx, 24, 24, 34), border_radius=3
        )
        pygame.draw.rect(
            self.image, (215, 65, 65), (cx - 12 + wobble_dx, 36, 24, 6)
        )
        pygame.draw.circle(self.image, (195, 155, 95), (cx + wobble_dx, 14), 10)
        pygame.draw.circle(self.image, (60, 40, 25), (cx + wobble_dx, 14), 10, 2)

        if self.hit_flash_timer > 0.0:
            self.image.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_ADD)

    def update(self, dt=1 / 60, **_kwargs):
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)
        if self.wobble_timer > 0.0:
            self.wobble_timer = max(0.0, self.wobble_timer - dt)
        self._render_sprite()

    def draw_hp_bar(self, screen, camera_x, camera_y, font):
        if not self.alive():
            return
        sx = int(self.pos_x - camera_x)
        sy = int(self.rect.top - 16 - camera_y)
        bw, bh = 54, 7
        ratio = max(0.0, self.boss_health / self.max_health)
        pygame.draw.rect(screen, (30, 30, 40), (sx - bw // 2, sy, bw, bh))
        pygame.draw.rect(
            screen, (240, 190, 60), (sx - bw // 2, sy, int(bw * ratio), bh)
        )
        pygame.draw.rect(screen, (220, 225, 235), (sx - bw // 2, sy, bw, bh), 1)
        lbl = font.render("DUMMY", False, (255, 235, 150))
        screen.blit(lbl, lbl.get_rect(center=(sx, sy - 9)))


class PogoTargetOrb(pygame.sprite.Sprite):
    """
    Stage 3 Interactive Aerial Target:
    A floating energy orb suspended over the hazard pit.
    Striking it with an aerial downward slash (S/DOWN + LMB) triggers Pogo Bounce!
    Never dies so the player can bounce off it repeatedly.
    """

    def __init__(self, x, y):
        super().__init__()
        self.pos_x = float(x)
        self.pos_y = float(y)
        self.max_health = 9999
        self.boss_health = 9999
        self.anim_timer = 0.0
        self.hit_pulse_timer = 0.0

        self.collision_rect = pygame.Rect(0, 0, 38, 38)
        self.collision_rect.center = (int(x), int(y))
        self.hurtbox = pygame.Rect(0, 0, 44, 44)
        self.hurtbox.center = (int(x), int(y))
        self.rect = pygame.Rect(0, 0, 56, 56)
        self.rect.center = (int(x), int(y))
        self.image = pygame.Surface((56, 56), pygame.SRCALPHA)
        self._render_orb()

    def be_attacked(self, _damage=12):
        self.hit_pulse_timer = 0.28

    def _render_orb(self):
        self.image.fill((0, 0, 0, 0))
        cx, cy = 28, 28
        bob = int(math.sin(self.anim_timer * 4.5) * 3)
        cy += bob

        outer_col = (
            (255, 235, 90, 230)
            if self.hit_pulse_timer > 0.0
            else (55, 225, 255, 200)
        )
        core_col = (255, 255, 240) if self.hit_pulse_timer > 0.0 else (180, 250, 255)

        pygame.draw.circle(self.image, (25, 110, 175, 110), (cx, cy), 22)
        pygame.draw.circle(self.image, outer_col, (cx, cy), 17, 3)
        pygame.draw.circle(self.image, (95, 240, 255, 230), (cx, cy), 11)
        pygame.draw.circle(self.image, core_col, (cx, cy), 6)

    def update(self, dt=1 / 60, **_kwargs):
        self.anim_timer += dt
        if self.hit_pulse_timer > 0.0:
            self.hit_pulse_timer = max(0.0, self.hit_pulse_timer - dt)
        self._render_orb()


class ParryGuardian(pygame.sprite.Sprite):
    """
    Stage 4 Interactive Combat Trainer:
    - Protected by an Energy Shield that blocks normal attacks ("SHIELDED! PARRY FIRST!").
    - Periodically performs a clearly telegraphed energy slash.
    - When the player lands a PERFECT PARRY, the shield shatters (entering STUNNED state)
      so the player can defeat it with their 1.35x Parry Buff counter-attack!
    """

    def __init__(self, target_player, x, ground_y):
        super().__init__()
        self.target = target_player
        self.spawn_x = float(x)
        self.spawn_y = float(ground_y)
        self.pos_x = float(x)
        self.pos_y = float(ground_y)
        self.max_health = 30
        self.boss_health = 30
        self.flip = True

        self.shield_active = True
        self.state = "IDLE"      # IDLE, WINDUP, ACTIVE, RECOVERY, STUNNED
        self.attack_phase = "NONE"
        self.state_timer = 0.0
        self.hit_flash_timer = 0.0
        self.current_hitbox = None

        self.collision_rect = pygame.Rect(0, 0, 38, 76)
        self.collision_rect.midbottom = (int(x), int(ground_y))
        self.hurtbox = pygame.Rect(0, 0, 36, 72)
        self.hurtbox.midbottom = (int(x), int(ground_y))
        self.rect = pygame.Rect(0, 0, 72, 88)
        self.rect.midbottom = (int(x), int(ground_y))
        self.image = pygame.Surface((72, 88), pygame.SRCALPHA)
        self._render_guardian()

    @property
    def facing_dir(self):
        return -1 if self.flip else 1

    def _clear_hitbox(self):
        if self.current_hitbox is not None:
            self.current_hitbox.destroy()
            self.current_hitbox = None

    def on_parried(self):
        """Called when the player successfully Perfect Parries the Guardian's attack"""
        self._clear_hitbox()
        self.shield_active = False
        self.state = "STUNNED"
        self.attack_phase = "STUNNED"
        self.state_timer = 0.0
        if self.target:
            self.target.status_text = "SHIELD SHATTERED! COUNTER NOW!"
            self.target.status_timer = 1.15

    def be_attacked(self, damage=12):
        if self.boss_health <= 0:
            return
        if self.shield_active:
            self.hit_flash_timer = 0.15
            if self.target:
                self.target.status_text = "SHIELDED! PARRY ATTACK FIRST!"
                self.target.status_timer = 0.85
            return

        self.boss_health = max(0, round(self.boss_health - damage, 2))
        self.hit_flash_timer = 0.25
        if self.boss_health <= 0:
            self._clear_hitbox()
            self.kill()

    def _render_guardian(self):
        self.image.fill((0, 0, 0, 0))
        cx = 36

        # Pixel-art armored automaton body
        pygame.draw.rect(self.image, (48, 56, 78), (cx - 14, 24, 28, 52), border_radius=4)
        pygame.draw.rect(self.image, (85, 100, 135), (cx - 14, 24, 28, 52), 2, border_radius=4)
        pygame.draw.rect(self.image, (62, 72, 98), (cx - 10, 8, 20, 18), border_radius=3)

        # Glowing visor eye
        eye_col = (
            (255, 175, 40)
            if self.state == "WINDUP"
            else ((120, 120, 140) if self.state == "STUNNED" else (0, 225, 255))
        )
        eye_x = cx - 8 if self.flip else cx + 2
        pygame.draw.rect(self.image, eye_col, (eye_x, 14, 6, 4))

        # Energy blade arm
        blade_col = (255, 140, 30) if self.state in ("WINDUP", "ACTIVE") else (70, 210, 255)
        bx = cx - 26 if self.flip else cx + 12
        pygame.draw.rect(self.image, blade_col, (bx, 34, 14, 6))

        # Energy shield barrier when active
        if self.shield_active:
            sh_x = cx - 22 if self.flip else cx + 18
            pygame.draw.arc(
                self.image,
                (70, 225, 255, 215),
                (sh_x - 8, 12, 18, 66),
                0.5 * math.pi if self.flip else -0.5 * math.pi,
                1.5 * math.pi if self.flip else 0.5 * math.pi,
                3,
            )

        if self.state == "WINDUP":
            pulse = int(abs(math.sin(self.state_timer * 20.0)) * 110)
            self.image.fill((pulse, int(pulse * 0.6), 0), special_flags=pygame.BLEND_RGB_ADD)
        elif self.hit_flash_timer > 0.0:
            self.image.fill((180, 50, 50), special_flags=pygame.BLEND_RGB_ADD)

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, **_kwargs):
        self.state_timer += dt
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)

        if self.target and self.target.alive():
            self.flip = self.target.pos_x < self.pos_x
            dist = abs(self.target.pos_x - self.pos_x)
        else:
            dist = 999.0

        if self.state == "IDLE":
            self.attack_phase = "NONE"
            if dist <= 260.0 and self.state_timer >= 0.95:
                self.state = "WINDUP"
                self.attack_phase = "WINDUP"
                self.state_timer = 0.0

        elif self.state == "WINDUP":
            # 0.50s clear telegraph before striking
            if self.state_timer >= 0.50:
                self.state = "ACTIVE"
                self.attack_phase = "ACTIVE"
                self.state_timer = 0.0

                cx = int(self.pos_x + self.facing_dir * 46)
                cy = int(self.pos_y - 36)
                hb_rect = pygame.Rect(0, 0, 96, 64)
                hb_rect.center = (cx, cy)
                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=15,
                    knockback_x=self.facing_dir * 200.0,
                    lifetime=0.22,
                    tag="tutorial_guardian_slash",
                )
                self.current_hitbox = hb
                if active_hitboxes is not None:
                    active_hitboxes.append(hb)
                if vfx_group is not None:
                    vfx_group.add(
                        SlashVFX(
                            anchor_entity=self,
                            forward_offset=46.0,
                            vertical_offset=-36.0,
                            width=102,
                            height=70,
                            flip=self.flip,
                            duration=0.22,
                            color_outer=(255, 145, 35),
                            color_inner=(255, 245, 200),
                            hitbox=hb,
                        )
                    )

        elif self.state == "ACTIVE":
            if self.state_timer >= 0.22:
                self._clear_hitbox()
                self.state = "RECOVERY"
                self.attack_phase = "RECOVERY"
                self.state_timer = 0.0

        elif self.state == "RECOVERY":
            if self.state_timer >= 0.65:
                self.state = "IDLE"
                self.attack_phase = "NONE"
                self.state_timer = 0.0

        elif self.state == "STUNNED":
            # Stays stunned for 3.8s so player can easily land their 1.35x counter-attacks
            if self.state_timer >= 3.8:
                self.shield_active = True
                self.state = "IDLE"
                self.attack_phase = "NONE"
                self.state_timer = 0.0

        self._render_guardian()

    def draw_extra_ui(self, screen, camera_x, camera_y, font):
        if not self.alive():
            return
        sx = int(self.pos_x - camera_x)
        sy = int(self.rect.top - 18 - camera_y)

        # Telegraph countdown ring during WINDUP
        if self.state == "WINDUP":
            wp = min(1.0, self.state_timer / 0.50)
            r = max(8, int(44 * (1.0 - wp)))
            pygame.draw.circle(
                screen,
                (255, 195, 50),
                (sx + self.facing_dir * 20, int(self.pos_y - 38 - camera_y)),
                r,
                2,
            )
            warn_txt = font.render("PARRY NOW! [RMB / J]", False, (80, 245, 255))
            screen.blit(warn_txt, warn_txt.get_rect(center=(sx, sy - 16)))
        elif self.state == "STUNNED":
            stun_txt = font.render(
                "STUNNED! STRIKE NOW (1.35x DMG)!", False, (255, 215, 65)
            )
            screen.blit(stun_txt, stun_txt.get_rect(center=(sx, sy - 16)))
        else:
            status_str = "SHIELD ACTIVE (PARRY TO BREAK)" if self.shield_active else "VULNERABLE"
            col = (110, 225, 255) if self.shield_active else (255, 210, 80)
            lbl = font.render(status_str, False, col)
            screen.blit(lbl, lbl.get_rect(center=(sx, sy - 14)))

        # HP Bar
        bw, bh = 68, 8
        ratio = max(0.0, self.boss_health / self.max_health)
        pygame.draw.rect(screen, (30, 30, 42), (sx - bw // 2, sy, bw, bh))
        bar_col = (80, 215, 255) if self.shield_active else (235, 65, 75)
        pygame.draw.rect(
            screen, bar_col, (sx - bw // 2, sy, int(bw * ratio), bh)
        )
        pygame.draw.rect(screen, (230, 235, 245), (sx - bw // 2, sy, bw, bh), 1)


class GuidedTutorialManager:
    """
    Manages the 5-Stage Interactive Guided Tutorial Level:
    - Stage 1 (x < 520): Movement & Fixed-Height Jump
    - Stage 2 (520 <= x < 960): Basic Attack vs Training Dummy & Gate 1
    - Stage 3 (960 <= x < 1420): Downward Slash (Pogo Bounce) off 2 Aerial Orbs over Hazard Pit
    - Stage 4 (1420 <= x < 2000): Perfect Parry & 1.35x Counter vs Parry Guardian & Gate 2
    - Stage 5 (x >= 2000): Checkpoint Save/Heal & Portal to Main World
    """

    def __init__(self, game):
        self.game = game
        self.font = get_pixel_font(16)

        # Spawn interactive targets & gates
        self.dummy = TrainingDummy(x=760, ground_y=640)
        self.orb_1 = PogoTargetOrb(x=1145, y=568)
        self.orb_2 = PogoTargetOrb(x=1275, y=508)
        self.guardian = ParryGuardian(
            target_player=game.player, x=1820, ground_y=544
        )

        # Gate 1 (blocks access to Stage 3 until Dummy is destroyed)
        self.gate1_rect = pygame.Rect(880, 440, 28, 200)
        self.gate1_open = False

        # Gate 2 (blocks access to Stage 5 until Guardian is defeated)
        self.gate2_rect = pygame.Rect(1960, 344, 28, 200)
        self.gate2_open = False

        # Register gates into map collisions
        self.game.game_map.collisions.append(self.gate1_rect)
        self.game.game_map.collisions.append(self.gate2_rect)

        # Register targets into game sprite groups
        for ent in (self.dummy, self.orb_1, self.orb_2, self.guardian):
            self.game.enemies.add(ent)
            self.game.all_sprites.add(ent)

        # Bind Guardian as game.boss so Perfect Parry in resolve_combat_collisions works natively!
        self.game.boss = self.guardian

    def update(self, scaled_dt):
        player = self.game.player

        # Keep player HP >= 25 during tutorial practice so they never die,
        # and can test healing at the Stage 5 Checkpoint!
        if player.player_hp < 25:
            player.player_hp = 25

        # Update tutorial entities
        self.dummy.update(scaled_dt)
        self.orb_1.update(scaled_dt)
        self.orb_2.update(scaled_dt)

        # Open Gate 1 when Training Dummy is destroyed
        if not self.gate1_open and not self.dummy.alive():
            self.gate1_open = True
            if self.gate1_rect in self.game.game_map.collisions:
                self.game.game_map.collisions.remove(self.gate1_rect)
            player.status_text = "GATE OPENED! ADVANCE RIGHT >>"
            player.status_timer = 1.2

        # Stage 3 Hazard Pit Safety Reset: if player falls to the bottom of the pit,
        # teleport them back to the Stage 3 take-off ledge so they can retry the Pogo jump!
        if 1045 <= player.pos_x <= 1370 and player.pos_y >= 695:
            player.teleport(980, 640)
            player.status_text = "TRY AGAIN: Jump + Hold [S] + [LMB] on the Orbs!"
            player.status_timer = 1.4

        # Open Gate 2 when Parry Guardian is defeated
        if not self.gate2_open and not self.guardian.alive():
            self.gate2_open = True
            if self.gate2_rect in self.game.game_map.collisions:
                self.game.game_map.collisions.remove(self.gate2_rect)
            # Slightly reduce player HP to 75 if still at 100 so they can clearly see
            # the Checkpoint heal bar fill animation in Stage 5!
            if player.player_hp >= 100:
                player.player_hp = 78
                self.game.hud.player_display_hp = 78.0
            player.status_text = "GUARDIAN DEFEATED! PROCEED TO SHRINE >>"
            player.status_timer = 1.4

    def get_current_stage_info(self, player_x):
        """Return (stage_title, primary_hint, secondary_hint, completed) for the player's current X zone"""
        if player_x < 520:
            return (
                "STAGE 1 / 5 : MOVEMENT, JUMP & TWO-WAY PLATFORMS",
                "[A / D] Move  |  [W / SPACE] Jump Up Through Platform  |  [S + SPACE] Drop Down",
                "Blue-trimmed platforms let you jump up from below and drop down with [S + SPACE].",
                False,
            )
        if player_x < 920:
            done = self.gate1_open
            return (
                "STAGE 2 / 5 : BASIC MELEE ATTACK",
                "Press [Left Click] to Slash and Destroy the Training Dummy!",
                "Gate Unlocked! Head Right to Stage 3 >>"
                if done
                else f"Dummy HP: {self.dummy.boss_health} / {self.dummy.max_health}",
                done,
            )
        if player_x < 1420:
            done = player_x >= 1380 and self.game.player.pos_y <= 550
            return (
                "STAGE 3 / 5 : AERIAL DOWNWARD SLASH (POGO BOUNCE)",
                "In Mid-Air: Hold [S / DOWN] + Press [Left Click] to Bounce off the Glowing Orbs!",
                "Hit Both Orbs in One Jump to Reach the High Ledge (Max 2 Bounces Per Jump).",
                done,
            )
        if player_x < 2000:
            done = self.gate2_open
            return (
                "STAGE 4 / 5 : PERFECT PARRY & BULLET TIME",
                "Press [Right Click / J / Shift] Just Before the Guardian Strikes to Trigger PERFECT PARRY!",
                "Guardian Defeated! Head Right to the Shrine >>"
                if done
                else "Perfect Parry triggers Slow-Mo, Ink-Splash VFX, Shatters Shield & Grants 1.35x DMG!",
                done,
            )
        cp_saved = any(cp.activated for cp in self.game.checkpoints)
        return (
            "STAGE 5 / 5 : CHECKPOINT HEAL & PORTAL TRANSITION",
            "Press [E] at the Shrine to Save & Full Heal, then Press [E] at the Portal!",
            "Checkpoint Saved! Walk to the Portal on the Right and Press [E] to Start!"
            if cp_saved
            else "Stand near the Shrine or Portal to reveal the floating [E] Prompt Window.",
            cp_saved,
        )

    def draw_world_elements(self, surface, camera_x, camera_y):
        """Draw tutorial gates, hazard spikes, signposts, and target HP bars on world_surface"""
        # 1. Draw Stage 1 & 3 & 4 pixel-art signboards in the background
        signs = [
            (195, 560, "[S + SPACE] Drop Down"),
            (395, 576, "[SPACE] Fixed Jump"),
            (650, 640, "[Left Click] Attack"),
            (980, 640, "Air [S + LMB] Pogo x2"),
            (1620, 544, "[RMB / J] Perfect Parry"),
        ]
        for wx, wy, label in signs:
            draw_floating_prompt_box(
                surface,
                wx,
                wy - 68,
                camera_x,
                camera_y,
                label,
                self.font,
                border_color=(120, 175, 235),
                text_color=(220, 238, 255),
            )

        # 2. Draw Stage 3 Hazard Pit Spikes (x=1044..1372, y=720)
        pit_y = 720 - camera_y
        for sp_x in range(1048, 1372, 16):
            sx = sp_x - camera_x
            pts = [(sx, pit_y), (sx + 8, pit_y - 16), (sx + 16, pit_y)]
            pygame.draw.polygon(surface, (215, 65, 75), pts)
            pygame.draw.polygon(surface, (255, 160, 160), pts, 1)

        # 3. Draw Gate 1 & Gate 2 if still closed
        for gate_rect, is_open, title in [
            (self.gate1_rect, self.gate1_open, "DESTROY DUMMY"),
            (self.gate2_rect, self.gate2_open, "PARRY & DEFEAT"),
        ]:
            if not is_open:
                gr = gate_rect.move(-camera_x, -camera_y)
                pygame.draw.rect(surface, (42, 48, 66), gr)
                pygame.draw.rect(surface, (255, 95, 95), gr, 2)
                for bar_y in range(gr.top + 16, gr.bottom, 24):
                    pygame.draw.line(
                        surface, (95, 110, 140), (gr.left + 3, bar_y), (gr.right - 3, bar_y), 3
                    )
                lbl = self.font.render(title, False, (255, 120, 120))
                surface.blit(lbl, lbl.get_rect(center=(gr.centerx, gr.top - 12)))

        # 4. Draw Dummy & Guardian floating HP / Telegraph UI
        self.dummy.draw_hp_bar(surface, camera_x, camera_y, self.font)
        self.guardian.draw_extra_ui(surface, camera_x, camera_y, self.font)

    def draw_hud_banner(self, screen, hud):
        title, hint1, hint2, done = self.get_current_stage_info(
            self.game.player.pos_x
        )
        hud.draw_tutorial_stage_banner(
            screen, title, hint1, secondary_hint=hint2, completed=done
        )
