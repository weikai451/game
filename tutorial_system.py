import math
import os
import pygame
from Settings import get_pixel_font
from VFX import BaseVFX, Hitbox, draw_floating_prompt_box
from enemies import Slimer
from audio_manager import get_audio

_TUTORIAL_SPRITE_CACHE = {}


def _load_tut_sprite(filename, fallback_size=(48, 48)):
    if filename in _TUTORIAL_SPRITE_CACHE:
        return _TUTORIAL_SPRITE_CACHE[filename]
    path = os.path.join("assets", "sprites", "tutorial", filename)
    if os.path.exists(path):
        surf = pygame.image.load(path).convert_alpha()
    else:
        surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (90, 225, 255), surf.get_rect(), 2)
    _TUTORIAL_SPRITE_CACHE[filename] = surf
    return surf


class TrainingDummy(pygame.sprite.Sprite):
    """Zone 2 Training Dummy (uses cached assets/sprites/tutorial/dummy.png)."""

    def __init__(self, x, ground_y):
        super().__init__()
        self.pos_x = float(x)
        self.pos_y = float(ground_y)
        self.max_health = 36
        self.boss_health = 36
        self.hit_flash_timer = 0.0
        self.wobble_timer = 0.0

        self.base_img = _load_tut_sprite("dummy.png", (56, 80))
        self.image = self.base_img
        self.collision_rect = pygame.Rect(0, 0, 36, 72)
        self.collision_rect.midbottom = (int(x), int(ground_y))
        self.hurtbox = self.collision_rect.inflate(8, 4)
        self.rect = self.image.get_rect(midbottom=(int(x), int(ground_y)))

    def be_attacked(self, damage=12):
        if self.boss_health <= 0:
            return
        self.boss_health = max(0, self.boss_health - damage)
        self.hit_flash_timer = 0.20
        self.wobble_timer = 0.32
        if self.boss_health <= 0:
            self.kill()

    def update(self, dt):
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)
        if self.wobble_timer > 0.0:
            self.wobble_timer = max(0.0, self.wobble_timer - dt)

        wobble_dx = int(math.sin(self.wobble_timer * 42.0) * 4) if self.wobble_timer > 0 else 0
        self.rect = self.base_img.get_rect(midbottom=(int(self.pos_x) + wobble_dx, int(self.pos_y)))
        if self.hit_flash_timer > 0.0:
            flashed = self.base_img.copy()
            flashed.fill((255, 85, 85), special_flags=pygame.BLEND_RGB_ADD)
            self.image = flashed
        else:
            self.image = self.base_img

    def draw_ui(self, screen, camera_x, camera_y, font):
        if not self.alive():
            return
        sx = int(self.pos_x - camera_x)
        sy = int(self.rect.top - 16 - camera_y)
        bw, bh = 54, 7
        ratio = max(0.0, self.boss_health / self.max_health)
        pygame.draw.rect(screen, (25, 25, 35), (sx - bw // 2, sy, bw, bh))
        pygame.draw.rect(screen, (235, 80, 80), (sx - bw // 2, sy, int(bw * ratio), bh))
        pygame.draw.rect(screen, (230, 235, 245), (sx - bw // 2, sy, bw, bh), 1)
        lbl = font.render("DUMMY", False, (255, 230, 150))
        screen.blit(lbl, lbl.get_rect(center=(sx, sy - 11)))


class PogoTargetOrb(pygame.sprite.Sprite):
    """Indestructible floating crystal orb (pogo_orb.png) for 2x Aerial Downward Slash practice."""

    def __init__(self, x, y):
        super().__init__()
        self.base_x = float(x)
        self.base_y = float(y)
        self.pos_x = float(x)
        self.pos_y = float(y)
        self.timer = 0.0
        self.flash_timer = 0.0

        self.base_img = _load_tut_sprite("pogo_orb.png", (48, 48))
        self.image = self.base_img
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.collision_rect = pygame.Rect(0, 0, 38, 38)
        self.collision_rect.center = (int(x), int(y))
        self.hurtbox = pygame.Rect(0, 0, 50, 50)
        self.hurtbox.center = (int(x), int(y))

    def be_attacked(self, damage=12):
        self.flash_timer = 0.25

    def update(self, dt):
        self.timer += dt
        if self.flash_timer > 0.0:
            self.flash_timer = max(0.0, self.flash_timer - dt)
        bob = math.sin(self.timer * 3.8 + self.base_x * 0.02) * 5.0
        self.pos_y = self.base_y + bob
        self.rect.center = (int(self.pos_x), int(self.pos_y))
        self.collision_rect.center = self.rect.center
        self.hurtbox.center = self.rect.center
        if self.flash_timer > 0.0:
            bright = self.base_img.copy()
            bright.fill((90, 220, 255), special_flags=pygame.BLEND_RGB_ADD)
            self.image = bright
        else:
            self.image = self.base_img


class ParryBoltVFX(BaseVFX):
    """Slow, crisp glowing test energy bolt fired by ParryTurret for Perfect Parry practice."""

    def __init__(self, x, y, speed=-340.0, damage=12, turret=None, hitbox_list=None):
        super().__init__(x, y, duration=2.2, hitbox=None)
        self.vx = float(speed)
        self.turret = turret
        self.img = _load_tut_sprite("parry_bolt.png", (36, 28))
        hb_rect = pygame.Rect(0, 0, 34, 28)
        hb_rect.center = (int(x), int(y))
        hb = Hitbox(
            owner="boss",
            rect=hb_rect,
            damage=damage,
            knockback_x=-180.0,
            lifetime=2.2,
            tag="tutorial_bolt",
        )
        hb.source_entity = turret
        self.bind_hitbox(hb)
        if hitbox_list is not None:
            hitbox_list.append(hb)

    def update(self, dt=1 / 60):
        super().update(dt)
        self.pos_x += self.vx * dt
        if self.hitbox and self.hitbox.active:
            self.hitbox.rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        screen.blit(self.img, self.img.get_rect(center=(sx, sy)))


class ParryTurret(pygame.sprite.Sprite):
    """
    Zone 3 Ancient Rune Parry Turret (parry_turret.png):
    - Periodically charges with a pulsing telegraph ring and fires a parryable ParryBoltVFX.
    - Landing 2 Perfect Parries (or destroying it after shattering its shield) opens Gate 2!
    """

    def __init__(self, target_player, x, ground_y):
        super().__init__()
        ground_y+=100

        self.target = target_player
        self.pos_x = float(x)
        self.pos_y = float(ground_y)
        self.facing_dir = -1
        self.flip = True

        self.max_health = 40
        self.boss_health = 40
        self.parries_required = 2
        self.parry_count = 0
        self.shield_active = True

        self.state = "IDLE"  # IDLE, CHARGE, COOLDOWN
        self.state_timer = 0.0
        self.hit_flash_timer = 0.0
        self.owned_vfx = []

        self.base_img = _load_tut_sprite("parry_turret.png", (64, 84))
        self.image = self.base_img
        self.collision_rect = pygame.Rect(0, 0, 44, 78)
        self.collision_rect.midbottom = (int(x), int(ground_y))
        self.hurtbox = self.collision_rect.inflate(6, 4)
        self.rect = self.image.get_rect(midbottom=(int(x), int(ground_y)))

    def get_active_hitboxes(self):
        self.owned_vfx[:] = [v for v in self.owned_vfx if v.alive()]
        return [v.hitbox for v in self.owned_vfx if getattr(v, "hitbox", None) and v.hitbox.active]

    def clear_owned_attacks(self):
        for v in self.owned_vfx:
            v.destroy()
        self.owned_vfx.clear()

    def be_attacked(self, damage=12):
        if self.boss_health <= 0:
            return
        if self.shield_active:
            if self.target:
                self.target.status_text = "SHIELDED! PARRY THE BOLT [Right Click]"
                self.target.status_timer = 0.9
            return
        self.boss_health = max(0, self.boss_health - damage)
        self.hit_flash_timer = 0.22
        if self.boss_health <= 0:
            self.clear_owned_attacks()
            self.kill()

    def on_parried(self):
        self.parry_count += 1
        self.hit_flash_timer = 0.30
        if self.parry_count >= self.parries_required:
            self.shield_active = False
            self.clear_owned_attacks()
            if self.target:
                self.target.status_text = "TURRET SHATTERED! PROCEED RIGHT >>"
                self.target.status_timer = 1.3
            self.boss_health = 0
            self.kill()
        elif self.target:
            self.target.status_text = f"PERFECT PARRY! ({self.parry_count}/{self.parries_required})"
            self.target.status_timer = 1.0

    def update(self, dt=1 / 60, active_hitboxes=None, vfx_group=None, map_width=2720):
        self.state_timer += dt
        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)

        player_in_zone = (
            self.target is not None
            and self.target.alive()
            and 1490 <= self.target.pos_x <= 2040
        )

        if self.state == "IDLE":
            if player_in_zone and self.state_timer >= 0.85:
                self.state = "CHARGE"
                self.state_timer = 0.0
                get_audio().play_sfx("blaster_charge")
        elif self.state == "CHARGE":
            if self.state_timer >= 0.65:
                self.state = "COOLDOWN"
                self.state_timer = 0.0
                get_audio().play_sfx("mirage_blade")
                bolt = ParryBoltVFX(
                    x=self.pos_x - 32.0,
                    y=self.pos_y - 44.0,
                    speed=-340.0,
                    damage=12,
                    turret=self,
                    hitbox_list=active_hitboxes,
                )
                self.owned_vfx.append(bolt)
                if vfx_group is not None:
                    vfx_group.add(bolt)
        elif self.state == "COOLDOWN":
            if self.state_timer >= 1.15:
                self.state = "IDLE"
                self.state_timer = 0.0

        if self.hit_flash_timer > 0.0:
            flashed = self.base_img.copy()
            flashed.fill((255, 210, 80), special_flags=pygame.BLEND_RGB_ADD)
            self.image = flashed
        else:
            self.image = self.base_img

    def draw_ui(self, screen, camera_x, camera_y, font):
        if not self.alive():
            return
        sx = int(self.pos_x - camera_x)
        sy = int(self.rect.top - 18 - camera_y)

        if self.state == "CHARGE":
            cp = min(1.0, self.state_timer / 0.65)
            r = max(6, int(36 * (1.0 - cp)))
            pygame.draw.circle(
                screen, (80, 240, 255), (sx - 28, int(self.pos_y - 44 - camera_y)), r, 2
            )
            warn = font.render("INCOMING! [Right Click] TO PARRY", False, (80, 245, 255))
            screen.blit(warn, warn.get_rect(center=(sx, sy - 16)))
        else:
            lbl = font.render(
                f"PARRY TURRET ({self.parry_count}/{self.parries_required} PARRIES)",
                False,
                (170, 235, 255),
            )
            screen.blit(lbl, lbl.get_rect(center=(sx, sy - 14)))


class GuidedTutorialManager:
    """
    Redesigned 5-Zone Interactive Guided Tutorial:
    - Zone 1 (x < 620): Movement, Jump, Drop-Through & Q-Key Dash across 200px Chasm
    - Zone 2 (620 <= x < 1480): Left Click Attack (Training Dummy) & 2x Pogo Orbs
    - Zone 3 (1480 <= x < 2160): Right Click Perfect Parry vs ParryTurret Test Bolts
    - Zone 4 (2160 <= x < 2660): Practical Combat Trial (Slimer after learning all moves!)
    - Zone 5 (x >= 2660): Checkpoint Save/Heal & Portal to Seamless Stage 1
    """

    def __init__(self, game):
        self.game = game
        self.font = get_pixel_font(16)
        self.sign_img = _load_tut_sprite("signpost.png", (48, 56))

        self.dummy = TrainingDummy(x=820, ground_y=640)
        self.orb_1 = PogoTargetOrb(x=1230, y=566)
        self.orb_2 = PogoTargetOrb(x=1365, y=506)
        self.turret = ParryTurret(target_player=game.player, x=1980, ground_y=544)
        # Practice Slimer placed in Zone 4 (AFTER ParryTurret, BEFORE final Checkpoint & Portal!)
        self.practice_slimer = Slimer(
            target_player=game.player,
            start_x=2410,
            ground_y=544,
            game_map=game.game_map,
            patrol_range=110.0,
            max_hp=36,
            attack_damage=5,
        )

        self.gate1_rect = pygame.Rect(1050, 440, 28, 200)
        self.gate1_open = False
        self.gate2_rect = pygame.Rect(2100, 440, 28, 200)
        self.gate2_open = False
        self.gate3_rect = pygame.Rect(2620, 440, 28, 200)
        self.gate3_open = False

        self.game.game_map.collisions.append(self.gate1_rect)
        self.game.game_map.collisions.append(self.gate2_rect)
        self.game.game_map.collisions.append(self.gate3_rect)

        self.game.regular_enemies.add(self.practice_slimer)
        for ent in (self.dummy, self.orb_1, self.orb_2, self.turret, self.practice_slimer):
            self.game.enemies.add(ent)
            self.game.all_sprites.add(ent)

        # Bind ParryTurret as game.boss so Perfect Parry / Block resolution works natively
        self.game.boss = self.turret

    def update(self, scaled_dt):
        player = self.game.player
        if player.player_hp < 30:
            player.player_hp = 30

        self.dummy.update(scaled_dt)
        self.orb_1.update(scaled_dt)
        self.orb_2.update(scaled_dt)

        # Zone 1 Dash Chasm safety reset
        if 420 <= player.pos_x <= 618 and player.pos_y >= 695:
            player.teleport(360, 640)
            player.status_text = "TRY AGAIN: Jump + Press [Q] to Dash Across!"
            player.status_timer = 1.4

        # Open Gate 1 once Training Dummy is destroyed
        if not self.gate1_open and not self.dummy.alive():
            self.gate1_open = True
            if self.gate1_rect in self.game.game_map.collisions:
                self.game.game_map.collisions.remove(self.gate1_rect)
            get_audio().play_sfx("level_clear")
            player.status_text = "GATE OPENED! ADVANCE TO POGO PIT >>"
            player.status_timer = 1.3

        # Zone 2 Pogo Pit safety reset
        if 1142 <= player.pos_x <= 1475 and player.pos_y >= 695:
            player.teleport(1090, 640)
            player.status_text = "TRY AGAIN: Hold [S] + [Left Click] on the Orbs!"
            player.status_timer = 1.4

        # Open Gate 2 when Parry Turret is shattered (2 Perfect Parries)
        if not self.gate2_open and not self.turret.alive():
            self.gate2_open = True
            if self.gate2_rect in self.game.game_map.collisions:
                self.game.game_map.collisions.remove(self.gate2_rect)
            get_audio().play_sfx("level_clear")
            player.status_text = "PARRY MASTERED! ENTER COMBAT TRIAL >>"
            player.status_timer = 1.4

        # Open Gate 3 once Practice Slimer in Zone 4 is defeated
        if not self.gate3_open and not self.practice_slimer.alive():
            self.gate3_open = True
            if self.gate3_rect in self.game.game_map.collisions:
                self.game.game_map.collisions.remove(self.gate3_rect)
            if player.player_hp >= 100:
                player.player_hp = 75
                self.game.hud.player_display_hp = 75.0
            get_audio().play_sfx("level_clear")
            player.status_text = "COMBAT TRIAL COMPLETE! HEAD TO SHRINE >>"
            player.status_timer = 1.4

    def get_current_stage_info(self, player_x):
        if player_x < 620:
            return (
                "ZONE 1 / 5 : MOVE, JUMP, DROP-THROUGH & DASH",
                "[A/D] Move  |  [SPACE] Jump  |  [S+SPACE] Drop Down  |  [Q] Dash",
                "Jump and press [Q] to Dash across the wide 200px chasm ahead!",
                False,
            )
        if player_x < 1480:
            if not self.gate1_open:
                return (
                    "ZONE 2 / 5 : BASIC ATTACK TRAINING",
                    "Press [Left Click] to Destroy the Training Dummy and Open Gate 1!",
                    "Combine [A/D] movement with crisp melee strikes.",
                    False,
                )
            return (
                "ZONE 2 / 5 : AERIAL DOWNWARD SLASH (POGO x2)",
                "In Mid-Air: Hold [S / DOWN] + [Left Click] to Bounce off Both Glowing Orbs!",
                "You can Pogo Bounce up to 2 times in mid-air (and Pogo refreshes your [Q] Air Dash!).",
                False,
            )
        if player_x < 2160:
            return (
                "ZONE 3 / 5 : PERFECT PARRY PRACTICE",
                "Press [Right Click] Right Before the Turret's Bolt Hits to Trigger PERFECT PARRY!",
                f"Land {self.turret.parries_required} Perfect Parries to shatter the turret and unlock Zone 4.",
                self.gate2_open,
            )
        if player_x < 2660:
            return (
                "ZONE 4 / 5 : LIVE COMBAT TRIAL (SLIMER)",
                "Defeat the Slimer! Attack, Pogo, Parry, [Q] Dash & Press [R] on Ground for Healing Flask!",
                "Put everything you learned together (+20% HP per Flask, refilled at Shrines).",
                self.gate3_open,
            )
        return (
            "ZONE 5 / 5 : SHRINE & DIMENSIONAL ANOMALY",
            "Press [E] at the Shrine to Save & Heal  |  Advance Right to Enter the Dimensional Rift!",
            "A strange spatial distortion awaits ahead... step forward to begin Stage 1.",
            True,
        )

    def draw_world_elements(self, surface, camera_x, camera_y):
        # 1. Signposts (cached signpost.png + crisp pixel labels)
        signposts = [
            (130, 640, "[A/D] Move | [SPACE] Jump"),
            (345, 640, "Jump + [Q] Dash Across!"),
            (700, 640, "[Left Click] Attack Dummy"),
            (1095, 640, "Air [S + Left Click] Pogo x2"),
            (1640, 640, "[Right Click] Perfect Parry"),
            (2220, 640, "COMBAT TRIAL: Defeat Slimer!"),
        ]
        for wx, wy, label in signposts:
            sx = int(wx - camera_x)
            sy = int(wy - camera_y)
            surface.blit(self.sign_img, self.sign_img.get_rect(midbottom=(sx, sy)))
            draw_floating_prompt_box(
                surface, wx, wy - 60, camera_x, camera_y, label, self.font
            )

        # 2. Chasm & Pogo Pit Hazard Spikes
        for spike_start, spike_end, spike_y in ((428, 612, 728), (1148, 1472, 728)):
            for sx_w in range(spike_start, spike_end, 16):
                sx = int(sx_w - camera_x)
                sy = int(spike_y - camera_y)
                pygame.draw.polygon(
                    surface, (215, 55, 70), [(sx, sy), (sx + 8, sy - 16), (sx + 16, sy)]
                )
                pygame.draw.polygon(
                    surface, (255, 190, 195), [(sx + 3, sy), (sx + 8, sy - 11), (sx + 13, sy)], 1
                )

        # 3. Energy Gates
        for gate_rect, is_open, lbl_txt in (
            (self.gate1_rect, self.gate1_open, "HIT DUMMY"),
            (self.gate2_rect, self.gate2_open, "PARRY x2"),
            (self.gate3_rect, self.gate3_open, "DEFEAT SLIMER"),
        ):
            if not is_open:
                gr = gate_rect.move(-camera_x, -camera_y)
                glow = pygame.Surface((gr.width, gr.height), pygame.SRCALPHA)
                glow.fill((255, 75, 85, 130))
                surface.blit(glow, gr.topleft)
                pygame.draw.rect(surface, (255, 130, 135), gr, 2)
                t_surf = self.font.render(lbl_txt, False, (255, 220, 220))
                surface.blit(t_surf, t_surf.get_rect(center=(gr.centerx, gr.top - 12)))

        # 4. Target UI overlays
        self.dummy.draw_ui(surface, camera_x, camera_y, self.font)
        self.turret.draw_ui(surface, camera_x, camera_y, self.font)

    def draw_hud_banner(self, screen, hud):
        title, primary, secondary, done = self.get_current_stage_info(self.game.player.pos_x)
        bw, bh = 860, 74
        bx = (screen.get_width() - bw) // 2
        by = 18
        panel = pygame.Surface((bw, bh), pygame.SRCALPHA)
        panel.fill((14, 18, 30, 215))
        screen.blit(panel, (bx, by))
        border_col = (85, 245, 155) if done else (85, 225, 255)
        pygame.draw.rect(screen, border_col, (bx, by, bw, bh), 2, border_radius=5)

        t_surf = hud.font_hud.render(title, False, border_col)
        p_surf = hud.font_hud.render(primary, False, (255, 255, 255))
        s_surf = hud.font_hud.render(secondary, False, (185, 200, 225))
        screen.blit(t_surf, t_surf.get_rect(center=(bx + bw // 2, by + 16)))
        screen.blit(p_surf, p_surf.get_rect(center=(bx + bw // 2, by + 38)))
        screen.blit(s_surf, s_surf.get_rect(center=(bx + bw // 2, by + 58)))
