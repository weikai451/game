import math
import pygame
from Settings import WIDTH, HEIGHT, get_pixel_font
from VFX import draw_floating_prompt_box, PortalTeleportVFX


class MapTrigger:
    """
    Stage Portal / Map Transition Trigger:
    - Completely hidden and non-interactable until `unlock(vfx_group)` is triggered
      upon completing the current stage's clear condition.
    - Plays a materializing scale-in & particle convergence animation upon unlock.
    - Shows `[E] Enter Portal` when the player stands near an unlocked portal.
    """

    def __init__(
        self,
        rect,
        target_map,
        spawn_pos,
        require_boss_dead=False,
        boss_type=None,
        name="Portal",
        unlocked=False,
    ):
        self.rect = rect if isinstance(rect, pygame.Rect) else pygame.Rect(rect)
        self.interaction_rect = self.rect.inflate(36, 20)
        self.target_map = target_map
        self.spawn_pos = spawn_pos
        self.require_boss_dead = require_boss_dead
        self.boss_type = boss_type
        self.name = name

        self.unlocked = bool(unlocked)
        self.unlock_anim_timer = 0.65 if self.unlocked else 0.0
        self.can_interact = False
        self.anim_timer = 0.0

    def unlock(self, vfx_group=None):
        """Reveal and activate this portal with a particle convergence burst."""
        if self.unlocked:
            return False
        self.unlocked = True
        self.unlock_anim_timer = 0.0
        if vfx_group is not None:
            vfx_group.add(
                PortalTeleportVFX(
                    self.rect.centerx,
                    self.rect.bottom,
                    duration=0.75,
                    mode="arrive",
                )
            )
        return True

    def is_locked(self, boss=None):
        if not self.unlocked:
            return True
        return bool(self.require_boss_dead and boss is not None and boss.alive())

    def update(self, raw_dt, player_rect):
        if not self.unlocked:
            self.can_interact = False
            return
        self.anim_timer += raw_dt
        if self.unlock_anim_timer < 0.65:
            self.unlock_anim_timer = min(0.65, self.unlock_anim_timer + raw_dt)
        self.can_interact = self.interaction_rect.colliderect(player_rect)

    def can_trigger(self, player_rect, boss=None):
        """Only allow portal interaction after the portal is unlocked and player is in range."""
        if not self.unlocked:
            return False
        if not self.interaction_rect.colliderect(player_rect):
            return False
        if self.is_locked(boss):
            return False
        return True

    def draw(self, screen, camera_x, camera_y, font, boss=None):
        """Render pixel-art portal aura and `[E] Enter Portal` prompt ONLY when unlocked."""
        if not self.unlocked:
            return

        cx, cy = self.rect.center
        sx = int(round(cx - camera_x))
        locked = self.is_locked(boss)

        # Smooth pixel scale-in reveal animation (0.0 -> 0.65s)
        reveal = min(1.0, self.unlock_anim_timer / 0.65)
        scale_t = 0.18 + 0.82 * (1.0 - (1.0 - reveal) ** 3)

        pw, ph = 52, 76
        low_w, low_h = pw // 2, ph // 2
        low_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        lcx, lcy = low_w // 2, low_h // 2

        outer_col = (255, 85, 95, 185) if locked else (90, 225, 255, 215)
        inner_col = (180, 50, 70, 150) if locked else (165, 105, 255, 195)
        pulse = int(math.sin(self.anim_timer * 5.0) * 2)

        pygame.draw.ellipse(
            low_surf,
            outer_col,
            (3, 3 - pulse // 2, low_w - 6, low_h - 6 + pulse),
            2,
        )
        pygame.draw.ellipse(
            low_surf,
            inner_col,
            (7, 8, low_w - 14, low_h - 16),
            2,
        )
        pygame.draw.ellipse(
            low_surf,
            (230, 250, 255, 115) if not locked else (255, 140, 140, 80),
            (10, 13, low_w - 20, low_h - 26),
        )

        # Orbiting pixel sparks
        for i in range(4):
            ang = self.anim_timer * 3.5 + i * (math.pi * 0.5)
            px = int(lcx + math.cos(ang) * (low_w * 0.38))
            py = int(lcy + math.sin(ang) * (low_h * 0.40))
            low_surf.fill((245, 255, 255, 240), pygame.Rect(px, py, 2, 2))

        cur_w = max(4, int(round(pw * scale_t)))
        cur_h = max(6, int(round(ph * scale_t)))
        hi_surf = pygame.transform.scale(low_surf, (cur_w, cur_h))
        screen.blit(hi_surf, (sx - cur_w // 2, self.rect.bottom - camera_y - cur_h))

        # Floating `[E] Enter Portal` prompt when player is nearby
        if self.can_interact and reveal >= 0.45 and not locked:
            prompt_y = min(self.rect.top, self.rect.bottom - ph) - 8
            draw_floating_prompt_box(
                screen,
                cx,
                prompt_y,
                camera_x,
                camera_y,
                "[E]",
                font,
                border_color=(140, 225, 255),
                text_color=(245, 252, 255),
            )

    def draw_debug(self, screen, camera_x, camera_y, boss=None):
        """Draw portal bounds in Debug Mode (dim gray when hidden/locked, bright green when unlocked)."""
        screen_rect = self.rect.move(-camera_x, -camera_y)
        ir = self.interaction_rect.move(-camera_x, -camera_y)
        if not self.unlocked:
            pygame.draw.rect(screen, (110, 110, 130), screen_rect, 1)
        else:
            color = (255, 80, 80) if self.is_locked(boss) else (80, 255, 160)
            pygame.draw.rect(screen, color, screen_rect, 2)
            pygame.draw.rect(screen, (180, 120, 255), ir, 1)


def find_interactable_portal(player, triggers, boss=None):
    """
    尋找玩家當前所處互動範圍內的傳送門 (供按下 E 鍵時觸發)
    """
    player_rect = getattr(player, "collision_rect", player.rect)
    for trigger in triggers:
        if trigger.can_trigger(player_rect, boss):
            return trigger
    return None


def check_map_transitions(player, triggers, boss=None):
    """相容舊版輔助函式名稱"""
    return find_interactable_portal(player, triggers, boss)


class TransitionManager:
    """
    處理傳送門切換與死亡重生時的過場動畫：
    - mode="PORTAL"：像素風圓形遮罩收縮 (Pixelated Iris Wipe) + 淡出淡入，同時鎖定玩家控制
    - mode="RESPAWN"：類魂 (Soul-like) 死亡淡出黑幕 + 提示文字 -> 重置關卡與檢查點重生
    """

    def __init__(self, fade_speed=460.0):
        self.fade_speed = fade_speed
        self.alpha = 0.0
        self.state = "IDLE"  # IDLE, FADING_OUT, FADING_IN
        self.mode = "PORTAL"
        self.banner_text = ""
        self.pending_trigger = None
        self.focus_screen_pos = (WIDTH // 2, HEIGHT // 2)
        self.overlay = pygame.Surface((WIDTH, HEIGHT))
        self.overlay.fill((0, 0, 0))
        self.iris_low_w = WIDTH // 4
        self.iris_low_h = HEIGHT // 4
        self.iris_low_surf = pygame.Surface(
            (self.iris_low_w, self.iris_low_h), pygame.SRCALPHA
        )
        self._banner_font = get_pixel_font(33)

    @property
    def is_transitioning(self):
        return self.state != "IDLE"

    def start(
        self,
        trigger,
        mode="PORTAL",
        focus_screen_pos=None,
        banner_text="",
    ):
        """開始轉場"""
        if self.state == "IDLE":
            self.pending_trigger = trigger
            self.mode = mode
            self.banner_text = banner_text
            if focus_screen_pos is not None:
                self.focus_screen_pos = (
                    int(focus_screen_pos[0]),
                    int(focus_screen_pos[1]),
                )
            else:
                self.focus_screen_pos = (WIDTH // 2, HEIGHT // 2)
            self.state = "FADING_OUT"

    def update(self, raw_dt, on_map_switch):
        """
        更新轉場進度
        """
        speed = self.fade_speed if self.mode == "PORTAL" else (self.fade_speed * 0.78)
        if self.state == "FADING_OUT":
            self.alpha += speed * raw_dt
            if self.alpha >= 255.0:
                self.alpha = 255.0
                if self.pending_trigger is not None:
                    on_map_switch(self.pending_trigger)
                    self.pending_trigger = None
                self.state = "FADING_IN"

        elif self.state == "FADING_IN":
            self.alpha -= speed * raw_dt
            if self.alpha <= 0.0:
                self.alpha = 0.0
                self.state = "IDLE"
                self.banner_text = ""

    def draw(self, screen):
        """在畫面最上層繪製像素風圓形收縮遮罩 (Iris Wipe) 或淡出黑幕"""
        if self.alpha <= 0.0:
            return

        progress = max(0.0, min(1.0, self.alpha / 255.0))

        if self.mode == "PORTAL":
            # 像素風圓形遮罩收縮 (Pixelated Iris Wipe)
            self.iris_low_surf.fill((6, 8, 18, int(min(255, progress * 270))))
            max_r = int(math.hypot(self.iris_low_w, self.iris_low_h) * 0.65)
            cur_r = max(0, int(max_r * (1.0 - progress)))

            cx = max(
                0, min(self.iris_low_w, int(self.focus_screen_pos[0] // 4))
            )
            cy = max(
                0, min(self.iris_low_h, int(self.focus_screen_pos[1] // 4))
            )

            if cur_r > 1:
                pygame.draw.circle(
                    self.iris_low_surf, (0, 0, 0, 0), (cx, cy), cur_r
                )
                pygame.draw.circle(
                    self.iris_low_surf,
                    (95, 235, 255, int(220 * math.sin(progress * math.pi))),
                    (cx, cy),
                    cur_r,
                    2,
                )

            scaled_iris = pygame.transform.scale(
                self.iris_low_surf, (WIDTH, HEIGHT)
            )
            screen.blit(scaled_iris, (0, 0))
        else:
            # 死亡重生黑幕淡入淡出
            self.overlay.set_alpha(int(self.alpha))
            screen.blit(self.overlay, (0, 0))

        if self.banner_text and progress > 0.35:
            txt_color = (
                (255, 95, 95)
                if "DIED" in self.banner_text or "死亡" in self.banner_text
                else (120, 240, 255)
            )
            txt_surf = self._banner_font.render(self.banner_text, False, txt_color)
            screen.blit(
                txt_surf, txt_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            )


def change_map(game, trigger, map_class):
    """執行實際的地圖切換、清場與玩家重新定位"""
    resolved = (
        game.resolve_map_path(trigger.target_map)
        if hasattr(game, "resolve_map_path")
        else trigger.target_map
    )
    game.current_map_path = resolved
    game.game_map = map_class(resolved)
    game.player.game_map = game.game_map

    new_floor_y = game.get_floor_y() if hasattr(game, "get_floor_y") else 576
    game.player.ground_y = float(new_floor_y)

    if hasattr(game.player, "teleport"):
        game.player.teleport(trigger.spawn_pos[0], trigger.spawn_pos[1])
    else:
        game.player.pos_x, game.player.pos_y = (
            float(trigger.spawn_pos[0]),
            float(trigger.spawn_pos[1]),
        )
        if hasattr(game.player, "sync_boxes"):
            game.player.sync_boxes()

    game.active_hitboxes.clear()
    game.vfx_group.empty()
    game.triggers = []
