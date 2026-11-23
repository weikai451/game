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
            and 2140 <= self.target.pos_x <= 2740
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


class SwitchCrystal:
    """Zone 1 floating glowing switch crystal above the One-Way Platform."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.activated = False
        self.timer = 0.0
        self.rect = pygame.Rect(0, 0, 36, 44)
        self.rect.center = (int(x), int(y))

    def update(self, dt, player):
        self.timer += dt
        if not self.activated and player is not None and player.alive():
            if self.rect.colliderect(player.collision_rect):
                self.activated = True
                get_audio().play_sfx("level_clear")
                return True
        return False

    def draw(self, surface, camera_x, camera_y, font):
        bob = math.sin(self.timer * 4.5) * 4.0
        sx = int(round(self.x - camera_x))
        sy = int(round(self.y + bob - camera_y))
        pts = [(sx, sy - 18), (sx + 13, sy), (sx, sy + 18), (sx - 13, sy)]
        fill_col = (85, 255, 165) if self.activated else (70, 220, 255)
        edge_col = (235, 255, 245)
        pygame.draw.polygon(surface, fill_col, pts)
        pygame.draw.polygon(surface, edge_col, pts, 2)
        lbl = "ACTIVATED" if self.activated else "TOUCH CRYSTAL"
        t_surf = font.render(lbl, False, fill_col)
        surface.blit(t_surf, t_surf.get_rect(center=(sx, sy - 28)))


class LaserBarrier:
    """
    Zone 2 continuous vertical laser barrier:
    - Walking into it knocks player back & deals 10 HP.
    - Pressing [Q] Dash (i-frames) phases cleanly straight through!
    """

    def __init__(self, x, top_y, bottom_y):
        self.x = float(x)
        self.top_y = float(top_y)
        self.bottom_y = float(bottom_y)
        self.rect = pygame.Rect(int(x - 10), int(top_y), 20, int(bottom_y - top_y))
        self.hit_cooldown = 0.0
        self.timer = 0.0

    def update(self, dt, player):
        self.timer += dt
        if self.hit_cooldown > 0.0:
            self.hit_cooldown = max(0.0, self.hit_cooldown - dt)
        if player is None or not player.alive():
            return
        if self.rect.colliderect(player.hurtbox):
            if getattr(player, "is_dashing", False):
                return
            if self.hit_cooldown <= 0.0:
                self.hit_cooldown = 0.55
                if not getattr(player, "god_mode", False):
                    player.player_hp = max(30, player.player_hp - 10)
                push_dir = -1 if player.pos_x < self.x else 1
                player.knockback_vel_x = push_dir * 320.0
                player.pos_x = (self.x - 28.0) if push_dir < 0 else (self.x + 28.0)
                player.sync_boxes()
                player.status_text = "USE [Q] DASH TO PHASE THROUGH LASER!"
                player.status_timer = 1.2
                get_audio().play_sfx("player_hurt")

    def draw(self, surface, camera_x, camera_y, font):
        sx = int(round(self.x - camera_x))
        ty = int(round(self.top_y - camera_y))
        by = int(round(self.bottom_y - camera_y))
        pulse = int(4 + 3 * abs(math.sin(self.timer * 14.0)))
        # Emitter caps
        pygame.draw.rect(surface, (75, 78, 95), (sx - 14, ty - 10, 28, 12))
        pygame.draw.rect(surface, (75, 78, 95), (sx - 14, by - 4, 28, 10))
        # Outer red glow + blazing white-orange core
        pygame.draw.line(surface, (235, 35, 65), (sx, ty), (sx, by), 10 + pulse)
        pygame.draw.line(surface, (255, 165, 80), (sx, ty), (sx, by), 5)
        pygame.draw.line(surface, (255, 248, 240), (sx, ty), (sx, by), 2)
        lbl = font.render("DASH THROUGH [Q]", False, (255, 150, 165))
        surface.blit(lbl, lbl.get_rect(center=(sx, ty - 22)))


class TestHazardSpikes:
    """
    Zone 6 retractable test spikes:
    - Deals 25 HP once on touch (clamped >= 30 HP) so player must practice [R] Flask,
      then smoothly retracts into the floor!
    """

    def __init__(self, start_x, end_x, ground_y):
        self.start_x = int(start_x)
        self.end_x = int(end_x)
        self.ground_y = int(ground_y)
        self.triggered = False
        self.retract_ratio = 0.0  # 0.0 = extended, 1.0 = retracted
        self.rect = pygame.Rect(self.start_x, self.ground_y - 20, self.end_x - self.start_x, 20)

    def update(self, dt, player):
        if self.triggered:
            self.retract_ratio = min(1.0, self.retract_ratio + dt * 2.6)
            return False
        if player is not None and player.alive() and self.rect.colliderect(player.hurtbox):
            self.triggered = True
            if not getattr(player, "god_mode", False):
                player.player_hp = max(30, min(player.player_hp - 25, 75))
            else:
                player.player_hp = min(player.player_hp, 75)
            player.invincible_timer = 0.45
            player.status_text = "OUCH! STAND STILL & PRESS [R] TO DRINK FLASK"
            player.status_timer = 1.8
            get_audio().play_sfx("player_hurt")
            return True
        return False

    def draw(self, surface, camera_x, camera_y):
        h = int(round(18 * (1.0 - self.retract_ratio)))
        if h <= 1:
            return
        for wx in range(self.start_x, self.end_x, 16):
            sx = int(wx - camera_x)
            sy = int(self.ground_y - camera_y)
            pygame.draw.polygon(surface, (225, 55, 75), [(sx, sy), (sx + 8, sy - h), (sx + 16, sy)])
            pygame.draw.polygon(
                surface, (255, 200, 205), [(sx + 3, sy), (sx + 8, sy - max(2, h - 4)), (sx + 13, sy)], 1
            )


class GuidedTutorialManager:
    """
    Comprehensive 7-Zone Progressive Tutorial Level (4864 x 768):
    - Zone 1 (0..620): Movement, Jump, One-Way Drop-Through + Switch Crystal -> Gate 1
    - Zone 2 (620..1240): [Q] Dash Chasm + Invincible Laser Barrier
    - Zone 3 (1240..1760): [Left Click] Basic Melee Attack vs Training Dummy -> Gate 2
    - Zone 4 (1760..2120): Aerial [S + Left Click] Downward Pogo x2 across Pit
    - Zone 5 (2120..2860): [Hold RMB] Guard & Tap Perfect Parry vs Parry Turret -> Gate 3
    - Zone 6 (2860..3480): Retractable Test Spikes + [R] Drink Flask -> Gate 4
    - Zone 7 (3480..4864): Dual Slimer Combat -> Gate 5 -> Checkpoint [E] Refill -> Indie Cross Rift!
    """

    def __init__(self, game):
        self.game = game
        self.font = get_pixel_font(16)
        self.sign_img = _load_tut_sprite("signpost.png", (48, 56))

        # Zone 1..7 interactive mechanisms & targets
        self.crystal = SwitchCrystal(x=430, y=472)
        self.laser = LaserBarrier(x=1120, top_y=440, bottom_y=640)
        self.dummy = TrainingDummy(x=1520, ground_y=640)
        self.orb_1 = PogoTargetOrb(x=1860, y=572)
        self.orb_2 = PogoTargetOrb(x=2000, y=508)
        self.turret = ParryTurret(target_player=game.player, x=2680, ground_y=544)
        self.test_spikes = TestHazardSpikes(start_x=3010, end_x=3090, ground_y=544)
        self.flask_practiced = False
        self._last_flask_count = getattr(game.player, "flasks", 3)

        self.slimer_1 = Slimer(
            target_player=game.player,
            start_x=3740,
            ground_y=544,
            game_map=game.game_map,
            patrol_range=95.0,
            max_hp=36,
            attack_damage=6,
        )
        self.slimer_2 = Slimer(
            target_player=game.player,
            start_x=3980,
            ground_y=544,
            game_map=game.game_map,
            patrol_range=95.0,
            max_hp=36,
            attack_damage=6,
        )

        # 5 Sequential Energy Gates
        self.gate1_rect = pygame.Rect(590, 440, 28, 200)
        self.gate1_open = False
        self.gate2_rect = pygame.Rect(1710, 440, 28, 200)
        self.gate2_open = False
        self.gate3_rect = pygame.Rect(2810, 344, 28, 200)
        self.gate3_open = False
        self.gate4_rect = pygame.Rect(3420, 344, 28, 200)
        self.gate4_open = False
        self.gate5_rect = pygame.Rect(4180, 344, 28, 200)
        self.gate5_open = False

        for g in (self.gate1_rect, self.gate2_rect, self.gate3_rect, self.gate4_rect, self.gate5_rect):
            self.game.game_map.collisions.append(g)

        self.game.regular_enemies.add(self.slimer_1, self.slimer_2)
        for ent in (self.dummy, self.orb_1, self.orb_2, self.turret, self.slimer_1, self.slimer_2):
            self.game.enemies.add(ent)
            self.game.all_sprites.add(ent)

        # Bind ParryTurret as game.boss so Perfect Parry / Block resolution works natively
        self.game.boss = self.turret

    def _open_gate(self, gate_rect, status_msg):
        if gate_rect in self.game.game_map.collisions:
            self.game.game_map.collisions.remove(gate_rect)
        get_audio().play_sfx("level_clear")
        self.game.player.status_text = status_msg
        self.game.player.status_timer = 1.4

    def update(self, scaled_dt):
        player = self.game.player
        if player.player_hp < 30:
            player.player_hp = 30

        self.dummy.update(scaled_dt)
        self.orb_1.update(scaled_dt)
        self.orb_2.update(scaled_dt)
        self.laser.update(scaled_dt, player)
        self.test_spikes.update(scaled_dt, player)

        # Zone 1: Switch Crystal -> Gate 1
        if self.crystal.update(scaled_dt, player) and not self.gate1_open:
            self.gate1_open = True
            self._open_gate(self.gate1_rect, "CRYSTAL ACTIVATED! DROP DOWN & ADVANCE >>")

        # Zone 2: Dash Chasm safety reset
        if 792 <= player.pos_x <= 1008 and player.pos_y >= 695:
            player.teleport(740, 640)
            player.status_text = "TRY AGAIN: Jump + Press [Q] to Dash Across!"
            player.status_timer = 1.4

        # Zone 3: Training Dummy -> Gate 2
        if not self.gate2_open and not self.dummy.alive():
            self.gate2_open = True
            self._open_gate(self.gate2_rect, "DUMMY DESTROYED! ADVANCE TO POGO PIT >>")

        # Zone 4: Pogo Pit safety reset
        if 1762 <= player.pos_x <= 2115 and player.pos_y >= 695:
            player.teleport(1720, 640)
            player.status_text = "TRY AGAIN: In Air Hold [S] + [Left Click] on Orbs!"
            player.status_timer = 1.4

        # Zone 5: Parry Turret (2 Perfect Parries) -> Gate 3
        if not self.gate3_open and not self.turret.alive():
            self.gate3_open = True
            self._open_gate(self.gate3_rect, "PARRY MASTERED! ADVANCE TO HEALING ZONE >>")

        # Zone 6: Detect drinking a Healing Flask -> Gate 4
        cur_flasks = getattr(player, "flasks", 3)
        if player.pos_x >= 2860:
            if (cur_flasks < self._last_flask_count and getattr(player, "drink_healed", False)) or (
                getattr(player, "drink_healed", False) and not self.flask_practiced
            ):
                self.flask_practiced = True
            if self.test_spikes.triggered and self.flask_practiced and not self.gate4_open:
                self.gate4_open = True
                self._open_gate(self.gate4_rect, "FLASK HEAL COMPLETE! ENTER FINAL TRIAL >>")
        self._last_flask_count = cur_flasks

        # Zone 7: Both Slimers defeated -> Gate 5 (unlocks Checkpoint & Rift Altar)
        if not self.gate5_open and not self.slimer_1.alive() and not self.slimer_2.alive():
            self.gate5_open = True
            self._open_gate(self.gate5_rect, "TRIAL COMPLETE! REST AT SHRINE [E] & ADVANCE >>")

    def get_current_stage_info(self, player_x):
        if player_x < 620:
            return (
                "ZONE 1 / 7 : MOVEMENT, JUMP & DROP-THROUGH",
                "[A / D] Move  |  [SPACE] Jump  |  [S + SPACE] Drop Down",
                "Jump onto the One-Way Platform and touch the glowing Switch Crystal to open Gate 1!",
                self.gate1_open,
            )
        if player_x < 1240:
            return (
                "ZONE 2 / 7 : DASH & INVINCIBILITY FRAMES",
                "Press [Q] to Dash Across the Chasm & Phase Through the Vertical Laser!",
                "Dash grants brief invincibility frames (i-frames) to pass straight through danger.",
                player_x > 1135,
            )
        if player_x < 1760:
            return (
                "ZONE 3 / 7 : BASIC MELEE SLASH",
                "Press [Left Click] Repeatedly to Destroy the Training Dummy!",
                "Shatter the Dummy blocking the path to unlock Gate 2.",
                self.gate2_open,
            )
        if player_x < 2120:
            return (
                "ZONE 4 / 7 : AERIAL DOWNWARD SLASH (POGO x2)",
                "In Mid-Air: Hold [S] + [Left Click] to Bounce off Both Glowing Pogo Orbs!",
                "Each Pogo bounce lifts you higher and refreshes your [Q] Air Dash.",
                False,
            )
        if player_x < 2860:
            return (
                "ZONE 5 / 7 : GUARD & PERFECT PARRY",
                "[Hold Right Click] Guard  |  Tap [Right Click] Before Hit: PERFECT PARRY!",
                f"Land {self.turret.parries_required} Perfect Parries to charge & unlock Gate 3.",
                self.gate3_open,
            )
        if player_x < 3480:
            return (
                "ZONE 6 / 7 : HEALING FLASK SYSTEM",
                "Stand on Ground & Press [R] to Drink Flask (+20% HP, Cannot Move While Drinking)",
                "Step over the test spikes, then press [R] to heal and open Gate 4!",
                self.gate4_open,
            )
        if player_x < 4200:
            return (
                "ZONE 7 / 7 : FINAL COMBAT TRIAL (2 SLIMERS)",
                "Defeat Both Slimers Using Slash, Pogo, Dash, Perfect Parry & Flasks!",
                "Clear both enemies to unlock the Checkpoint Shrine & Dimensional Rift.",
                self.gate5_open,
            )
        return (
            "ZONE 7 / 7 : SHRINE REFILL & DIMENSIONAL RIFT",
            "Press [E] at the Shrine (Full Heal + Refill 3 Flasks)  |  Walk Right to the Altar!",
            "Rest at the Checkpoint, then step onto the Dimensional Altar to begin your journey.",
            True,
        )

    def draw_world_elements(self, surface, camera_x, camera_y):
        # 1. Pixel Signposts across all 7 Zones (antialias=False)
        signposts = [
            (120, 640, "[A / D] Move | [SPACE] Jump"),
            (430, 512, "[S + SPACE] Drop Down"),
            (715, 640, "[Q] Dash (Invincible)"),
            (1350, 640, "[Left Click] Slash Attack"),
            (1640, 640, "In Air: [S + Left Click] Downward Pogo"),
            (2250, 544, "[Hold Right Click] Guard"),
            (2485, 544, "Tap Before Hit: Perfect Parry"),
            (3210, 544, "[R] Drink Flask (Heal 20% HP, Cannot Move)"),
            (3590, 544, "COMBAT TRIAL: Defeat 2 Slimers!"),
            (4360, 544, "[E] Save, Full Heal & Refill Flasks"),
        ]
        for wx, wy, label in signposts:
            sx = int(wx - camera_x)
            sy = int(wy - camera_y)
            surface.blit(self.sign_img, self.sign_img.get_rect(midbottom=(sx, sy)))
            draw_floating_prompt_box(
                surface, wx, wy - 60, camera_x, camera_y, label, self.font
            )

        # 2. Zone 1 Crystal, Zone 2 Laser Barrier, Zone 6 Retractable Test Spikes
        self.crystal.draw(surface, camera_x, camera_y, self.font)
        self.laser.draw(surface, camera_x, camera_y, self.font)
        self.test_spikes.draw(surface, camera_x, camera_y)

        # 3. Zone 2 Dash Chasm & Zone 4 Pogo Pit Hazard Spikes
        for spike_start, spike_end, spike_y in ((798, 1002, 728), (1768, 2112, 728)):
            for sx_w in range(spike_start, spike_end, 16):
                sx = int(sx_w - camera_x)
                sy = int(spike_y - camera_y)
                pygame.draw.polygon(
                    surface, (215, 55, 70), [(sx, sy), (sx + 8, sy - 16), (sx + 16, sy)]
                )
                pygame.draw.polygon(
                    surface, (255, 190, 195), [(sx + 3, sy), (sx + 8, sy - 11), (sx + 13, sy)], 1
                )

        # 4. 5 Sequential Energy Gates
        for gate_rect, is_open, lbl_txt in (
            (self.gate1_rect, self.gate1_open, "TOUCH CRYSTAL"),
            (self.gate2_rect, self.gate2_open, "BREAK DUMMY"),
            (self.gate3_rect, self.gate3_open, "PARRY x2"),
            (self.gate4_rect, self.gate4_open, "DRINK FLASK [R]"),
            (self.gate5_rect, self.gate5_open, "DEFEAT 2 SLIMERS"),
        ):
            if not is_open:
                gr = gate_rect.move(-camera_x, -camera_y)
                glow = pygame.Surface((gr.width, gr.height), pygame.SRCALPHA)
                glow.fill((255, 75, 85, 130))
                surface.blit(glow, gr.topleft)
                pygame.draw.rect(surface, (255, 130, 135), gr, 2)
                t_surf = self.font.render(lbl_txt, False, (255, 220, 220))
                surface.blit(t_surf, t_surf.get_rect(center=(gr.centerx, gr.top - 12)))

        # 5. Target UI overlays (Note: Zone 7 end rift trigger at x>=4620 is strictly INVISIBLE
        # so the sudden mid-air Dimensional Cross-Star Rift ambush feels completely unexpected!)
        self.dummy.draw_ui(surface, camera_x, camera_y, self.font)
        self.turret.draw_ui(surface, camera_x, camera_y, self.font)

    def draw_hud_banner(self, screen, hud):
        # Intentionally disabled: world pixel signposts provide clean, non-redundant guidance
        # without cluttering the top of the screen with blue mission text banners.
        return
