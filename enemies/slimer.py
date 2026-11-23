import os
import pygame
from Settings import GRAVITY, GROUND_Y
from VFX import Hitbox, SlimerDeathVFX


# Global cache for sliced, trimmed, and scaled Slimer frames (left-native & right-flipped)
_SLIMER_FRAME_CACHE = {}


def _load_slimer_frames(scale=1.9):
    """
    Load assets/sprites/slimer/Slimer.png (328x38, 8 frames of 41x38),
    automatically trim transparent margins per frame, scale with nearest-neighbor,
    and cache both left-facing (native) and right-facing (flipped) surfaces.
    """
    cache_key = round(float(scale), 2)
    if cache_key in _SLIMER_FRAME_CACHE:
        return _SLIMER_FRAME_CACHE[cache_key]

    path = os.path.join("assets", "sprites", "slimer", "Slimer.png")
    left_frames = []
    right_frames = []

    if os.path.exists(path):
        sheet = pygame.image.load(path).convert_alpha()
        sheet_w, sheet_h = sheet.get_size()
        # Auto-detect horizontal frame count (328x38 -> 8 frames of 41x38)
        num_frames = 8 if sheet_w % 8 == 0 else max(1, round(sheet_w / max(1, sheet_h)))
        fw = sheet_w // num_frames

        for i in range(num_frames):
            raw = sheet.subsurface(pygame.Rect(i * fw, 0, fw, sheet_h)).copy()
            bbox = raw.get_bounding_rect(min_alpha=10)
            if bbox.width > 0 and bbox.height > 0:
                cropped = raw.subsurface(bbox).copy()
            else:
                cropped = raw

            tw = max(1, int(round(cropped.get_width() * scale)))
            th = max(1, int(round(cropped.get_height() * scale)))
            scaled_left = pygame.transform.scale(cropped, (tw, th))
            scaled_right = pygame.transform.flip(scaled_left, True, False)
            left_frames.append(scaled_left)
            right_frames.append(scaled_right)
    else:
        fallback = pygame.Surface((44, 38), pygame.SRCALPHA)
        pygame.draw.ellipse(fallback, (40, 220, 60), (2, 4, 40, 34))
        left_frames.append(fallback)
        right_frames.append(pygame.transform.flip(fallback, True, False))

    _SLIMER_FRAME_CACHE[cache_key] = (left_frames, right_frames)
    return left_frames, right_frames


class Slimer(pygame.sprite.Sprite):
    """
    Regular Stage Enemy — Slimer:
    - Auto-sliced 8-frame pixel-art sprite with transparent margins trimmed & midbottom aligned.
    - Full gravity + solid/one-way platform collision with platform-edge drop prevention.
    - Patrols around spawn_pos; switches to Chase + Hop Pounce when player enters aggro range.
    - Full combat integration: supports player normal slash, aerial down-slash Pogo bounce
      (survives 2 hits so players can chain 2x Pogo), Normal Block, and Perfect Parry.
    """

    STATE_PATROL = "PATROL"
    STATE_CHASE = "CHASE"
    STATE_STUNNED = "STUNNED"

    def __init__(
        self,
        target_player,
        start_x=560,
        ground_y=GROUND_Y,
        game_map=None,
        patrol_range=110.0,
        max_hp=24,
        attack_damage=5,
    ):
        super().__init__()
        self.target = target_player
        self.game_map = game_map
        self.spawn_x = float(start_x)
        self.spawn_y = float(ground_y)
        self.spawn_pos = (self.spawn_x, self.spawn_y)
        self.patrol_range = float(patrol_range)

        self.max_hp = int(max_hp)
        self.hp = float(self.max_hp)
        self.attack_damage = int(attack_damage)

        self.pos_x = float(start_x)
        self.pos_y = float(ground_y)
        self.ground_y = float(ground_y)
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.knockback_vx = 0.0
        self.on_ground = False
        self.on_one_way_platform = False

        # Native sprite faces LEFT (-1); facing_dir = +1 flips horizontally to face RIGHT
        self.facing_dir = -1
        self.patrol_speed = 74.0
        self.chase_speed = 142.0
        self.lunge_speed = 235.0
        self.hop_speed = -215.0
        self.aggro_range = 265.0
        self.aggro_vertical_limit = 115.0

        self.state = self.STATE_PATROL
        self.stun_timer = 0.0
        self.hop_cooldown = 0.65
        self.lunge_timer = 0.0
        self.hit_flash_timer = 0.0
        self.hit_invuln_timer = 0.0
        self.attack_cooldown = 0.0

        self.left_frames, self.right_frames = _load_slimer_frames(scale=1.9)
        self.anim_index = 0.0
        self.anim_fps = 9.0
        self.image = self.left_frames[0]

        # Separated collision_rect & hurtbox (hitbox alias), strictly anchored to midbottom
        self.collision_rect = pygame.Rect(0, 0, 42, 36)
        self.hurtbox = pygame.Rect(0, 0, 46, 40)
        self.hitbox = self.hurtbox
        self.rect = self.image.get_rect()

        self.contact_hitbox = None
        self._last_vfx_group = None
        self.sync_boxes()

    @property
    def flip(self):
        return self.facing_dir < 0

    def sync_boxes(self):
        anchor_x = int(round(self.pos_x))
        anchor_y = int(round(self.pos_y))
        self.collision_rect.midbottom = (anchor_x, anchor_y)
        self.hurtbox.midbottom = (anchor_x, anchor_y)
        self.hitbox = self.hurtbox
        self.rect = self.image.get_rect()
        self.rect.midbottom = (anchor_x, anchor_y)

        if self.contact_hitbox is not None and self.contact_hitbox.active:
            self.contact_hitbox.rect.midbottom = (
                anchor_x + self.facing_dir * 4,
                anchor_y,
            )
            self.contact_hitbox.knockback_x = self.facing_dir * 200.0

    def _clear_contact_hitbox(self):
        if self.contact_hitbox is not None:
            self.contact_hitbox.destroy()
            self.contact_hitbox = None

    def _ensure_contact_hitbox(self):
        if self.state == self.STATE_STUNNED or self.attack_cooldown > 0.0 or self.hp <= 0:
            self._clear_contact_hitbox()
            return

        # Hitbox.register_hit(target) stores the target object itself (NOT id(target))!
        # Once it hits or is blocked/parried by the player, put contact hit on a short cooldown
        # and recreate a fresh Hitbox so Slimer can strike again cleanly.
        if self.contact_hitbox is not None and self.contact_hitbox.active:
            if self.target is not None and self.target in self.contact_hitbox.hit_targets:
                self._clear_contact_hitbox()
                self.attack_cooldown = 0.65
                return
            return

        hb_rect = pygame.Rect(0, 0, 52, 44)
        hb_rect.midbottom = (
            int(round(self.pos_x)) + self.facing_dir * 4,
            int(round(self.pos_y)),
        )
        hb = Hitbox(
            owner="enemy",
            rect=hb_rect,
            damage=self.attack_damage,
            knockback_x=self.facing_dir * 200.0,
            lifetime=None,
            tag="slimer_tackle",
        )
        hb.source_entity = self
        self.contact_hitbox = hb

    def get_active_hitboxes(self):
        if self.alive() and self.contact_hitbox is not None and self.contact_hitbox.active:
            return [self.contact_hitbox]
        return []

    def _has_floor_ahead(self, direction):
        """Platform edge drop-prevention probe: checks if solid or one-way floor exists ahead."""
        if self.game_map is None:
            return True
        if hasattr(self.game_map, "has_ground_ahead"):
            return self.game_map.has_ground_ahead(self.collision_rect, direction)
        probe = pygame.Rect(
            int(round(self.pos_x + direction * 24)) - 4,
            int(round(self.pos_y)) + 2,
            8,
            18,
        )
        for r in getattr(self.game_map, "collisions", ()):
            if probe.colliderect(r):
                return True
        for r in getattr(self.game_map, "platforms", ()):
            if probe.colliderect(r):
                return True
        return False

    def take_damage(self, damage=12, vfx_group=None):
        if self.hit_invuln_timer > 0.0 or self.hp <= 0:
            return
        self.hp = max(0.0, round(self.hp - damage, 2))
        self.hit_flash_timer = 0.20
        self.hit_invuln_timer = 0.16

        if vfx_group is None:
            vfx_group = self._last_vfx_group

        if self.hp <= 0.0:
            self._clear_contact_hitbox()
            from audio_manager import get_audio

            get_audio().play_sfx("slime_death")
            if vfx_group is not None:
                vfx_group.add(
                    SlimerDeathVFX(
                        self.hurtbox.centerx,
                        self.hurtbox.centery,
                        duration=0.46,
                        scale=1.45,
                    )
                )
            self.kill()
            return

        from audio_manager import get_audio

        get_audio().play_sfx("slime_hit")

        # Slight knockback & brief stun on hit (doesn't push Slimer too far so 2x Pogo stays reliable)
        if self.target is not None:
            push_dir = 1 if self.pos_x >= self.target.pos_x else -1
            self.knockback_vx = push_dir * 95.0
        self.stun_timer = max(self.stun_timer, 0.16)
        self.state = self.STATE_STUNNED
        self._clear_contact_hitbox()

    def be_attacked(self, damage=12, vfx_group=None):
        """Alias matching Boss interface for unified player attack collision resolution."""
        self.take_damage(damage, vfx_group=vfx_group)

    def on_parried(self):
        """Called when the player lands a Perfect Parry against this Slimer."""
        self._clear_contact_hitbox()
        self.state = self.STATE_STUNNED
        self.stun_timer = 0.65
        self.attack_cooldown = 0.95
        self.hit_flash_timer = 0.25
        if self.target is not None:
            push_dir = 1 if self.pos_x >= self.target.pos_x else -1
            self.knockback_vx = push_dir * 210.0
            if self.on_ground:
                self.velocity_y = -210.0
                self.on_ground = False

    def reset(self):
        """Respawn / reset Slimer at its initial spawn_pos with full HP and PATROL state."""
        self._clear_contact_hitbox()
        self.hp = float(self.max_hp)
        self.pos_x = float(self.spawn_x)
        self.pos_y = float(self.spawn_y)
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.knockback_vx = 0.0
        self.on_ground = False
        self.on_one_way_platform = False
        self.facing_dir = -1
        self.state = self.STATE_PATROL
        self.stun_timer = 0.0
        self.hop_cooldown = 0.75
        self.hit_flash_timer = 0.0
        self.hit_invuln_timer = 0.0
        self.attack_cooldown = 0.0
        self.anim_index = 0.0
        self.image = self.left_frames[0]
        self.sync_boxes()

    def update(self, dt=1 / 60, vfx_group=None, map_width=3520):
        if vfx_group is not None:
            self._last_vfx_group = vfx_group

        if self.hit_flash_timer > 0.0:
            self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)
        if self.hit_invuln_timer > 0.0:
            self.hit_invuln_timer = max(0.0, self.hit_invuln_timer - dt)
        if self.hop_cooldown > 0.0:
            self.hop_cooldown = max(0.0, self.hop_cooldown - dt)
        if self.lunge_timer > 0.0:
            self.lunge_timer = max(0.0, self.lunge_timer - dt)
        if self.attack_cooldown > 0.0:
            self.attack_cooldown = max(0.0, self.attack_cooldown - dt)

        # 1. AI State Decision (PATROL / CHASE / STUNNED)
        move_dx = 0.0
        if self.state == self.STATE_STUNNED:
            self.stun_timer -= dt
            move_dx = self.knockback_vx * dt
            self.knockback_vx *= max(0.0, 1.0 - 7.5 * dt)
            if self.stun_timer <= 0.0:
                self.state = self.STATE_PATROL
                self.knockback_vx = 0.0
        else:
            player_in_aggro = False
            if self.target is not None and self.target.alive():
                dx_to_player = self.target.pos_x - self.pos_x
                dy_to_player = abs(self.target.pos_y - self.pos_y)
                if (
                    abs(dx_to_player) <= self.aggro_range
                    and dy_to_player <= self.aggro_vertical_limit
                ):
                    player_in_aggro = True

            if player_in_aggro:
                self.state = self.STATE_CHASE
                dx_to_player = self.target.pos_x - self.pos_x
                if abs(dx_to_player) > 6.0 and self.lunge_timer <= 0.0:
                    self.facing_dir = 1 if dx_to_player > 0 else -1

                cur_speed = self.lunge_speed if self.lunge_timer > 0.0 else self.chase_speed
                # Stay safe on platforms even while chasing
                if self.on_ground and not self._has_floor_ahead(self.facing_dir):
                    move_dx = 0.0
                else:
                    move_dx = self.facing_dir * cur_speed * dt

                # Low forward Lunge pounce directly into standing players (never sails over their head!)
                if (
                    self.on_ground
                    and self.hop_cooldown <= 0.0
                    and 24.0 <= abs(dx_to_player) <= 135.0
                    and self._has_floor_ahead(self.facing_dir)
                ):
                    self.velocity_y = self.hop_speed
                    self.on_ground = False
                    self.on_one_way_platform = False
                    self.lunge_timer = 0.30
                    self.hop_cooldown = 1.05
                    from audio_manager import get_audio

                    get_audio().play_sfx("slime_hop")
            else:
                self.state = self.STATE_PATROL
                # Turn around at patrol bounds or platform edges
                if self.pos_x <= self.spawn_x - self.patrol_range:
                    self.facing_dir = 1
                elif self.pos_x >= self.spawn_x + self.patrol_range:
                    self.facing_dir = -1
                elif self.on_ground and not self._has_floor_ahead(self.facing_dir):
                    self.facing_dir *= -1

                move_dx = self.facing_dir * self.patrol_speed * dt

        # 2. Continuous Gravity & Map Tile/One-Way Platform Collision
        self.velocity_y = min(self.velocity_y + GRAVITY * dt, 950.0)
        dy = self.velocity_y * dt

        has_map_geometry = bool(
            self.game_map
            and (
                getattr(self.game_map, "collisions", None)
                or getattr(self.game_map, "polygons", None)
                or getattr(self.game_map, "platforms", None)
            )
        )

        if has_map_geometry:
            self.collision_rect.midbottom = (
                int(round(self.pos_x)),
                int(round(self.pos_y)),
            )
            old_x = self.collision_rect.centerx
            on_ground_now, hit_ceiling = self.game_map.move_with_collisions(
                self.collision_rect,
                move_dx,
                dy,
                drop_through=False,
            )
            self.on_one_way_platform = bool(
                getattr(self.game_map, "last_on_one_way", False)
            )
            if self.collision_rect.left < 32:
                self.collision_rect.left = 32
            elif self.collision_rect.right > map_width - 32:
                self.collision_rect.right = map_width - 32

            self.pos_x = float(self.collision_rect.centerx)
            self.pos_y = float(self.collision_rect.bottom)

            if on_ground_now and self.velocity_y >= 0.0:
                self.velocity_y = 0.0
                self.on_ground = True
                self.ground_y = self.pos_y
            else:
                self.on_ground = on_ground_now
                if hit_ceiling and self.velocity_y < 0.0:
                    self.velocity_y = 0.0

            # Turn around if bumped into a wall while patrolling
            actual_dx = self.pos_x - old_x
            if (
                self.state == self.STATE_PATROL
                and abs(move_dx) > 0.5
                and abs(actual_dx) < abs(move_dx) * 0.25
            ):
                self.facing_dir *= -1
        else:
            self.pos_x = max(32.0, min(float(map_width - 32), self.pos_x + move_dx))
            self.pos_y += dy
            if self.pos_y >= self.ground_y:
                self.pos_y = float(self.ground_y)
                self.velocity_y = 0.0
                self.on_ground = True
            else:
                self.on_ground = False

        # 3. Animation Update (faster bounce while chasing)
        fps = self.anim_fps * (1.35 if self.state == self.STATE_CHASE else 1.0)
        self.anim_index = (self.anim_index + fps * dt) % len(self.left_frames)
        frame_idx = int(self.anim_index)
        base_img = (
            self.right_frames[frame_idx]
            if self.facing_dir > 0
            else self.left_frames[frame_idx]
        )

        if self.hit_flash_timer > 0.0:
            flashed = base_img.copy()
            flashed.fill((255, 100, 100), special_flags=pygame.BLEND_RGB_ADD)
            self.image = flashed
        else:
            self.image = base_img

        # 4. Sync Hitboxes & Contact Attack Box
        self._ensure_contact_hitbox()
        self.sync_boxes()

    def draw_hp_bar(self, surface, camera_x=0, camera_y=0):
        """Draw a crisp mini pixel HP bar above Slimer whenever damaged."""
        if not self.alive() or self.hp >= self.max_hp:
            return
        bar_w = 38
        bar_h = 5
        sx = int(round(self.pos_x - camera_x)) - bar_w // 2
        sy = int(round(self.hurtbox.top - camera_y)) - 10
        ratio = max(0.0, min(1.0, self.hp / max(1, self.max_hp)))

        pygame.draw.rect(surface, (20, 20, 28), (sx - 1, sy - 1, bar_w + 2, bar_h + 2))
        pygame.draw.rect(surface, (75, 25, 35), (sx, sy, bar_w, bar_h))
        if ratio > 0:
            pygame.draw.rect(
                surface, (85, 235, 110), (sx, sy, max(1, int(bar_w * ratio)), bar_h)
            )
