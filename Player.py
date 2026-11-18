import math
import random
import pygame
from Animator import AnimatedSprite
from Settings import (
    GROUND_Y,
    GRAVITY,
    PLAYER_JUMP_VELOCITY,
    PLAYER_SPEED,
    PLAYER_POGO_VELOCITY,
    PLAYER_AIR_STAY_DURATION,
    PLAYER_AIR_STAY_GRAVITY_SCALE,
    MAX_POGO_BOUNCES,
    PARRY_WINDOW,
    PARRY_COOLDOWN,
    PARRY_BUFF_MULTIPLIER,
    PARRY_BUFF_DURATION,
    BLOCK_DAMAGE_FACTOR,
    BLOCK_KNOCKBACK_SPEED,
    PLAYER_IFRAME_DURATION,
)
from VFX import Hitbox, SlashVFX, DownSlashVFX, PogoBounceVFX, ParrySparkVFX


class Player(pygame.sprite.Sprite):
    def __init__(self, start_x=260, ground_y=GROUND_Y):
        super().__init__()

        # Base stats & attributes
        self.max_hp = 100
        self.player_hp = 100
        self.player_stamina = 100
        self.player_speed = PLAYER_SPEED
        self.base_attack_damage = 12

        # Fixed jump height, gravity, Pogo bounce & Drop-Through platform state
        self.jump_velocity = PLAYER_JUMP_VELOCITY
        self.player_jump_power = PLAYER_JUMP_VELOCITY
        self.gravity = GRAVITY
        self.velocity_y = 0.0
        self.knockback_vel_x = 0.0
        self.ground_y = ground_y
        self.game_map = None
        self.air_stay_timer = 0.0          # Low-gravity hover timer after Pogo hit
        self.pogo_bounce_count = 0         # Consecutive Pogo bounces in current airborne state (max 2)
        self.on_one_way_platform = False   # True when standing on a One-Way / Drop-Through platform
        self.drop_through_timer = 0.0      # > 0 ignores one-way platforms to drop down (S/DOWN + Jump)

        # State flags
        self.on_ground = True
        self.is_jumping = False
        self.is_attacking = False
        self.is_down_slashing = False
        self.is_teleporting = False
        self.flip = False
        self.god_mode = False

        # Defense, Perfect Parry & 1.5s Duration-Based 1.35x Damage Buff
        self.is_blocking = False
        self.parry_timer = 0.0
        self.parry_cooldown = 0.0
        self.parry_damage_buff = False
        self.parry_buff_timer = 0.0
        self.damage_multiplier = 1.0
        self.active_attack_multiplier = 1.0
        self.neon_aura_timer = 0.0

        self.invincible_timer = 0.0
        self.status_text = ""
        self.status_timer = 0.0

        # Cached surfaces & queues for performance optimization (zero per-frame Surface allocation)
        self.afterimages = []
        self.afterimage_spawn_timer = 0.0
        self.buff_particles = []
        self._aura_cache = {}
        self._aura_low_surf = pygame.Surface((38, 36), pygame.SRCALPHA)
        self._particle_surf_cache = {}

        # Animation speeds (60 FPS baseline)
        self.animation_speed = {
            "Run": 0.20,
            "idle": 0.12,
            "Attack": 0.28,
            "AirDownAttack": 0.30,
            "Jump": 0.18,
        }

        # Non-transparent bounding box offsets per animation state
        self.sprite_offsets = {
            "idle": (1.0, 22.0),
            "Run": (13.0, 18.0),
            "Attack": (6.0, 22.0),
            "AirDownAttack": (-6.0, 8.0),
            "Jump": (-9.0, 3.0),
        }

        self.animator = AnimatedSprite()
        self.animator.load_animation(
            "idle",
            "asset/Legacy-Fantasy - High Forest 2.3/Character/Idle/Idle-Sheet.png",
            4,
            1.2,
        )
        self.animator.load_animation(
            "Run",
            "asset/Legacy-Fantasy - High Forest 2.3/Character/Run/Run-Sheet.png",
            8,
            1.2,
        )
        self.animator.load_animation(
            "Attack",
            "asset/Legacy-Fantasy - High Forest 2.3/Character/Attack-01/Attack-01-Sheet.png",
            8,
            1.2,
        )
        self.animator.load_animation(
            "Jump",
            "asset/Legacy-Fantasy - High Forest 2.3/Character/Jump-Start/Jump-Start-Sheet.png",
            4,
            1.2,
        )
        self._build_air_down_attack_animation()

        self.animator.play("idle")
        self.image = self.animator.update_get_image(self.animation_speed["idle"])

        # Unified ground anchor & separated collision / hurt / parry boxes
        self.pos_x = float(start_x)
        self.pos_y = float(ground_y)

        self.collision_rect = pygame.Rect(0, 0, 30, 54)
        self.hurtbox = pygame.Rect(0, 0, 24, 50)
        self.parry_box = pygame.Rect(0, 0, 38, 54)
        self.current_attack_hitbox = None
        self.spawned_hitbox_this_swing = False

        self.rect = self.image.get_rect()
        self.sync_boxes()

    def _build_air_down_attack_animation(self):
        jump_frames = self.animator.animation["Jump"]
        air_base_a = jump_frames[2]
        air_base_b = jump_frames[3]
        fw, fh = air_base_a.get_size()

        down_frames = []
        frame_specs = [
            (air_base_b, -3, -45, False, 0.0),
            (air_base_b, -4, 15, False, 0.0),
            (air_base_a, 1, 72, True, 0.25),
            (air_base_a, 3, 92, True, 0.55),
            (air_base_a, 2, 108, True, 0.80),
            (air_base_a, 1, 118, True, 1.00),
            (air_base_b, 0, 95, False, 0.0),
            (air_base_b, 0, 80, False, 0.0),
        ]

        for base_surf, dy, sword_deg, show_arc, arc_p in frame_specs:
            canvas = pygame.Surface((fw, fh), pygame.SRCALPHA)
            canvas.blit(base_surf, (0, dy))

            low_w, low_h = fw // 2, fh // 2
            overlay_low = pygame.Surface((low_w, low_h), pygame.SRCALPHA)

            hand_x = low_w // 2 - 4
            hand_y = low_h // 2 + 2 + (dy // 2)
            rad = math.radians(sword_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)

            blade_len = 16
            tip_x = hand_x + cos_a * blade_len
            tip_y = hand_y + sin_a * blade_len

            pygame.draw.line(
                overlay_low,
                (65, 75, 95, 255),
                (int(hand_x), int(hand_y)),
                (int(tip_x), int(tip_y)),
                3,
            )
            pygame.draw.line(
                overlay_low,
                (230, 240, 255, 255),
                (int(hand_x), int(hand_y)),
                (int(tip_x), int(tip_y)),
                1,
            )
            perp_x, perp_y = -sin_a * 3.0, cos_a * 3.0
            pygame.draw.line(
                overlay_low,
                (235, 180, 40, 255),
                (int(hand_x - perp_x), int(hand_y - perp_y)),
                (int(hand_x + perp_x), int(hand_y + perp_y)),
                2,
            )

            if show_arc:
                arc_pts_out = []
                arc_pts_in = []
                a_start = 0.15 * math.pi + arc_p * 0.20 * math.pi
                a_end = min(0.92 * math.pi, a_start + 0.52 * math.pi)
                steps = 7
                ox, oy = low_w * 0.46, low_h * 0.56
                rx, ry = 17.0, 18.0
                for s in range(steps + 1):
                    ang = a_start + (a_end - a_start) * (s / steps)
                    arc_pts_out.append((ox + math.cos(ang) * rx, oy + math.sin(ang) * ry))
                    arc_pts_in.append(
                        (ox + math.cos(ang) * (rx * 0.65), oy + math.sin(ang) * (ry * 0.62))
                    )
                poly = arc_pts_out + list(reversed(arc_pts_in))
                if len(poly) >= 3:
                    pygame.draw.polygon(overlay_low, (235, 245, 255, 190), poly)
                    pygame.draw.lines(
                        overlay_low, (255, 215, 90, 235), False, arc_pts_out, 1
                    )

            overlay_hi = pygame.transform.scale(overlay_low, (fw, fh))
            canvas.blit(overlay_hi, (0, 0))
            down_frames.append(canvas)

        self.animator.animation["AirDownAttack"] = down_frames

    @property
    def facing_dir(self):
        return -1 if self.flip else 1

    @property
    def is_parrying(self):
        return self.is_blocking and self.parry_timer > 0.0

    @property
    def is_grounded(self):
        return self.on_ground

    @is_grounded.setter
    def is_grounded(self, val):
        self.on_ground = bool(val)

    def teleport(self, x, y):
        """Safely teleport player to target world coordinates"""
        self.pos_x = float(x)
        self.pos_y = float(y)
        self.velocity_y = 0.0
        self.knockback_vel_x = 0.0
        self.on_ground = False
        self.on_one_way_platform = False
        self.drop_through_timer = 0.0
        self.is_jumping = False
        self.is_down_slashing = False
        self.air_stay_timer = 0.0
        self.pogo_bounce_count = 0
        self._clear_attack_hitbox()
        self.sync_boxes()

    def full_heal(self):
        self.player_hp = self.max_hp

    def reset_state_on_respawn(self, spawn_x=None, spawn_y=None):
        if spawn_x is not None and spawn_y is not None:
            self.pos_x = float(spawn_x)
            self.pos_y = float(spawn_y)
        self.player_hp = self.max_hp
        self.velocity_y = 0.0
        self.knockback_vel_x = 0.0
        self.on_ground = True
        self.on_one_way_platform = False
        self.drop_through_timer = 0.0
        self.is_jumping = False
        self.is_attacking = False
        self.is_down_slashing = False
        self.is_blocking = False
        self.is_teleporting = False
        self.parry_timer = 0.0
        self.parry_cooldown = 0.0
        self.parry_damage_buff = False
        self.parry_buff_timer = 0.0
        self.damage_multiplier = 1.0
        self.active_attack_multiplier = 1.0
        self.neon_aura_timer = 0.0
        self.invincible_timer = 0.50
        self.air_stay_timer = 0.0
        self.pogo_bounce_count = 0
        self.afterimages.clear()
        self.buff_particles.clear()
        self._clear_attack_hitbox()
        self.animator.play("idle", force_reset=True)
        self.image = self.animator.update_get_image(
            self.animation_speed["idle"], dt_scale=0.0
        )
        self.sync_boxes()

    def jump(self, down_pressed=None):
        """
        Fixed-height jump & One-Way Platform Drop-Through:
        - If standing on a One-Way Platform (on_ground and on_one_way_platform) while holding S / DOWN:
          starts drop_through_timer = 0.25s and drops smoothly through the platform!
        - Otherwise, if on_ground: launches upward with fixed velocity -jump_velocity.
        """
        if down_pressed is None:
            keys = pygame.key.get_pressed()
            down_pressed = bool(keys[pygame.K_s] or keys[pygame.K_DOWN])

        if self.on_ground and self.on_one_way_platform and down_pressed:
            self.drop_through_timer = 0.25
            self.on_ground = False
            self.on_one_way_platform = False
            self.is_jumping = True
            self.air_stay_timer = 0.0
            self.pogo_bounce_count = 0
            self.velocity_y = 140.0
            self.pos_y += 3.0
            self.animator.play("Jump", force_reset=True)
            return

        if self.on_ground:
            self.velocity_y = -self.jump_velocity
            self.on_ground = False
            self.on_one_way_platform = False
            self.is_jumping = True
            self.air_stay_timer = 0.0
            self.pogo_bounce_count = 0
            self.animator.play("Jump", force_reset=True)

    def start_block(self):
        if self.is_attacking:
            self.is_attacking = False
            self.is_down_slashing = False
            self._clear_attack_hitbox()

        if not self.is_blocking:
            self.is_blocking = True
            if self.parry_cooldown <= 0.0:
                self.parry_timer = PARRY_WINDOW
            else:
                self.parry_timer = 0.0

    def stop_block(self):
        if self.is_blocking:
            self.is_blocking = False
            self.parry_timer = 0.0
            self.parry_cooldown = PARRY_COOLDOWN

    def attack(self, down_pressed=None):
        if not self.is_attacking and not self.is_blocking:
            if down_pressed is None:
                keys = pygame.key.get_pressed()
                down_pressed = bool(keys[pygame.K_s] or keys[pygame.K_DOWN])

            self.is_attacking = True
            self.is_down_slashing = (not self.on_ground) and down_pressed
            self.spawned_hitbox_this_swing = False

            self.active_attack_multiplier = (
                self.damage_multiplier if self.parry_damage_buff else 1.0
            )
            anim_name = "AirDownAttack" if self.is_down_slashing else "Attack"
            self.animator.play(anim_name, force_reset=True)

    def on_pogo_hit(self, vfx_group=None):
        if self.pogo_bounce_count < MAX_POGO_BOUNCES:
            self.pogo_bounce_count += 1
            self.velocity_y = -PLAYER_POGO_VELOCITY
            self.air_stay_timer = PLAYER_AIR_STAY_DURATION
            self.on_ground = False
            self.on_one_way_platform = False
            self.is_jumping = True

            if vfx_group is not None:
                vfx_group.add(PogoBounceVFX(self.pos_x, self.pos_y + 10))

            self.status_text = (
                f"POGO BOUNCE! ({self.pogo_bounce_count}/{MAX_POGO_BOUNCES})"
            )
            self.status_timer = 0.65
        else:
            self.status_text = "MAX POGO LIMIT (2/2)"
            self.status_timer = 0.55

    def _clear_attack_hitbox(self):
        if self.current_attack_hitbox is not None:
            self.current_attack_hitbox.destroy()
            self.current_attack_hitbox = None

    def sync_boxes(self):
        anchor_x = int(round(self.pos_x))
        anchor_y = int(round(self.pos_y))
        f_dir = self.facing_dir

        self.collision_rect.midbottom = (anchor_x, anchor_y)
        self.hurtbox.midbottom = (anchor_x, anchor_y - 2)
        self.parry_box.center = (anchor_x + f_dir * 20, anchor_y - 27)

        anim_state = self.animator.current_state or "idle"
        body_dx, bottom_pad = self.sprite_offsets.get(anim_state, (0.0, 22.0))
        self.rect = self.image.get_rect()
        self.rect.centerx = int(round(self.pos_x - f_dir * body_dx))
        self.rect.bottom = int(round(self.pos_y + bottom_pad))

    def update_attack_hitbox(self, active_hitboxes, vfx_group):
        if not self.is_attacking or self.animator.current_state not in (
            "Attack",
            "AirDownAttack",
        ):
            self._clear_attack_hitbox()
            return

        frame = self.animator.current_frames
        if 1.2 <= frame <= 5.8:
            is_buffed = (
                self.parry_damage_buff or self.active_attack_multiplier > 1.0
            )
            mult = (
                PARRY_BUFF_MULTIPLIER
                if is_buffed
                else self.active_attack_multiplier
            )
            final_damage = round(self.base_attack_damage * mult, 2)

            if self.is_down_slashing:
                down_offset_y = 20.0
                hb_cx = int(round(self.pos_x))
                hb_cy = int(round(self.pos_y + down_offset_y))

                if not self.spawned_hitbox_this_swing:
                    self.spawned_hitbox_this_swing = True

                    hb_rect = pygame.Rect(0, 0, 80, 60)
                    hb_rect.center = (hb_cx, hb_cy)
                    hb = Hitbox(
                        owner="player",
                        rect=hb_rect,
                        damage=final_damage,
                        knockback_x=self.facing_dir * 140.0,
                        lifetime=None,
                        tag="player_down_slash",
                    )
                    self.current_attack_hitbox = hb
                    active_hitboxes.append(hb)

                    down_vfx = DownSlashVFX(
                        anchor_entity=self,
                        vertical_offset=down_offset_y,
                        width=84,
                        height=64,
                        duration=0.20,
                        buffed=is_buffed,
                        hitbox=hb,
                    )
                    vfx_group.add(down_vfx)
                elif self.current_attack_hitbox and self.current_attack_hitbox.active:
                    self.current_attack_hitbox.rect.center = (hb_cx, hb_cy)
            else:
                forward_dist = 36.0
                vertical_off = -28.0
                hb_cx = int(round(self.pos_x + self.facing_dir * forward_dist))
                hb_cy = int(round(self.pos_y + vertical_off))

                if not self.spawned_hitbox_this_swing:
                    self.spawned_hitbox_this_swing = True

                    hb_w = 84 if is_buffed else 72
                    hb_h = 62 if is_buffed else 56
                    hb_rect = pygame.Rect(0, 0, hb_w, hb_h)
                    hb_rect.center = (hb_cx, hb_cy)
                    kb = self.facing_dir * (280.0 if is_buffed else 220.0)
                    hb = Hitbox(
                        owner="player",
                        rect=hb_rect,
                        damage=final_damage,
                        knockback_x=kb,
                        lifetime=None,
                        tag="player_slash",
                    )
                    self.current_attack_hitbox = hb
                    active_hitboxes.append(hb)

                    slash_vfx = SlashVFX(
                        anchor_entity=self,
                        forward_offset=forward_dist,
                        vertical_offset=vertical_off,
                        width=hb_w + 6,
                        height=hb_h + 6,
                        flip=self.flip,
                        duration=0.22,
                        color_outer=(255, 200, 70),
                        color_inner=(255, 255, 220),
                        buffed=is_buffed,
                        hitbox=hb,
                    )
                    vfx_group.add(slash_vfx)
                elif self.current_attack_hitbox and self.current_attack_hitbox.active:
                    self.current_attack_hitbox.rect.center = (hb_cx, hb_cy)
        else:
            self._clear_attack_hitbox()

    def attack_hitbox(self, enemies_group, screen):
        if self.is_attacking and 1.2 <= self.animator.current_frames <= 5.8:
            attack_rect = pygame.Rect(0, 0, 72, 56)
            attack_rect.center = (
                int(round(self.pos_x + self.facing_dir * 36)),
                int(round(self.pos_y - 28)),
            )
            pygame.draw.rect(screen, (250, 0, 0), attack_rect, 2)
            for enemy in enemies_group:
                if attack_rect.colliderect(enemy.hurtbox):
                    enemy.be_attacked()

    def take_hit(self, hitbox, attacker=None, vfx_group=None):
        if self.is_teleporting:
            return "ignored"

        spark_x = (
            self.parry_box.centerx if self.is_blocking else self.hurtbox.centerx
        )
        spark_y = self.hurtbox.centery

        if self.is_blocking:
            if attacker is not None:
                self.flip = attacker.pos_x < self.pos_x
                self.sync_boxes()
                spark_x = self.parry_box.centerx

            if self.is_parrying:
                self.parry_timer = 0.0
                self.parry_cooldown = 0.0
                self.invincible_timer = 0.35
                self.parry_damage_buff = True
                self.parry_buff_timer = PARRY_BUFF_DURATION
                self.damage_multiplier = PARRY_BUFF_MULTIPLIER
                self.neon_aura_timer = 0.85
                self.status_text = "PERFECT PARRY!"
                self.status_timer = 0.95

                if vfx_group is not None:
                    vfx_group.add(
                        ParrySparkVFX(
                            spark_x,
                            spark_y - 2,
                            perfect=True,
                            facing_dir=self.facing_dir,
                            ground_y=self.pos_y,
                        )
                    )
                if self.god_mode:
                    print(
                        f"[DEBUG GOD MODE] Perfect Parry against '{hitbox.tag}'! 1.35x Damage Buff activated."
                    )
                return "parry"
            else:
                reduced_dmg = max(1, int(round(hitbox.damage * BLOCK_DAMAGE_FACTOR)))
                if not self.god_mode:
                    self.player_hp = max(0, self.player_hp - reduced_dmg)
                    self.status_text = f"BLOCKED (-{reduced_dmg})"
                else:
                    self.status_text = "BLOCKED [GOD MODE: 0 DMG]"
                    print(
                        f"[DEBUG GOD MODE] Normal Block against '{hitbox.tag}'! Prevented {reduced_dmg} DMG."
                    )

                self.invincible_timer = 0.25
                push_dir = -1 if (attacker and attacker.pos_x > self.pos_x) else 1
                self.knockback_vel_x = push_dir * BLOCK_KNOCKBACK_SPEED
                self.status_timer = 0.65
                if vfx_group is not None:
                    vfx_group.add(
                        ParrySparkVFX(
                            spark_x,
                            spark_y,
                            perfect=False,
                            facing_dir=self.facing_dir,
                            ground_y=self.pos_y,
                        )
                    )
                return "block"

        if self.invincible_timer > 0.0:
            return "ignored"

        if not self.god_mode:
            self.player_hp = max(0, self.player_hp - int(round(hitbox.damage)))
            self.status_text = f"-{int(round(hitbox.damage))} HP"
        else:
            self.status_text = "HIT! [GOD MODE: 0 DMG]"
            print(
                f"[DEBUG GOD MODE] Hurtbox hit by '{hitbox.tag}'! Prevented {hitbox.damage} DMG."
            )

        self.invincible_timer = PLAYER_IFRAME_DURATION
        push_dir = -1 if (attacker and attacker.pos_x > self.pos_x) else 1
        self.knockback_vel_x = push_dir * (BLOCK_KNOCKBACK_SPEED * 0.85)
        self.status_timer = 0.60
        return "hit"

    def _apply_parry_pixel_aura(self, base_image):
        """
        Cached dual-color pixel aura outline (avoids recomputing mask & scale on identical frames).
        """
        is_strong = self.neon_aura_timer > 0.0
        cache_key = (id(base_image), self.flip, is_strong)
        cached = self._aura_cache.get(cache_key)
        if cached is not None:
            return cached

        w, h = base_image.get_size()
        padded = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
        mask = pygame.mask.from_surface(base_image)

        if is_strong:
            gold_silhouette = mask.to_surface(
                setcolor=(255, 205, 45, 225), unsetcolor=(0, 0, 0, 0)
            )
            cyan_silhouette = mask.to_surface(
                setcolor=(45, 230, 255, 225), unsetcolor=(0, 0, 0, 0)
            )
            padded.blit(gold_silhouette, (1, 2))
            padded.blit(gold_silhouette, (2, 1))
            padded.blit(cyan_silhouette, (5, 3))
            padded.blit(cyan_silhouette, (4, 5))

            lit_body = base_image.copy()
            lit_body.fill((25, 65, 130), special_flags=pygame.BLEND_RGB_ADD)
            padded.blit(lit_body, (3, 3))
        else:
            soft_gold = mask.to_surface(
                setcolor=(255, 200, 55, 115), unsetcolor=(0, 0, 0, 0)
            )
            soft_cyan = mask.to_surface(
                setcolor=(50, 215, 255, 115), unsetcolor=(0, 0, 0, 0)
            )
            padded.blit(soft_gold, (2, 2))
            padded.blit(soft_cyan, (4, 4))
            padded.blit(base_image, (3, 3))

        result = pygame.transform.scale(padded, (w, h))
        if len(self._aura_cache) > 64:
            self._aura_cache.clear()
        self._aura_cache[cache_key] = result
        return result

    def draw_extras(self, screen, camera_x=0, camera_y=0):
        if self.neon_aura_timer > 0.0:
            aura_scale = 3
            lw, lh = 38, 36
            low_aura = self._aura_low_surf
            low_aura.fill((0, 0, 0, 0))
            cx, cy = lw // 2, lh - 5
            t_phase = self.neon_aura_timer * 18.0

            for i in range(7):
                ang = math.pi + (i / 6.0) * math.pi
                fx = int(cx + math.cos(ang) * 11)
                fy = int(cy - 9 + math.sin(ang) * 12)
                pygame.draw.circle(low_aura, (10, 22, 76, 220), (fx, fy), 5)

            for i in range(9):
                ox = (i - 4) * 3
                flame_h = int(12 + 7 * math.sin(t_phase + i * 1.3))
                col = (255, 200, 40, 235) if i % 2 == 0 else (40, 225, 255, 235)
                pts = [
                    (cx + ox - 3, cy),
                    (cx + ox + int(2 * math.sin(t_phase + i)), cy - flame_h),
                    (cx + ox + 3, cy),
                ]
                pygame.draw.polygon(low_aura, col, pts)

            for bx_off, by_off in [(-13, -10), (-15, -18), (-11, -24), (12, -16)]:
                pygame.draw.circle(
                    low_aura,
                    (90, 235, 255, 220),
                    (cx - self.facing_dir * abs(bx_off), cy + by_off),
                    2,
                    1,
                )

            hi_aura = pygame.transform.scale(
                low_aura, (lw * aura_scale, lh * aura_scale)
            )
            sx = int(self.pos_x - camera_x - (lw * aura_scale) // 2)
            sy = int(self.pos_y - camera_y - (lh - 4) * aura_scale)
            screen.blit(hi_aura, (sx, sy))

        for surf, rect, alpha in self.afterimages:
            ghost = surf.copy()
            ghost.set_alpha(int(alpha))
            screen.blit(ghost, rect.move(-camera_x, -camera_y))

        for px, py, pr, col, alpha in self.buff_particles:
            sx = int(px - camera_x)
            sy = int(py - camera_y)
            q_alpha = max(16, (int(alpha) // 16) * 16)
            pkey = (pr, col, q_alpha)
            p_surf = self._particle_surf_cache.get(pkey)
            if p_surf is None:
                p_surf = pygame.Surface((pr * 2, pr * 2), pygame.SRCALPHA)
                p_surf.fill((*col, q_alpha))
                self._particle_surf_cache[pkey] = p_surf
            screen.blit(p_surf, (sx - pr, sy - pr))

    def update(
        self,
        dt=1 / 60,
        raw_dt=None,
        active_hitboxes=None,
        vfx_group=None,
        map_width=1600,
    ):
        if raw_dt is None:
            raw_dt = dt

        # 1. Update timers
        if self.parry_timer > 0.0:
            self.parry_timer = max(0.0, self.parry_timer - raw_dt)
        if self.parry_cooldown > 0.0:
            self.parry_cooldown = max(0.0, self.parry_cooldown - raw_dt)
        if self.invincible_timer > 0.0:
            self.invincible_timer = max(0.0, self.invincible_timer - dt)
        if self.status_timer > 0.0:
            self.status_timer = max(0.0, self.status_timer - raw_dt)
        if self.neon_aura_timer > 0.0:
            self.neon_aura_timer = max(0.0, self.neon_aura_timer - raw_dt)
        if self.air_stay_timer > 0.0:
            self.air_stay_timer = max(0.0, self.air_stay_timer - raw_dt)
        if self.drop_through_timer > 0.0:
            self.drop_through_timer = max(0.0, self.drop_through_timer - raw_dt)

        # 1.5s 1.35x Parry Damage Buff countdown (ticks down after slow-motion ends)
        if self.parry_buff_timer > 0.0:
            if dt >= raw_dt * 0.95:
                self.parry_buff_timer = max(0.0, self.parry_buff_timer - raw_dt)
            if self.parry_buff_timer > 0.0:
                self.parry_damage_buff = True
                self.damage_multiplier = PARRY_BUFF_MULTIPLIER
            else:
                self.parry_damage_buff = False
                self.damage_multiplier = 1.0

        if self.is_teleporting:
            self.velocity_y = 0.0
            self.knockback_vel_x = 0.0
            self.is_attacking = False
            self.is_blocking = False
            self._clear_attack_hitbox()
            self.animator.play("idle")
            self.image = self.animator.update_get_image(
                self.animation_speed["idle"], dt_scale=dt * 60.0
            )
            if self.flip:
                self.image = pygame.transform.flip(self.image, True, False)
            self.image = self.image.copy()
            self.image.fill((70, 195, 255), special_flags=pygame.BLEND_RGB_ADD)
            self.sync_boxes()
            return

        # 2. Continuous input checks
        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        holding_block = (
            mouse_buttons[2]
            or keys[pygame.K_j]
            or keys[pygame.K_LSHIFT]
        )
        if not holding_block and self.is_blocking:
            self.stop_block()

        # 3. Horizontal movement & gravity
        is_moving = False
        move_speed = self.player_speed * (0.45 if self.is_blocking else 1.0)
        move_dir_x = 0.0

        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir_x -= 1.0
            is_moving = True
            if not self.is_attacking:
                self.flip = True

        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir_x += 1.0
            is_moving = True
            if not self.is_attacking:
                self.flip = False

        dx = move_dir_x * move_speed * dt
        if abs(self.knockback_vel_x) > 5.0:
            dx += self.knockback_vel_x * dt
            self.knockback_vel_x *= max(0.0, 1.0 - 10.0 * dt)
        else:
            self.knockback_vel_x = 0.0

        grav_scale = (
            PLAYER_AIR_STAY_GRAVITY_SCALE if self.air_stay_timer > 0.0 else 1.0
        )

        # 4. Map Collision Resolution (Solid Tiles, One-Way / Drop-Through Platforms & Polygons)
        has_map_geometry = bool(
            self.game_map
            and (
                getattr(self.game_map, "collisions", None)
                or getattr(self.game_map, "polygons", None)
                or getattr(self.game_map, "platforms", None)
            )
        )

        if has_map_geometry:
            self.velocity_y = min(
                self.velocity_y + (self.gravity * grav_scale) * dt, 900.0
            )
            dy = self.velocity_y * dt

            self.collision_rect.midbottom = (round(self.pos_x), round(self.pos_y))
            on_ground_now, hit_ceiling = self.game_map.move_with_collisions(
                self.collision_rect,
                dx,
                dy,
                drop_through=(self.drop_through_timer > 0.0),
            )
            self.on_one_way_platform = bool(
                getattr(self.game_map, "last_on_one_way", False)
            )

            if self.collision_rect.left < 25:
                self.collision_rect.left = 25
            elif self.collision_rect.right > map_width - 25:
                self.collision_rect.right = map_width - 25

            self.pos_x = float(self.collision_rect.centerx)
            self.pos_y = float(self.collision_rect.bottom)

            if on_ground_now and self.velocity_y >= 0.0:
                self.velocity_y = 0.0
                self.on_ground = True
                self.is_jumping = False
                self.is_down_slashing = False
                self.air_stay_timer = 0.0
                self.pogo_bounce_count = 0
            else:
                self.on_ground = on_ground_now
                if hit_ceiling and self.velocity_y < 0.0:
                    self.velocity_y = 0.0
        else:
            self.pos_x += dx
            self.pos_x = max(25.0, min(float(map_width - 25), self.pos_x))
            self.on_one_way_platform = False

            if not self.on_ground or self.velocity_y != 0.0:
                self.velocity_y += (self.gravity * grav_scale) * dt
                self.pos_y += self.velocity_y * dt

                if self.pos_y >= self.ground_y:
                    self.pos_y = float(self.ground_y)
                    self.velocity_y = 0.0
                    self.on_ground = True
                    self.is_jumping = False
                    self.is_down_slashing = False
                    self.air_stay_timer = 0.0
                    self.pogo_bounce_count = 0

        # 5. State & Animation update
        new_state = "idle"
        loop_anim = True

        if self.is_attacking:
            new_state = "AirDownAttack" if self.is_down_slashing else "Attack"
            loop_anim = False
        elif not self.on_ground:
            new_state = "Jump"
            loop_anim = False
        elif is_moving:
            new_state = "Run"

        current_fspeed = self.animation_speed[new_state]
        self.animator.play(new_state)
        dt_scale = dt * 60.0
        self.image = self.animator.update_get_image(
            current_fspeed, dt_scale=dt_scale, loop=loop_anim
        )

        if self.is_attacking and self.animator.finished:
            self.is_attacking = False
            self.is_down_slashing = False
            self.active_attack_multiplier = 1.0
            self._clear_attack_hitbox()
            fallback_state = "Jump" if not self.on_ground else "idle"
            self.animator.play(fallback_state, force_reset=self.on_ground)
            self.image = self.animator.update_get_image(
                self.animation_speed[fallback_state],
                dt_scale=0.0,
                loop=self.on_ground,
            )

        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False)
        self.sync_boxes()

        if active_hitboxes is not None and vfx_group is not None:
            self.update_attack_hitbox(active_hitboxes, vfx_group)

        # 6. Visual overlays
        if (
            self.neon_aura_timer > 0.0
            or self.parry_damage_buff
            or self.active_attack_multiplier > 1.0
        ):
            self.image = self._apply_parry_pixel_aura(self.image)
        elif self.is_parrying:
            self.image = self.image.copy()
            self.image.fill((60, 180, 220), special_flags=pygame.BLEND_RGB_ADD)
        elif self.is_blocking:
            self.image = self.image.copy()
            self.image.fill((30, 70, 150), special_flags=pygame.BLEND_RGB_ADD)
        elif self.invincible_timer > 0.0:
            if int(self.invincible_timer * 20) % 2 == 0:
                self.image = self.image.copy()
                self.image.set_alpha(130)

        # 7. Update afterimages & buff particles
        self.afterimages = [
            (s, r, a - 420.0 * raw_dt)
            for (s, r, a) in self.afterimages
            if a - 420.0 * raw_dt > 12
        ]
        if self.neon_aura_timer > 0.0 or self.air_stay_timer > 0.0:
            self.afterimage_spawn_timer += raw_dt
            if self.afterimage_spawn_timer >= 0.045:
                self.afterimage_spawn_timer = 0.0
                tint = self.image.copy()
                tint.fill((0, 140, 255), special_flags=pygame.BLEND_RGB_ADD)
                self.afterimages.append((tint, self.rect.copy(), 145.0))

        if self.parry_damage_buff:
            if random.random() < 0.45:
                px = self.pos_x + random.uniform(-15, 15)
                py = self.pos_y - random.uniform(4, 46)
                col = random.choice([(45, 225, 255), (255, 205, 50)])
                self.buff_particles.append([px, py, random.randint(2, 3), col, 175.0])

        updated_particles = []
        for p in self.buff_particles:
            p[1] -= 50.0 * raw_dt
            p[4] -= 340.0 * raw_dt
            if p[4] > 10.0:
                updated_particles.append(p)
        self.buff_particles = updated_particles
