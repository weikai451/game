import math
import os
import random
import pygame
from Settings import (
    GROUND_Y,
    COLOR_DEBUG_HITBOX,
    COLOR_DEBUG_HURTBOX,
    COLOR_DEBUG_PARRY,
    COLOR_DEBUG_BLOCK,
    COLOR_DEBUG_COLLISION,
)


class Hitbox:
    """
    獨立的攻擊判定框物件（不常駐於角色身上）。
    僅在攻擊動畫 Active Frames 或攻擊 VFX 存在期間啟用，結束時立即銷毀。
    內建 hit_targets 集合，確保單次攻擊對同一目標只造成一次傷害/格擋判定。
    """

    def __init__(
        self,
        owner,
        rect,
        damage=15,
        knockback_x=180.0,
        lifetime=None,
        tag="melee",
        attack_type="white",
        knockback_y=0.0,
    ):
        self.owner = owner  # "player", "boss", or "enemy"
        self.rect = pygame.Rect(rect)
        self.damage = damage
        self.knockback_x = knockback_x
        self.knockback_y = float(knockback_y)
        self.lifetime = lifetime
        self.elapsed = 0.0
        self.active = True
        self.tag = tag
        self.attack_type = attack_type  # "white" (always hits) or "blue" (stay still to dodge)
        self.hit_targets = set()

    def can_hit(self, target):
        return self.active and (target not in self.hit_targets)

    def register_hit(self, target):
        self.hit_targets.add(target)

    def update(self, dt):
        if not self.active:
            return
        self.elapsed += dt
        if self.lifetime is not None and self.elapsed >= self.lifetime:
            self.destroy()

    def destroy(self):
        self.active = False


class BaseVFX(pygame.sprite.Sprite):
    """
    視覺特效基底類別：
    具備獨立的 update(dt) 與 draw(screen, camera_x, camera_y) 生命週期，
    並可綁定一個 Hitbox，共用相同的錨點中心 (pos_x, pos_y)，於特效結束時自動銷毀該 Hitbox。
    """

    def __init__(self, x, y, duration=0.25, hitbox=None):
        super().__init__()
        self.pos_x = float(x)
        self.pos_y = float(y)
        self.duration = max(duration, 0.01)
        self.elapsed = 0.0
        self.hitbox = hitbox
        self.image = pygame.Surface((1, 1), pygame.SRCALPHA)
        self.rect = pygame.Rect(int(x), int(y), 1, 1)

    @property
    def progress(self):
        return min(max(self.elapsed / self.duration, 0.0), 1.0)

    @property
    def anchor_point(self):
        return (int(self.pos_x), int(self.pos_y))

    def bind_hitbox(self, hitbox):
        self.hitbox = hitbox
        return hitbox

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.hitbox and self.hitbox.active:
            self.hitbox.update(dt)
        if self.elapsed >= self.duration:
            self.destroy()

    def destroy(self):
        if self.hitbox:
            self.hitbox.destroy()
            self.hitbox = None
        self.kill()

    def draw(self, screen, camera_x=0, camera_y=0):
        if self.image.get_width() > 1:
            screen.blit(self.image, self.rect.move(-camera_x, -camera_y))


class SlashVFX(BaseVFX):
    """
    近戰斬擊刀光特效（支援玩家水平揮砍、1.35x 強化斬擊與 Boss 近距連擊）：
    - 維持一般像素畫風（透過低解析度繪製 + Nearest-Neighbor 放大保留像素顆粒感）
    - 統一以出招者的地面基準錨點 (anchor.pos_x, anchor.pos_y) 為基準
    - 特效繪製中心與 Hitbox.rect.center 100% 對齊
    """

    def __init__(
        self,
        anchor_entity,
        forward_offset,
        vertical_offset,
        width=88,
        height=72,
        flip=False,
        duration=0.18,
        color_outer=(60, 170, 255),
        color_inner=(220, 245, 255),
        tilt_angle=0.0,
        buffed=False,
        hitbox=None,
    ):
        self.anchor = anchor_entity
        self.forward_offset = float(abs(forward_offset))
        self.vertical_offset = float(vertical_offset)
        self.width = width
        self.height = height
        self.flip = flip
        self.color_outer = color_outer
        self.color_inner = color_inner
        self.tilt_angle = tilt_angle
        self.buffed = buffed

        facing_dir = -1 if flip else 1
        cx = anchor_entity.pos_x + facing_dir * self.forward_offset
        cy = anchor_entity.pos_y + self.vertical_offset
        super().__init__(cx, cy, duration=duration, hitbox=hitbox)

        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (int(cx), int(cy))
        self._px_scale = 2
        self._low_w = max(8, width // self._px_scale)
        self._low_h = max(8, height // self._px_scale)
        self._low_surf = pygame.Surface((self._low_w, self._low_h), pygame.SRCALPHA)
        if self.hitbox:
            self.hitbox.rect.center = self.rect.center

    def _sync_with_anchor(self):
        if self.anchor and self.anchor.alive():
            self.flip = self.anchor.flip
            facing_dir = -1 if self.flip else 1
            self.pos_x = self.anchor.pos_x + facing_dir * self.forward_offset
            self.pos_y = self.anchor.pos_y + self.vertical_offset
            self.rect.center = (int(self.pos_x), int(self.pos_y))
            if self.hitbox and self.hitbox.active:
                self.hitbox.rect.center = self.rect.center

    def update(self, dt=1 / 60):
        self._sync_with_anchor()
        super().update(dt)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = int(255 * math.sin(p * math.pi))
        if alpha <= 5:
            return

        # Reuse pre-allocated low-resolution canvas to avoid per-frame Surface allocation
        lw, lh = self._low_w, self._low_h
        low_surf = self._low_surf
        low_surf.fill((0, 0, 0, 0))

        points_outer = []
        points_inner = []
        steps = 12
        start_t = max(0.0, p - 0.65)
        end_t = min(1.0, p + 0.35)

        for i in range(steps + 1):
            t = start_t + (end_t - start_t) * (i / steps)
            angle = -0.46 * math.pi + t * 0.92 * math.pi
            origin_x = lw * 0.08
            origin_y = lh * 0.50
            rx_out = lw * 0.84
            ry_out = lh * 0.46
            thickness = math.sin((i / steps) * math.pi) * (
                lw * (0.42 if self.buffed else 0.36)
            )

            x_out = origin_x + math.cos(angle) * rx_out
            y_out = origin_y + math.sin(angle) * ry_out
            x_in = origin_x + math.cos(angle) * max(3.0, rx_out - thickness)
            y_in = origin_y + math.sin(angle) * (ry_out * 0.78)
            points_outer.append((x_out, y_out))
            points_inner.append((x_in, y_in))

        polygon_pts = points_outer + list(reversed(points_inner))
        if len(polygon_pts) >= 3:
            if self.buffed:
                pygame.draw.polygon(
                    low_surf, (45, 215, 255, int(alpha * 0.90)), polygon_pts
                )
                pygame.draw.lines(
                    low_surf, (255, 200, 50, alpha), False, points_inner, 1
                )
                pygame.draw.lines(
                    low_surf,
                    (255, 255, 225, min(255, alpha + 35)),
                    False,
                    points_outer,
                    2,
                )
            else:
                pygame.draw.polygon(low_surf, (*self.color_outer, alpha), polygon_pts)
                pygame.draw.lines(
                    low_surf,
                    (*self.color_inner, min(255, alpha + 30)),
                    False,
                    points_outer,
                    2,
                )

        surf = pygame.transform.scale(low_surf, (self.width, self.height))
        if self.flip:
            surf = pygame.transform.flip(surf, True, False)

        draw_rect = surf.get_rect(
            center=(self.rect.centerx - camera_x, self.rect.centery - camera_y)
        )
        screen.blit(surf, draw_rect)


class DownSlashVFX(BaseVFX):
    """
    玩家空中向下劈砍 (Downward Slash / Pogo) 專用像素弧形刀光特效：
    - 維持一般像素畫風（不使用水墨風），透過低解析度畫布 + Nearest-Neighbor 放大呈現銳利像素階層
    - 錨定於玩家腳底正下方 (pos_x, pos_y + vertical_offset)，與下方的攻擊 Hitbox 100% 精確對齊
    """

    def __init__(
        self,
        anchor_entity,
        vertical_offset=20.0,
        width=84,
        height=64,
        duration=0.20,
        buffed=False,
        hitbox=None,
    ):
        self.anchor = anchor_entity
        self.vertical_offset = float(vertical_offset)
        self.width = width
        self.height = height
        self.buffed = buffed

        cx = anchor_entity.pos_x
        cy = anchor_entity.pos_y + self.vertical_offset
        super().__init__(cx, cy, duration=duration, hitbox=hitbox)

        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (int(cx), int(cy))
        self._px_scale = 2
        self._low_w = max(8, width // self._px_scale)
        self._low_h = max(8, height // self._px_scale)
        self._low_surf = pygame.Surface((self._low_w, self._low_h), pygame.SRCALPHA)
        if self.hitbox:
            self.hitbox.rect.center = self.rect.center

    def update(self, dt=1 / 60):
        if self.anchor and self.anchor.alive():
            self.pos_x = self.anchor.pos_x
            self.pos_y = self.anchor.pos_y + self.vertical_offset
            self.rect.center = (int(self.pos_x), int(self.pos_y))
            if self.hitbox and self.hitbox.active:
                self.hitbox.rect.center = self.rect.center
        super().update(dt)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = int(255 * math.sin(p * math.pi))
        if alpha <= 5:
            return

        # Reuse pre-allocated low-resolution canvas to avoid per-frame Surface allocation
        lw, lh = self._low_w, self._low_h
        low_surf = self._low_surf
        low_surf.fill((0, 0, 0, 0))

        pts_outer = []
        pts_inner = []
        pts_mid = []
        steps = 12

        # 隨動畫進度由一側向另一側掃過正下方 U 型弧線
        facing_dir = -1 if (self.anchor and self.anchor.flip) else 1
        sweep_start = max(0.0, p - 0.72)
        sweep_end = min(1.0, p + 0.32)

        origin_x = lw * 0.50
        origin_y = lh * 0.08
        rx_out = lw * 0.46
        ry_out = lh * 0.84

        for i in range(steps + 1):
            t = sweep_start + (sweep_end - sweep_start) * (i / steps)
            if facing_dir < 0:
                t = 1.0 - t
            ang = 0.05 * math.pi + t * 0.90 * math.pi
            thickness = math.sin((i / steps) * math.pi) * (
                lh * (0.44 if self.buffed else 0.36)
            )

            xo = origin_x + math.cos(ang) * rx_out
            yo = origin_y + math.sin(ang) * ry_out
            xm = origin_x + math.cos(ang) * (rx_out * 0.90)
            ym = origin_y + math.sin(ang) * max(4.0, ry_out - thickness * 0.45)
            xi = origin_x + math.cos(ang) * (rx_out * 0.74)
            yi = origin_y + math.sin(ang) * max(3.0, ry_out - thickness)

            pts_outer.append((xo, yo))
            pts_mid.append((xm, ym))
            pts_inner.append((xi, yi))

        poly_full = pts_outer + list(reversed(pts_inner))
        poly_edge = pts_outer + list(reversed(pts_mid))

        if len(poly_full) >= 3:
            if self.buffed:
                # 1.35x Buff 狀態下的一般像素風格強化刀光（亮青金雙色像素弧光）
                pygame.draw.polygon(
                    low_surf, (35, 195, 255, int(alpha * 0.82)), poly_full
                )
                pygame.draw.polygon(
                    low_surf, (255, 215, 75, int(alpha * 0.92)), poly_edge
                )
                pygame.draw.lines(
                    low_surf, (255, 255, 235, alpha), False, pts_outer, 2
                )
            else:
                # 標準像素刀光：銀藍劍風底 + 金橘刀肚 + 亮白像素刃口
                pygame.draw.polygon(
                    low_surf, (185, 210, 235, int(alpha * 0.72)), poly_full
                )
                pygame.draw.polygon(
                    low_surf, (255, 195, 65, int(alpha * 0.90)), poly_edge
                )
                pygame.draw.lines(
                    low_surf, (255, 252, 225, alpha), False, pts_outer, 2
                )

        # 點綴幾顆方形像素劍花
        tip_idx = len(pts_outer) // 2
        if tip_idx < len(pts_outer):
            tx, ty = int(pts_outer[tip_idx][0]), int(pts_outer[tip_idx][1])
            spark_col = (120, 245, 255, alpha) if self.buffed else (255, 240, 150, alpha)
            low_surf.fill(spark_col, pygame.Rect(tx - 1, ty, 2, 2))

        surf = pygame.transform.scale(low_surf, (self.width, self.height))
        draw_rect = surf.get_rect(
            center=(self.rect.centerx - camera_x, self.rect.centery - camera_y)
        )
        screen.blit(surf, draw_rect)


class PogoBounceVFX(BaseVFX):
    """
    空中下劈命中目標時的像素風反彈氣流特效 (Pogo Impact Ring)
    """

    def __init__(self, x, y):
        super().__init__(x, y, duration=0.22, hitbox=None)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, int(245 * (1.0 - p)))
        if alpha <= 5:
            return

        sx = int(self.pos_x - camera_x)
        sy = int(self.pos_y - camera_y)
        rx = int(9 + 22 * p)
        ry = int(3 + 7 * p)

        low_w, low_h = rx * 2 + 8, ry * 2 + 12
        low_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        cx, cy = low_w // 2, low_h // 2
        pygame.draw.ellipse(
            low_surf, (130, 240, 255, alpha), (cx - rx, cy - ry, rx * 2, ry * 2), 2
        )
        pygame.draw.ellipse(
            low_surf,
            (255, 245, 180, int(alpha * 0.85)),
            (cx - int(rx * 0.6), cy - int(ry * 0.6), int(rx * 1.2), int(ry * 1.2)),
            1,
        )
        surf = pygame.transform.scale(low_surf, (low_w * 2, low_h * 2))
        screen.blit(surf, (sx - low_w, sy - low_h))


class DashSlashVFX(BaseVFX):
    """
    Boss 突進斬擊 (ATTACK_2) 專用視覺特效
    """

    def __init__(
        self,
        anchor_entity,
        start_x,
        vertical_offset=-50.0,
        forward_offset=28.0,
        hitbox_w=116,
        hitbox_h=72,
        flip=False,
        duration=0.26,
        hitbox=None,
    ):
        self.anchor = anchor_entity
        self.start_x = float(start_x)
        self.vertical_offset = float(vertical_offset)
        self.forward_offset = float(abs(forward_offset))
        self.hitbox_w = hitbox_w
        self.hitbox_h = hitbox_h
        self.flip = flip

        facing_dir = -1 if flip else 1
        cx = anchor_entity.pos_x + facing_dir * self.forward_offset
        cy = anchor_entity.pos_y + self.vertical_offset
        super().__init__(cx, cy, duration=duration, hitbox=hitbox)

        self.rect = pygame.Rect(0, 0, hitbox_w, hitbox_h)
        self.rect.center = (int(cx), int(cy))
        if self.hitbox:
            self.hitbox.rect = self.rect.copy()

    def update(self, dt=1 / 60):
        if self.anchor and self.anchor.alive():
            self.flip = self.anchor.flip
            facing_dir = -1 if self.flip else 1
            cur_x = self.anchor.pos_x
            cur_y = self.anchor.pos_y + self.vertical_offset

            hb_cx = cur_x + facing_dir * self.forward_offset
            self.pos_x = hb_cx
            self.pos_y = cur_y

            if self.hitbox and self.hitbox.active:
                self.hitbox.rect.size = (self.hitbox_w, self.hitbox_h)
                self.hitbox.rect.center = (int(hb_cx), int(cur_y))

            left_x = min(self.start_x, hb_cx - self.hitbox_w * 0.5)
            right_x = max(self.start_x, hb_cx + self.hitbox_w * 0.5)
            span_w = max(self.hitbox_w, int(right_x - left_x))
            self.rect = pygame.Rect(
                int(left_x),
                int(cur_y - self.hitbox_h // 2),
                span_w,
                self.hitbox_h,
            )

        super().update(dt)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = int(240 * (1.0 - p * 0.72))
        if alpha <= 5:
            return

        w, h = self.rect.width, self.rect.height
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        beam_h = max(4, int(h * 0.30 * (1.0 - p * 0.45)))
        cy = h // 2
        pygame.draw.ellipse(
            surf, (40, 140, 255, int(alpha * 0.65)), (0, cy - beam_h, w, beam_h * 2)
        )
        pygame.draw.line(
            surf, (220, 250, 255, alpha), (4, cy), (w - 4, cy), max(2, beam_h // 2)
        )
        pygame.draw.line(
            surf,
            (100, 210, 255, int(alpha * 0.85)),
            (12, cy - 14),
            (w - 12, cy + 10),
            2,
        )
        pygame.draw.line(
            surf,
            (100, 210, 255, int(alpha * 0.85)),
            (12, cy + 14),
            (w - 12, cy - 10),
            2,
        )

        screen.blit(surf, (self.rect.x - camera_x, self.rect.y - camera_y))


class ProjectileWaveVFX(BaseVFX):
    """
    Boss 遠程劍氣波 (ATTACK_3) 特效
    """

    def __init__(
        self,
        x,
        y,
        direction,
        speed=560.0,
        width=56,
        height=92,
        duration=1.35,
        hitbox=None,
    ):
        super().__init__(x, y, duration=duration, hitbox=hitbox)
        self.direction = -1 if direction < 0 else 1
        self.speed = speed
        self.width = width
        self.height = height
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (int(x), int(y))
        if self.hitbox:
            self.hitbox.rect = self.rect.inflate(-8, -10)
            self.hitbox.rect.center = self.rect.center

    def update(self, dt=1 / 60):
        self.pos_x += self.direction * self.speed * dt
        self.rect.center = (int(self.pos_x), int(self.pos_y))
        if self.hitbox and self.hitbox.active:
            self.hitbox.rect.center = self.rect.center
        super().update(dt)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        fade = 1.0 if p < 0.8 else (1.0 - (p - 0.8) / 0.2)
        alpha = max(0, min(255, int(245 * fade)))
        if alpha <= 5:
            return

        w, h = self.width, self.height
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        pts_outer = []
        pts_inner = []
        steps = 14
        for i in range(steps + 1):
            t = i / steps
            ang = -0.46 * math.pi + t * 0.92 * math.pi
            xo = w * 0.14 + math.cos(ang) * (w * 0.74)
            yo = h * 0.50 + math.sin(ang) * (h * 0.46)
            xi = w * 0.14 + math.cos(ang) * (w * 0.38)
            yi = h * 0.50 + math.sin(ang) * (h * 0.38)
            pts_outer.append((xo, yo))
            pts_inner.append((xi, yi))

        poly = pts_outer + list(reversed(pts_inner))
        pygame.draw.polygon(surf, (70, 150, 255, int(alpha * 0.82)), poly)
        pygame.draw.lines(surf, (230, 250, 255, alpha), False, pts_outer, 3)

        if self.direction < 0:
            surf = pygame.transform.flip(surf, True, False)

        screen.blit(surf, (self.rect.x - camera_x, self.rect.y - camera_y))


class GroundShockwaveVFX(BaseVFX):
    """
    Boss 次元斬領域 / 範圍衝擊波特效 (ATTACK_3 第二段)
    """

    def __init__(
        self,
        target_x,
        ground_y,
        radius=64,
        windup_time=0.45,
        active_time=0.26,
        recovery_time=0.18,
        damage=20,
        hitbox_list=None,
    ):
        total_duration = windup_time + active_time + recovery_time
        center_y = ground_y - radius
        super().__init__(target_x, center_y, duration=total_duration, hitbox=None)
        self.windup_time = windup_time
        self.active_time = active_time
        self.recovery_time = recovery_time
        self.radius = radius
        self.ground_y = ground_y
        self.damage = damage
        self.hitbox_list = hitbox_list
        self.spawned_active_hitbox = False

        self.rect = pygame.Rect(0, 0, int(radius * 2), int(radius * 2))
        self.rect.center = (int(self.pos_x), int(self.pos_y))
        self.slash_lines = [random.uniform(0, math.pi) for _ in range(7)]

    def update(self, dt=1 / 60):
        if (
            not self.spawned_active_hitbox
            and self.elapsed >= self.windup_time
            and self.elapsed < self.windup_time + self.active_time
        ):
            self.spawned_active_hitbox = True
            hb_rect = self.rect.inflate(-18, -18)
            hb_rect.center = self.rect.center
            hb = Hitbox(
                owner="boss",
                rect=hb_rect,
                damage=self.damage,
                knockback_x=240.0,
                lifetime=self.active_time,
                tag="boss_aoe",
            )
            self.bind_hitbox(hb)
            if self.hitbox_list is not None:
                self.hitbox_list.append(hb)

        if (
            self.hitbox
            and self.hitbox.active
            and self.elapsed >= self.windup_time + self.active_time
        ):
            self.hitbox.destroy()

        super().update(dt)

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(self.pos_x - camera_x)
        sy = int(self.pos_y - camera_y)
        gy = int(self.ground_y - camera_y)

        if self.elapsed < self.windup_time:
            wp = self.elapsed / max(self.windup_time, 0.01)
            r = int(self.radius * (1.25 - 0.35 * wp))
            alpha = int(80 + 140 * wp)
            warn_surf = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
            pygame.draw.circle(
                warn_surf, (130, 80, 255, int(alpha * 0.35)), (r + 4, r + 4), r
            )
            pygame.draw.circle(
                warn_surf, (180, 220, 255, alpha), (r + 4, r + 4), r, 2
            )
            screen.blit(warn_surf, (sx - r - 4, sy - r - 4))
            pygame.draw.line(
                screen,
                (120, 220, 255),
                (sx - self.radius, gy),
                (sx + self.radius, gy),
                3,
            )
        else:
            act_elapsed = self.elapsed - self.windup_time
            act_total = self.active_time + self.recovery_time
            ap = min(1.0, act_elapsed / max(act_total, 0.01))
            alpha = int(245 * (1.0 - ap * 0.85))
            r = self.radius
            surf = pygame.Surface((r * 2 + 20, r * 2 + 20), pygame.SRCALPHA)
            cx, cy = r + 10, r + 10

            pygame.draw.circle(surf, (45, 25, 110, int(alpha * 0.75)), (cx, cy), r)
            pygame.draw.circle(surf, (130, 220, 255, alpha), (cx, cy), r, 3)

            for ang in self.slash_lines:
                dx = math.cos(ang + ap * 1.8) * (r * 1.05)
                dy = math.sin(ang + ap * 1.8) * (r * 1.05)
                pygame.draw.line(
                    surf,
                    (235, 250, 255, alpha),
                    (cx - dx, cy - dy),
                    (cx + dx, cy + dy),
                    2,
                )

            screen.blit(surf, (sx - cx, sy - cy))


class ParrySparkVFX(BaseVFX):
    """
    格擋與完美格擋專屬「像素水墨風格 (Pixel Art Ink-Splash)」特效：
    - 嚴格僅在完美格擋 (perfect=True) 時啟用像素水墨渲染管線：
      1. 像素化渲染管線 (Pixelation Pass)：所有水墨、光盾、火花與雙圓環皆先繪製於 1/3 低解析度小畫布，
         再以 pygame.transform.scale (Nearest-Neighbor 無平滑濾鏡) 放大 3 倍貼回世界畫布，保留粗顆粒硬邊像素鋸齒感。
      2. 格擋亮青色半月光盾 (Cyan Crescent Shield)：在玩家格擋前方生成像素風半月形青藍能量護盾。
      3. 橘黃尖刺爆裂核心 (Orange-Yellow Spiky Core)：由護盾前方朝向 Boss 噴發刺眼的亮黃 / 亮橘 / 赤紅放射狀尖刺火花。
      4. 深海軍藍與寶藍水墨飛濺 (Dark Navy & Royal Blue Ink Splatters & Floor Puddles)：
         在外圍、Boss 斜上方、玩家後方與地面飛濺出大量深海軍藍與寶藍色的大塊墨漬、水滴與地板橫向墨跡。
      5. 擴散雙圓環 (Dual Concentric Cyan Shockwave Rings)：以格擋點為中心向外擴散兩道淡青色同心圓震波。
    """

    PIXEL_SCALE = 3  # 像素粗顆粒放大倍率 (3x3 像素塊)

    def __init__(self, x, y, perfect=True, facing_dir=1, ground_y=GROUND_Y):
        # 完美格擋在子彈時間 (0.2x) 下更新，duration=0.22 對應真實時間約 1.0 秒
        duration = 0.22 if perfect else 0.18
        super().__init__(x, y, duration=duration, hitbox=None)
        self.perfect = perfect
        self.facing_dir = -1 if facing_dir < 0 else 1
        self.ground_y = float(ground_y)
        self._low_surf = (
            pygame.Surface((176, 124), pygame.SRCALPHA)
            if perfect
            else pygame.Surface((100, 100), pygame.SRCALPHA)
        )

        if perfect:
            # A. 深海軍藍 (Dark Navy) 與寶藍色 (Royal Blue) 水墨斑點與墨漬
            ink_colors = [
                (8, 18, 62),      # 極深海軍藍墨漬 (Deepest Navy Ink)
                (14, 32, 96),     # 深海軍藍 (Dark Navy Blue)
                (22, 68, 178),    # 靛藍墨色 (Indigo Ink)
                (30, 105, 240),   # 寶藍色 (Royal Blue)
            ]
            self.ink_splatters = []
            for _ in range(48):
                # 讓大量水墨往 Boss 右上方與玩家左後方噴濺 (還原參考圖構圖)
                if random.random() < 0.62:
                    base_ang = random.uniform(-0.85 * math.pi, 0.45 * math.pi)
                    if self.facing_dir < 0:
                        base_ang = math.pi - base_ang
                else:
                    base_ang = random.uniform(-math.pi, math.pi)

                dist_low = random.uniform(12.0, 74.0)
                radius_low = random.uniform(2.2, 7.2)
                col = random.choice(ink_colors)
                lobes = [random.uniform(0.55, 1.45) for _ in range(6)]
                has_droplet = random.random() < 0.75
                self.ink_splatters.append(
                    (base_ang, dist_low, radius_low, col, lobes, has_droplet)
                )

            # B. 細小噴散墨珠 (Fine Ink Dots)
            self.ink_dots = [
                (
                    random.uniform(-math.pi, math.pi),
                    random.uniform(16.0, 82.0),
                    random.choice([1, 1, 2]),
                    random.choice(ink_colors + [(70, 215, 255), (255, 210, 55)]),
                )
                for _ in range(55)
            ]

            # C. 地面橫向水墨飛濺與墨漬 (Floor Ink Puddles & Splashes)
            self.floor_puddles = []
            for _ in range(18):
                ox = random.uniform(-62.0, 58.0)
                pw = random.uniform(5.0, 18.0)
                ph = random.uniform(1.5, 4.0)
                col = random.choice([(8, 18, 62), (14, 32, 96), (22, 68, 178)])
                self.floor_puddles.append((ox, pw, ph, col))

            # D. 朝向 Boss 方向噴發的橘黃尖刺爆裂核心 (Orange-Yellow Spiky Rays)
            self.spiky_rays = []
            num_spikes = 17
            for i in range(num_spikes):
                # 集中於面向 Boss 的前方扇形 (-72度 ~ +72度)
                rel_ang = -0.40 * math.pi + (i / max(1, num_spikes - 1)) * 0.80 * math.pi
                rel_ang += random.uniform(-0.06, 0.06)
                length_low = random.uniform(22.0, 54.0)
                half_w = random.uniform(2.2, 4.8)
                self.spiky_rays.append((rel_ang, length_low, half_w))
        else:
            self.sparks = [
                (random.uniform(0, math.tau), random.uniform(45, 110), (180, 225, 255))
                for _ in range(8)
            ]

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        sx = int(self.pos_x - camera_x)
        sy = int(self.pos_y - camera_y)

        if not self.perfect:
            alpha = max(0, int(255 * (1.0 - p)))
            r = max(4, int(38 * (0.25 + 0.75 * p)))
            surf = self._low_surf
            surf.fill((0, 0, 0, 0))
            cx, cy = 50, 50
            pygame.draw.circle(surf, (80, 160, 255, alpha), (cx, cy), r, 2)
            for ang, spd, col in self.sparks:
                x1 = cx + math.cos(ang) * (spd * p * 0.4)
                y1 = cy + math.sin(ang) * (spd * p * 0.4)
                x2 = cx + math.cos(ang) * (spd * p * 0.85)
                y2 = cy + math.sin(ang) * (spd * p * 0.85)
                pygame.draw.line(surf, (*col, alpha), (x1, y1), (x2, y2), 2)
            screen.blit(surf, (sx - cx, sy - cy))
            return

        # ==================== 完美格擋專屬：像素水墨風格 (Pixel Art Ink-Splash) ====================
        burst_t = 1.0 - pow(1.0 - p, 3.4)
        fade_alpha = max(0, min(255, int(255 * (1.0 - pow(p, 1.8)))))
        if fade_alpha <= 5:
            return

        # Reuse pre-allocated low-res canvas (176 x 124) and scale up 3x with Nearest-Neighbor
        scale = self.PIXEL_SCALE
        low_w, low_h = 176, 124
        low_surf = self._low_surf
        low_surf.fill((0, 0, 0, 0))
        cx, cy = low_w // 2, low_h // 2
        f_dir = self.facing_dir

        # 計算地面在低解析度畫布上的 Y 座標
        ground_dy_low = int(round((self.ground_y - self.pos_y) / scale))
        floor_y = min(low_h - 4, max(cy + 6, cy + ground_dy_low))

        # -------------------------------------------------------------------------
        # 1. 擴散雙圓環 (Dual Concentric Cyan Shockwave Rings)
        # -------------------------------------------------------------------------
        ring_r1 = int(14 + 42 * burst_t)
        ring_r2 = int(9 + 30 * burst_t)
        ring_alpha = int(fade_alpha * 0.88)
        pygame.draw.circle(
            low_surf, (165, 240, 255, ring_alpha), (cx, cy), ring_r1, 2
        )
        pygame.draw.circle(
            low_surf, (70, 205, 255, int(ring_alpha * 0.85)), (cx, cy), ring_r2, 1
        )

        # -------------------------------------------------------------------------
        # 2. 外圍與地板：深海軍藍與寶藍水墨飛濺 (Dark Navy & Royal Blue Ink Splatters)
        # -------------------------------------------------------------------------
        ink_alpha = int(fade_alpha * 0.96)

        # (a) 地板橫向墨漬與同心水墨弧跡 (還原參考圖角色腳底與地板的深藍墨水圈)
        pygame.draw.ellipse(
            low_surf,
            (8, 18, 62, ink_alpha),
            (cx - int(46 * burst_t), floor_y - 4, int(92 * burst_t), 8),
            2,
        )
        for ox, pw, ph, col in self.floor_puddles:
            px = int(cx + ox * burst_t)
            py = int(floor_y + random.uniform(-2.0, 2.0))
            cur_w = max(2, int(pw * (1.0 - 0.35 * p)))
            cur_h = max(1, int(ph))
            pygame.draw.ellipse(
                low_surf,
                (*col, ink_alpha),
                (px - cur_w // 2, py - cur_h // 2, cur_w, cur_h),
            )

        # (b) 空中放射飛濺的大塊不規則水墨斑點
        for ang, max_d, base_r, col, lobes, has_drop in self.ink_splatters:
            cur_d = max_d * burst_t
            bx = cx + math.cos(ang) * cur_d
            by = min(floor_y, cy + math.sin(ang) * (cur_d * 0.85) + p * 4.5)
            cur_r = base_r * (1.0 - 0.48 * p)
            if cur_r < 1.0:
                continue

            pts = []
            n_lobes = len(lobes)
            for idx, lf in enumerate(lobes):
                theta = ang + (idx / n_lobes) * math.tau
                stretch = 1.45 if idx in (0, n_lobes - 1) else 0.88
                pts.append(
                    (
                        bx + math.cos(theta) * cur_r * lf * stretch,
                        by + math.sin(theta) * cur_r * lf,
                    )
                )
            pygame.draw.polygon(low_surf, (*col, ink_alpha), pts)

            if has_drop:
                tx = int(bx + math.cos(ang) * (cur_r * 1.55))
                ty = int(by + math.sin(ang) * (cur_r * 1.55))
                pygame.draw.circle(
                    low_surf, (*col, ink_alpha), (tx, ty), max(1, int(cur_r * 0.38))
                )

        # (c) 細小像素墨點 (Fine Pixel Ink Drops)
        for ang, max_d, dot_r, col in self.ink_dots:
            dx = int(cx + math.cos(ang) * max_d * burst_t)
            dy = int(min(floor_y, cy + math.sin(ang) * max_d * burst_t * 0.85))
            if dot_r <= 1:
                low_surf.fill((*col, ink_alpha), pygame.Rect(dx, dy, 1, 1))
            else:
                pygame.draw.circle(low_surf, (*col, ink_alpha), (dx, dy), dot_r)

        # -------------------------------------------------------------------------
        # 3. 碰撞點右側 (Boss 方向)：橘黃爆裂尖刺核心 (Orange-Yellow Spiky Core)
        # -------------------------------------------------------------------------
        core_x = cx + f_dir * 6
        core_y = cy
        core_scale = (0.45 + 0.55 * burst_t) * max(0.15, 1.0 - p * 0.65)

        # (a) 底層深海軍藍墨水襯底塊 (突顯橘黃火花的強烈對比)
        pygame.draw.circle(
            low_surf,
            (10, 22, 72, ink_alpha),
            (core_x + f_dir * 12, core_y),
            max(4, int(16 * core_scale)),
        )

        # (b) 外層赤紅/亮橘放射狀尖刺火花 (Spiky Orange-Red Rays)
        for rel_ang, ray_len, half_w in self.spiky_rays:
            world_ang = rel_ang if f_dir > 0 else (math.pi - rel_ang)
            cur_len = ray_len * core_scale
            perp_ang = world_ang + math.pi * 0.5

            tip_x = core_x + math.cos(world_ang) * cur_len
            tip_y = core_y + math.sin(world_ang) * cur_len
            b1_x = core_x + math.cos(perp_ang) * half_w
            b1_y = core_y + math.sin(perp_ang) * half_w
            b2_x = core_x - math.cos(perp_ang) * half_w
            b2_y = core_y - math.sin(perp_ang) * half_w

            pygame.draw.polygon(
                low_surf,
                (255, 110, 20, fade_alpha),
                [(b1_x, b1_y), (tip_x, tip_y), (b2_x, b2_y)],
            )

            # 內層亮黃尖刺 (Bright Yellow Inner Spike)
            in_len = cur_len * 0.68
            in_w = half_w * 0.58
            itip_x = core_x + math.cos(world_ang) * in_len
            itip_y = core_y + math.sin(world_ang) * in_len
            ib1_x = core_x + math.cos(perp_ang) * in_w
            ib1_y = core_y + math.sin(perp_ang) * in_w
            ib2_x = core_x - math.cos(perp_ang) * in_w
            ib2_y = core_y - math.sin(perp_ang) * in_w
            pygame.draw.polygon(
                low_surf,
                (255, 242, 65, fade_alpha),
                [(ib1_x, ib1_y), (itip_x, itip_y), (ib2_x, ib2_y)],
            )

        # (c) 爆裂核心處點綴深藍水墨碎塊 (重現參考圖橘黃火花中夾雜的深藍墨塊)
        for i in range(6):
            ang = (-0.32 + i * 0.13) * math.pi
            if f_dir < 0:
                ang = math.pi - ang
            fx = int(core_x + math.cos(ang) * (15 * core_scale))
            fy = int(core_y + math.sin(ang) * (15 * core_scale))
            pygame.draw.circle(low_surf, (10, 22, 72, ink_alpha), (fx, fy), 2)

        # -------------------------------------------------------------------------
        # 4. 格擋亮青色半月像素光盾 (Cyan Crescent Energy Shield)
        # -------------------------------------------------------------------------
        shield_x = cx - f_dir * 2
        shield_y = cy
        sh_rx = max(4, int(9 * (0.75 + 0.25 * burst_t)))
        sh_ry = max(8, int(22 * (0.75 + 0.25 * burst_t)))

        pts_sh_outer = []
        pts_sh_inner = []
        pts_sh_core = []
        sh_steps = 10
        for i in range(sh_steps + 1):
            t = -0.48 * math.pi + (i / sh_steps) * 0.96 * math.pi
            ox = shield_x + f_dir * math.cos(t) * sh_rx
            oy = shield_y + math.sin(t) * sh_ry
            ix = shield_x + f_dir * (math.cos(t) * (sh_rx * 0.42) - 2.0)
            iy = shield_y + math.sin(t) * (sh_ry * 0.86)
            cx_pt = shield_x + f_dir * (math.cos(t) * (sh_rx * 0.72))
            cy_pt = shield_y + math.sin(t) * (sh_ry * 0.88)

            pts_sh_outer.append((ox, oy))
            pts_sh_inner.append((ix, iy))
            pts_sh_core.append((cx_pt, cy_pt))

        shield_poly = pts_sh_outer + list(reversed(pts_sh_inner))
        if len(shield_poly) >= 3:
            # 外層電光青藍護盾
            pygame.draw.polygon(
                low_surf, (0, 175, 255, fade_alpha), shield_poly
            )
            # 中層亮青色光暈
            pygame.draw.lines(
                low_surf, (95, 245, 255, fade_alpha), False, pts_sh_outer, 2
            )
            # 內核純白高光弧線
            pygame.draw.lines(
                low_surf, (235, 255, 255, fade_alpha), False, pts_sh_core, 2
            )

        # -------------------------------------------------------------------------
        # 5. Pixelation Pass：以 Nearest-Neighbor 硬邊放大貼回世界畫布
        # -------------------------------------------------------------------------
        pixelated_surf = pygame.transform.scale(
            low_surf, (low_w * scale, low_h * scale)
        )
        screen.blit(
            pixelated_surf,
            (sx - (low_w * scale) // 2, sy - (low_h * scale) // 2),
        )


class HealVFX(BaseVFX):
    """
    檢查點 (Checkpoint) 按 E 存檔並回滿血量時的像素恢復粒子特效：
    - 產生向上飄升的亮綠色與亮青色像素方塊與十字光芒 (+)，以及腳底擴散治癒光圈
    """

    def __init__(self, x, y, duration=0.85):
        super().__init__(x, y, duration=duration, hitbox=None)
        self._canvas = pygame.Surface((120, 140), pygame.SRCALPHA)
        self.particles = []
        palette = [
            (65, 255, 145),   # 亮翠綠
            (85, 245, 255),   # 亮青藍
            (185, 255, 195),  # 嫩白綠
        ]
        for _ in range(28):
            ox = random.uniform(-26.0, 26.0)
            oy = random.uniform(-6.0, 12.0)
            vy = random.uniform(48.0, 115.0)
            size = random.choice([2, 3, 4])
            is_cross = random.random() < 0.45
            col = random.choice(palette)
            self.particles.append([ox, oy, vy, size, is_cross, col])

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, min(255, int(255 * (1.0 - pow(p, 1.5)))))
        if alpha <= 5:
            return

        sx = int(self.pos_x - camera_x)
        sy = int(self.pos_y - camera_y)

        surf = self._canvas
        surf.fill((0, 0, 0, 0))
        cx, cy = 60, 110

        # 1. 腳底擴散治癒雙光圈
        ring_rx = int(16 + 34 * p)
        ring_ry = int(5 + 10 * p)
        pygame.draw.ellipse(
            surf,
            (65, 255, 145, int(alpha * 0.85)),
            (cx - ring_rx, cy - ring_ry, ring_rx * 2, ring_ry * 2),
            2,
        )
        pygame.draw.ellipse(
            surf,
            (120, 245, 255, int(alpha * 0.70)),
            (
                cx - int(ring_rx * 0.65),
                cy - int(ring_ry * 0.65),
                int(ring_rx * 1.3),
                int(ring_ry * 1.3),
            ),
            2,
        )

        # 2. 向上飄升的像素恢復粒子與十字
        for ox, oy, vy, sz, is_cross, col in self.particles:
            px = int(cx + ox + math.sin(p * 8.0 + ox) * 3.0)
            py = int(cy + oy - vy * p)
            if is_cross:
                pygame.draw.rect(
                    surf, (*col, alpha), (px - sz, py - 1, sz * 2 + 1, 3)
                )
                pygame.draw.rect(
                    surf, (*col, alpha), (px - 1, py - sz, 3, sz * 2 + 1)
                )
            else:
                pygame.draw.rect(surf, (*col, alpha), (px - sz // 2, py - sz // 2, sz, sz))

        screen.blit(surf, (sx - cx, sy - cy))


class PortalTeleportVFX(BaseVFX):
    """
    傳送門 (Portal) 按 E 觸發時的傳送光粒子特效：
    - mode="depart"：玩家被吸入傳送門、化為螺旋收束光粒子與垂直光柱
    - mode="arrive"：玩家於新場景出現時的光粒子向外擴散凝聚特效
    """

    def __init__(self, x, y, duration=0.55, mode="depart"):
        super().__init__(x, y, duration=duration, hitbox=None)
        self.mode = mode
        self._canvas = pygame.Surface((140, 140), pygame.SRCALPHA)
        self.particles = []
        colors = [
            (95, 245, 255),   # 亮青
            (175, 115, 255),  # 秘法紫
            (240, 250, 255),  # 純白光點
        ]
        for i in range(34):
            ang = (i / 34.0) * math.tau + random.uniform(-0.1, 0.1)
            max_r = random.uniform(18.0, 56.0)
            y_off = random.uniform(-54.0, 4.0)
            sz = random.choice([2, 3, 4])
            col = random.choice(colors)
            self.particles.append((ang, max_r, y_off, sz, col))

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        t = (1.0 - p) if self.mode == "depart" else p
        alpha = max(0, min(255, int(255 * math.sin(p * math.pi))))
        if alpha <= 5:
            return

        sx = int(self.pos_x - camera_x)
        sy = int(self.pos_y - camera_y)

        surf = self._canvas
        surf.fill((0, 0, 0, 0))
        cx, cy = 70, 95

        # 中央垂直傳送光束
        beam_w = max(2, int(24 * math.sin(p * math.pi)))
        pygame.draw.rect(
            surf,
            (90, 225, 255, int(alpha * 0.65)),
            (cx - beam_w, 8, beam_w * 2, cy - 4),
        )
        pygame.draw.rect(
            surf,
            (235, 250, 255, int(alpha * 0.90)),
            (cx - max(1, beam_w // 2), 8, max(2, beam_w), cy - 4),
        )

        # 螺旋光粒子
        for ang, max_r, y_off, sz, col in self.particles:
            cur_ang = ang + p * 6.5
            cur_r = max_r * t
            px = int(cx + math.cos(cur_ang) * cur_r)
            py = int(cy + y_off * (0.4 + 0.6 * t) - (1.0 - t) * 18.0)
            pygame.draw.rect(surf, (*col, alpha), (px - sz // 2, py - sz // 2, sz, sz))

        screen.blit(surf, (sx - cx, sy - cy))


def draw_floating_prompt_box(
    screen,
    world_x,
    world_y,
    camera_x,
    camera_y,
    text,
    font,
    border_color=(90, 230, 255),
    text_color=(245, 252, 255),
):
    """
    Draw a floating pixel-art prompt window above an interactive object (Checkpoint / Portal).
    Uses antialias=False for crisp pixel edges and calibrated padding so English text never overflows.
    """
    t_sec = pygame.time.get_ticks() / 1000.0
    bob_offset = int(round(math.sin(t_sec * 5.2) * 3.5))

    sx = int(round(world_x - camera_x))
    sy = int(round(world_y - camera_y)) + bob_offset

    txt_surf = font.render(text, False, text_color)
    pad_x, pad_y = 14, 7
    box_w = max(120, txt_surf.get_width() + pad_x * 2)
    box_h = txt_surf.get_height() + pad_y * 2

    box_rect = pygame.Rect(sx - box_w // 2, sy - box_h - 8, box_w, box_h)

    # Pixel-art double-bordered frame
    bg_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    bg_surf.fill((14, 18, 32, 230))
    screen.blit(bg_surf, box_rect.topleft)

    pygame.draw.rect(screen, (30, 42, 68), box_rect.inflate(4, 4), 2)
    pygame.draw.rect(screen, border_color, box_rect, 2)

    # Downward-pointing pixel arrow
    tri_pts = [
        (sx - 5, box_rect.bottom),
        (sx + 5, box_rect.bottom),
        (sx, box_rect.bottom + 5),
    ]
    pygame.draw.polygon(screen, border_color, tri_pts)

    txt_rect = txt_surf.get_rect(center=box_rect.center)
    screen.blit(txt_surf, txt_rect)


def _draw_crosshair(screen, x, y, color, radius=5):
    """繪製基準錨點十字與中心圓點"""
    ix, iy = int(x), int(y)
    pygame.draw.line(screen, color, (ix - radius - 2, iy), (ix + radius + 2, iy), 2)
    pygame.draw.line(screen, color, (ix, iy - radius - 2), (ix, iy + radius + 2), 2)
    pygame.draw.circle(screen, color, (ix, iy), radius, 1)


def draw_debug_boxes(
    screen,
    camera_x,
    camera_y,
    player,
    boss,
    active_hitboxes,
    vfx_group=None,
    regular_enemies=None,
):
    """
    在開啟 Debug 模式時繪製：
    - 灰色細框：原始圖片外框 (Sprite Rect，含透明邊距)
    - 黃色線框：移動物理碰撞框 (Collision Box)
    - 綠色線框 + 中心十字：受擊框 (Hurtbox) 與角色身體中心
    - 洋紅/白色十字圓點：角色腳底基準錨點 (Anchor Point: pos_x, pos_y) 與面向指示線
    - 青色/藍色線框：玩家格擋判定框 (Parry/Block Box)
    - 紅色線框 + 中心十字：啟用中的攻擊判定框 (Active Hitbox) 與特效錨點
    """
    if player and player.alive():
        pygame.draw.rect(
            screen,
            (110, 110, 120),
            player.rect.move(-camera_x, -camera_y),
            1,
        )
        pygame.draw.rect(
            screen,
            COLOR_DEBUG_COLLISION,
            player.collision_rect.move(-camera_x, -camera_y),
            1,
        )
        hb_screen = player.hurtbox.move(-camera_x, -camera_y)
        pygame.draw.rect(screen, COLOR_DEBUG_HURTBOX, hb_screen, 2)
        _draw_crosshair(
            screen, hb_screen.centerx, hb_screen.centery, COLOR_DEBUG_HURTBOX, radius=4
        )

        ax = int(player.pos_x - camera_x)
        ay = int(player.pos_y - camera_y)
        _draw_crosshair(screen, ax, ay, (255, 80, 255), radius=5)
        facing_dir = -1 if player.flip else 1
        pygame.draw.line(
            screen,
            (255, 80, 255),
            (hb_screen.centerx, hb_screen.centery),
            (hb_screen.centerx + facing_dir * 18, hb_screen.centery),
            2,
        )

        if player.is_blocking and player.parry_box:
            p_color = COLOR_DEBUG_PARRY if player.is_parrying else COLOR_DEBUG_BLOCK
            pb_screen = player.parry_box.move(-camera_x, -camera_y)
            pygame.draw.rect(screen, p_color, pb_screen, 2)
            _draw_crosshair(screen, pb_screen.centerx, pb_screen.centery, p_color, 3)

    if boss and boss.alive():
        pygame.draw.rect(
            screen,
            (110, 110, 120),
            boss.rect.move(-camera_x, -camera_y),
            1,
        )
        pygame.draw.rect(
            screen,
            COLOR_DEBUG_COLLISION,
            boss.collision_rect.move(-camera_x, -camera_y),
            1,
        )
        bh_screen = boss.hurtbox.move(-camera_x, -camera_y)
        pygame.draw.rect(screen, COLOR_DEBUG_HURTBOX, bh_screen, 2)
        _draw_crosshair(
            screen, bh_screen.centerx, bh_screen.centery, COLOR_DEBUG_HURTBOX, radius=4
        )

        b_ax = int(boss.pos_x - camera_x)
        b_ay = int(boss.pos_y - camera_y)
        _draw_crosshair(screen, b_ax, b_ay, (255, 80, 255), radius=5)
        b_facing = -1 if boss.flip else 1
        pygame.draw.line(
            screen,
            (255, 80, 255),
            (bh_screen.centerx, bh_screen.centery),
            (bh_screen.centerx + b_facing * 24, bh_screen.centery),
            2,
        )

    if regular_enemies is not None:
        for mob in regular_enemies:
            if not mob.alive():
                continue
            pygame.draw.rect(
                screen,
                (110, 110, 120),
                mob.rect.move(-camera_x, -camera_y),
                1,
            )
            pygame.draw.rect(
                screen,
                COLOR_DEBUG_COLLISION,
                mob.collision_rect.move(-camera_x, -camera_y),
                1,
            )
            mh_screen = mob.hurtbox.move(-camera_x, -camera_y)
            pygame.draw.rect(screen, COLOR_DEBUG_HURTBOX, mh_screen, 2)
            _draw_crosshair(
                screen,
                mh_screen.centerx,
                mh_screen.centery,
                COLOR_DEBUG_HURTBOX,
                radius=3,
            )
            m_ax = int(mob.pos_x - camera_x)
            m_ay = int(mob.pos_y - camera_y)
            _draw_crosshair(screen, m_ax, m_ay, (255, 80, 255), radius=4)
            m_facing = getattr(mob, "facing_dir", -1)
            pygame.draw.line(
                screen,
                (255, 80, 255),
                (mh_screen.centerx, mh_screen.centery),
                (mh_screen.centerx + m_facing * 16, mh_screen.centery),
                2,
            )

    if vfx_group is not None:
        for vfx in vfx_group:
            vx, vy = vfx.anchor_point
            pygame.draw.circle(
                screen, (255, 180, 40), (vx - camera_x, vy - camera_y), 3
            )

    for hb in active_hitboxes:
        if hb.active:
            r_screen = hb.rect.move(-camera_x, -camera_y)
            pygame.draw.rect(screen, COLOR_DEBUG_HITBOX, r_screen, 2)
            _draw_crosshair(
                screen,
                r_screen.centerx,
                r_screen.centery,
                COLOR_DEBUG_HITBOX,
                radius=4,
            )


# =============================================================================
# Undertale-Style Sans Attack VFX (Bone Wave, Homing Bone, Gaster Blaster)
# =============================================================================

_SANS_ASSET_CACHE = {}


def _load_sans_asset(filename):
    """Load and cache transparent RGBA pixel-art assets from assets/sprites/sans/"""
    if filename in _SANS_ASSET_CACHE:
        return _SANS_ASSET_CACHE[filename]
    path = os.path.join("assets", "sprites", "sans", filename)
    if os.path.exists(path):
        surf = pygame.image.load(path).convert_alpha()
    else:
        surf = pygame.Surface((24, 64), pygame.SRCALPHA)
        pygame.draw.rect(surf, (245, 248, 255), (6, 4, 12, 56))
    _SANS_ASSET_CACHE[filename] = surf
    return surf


class BoneWaveVFX(BaseVFX):
    """
    Sans Attack 1 — Bone Wave (骨浪突襲):
    - Rises sequentially from the ground/platform and surges forward.
    - Synced Hitbox (tag='sans_bone_wave') activates during active rise/surge and is destroyed on retract.
    """

    def __init__(
        self,
        x,
        ground_y,
        height=76,
        direction=1,
        speed=255.0,
        delay=0.0,
        duration=0.95,
        cyan=False,
        damage=14,
        hitbox_list=None,
    ):
        super().__init__(x, ground_y, duration=delay + duration, hitbox=None)
        self.ground_y = float(ground_y)
        self.max_height = int(height)
        self.direction = -1 if direction < 0 else 1
        self.speed = float(speed)
        self.delay = max(0.0, float(delay))
        self.active_duration = max(0.1, float(duration))
        self.damage = damage
        self.is_blue = bool(cyan)
        self.attack_type = "blue" if self.is_blue else "white"
        self.hitbox_list = hitbox_list
        self.spawned_hb = False

        base_img = _load_sans_asset("bone_cyan.png" if cyan else "bone_white.png")
        self.bone_w = 24
        self.bone_img = pygame.transform.scale(base_img, (self.bone_w, self.max_height))
        if self.is_blue:
            # High-saturation Sky Blue (#00BFFF) enhancement for unmistakable Blue Attacks
            self.bone_img = self.bone_img.copy()
            self.bone_img.fill((0, 191, 255), special_flags=pygame.BLEND_RGB_MULT)
            self.bone_img.fill((0, 95, 165), special_flags=pygame.BLEND_RGB_ADD)
        self.cur_height = 0

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return

        if self.elapsed < self.delay:
            self.cur_height = 0
            return

        act_t = (self.elapsed - self.delay) / self.active_duration
        # Rise quickly (0..0.18), stay tall while surging forward (0.18..0.82), retract (0.82..1.0)
        if act_t < 0.18:
            h_ratio = act_t / 0.18
        elif act_t < 0.82:
            h_ratio = 1.0
        else:
            h_ratio = max(0.0, (1.0 - act_t) / 0.18)

        self.cur_height = int(self.max_height * h_ratio)
        self.pos_x += self.direction * self.speed * dt
        self.pos_y = self.ground_y - self.cur_height * 0.5

        if self.cur_height >= 18 and act_t < 0.86:
            hb_rect = pygame.Rect(
                int(round(self.pos_x - (self.bone_w - 6) * 0.5)),
                int(round(self.ground_y - self.cur_height + 4)),
                self.bone_w - 6,
                max(10, self.cur_height - 6),
            )
            if not self.spawned_hb:
                self.spawned_hb = True
                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=self.damage,
                    knockback_x=self.direction * 220.0,
                    lifetime=None,
                    tag="sans_bone_wave",
                    attack_type=self.attack_type,
                )
                self.bind_hitbox(hb)
                if self.hitbox_list is not None:
                    self.hitbox_list.append(hb)
            elif self.hitbox and self.hitbox.active:
                self.hitbox.rect = hb_rect
        else:
            if self.hitbox and self.hitbox.active:
                self.hitbox.destroy()

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        gy = int(round(self.ground_y - camera_y))

        if self.elapsed < self.delay:
            # Ground cyan telegraph spark before bone erupts
            pygame.draw.line(screen, (40, 225, 255), (sx - 12, gy), (sx + 12, gy), 3)
            return

        if self.cur_height < 4:
            return

        crop_rect = pygame.Rect(0, 0, self.bone_w, min(self.max_height, self.cur_height))
        sub = self.bone_img.subsurface(crop_rect)
        screen.blit(sub, (sx - self.bone_w // 2, gy - crop_rect.height))


class HomingBoneVFX(BaseVFX):
    """
    Sans Attack 2 — Homing Bone Barrage (懸空骨頭齊射):
    - Hovers and aims at the player during windup with a cyan sightline (no hitbox).
    - Launches at high speed along the locked aim vector with a synced Hitbox (tag='sans_homing_bone').
    """

    def __init__(
        self,
        x,
        y,
        target_x,
        target_y,
        windup=0.45,
        speed=580.0,
        duration=1.45,
        cyan=False,
        damage=15,
        hitbox_list=None,
    ):
        super().__init__(x, y, duration=windup + duration, hitbox=None)
        self.windup = max(0.05, float(windup))
        self.speed = float(speed)
        self.damage = damage
        self.is_blue = bool(cyan)
        self.attack_type = "blue" if self.is_blue else "white"
        self.hitbox_list = hitbox_list
        self.launched = False

        dx = float(target_x) - float(x)
        dy = float(target_y) - float(y)
        dist = max(1.0, math.hypot(dx, dy))
        self.vx = (dx / dist) * self.speed
        self.vy = (dy / dist) * self.speed
        self.angle_rad = math.atan2(dy, dx)

        base_img = _load_sans_asset("bone_cyan.png" if cyan else "bone_white.png")
        scaled = pygame.transform.scale(base_img, (20, 56))
        if self.is_blue:
            scaled = scaled.copy()
            scaled.fill((0, 191, 255), special_flags=pygame.BLEND_RGB_MULT)
            scaled.fill((0, 95, 165), special_flags=pygame.BLEND_RGB_ADD)
        # Bone sprite is vertical; rotate so its lengthwise axis points along angle_rad
        rot_deg = -math.degrees(self.angle_rad) - 90.0
        self.rotated_img = pygame.transform.rotate(scaled, rot_deg)
        self.rect = self.rotated_img.get_rect(center=(int(x), int(y)))

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return

        if self.elapsed < self.windup:
            return

        if not self.launched:
            self.launched = True
            from audio_manager import get_audio

            get_audio().play_sfx("bone_shoot")
            hb_rect = pygame.Rect(0, 0, 26, 26)
            hb_rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))
            kb = 230.0 if self.vx >= 0 else -230.0
            hb = Hitbox(
                owner="boss",
                rect=hb_rect,
                damage=self.damage,
                knockback_x=kb,
                lifetime=None,
                tag="sans_homing_bone",
                attack_type=self.attack_type,
            )
            self.bind_hitbox(hb)
            if self.hitbox_list is not None:
                self.hitbox_list.append(hb)

        self.pos_x += self.vx * dt
        self.pos_y += self.vy * dt
        self.rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))
        if self.hitbox and self.hitbox.active:
            self.hitbox.rect.center = self.rect.center

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))

        if self.elapsed < self.windup:
            # Draw pulsing cyan aim line during windup
            ex = int(sx + math.cos(self.angle_rad) * 260)
            ey = int(sy + math.sin(self.angle_rad) * 260)
            pygame.draw.line(screen, (45, 225, 255), (sx, sy), (ex, ey), 1)
            pygame.draw.circle(screen, (90, 240, 255), (sx, sy), 14, 2)

        draw_rect = self.rotated_img.get_rect(center=(sx, sy))
        screen.blit(self.rotated_img, draw_rect)


class GasterBlasterVFX(BaseVFX):
    """
    Sans Attack 3 — Gaster Blaster Laser Beam (龍骨砲高能光束):
    - WINDUP (0..windup): Summons Gaster Blaster aimed at player with pulsing red/cyan targeting sightline.
    - ACTIVE (windup..windup+active_time): Jaw snaps open and fires a wide white-cyan laser beam with
      multi-segment synced Hitboxes sharing a single hit_targets set (so it hits or Perfect Parries cleanly once!).
    - RECOVERY: Immediately destroys all beam Hitboxes and fades out.
    """

    def __init__(
        self,
        x,
        y,
        target_x,
        target_y,
        windup=0.65,
        active_time=0.46,
        recovery_time=0.26,
        beam_length=660.0,
        beam_width=40,
        damage=22,
        hitbox_list=None,
    ):
        total = windup + active_time + recovery_time
        super().__init__(x, y, duration=total, hitbox=None)
        self.windup = float(windup)
        self.active_time = float(active_time)
        self.recovery_time = float(recovery_time)
        self.beam_length = float(beam_length)
        self.beam_width = int(beam_width)
        self.damage = damage
        self.hitbox_list = hitbox_list

        dx = float(target_x) - float(x)
        dy = float(target_y) - float(y)
        self.angle_rad = math.atan2(dy, dx)
        self.dir_x = math.cos(self.angle_rad)
        self.dir_y = math.sin(self.angle_rad)

        rot_deg = -math.degrees(self.angle_rad)
        closed_raw = _load_sans_asset("gaster_blaster_closed.png")
        open_raw = _load_sans_asset("gaster_blaster_open.png")
        beam_raw = _load_sans_asset("gaster_beam.png")

        self.blaster_closed = pygame.transform.rotate(closed_raw, rot_deg)
        self.blaster_open = pygame.transform.rotate(open_raw, rot_deg)
        beam_stretched = pygame.transform.scale(
            beam_raw, (int(self.beam_length), self.beam_width)
        )
        self.beam_img = pygame.transform.rotate(beam_stretched, rot_deg)

        self.beam_hitboxes = []
        self.spawned_beam = False
        from audio_manager import get_audio

        get_audio().play_sfx("blaster_charge")

    def _clear_beam_hitboxes(self):
        for hb in self.beam_hitboxes:
            hb.destroy()
        self.beam_hitboxes.clear()

    def destroy(self):
        self._clear_beam_hitboxes()
        super().destroy()

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return

        if (
            not self.spawned_beam
            and self.elapsed >= self.windup
            and self.elapsed < self.windup + self.active_time
        ):
            self.spawned_beam = True
            from audio_manager import get_audio

            get_audio().play_sfx("blaster_fire")
            # Share one hit_targets set across all beam segments so player only takes 1 hit / 1 parry
            shared_hits = set()
            seg_size = max(32, int(self.beam_width * 0.90))
            num_segments = max(14, int(math.ceil(self.beam_length / (seg_size * 0.75))))
            seg_step = self.beam_length / num_segments
            kb = 280.0 if self.dir_x >= 0 else -280.0

            for i in range(num_segments):
                dist = 36.0 + seg_step * (i + 0.5)
                cx = self.pos_x + self.dir_x * dist
                cy = self.pos_y + self.dir_y * dist
                hb_rect = pygame.Rect(0, 0, seg_size, seg_size)
                hb_rect.center = (int(round(cx)), int(round(cy)))
                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=self.damage,
                    knockback_x=kb,
                    lifetime=self.active_time,
                    tag="sans_gaster_beam",
                )
                hb.hit_targets = shared_hits
                self.beam_hitboxes.append(hb)
                if self.hitbox_list is not None:
                    self.hitbox_list.append(hb)

        elif self.elapsed >= self.windup + self.active_time and self.beam_hitboxes:
            self._clear_beam_hitboxes()

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))

        # 1. WINDUP: Pulsing red/cyan laser sightline + Blaster sliding/charging
        if self.elapsed < self.windup:
            wp = self.elapsed / max(self.windup, 0.01)
            ex = int(sx + self.dir_x * self.beam_length)
            ey = int(sy + self.dir_y * self.beam_length)
            line_col = (255, 70, 90) if int(self.elapsed * 18) % 2 == 0 else (70, 235, 255)
            pygame.draw.line(screen, line_col, (sx, sy), (ex, ey), 2 if wp > 0.65 else 1)

            img = self.blaster_open if wp > 0.72 else self.blaster_closed
            screen.blit(img, img.get_rect(center=(sx, sy)))
            return

        # 2. ACTIVE: Full blazing Gaster Blaster beam + slight recoil
        if self.elapsed < self.windup + self.active_time:
            recoil = 8.0 * (1.0 - (self.elapsed - self.windup) / max(self.active_time, 0.01))
            bx = int(round(sx - self.dir_x * recoil))
            by = int(round(sy - self.dir_y * recoil))

            beam_mid_x = int(round(bx + self.dir_x * (30.0 + self.beam_length * 0.5)))
            beam_mid_y = int(round(by + self.dir_y * (30.0 + self.beam_length * 0.5)))
            screen.blit(
                self.beam_img, self.beam_img.get_rect(center=(beam_mid_x, beam_mid_y))
            )
            screen.blit(self.blaster_open, self.blaster_open.get_rect(center=(bx, by)))
            return

        # 3. RECOVERY: Fading blaster & beam afterglow
        rp = (self.elapsed - self.windup - self.active_time) / max(self.recovery_time, 0.01)
        alpha = max(0, int(255 * (1.0 - rp)))
        if alpha > 8:
            ghost = self.blaster_open.copy()
            ghost.set_alpha(alpha)
            screen.blit(ghost, ghost.get_rect(center=(sx, sy)))


# =============================================================================
# Regular Enemy VFX — Slimer Death Burst (SlimerDeath.png, 7 frames of 64x58)
# =============================================================================

_SLIMER_DEATH_FRAMES = None


def _get_slimer_death_frames(scale=1.45):
    global _SLIMER_DEATH_FRAMES
    if _SLIMER_DEATH_FRAMES is not None:
        return _SLIMER_DEATH_FRAMES

    path = os.path.join("assets", "sprites", "slimer", "SlimerDeath.png")
    frames = []
    if os.path.exists(path):
        sheet = pygame.image.load(path).convert_alpha()
        num_frames = 7
        fw = sheet.get_width() // num_frames
        fh = sheet.get_height()
        tw = max(1, int(round(fw * scale)))
        th = max(1, int(round(fh * scale)))
        for i in range(num_frames):
            sub = sheet.subsurface(pygame.Rect(i * fw, 0, fw, fh)).copy()
            frames.append(pygame.transform.scale(sub, (tw, th)))
    else:
        for i in range(5):
            surf = pygame.Surface((48, 48), pygame.SRCALPHA)
            pygame.draw.circle(surf, (190, 90, 220, max(30, 230 - i * 45)), (24, 24), 8 + i * 4, 2)
            frames.append(surf)

    _SLIMER_DEATH_FRAMES = frames
    return frames


class SlimerDeathVFX(BaseVFX):
    """Plays the 7-frame pixel-art SlimerDeath.png skull explosion when a Slimer dies."""

    def __init__(self, x, y, duration=0.46, scale=1.45):
        super().__init__(x, y, duration=duration, hitbox=None)
        self.frames = _get_slimer_death_frames(scale=scale)

    def draw(self, screen, camera_x=0, camera_y=0):
        if not self.frames:
            return
        idx = min(len(self.frames) - 1, int(self.progress * len(self.frames)))
        img = self.frames[idx]
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        screen.blit(img, img.get_rect(center=(sx, sy)))


# =============================================================================
# Vergil Phase 2 Awakening & Judgement Cut End (DMC5 Ultimate VFX)
# =============================================================================


class VergilAuraBurstVFX(BaseVFX):
    """
    Blue-violet Devil Trigger awakening aura burst when Vergil drops below 50% HP.
    """

    def __init__(self, x, y, duration=1.0):
        super().__init__(x, y, duration=duration, hitbox=None)
        self._canvas = pygame.Surface((320, 320), pygame.SRCALPHA)
        self.shards = []
        for i in range(28):
            ang = (i / 28.0) * math.tau + random.uniform(-0.1, 0.1)
            spd = random.uniform(70.0, 155.0)
            sz = random.choice([3, 4, 5])
            col = random.choice([(80, 195, 255), (145, 90, 255), (225, 245, 255)])
            self.shards.append((ang, spd, sz, col))

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, min(255, int(255 * math.sin(min(1.0, p) * math.pi))))
        if alpha <= 6:
            return

        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))

        surf = self._canvas
        surf.fill((0, 0, 0, 0))
        cx, cy = 160, 180

        # Vertical blue-violet awakening pillar
        pillar_w = max(4, int(52 * math.sin(p * math.pi)))
        pygame.draw.rect(
            surf,
            (95, 70, 255, int(alpha * 0.48)),
            (cx - pillar_w, 0, pillar_w * 2, 320),
        )
        pygame.draw.rect(
            surf,
            (130, 230, 255, int(alpha * 0.78)),
            (cx - pillar_w // 2, 0, max(2, pillar_w), 320),
        )

        # Expanding shockwave rings
        r1 = int(24 + 130 * p)
        r2 = int(12 + 92 * p)
        pygame.draw.circle(surf, (110, 215, 255, alpha), (cx, cy), r1, 3)
        pygame.draw.circle(surf, (165, 95, 255, int(alpha * 0.85)), (cx, cy), r2, 2)

        # Radiating pixel shards
        for ang, spd, sz, col in self.shards:
            px = int(cx + math.cos(ang) * spd * p)
            py = int(cy + math.sin(ang) * spd * p)
            pygame.draw.rect(surf, (*col, alpha), (px - sz // 2, py - sz // 2, sz, sz))

        screen.blit(surf, (sx - cx, sy - cy))


class JudgementCutEndVFX(BaseVFX):
    """
    DMC5-Inspired Vergil Phase 2 Ultimate — Judgement Cut End (3-Layer Depth & Screen-Breaking):
    1. draw_background_layer(world_surface, cx, cy): Deep darkened space, expanding blue-violet
       spatial rifts & radial speed lines behind all characters.
    2. draw(world_surface, cx, cy): Multi-concentric translucent cyan-blue Dimensional Spheres,
       3-tone slashes (deep purple afterimage + bright cyan glow + pure white core) & flying shards.
    3. draw_screen_overlay(screen): Rendered ABOVE all entities, camera zoom, and HUD! Draws massive
       diagonal screen-spanning slash beams, 4-corner shattered screen cracks, and a high-contrast
       sheathe-click flash that visually splits the entire monitor!
    """

    def __init__(
        self,
        center_x,
        center_y,
        radius=295,
        windup_time=1.15,
        slash_duration=1.20,
        shatter_duration=0.45,
    ):
        total = windup_time + slash_duration + shatter_duration
        super().__init__(center_x, center_y, duration=total, hitbox=None)
        self.radius = int(radius)
        self.windup_time = float(windup_time)
        self.slash_end = float(windup_time + slash_duration)
        self.shatter_duration = float(shatter_duration)

        # Midground 3-tone slash pool inside the Dimensional Sphere
        self.slash_pool = []
        for _ in range(64):
            a1 = random.uniform(0.0, math.tau)
            a2 = a1 + random.uniform(math.pi * 0.55, math.pi * 1.45)
            r1 = random.uniform(0.45, 1.08) * self.radius
            r2 = random.uniform(0.45, 1.08) * self.radius
            thick = random.choice([2, 3, 3, 4])
            self.slash_pool.append(
                (
                    math.cos(a1) * r1,
                    math.sin(a1) * r1,
                    math.cos(a2) * r2,
                    math.sin(a2) * r2,
                    thick,
                )
            )

        # Background radial dark speed lines
        self.bg_speed_rays = []
        for i in range(48):
            ang = (i / 48.0) * math.tau + random.uniform(-0.04, 0.04)
            inner_r = random.uniform(110.0, 260.0)
            thick = random.choice([2, 3, 4])
            self.bg_speed_rays.append((ang, inner_r, thick))

        # Geometric glass shards for midground & foreground shatter
        self.shards = []
        for _ in range(44):
            ang = random.uniform(0.0, math.tau)
            dist = random.uniform(35.0, self.radius * 0.98)
            spd = random.uniform(85.0, 260.0)
            sz = random.choice([5, 7, 9, 11])
            col = random.choice([(135, 235, 255), (165, 105, 255), (240, 252, 255)])
            self.shards.append((ang, dist, spd, sz, col))

        # Foreground screen-breaking diagonal slash specifications (normalized 0..1 screen coords)
        self.screen_slashes = [
            ((0.0, 0.14), (1.0, 0.86), 5),
            ((1.0, 0.10), (0.0, 0.88), 5),
            ((0.12, 0.0), (0.86, 1.0), 4),
            ((0.88, 0.0), (0.14, 1.0), 4),
            ((0.0, 0.52), (1.0, 0.34), 4),
            ((0.0, 0.72), (1.0, 0.18), 3),
            ((0.35, 0.0), (0.68, 1.0), 3),
            ((0.66, 0.0), (0.30, 1.0), 3),
        ]

        # 4-Corner screen glass fracture branches (normalized offsets from each corner)
        self.corner_cracks = []
        for cx_n, cy_n, dx_s, dy_s in (
            (0.0, 0.0, 1, 1),
            (1.0, 0.0, -1, 1),
            (0.0, 1.0, 1, -1),
            (1.0, 1.0, -1, -1),
        ):
            for branch in range(4):
                ang = (0.14 + branch * 0.22) * (math.pi * 0.5)
                l1 = random.uniform(80.0, 155.0)
                l2 = random.uniform(60.0, 130.0)
                bend = random.uniform(-0.28, 0.28)
                self.corner_cracks.append((cx_n, cy_n, dx_s, dy_s, ang, l1, l2, bend))

        self._dim_surf = None
        self._fg_surf = None
        self._sphere_surf = pygame.Surface(
            (self.radius * 2 + 40, self.radius * 2 + 40), pygame.SRCALPHA
        )

    # ------------------------------------------------------------------
    # LAYER 1: Background Spatial Distortion & Radial Speed Lines
    # ------------------------------------------------------------------
    def draw_background_layer(self, screen, camera_x=0, camera_y=0):
        sw, sh = screen.get_size()
        if self._dim_surf is None or self._dim_surf.get_size() != (sw, sh):
            self._dim_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)

        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        t = self.elapsed

        if t < self.windup_time:
            wp = t / max(0.01, self.windup_time)
            self._dim_surf.fill((8, 10, 30, int(125 * wp)))
            # Subtle inward-pulling dark violet speed lines
            for ang, inner_r, thick in self.bg_speed_rays[::2]:
                r_out = max(sw, sh) * 0.85
                r_in = max(60.0, inner_r * (1.25 - 0.55 * wp))
                p1 = (int(sx + math.cos(ang) * r_out), int(sy + math.sin(ang) * r_out))
                p2 = (int(sx + math.cos(ang) * r_in), int(sy + math.sin(ang) * r_in))
                pygame.draw.line(self._dim_surf, (90, 60, 210, int(110 * wp)), p1, p2, thick)
            screen.blit(self._dim_surf, (0, 0))
            return

        if t < self.slash_end:
            sp = (t - self.windup_time) / max(0.01, self.slash_end - self.windup_time)
            self._dim_surf.fill((4, 6, 22, 185))
            # Expanding deep blue-violet spatial rift rings in the background
            for k in range(3):
                ring_p = (sp * 1.6 + k * 0.33) % 1.0
                rr = int(120 + ring_p * 520)
                ra = int(165 * (1.0 - ring_p))
                pygame.draw.circle(self._dim_surf, (85, 65, 220, ra), (sx, sy), rr, 3)

            # High-density radial dark/blue speed lines bursting outward
            jitter = int(t * 24.0) * 0.03
            for i, (ang, inner_r, thick) in enumerate(self.bg_speed_rays):
                a = ang + jitter * (1 if i % 2 == 0 else -1)
                r_out = max(sw, sh) * 0.95
                p1 = (int(sx + math.cos(a) * inner_r), int(sy + math.sin(a) * inner_r))
                p2 = (int(sx + math.cos(a) * r_out), int(sy + math.sin(a) * r_out))
                col = (25, 45, 130, 170) if i % 3 else (105, 70, 235, 145)
                pygame.draw.line(self._dim_surf, col, p1, p2, thick)

            screen.blit(self._dim_surf, (0, 0))
            return

        # Shatter fade-out
        fp = min(1.0, (t - self.slash_end) / max(0.01, self.shatter_duration))
        fade = max(0.0, 1.0 - fp)
        self._dim_surf.fill((6, 10, 28, int(145 * fade)))
        screen.blit(self._dim_surf, (0, 0))

    # ------------------------------------------------------------------
    # LAYER 2: Midground Concentric Dimensional Sphere & 3-Tone Slashes
    # ------------------------------------------------------------------
    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        t = self.elapsed
        r = self.radius
        sc = r + 20

        self._sphere_surf.fill((0, 0, 0, 0))

        # PHASE 1: WINDUP (Converging Spatial Rifts & Concentric Warning Sphere)
        if t < self.windup_time:
            wp = t / max(0.01, self.windup_time)
            pygame.draw.circle(self._sphere_surf, (30, 38, 128, int(40 + 50 * wp)), (sc, sc), r)
            ring_a = int(135 + 115 * abs(math.sin(t * 16.0)))
            pygame.draw.circle(self._sphere_surf, (130, 240, 255, ring_a), (sc, sc), r, 3)
            pygame.draw.circle(
                self._sphere_surf, (145, 95, 255, int(120 * wp)), (sc, sc), int(r * 0.72), 2
            )

            for i in range(16):
                ang = (i / 16.0) * math.tau + t * 1.6
                outer_r = int(r * (1.0 - wp * 0.74))
                inner_r = max(12, outer_r - 64)
                p1 = (int(sc + math.cos(ang) * outer_r), int(sc + math.sin(ang) * outer_r))
                p2 = (int(sc + math.cos(ang) * inner_r), int(sc + math.sin(ang) * inner_r))
                pygame.draw.line(self._sphere_surf, (135, 230, 255, 210), p1, p2, 2)

            glint_r = max(5, int(22 * (1.0 - abs(wp - 0.85))))
            pygame.draw.circle(self._sphere_surf, (235, 252, 255, 240), (sc, sc), glint_r)
            screen.blit(self._sphere_surf, (sx - sc, sy - sc))
            return

        # PHASE 2: MULTI-CONCENTRIC SPHERE + 3-TONE SLASHES + FLYING SHARDS
        if t < self.slash_end:
            sp = (t - self.windup_time) / max(0.01, self.slash_end - self.windup_time)
            pulse = int(math.sin(t * 18.0) * 6)

            # 3 Concentric Translucent Cyan-Blue Dimensional Spheres
            pygame.draw.circle(self._sphere_surf, (18, 28, 102, 132), (sc, sc), r)
            pygame.draw.circle(self._sphere_surf, (45, 95, 225, 86), (sc, sc), int(r * 0.82) + pulse)
            pygame.draw.circle(self._sphere_surf, (95, 195, 255, 58), (sc, sc), int(r * 0.58) - pulse)

            pygame.draw.circle(self._sphere_surf, (135, 242, 255, 245), (sc, sc), r, 4)
            pygame.draw.circle(self._sphere_surf, (170, 100, 255, 200), (sc, sc), int(r * 0.84), 2)
            pygame.draw.circle(self._sphere_surf, (215, 250, 255, 175), (sc, sc), int(r * 0.62), 2)

            # 3-Tone High-Frequency Slashes: Deep Purple Afterimage -> Bright Cyan Glow -> Pure White Core
            step = int(t * 32.0)
            total_pool = len(self.slash_pool)
            for k in range(20):
                idx = (step * 5 + k * 3) % total_pool
                x1, y1, x2, y2, thick = self.slash_pool[idx]
                p1 = (int(sc + x1), int(sc + y1))
                p2 = (int(sc + x2), int(sc + y2))
                is_fresh = k >= 12
                a_purp = 185 if is_fresh else 110
                a_cyan = 235 if is_fresh else 155
                a_core = 255 if is_fresh else 190
                pygame.draw.line(self._sphere_surf, (125, 55, 235, a_purp), p1, p2, thick + 5)
                pygame.draw.line(self._sphere_surf, (65, 225, 255, a_cyan), p1, p2, thick + 2)
                pygame.draw.line(self._sphere_surf, (255, 255, 255, a_core), p1, p2, max(1, thick - 1))

            # Flying geometric glass shards inside & bursting out of the sphere
            for ang, dist, spd, sz, col in self.shards[:24]:
                cur_d = (dist + spd * sp * 0.9) % (r + 12)
                px = int(sc + math.cos(ang) * cur_d)
                py = int(sc + math.sin(ang) * cur_d)
                pygame.draw.polygon(
                    self._sphere_surf,
                    (*col, 210),
                    [(px, py - sz), (px + sz, py), (px, py + sz), (px - sz // 2, py)],
                )

            screen.blit(self._sphere_surf, (sx - sc, sy - sc))
            return

        # PHASE 3: SHEATHE-CLICK SHATTER RING & BURSTING SHARDS
        fp = min(1.0, (t - self.slash_end) / max(0.01, self.shatter_duration))
        fade = max(0.0, 1.0 - fp)
        ring_r = min(sc - 2, int(r * (1.0 + 0.08 * fp)))
        pygame.draw.circle(self._sphere_surf, (230, 252, 255, int(245 * fade)), (sc, sc), ring_r, 5)

        shard_a = int(250 * fade)
        for ang, dist, spd, sz, col in self.shards:
            cur_d = dist + spd * fp
            px = int(sc + math.cos(ang) * cur_d)
            py = int(sc + math.sin(ang) * cur_d)
            if 0 <= px < self._sphere_surf.get_width() and 0 <= py < self._sphere_surf.get_height():
                pygame.draw.polygon(
                    self._sphere_surf,
                    (*col, shard_a),
                    [(px, py - sz), (px + sz, py), (px, py + sz), (px - sz // 2, py)],
                )

        screen.blit(self._sphere_surf, (sx - sc, sy - sc))

    # ------------------------------------------------------------------
    # LAYER 3: Foreground Screen-Breaking Overlay (Above ALL Entities & HUD!)
    # ------------------------------------------------------------------
    def draw_screen_overlay(self, screen):
        t = self.elapsed
        if t < self.windup_time * 0.72:
            return

        sw, sh = screen.get_size()
        if self._fg_surf is None or self._fg_surf.get_size() != (sw, sh):
            self._fg_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        self._fg_surf.fill((0, 0, 0, 0))

        # Late windup: faint corner cracks begin forming
        if t < self.windup_time:
            cp = (t - self.windup_time * 0.72) / max(0.01, self.windup_time * 0.28)
            self._draw_corner_cracks(self._fg_surf, sw, sh, intensity=cp * 0.45, alpha=int(120 * cp))
            screen.blit(self._fg_surf, (0, 0))
            return

        # ACTIVE PHASE: Massive diagonal screen-spanning slashes + cracking monitor edges!
        if t < self.slash_end:
            sp = (t - self.windup_time) / max(0.01, self.slash_end - self.windup_time)
            self._draw_corner_cracks(self._fg_surf, sw, sh, intensity=0.55 + 0.45 * sp, alpha=220)

            step = int(t * 16.0)
            num_sl = len(self.screen_slashes)
            for k in range(4):
                idx = (step + k * 2) % num_sl
                (x1n, y1n), (x2n, y2n), thick = self.screen_slashes[idx]
                p1 = (int(x1n * sw), int(y1n * sh))
                p2 = (int(x2n * sw), int(y2n * sh))
                # 3-tone giant screen-breaking beam cutting across the entire monitor
                pygame.draw.line(self._fg_surf, (130, 60, 255, 160), p1, p2, thick + 10)
                pygame.draw.line(self._fg_surf, (70, 230, 255, 225), p1, p2, thick + 4)
                pygame.draw.line(self._fg_surf, (255, 255, 255, 255), p1, p2, thick)

            screen.blit(self._fg_surf, (0, 0))
            return

        # SHEATHE-CLICK DETONATION: High-contrast flash + all screen slashes & cracks shattering!
        fp = min(1.0, (t - self.slash_end) / max(0.01, self.shatter_duration))
        fade = max(0.0, 1.0 - fp)

        if fp < 0.14:
            # Blazing high-contrast cyan-white flash
            flash_a = int(225 * (1.0 - fp / 0.14))
            self._fg_surf.fill((220, 248, 255, flash_a))
        elif fp < 0.30:
            # High-contrast deep electric blue-violet negative pulse
            pulse_a = int(155 * (1.0 - (fp - 0.14) / 0.16))
            self._fg_surf.fill((35, 95, 255, pulse_a))

        self._draw_corner_cracks(self._fg_surf, sw, sh, intensity=1.15, alpha=int(245 * fade))
        for (x1n, y1n), (x2n, y2n), thick in self.screen_slashes[:4]:
            p1 = (int(x1n * sw), int(y1n * sh))
            p2 = (int(x2n * sw), int(y2n * sh))
            pygame.draw.line(self._fg_surf, (95, 235, 255, int(210 * fade)), p1, p2, thick + 3)
            pygame.draw.line(self._fg_surf, (255, 255, 255, int(245 * fade)), p1, p2, max(1, thick - 1))

        screen.blit(self._fg_surf, (0, 0))

    def _draw_corner_cracks(self, surf, sw, sh, intensity=1.0, alpha=200):
        if alpha <= 8:
            return
        for cx_n, cy_n, dx_s, dy_s, ang, l1, l2, bend in self.corner_cracks:
            x0 = int(cx_n * sw)
            y0 = int(cy_n * sh)
            x1 = int(x0 + dx_s * math.cos(ang) * l1 * intensity)
            y1 = int(y0 + dy_s * math.sin(ang) * l1 * intensity)
            x2 = int(x1 + dx_s * math.cos(ang + bend) * l2 * intensity)
            y2 = int(y1 + dy_s * math.sin(ang + bend) * l2 * intensity)
            pygame.draw.line(surf, (95, 195, 255, int(alpha * 0.7)), (x0, y0), (x1, y1), 3)
            pygame.draw.line(surf, (240, 252, 255, alpha), (x0, y0), (x1, y1), 1)
            pygame.draw.line(surf, (150, 110, 255, int(alpha * 0.65)), (x1, y1), (x2, y2), 2)
            pygame.draw.line(surf, (225, 250, 255, int(alpha * 0.9)), (x1, y1), (x2, y2), 1)


class FloatingTextVFX(BaseVFX):
    """
    Crisp pixel-art floating combat text (e.g. Undertale Sans 'MISS') that drifts upward
    and fades out cleanly with a dark pixel outline.
    """

    def __init__(
        self,
        x,
        y,
        text="MISS",
        color=(255, 255, 255),
        outline_color=(15, 15, 25),
        font_size=26,
        duration=0.85,
        rise_speed=58.0,
    ):
        super().__init__(x, y, duration=duration, hitbox=None)
        from Settings import get_pixel_font

        self.rise_speed = float(rise_speed)
        font = get_pixel_font(font_size)
        fg = font.render(text, False, color)
        bg = font.render(text, False, outline_color)
        w, h = fg.get_size()
        self.text_surf = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            self.text_surf.blit(bg, (2 + ox, 2 + oy))
        self.text_surf.blit(fg, (2, 2))

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, min(255, int(255 * (1.0 - max(0.0, (p - 0.35) / 0.65)))))
        if alpha <= 8:
            return
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - self.rise_speed * p - camera_y))
        surf = self.text_surf.copy()
        surf.set_alpha(alpha)
        screen.blit(surf, surf.get_rect(center=(sx, sy)))


class BlueSoulHeartVFX(BaseVFX):
    """
    Undertale Blue Soul Heart overlay rendered directly on the Player during
    Sans's Telekinesis Slam, accompanied by an expanding blue gravity pulse ring.
    """

    def __init__(self, target_player, duration=0.95):
        cx = target_player.hurtbox.centerx if target_player else 0
        cy = target_player.hurtbox.centery if target_player else 0
        super().__init__(cx, cy, duration=duration, hitbox=None)
        self.target = target_player

        # Build crisp 11x10 pixel-art Blue Soul Heart (scaled 2x -> 22x20)
        heart_pattern = [
            "..XX...XX..",
            ".XXXX.XXXX.",
            "XXXXXXXXXXX",
            "XXXXXXXXXXX",
            "XXXXXXXXXXX",
            ".XXXXXXXXX.",
            "..XXXXXXX..",
            "...XXXXX...",
            "....XXX....",
            ".....X.....",
        ]
        low = pygame.Surface((13, 12), pygame.SRCALPHA)
        for ry, row in enumerate(heart_pattern):
            for rx, ch in enumerate(row):
                if ch == "X":
                    # Dark navy pixel outline
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        low.set_at((rx + 1 + ox, ry + 1 + oy), (10, 20, 65, 255))
        for ry, row in enumerate(heart_pattern):
            for rx, ch in enumerate(row):
                if ch == "X":
                    col = (95, 220, 255, 255) if (ry <= 2 and rx in (2, 3, 7)) else (0, 165, 255, 255)
                    low.set_at((rx + 1, ry + 1), col)
        self.heart_img = pygame.transform.scale(low, (26, 24))

    def update(self, dt=1 / 60):
        super().update(dt)
        if self.target is not None and self.target.alive():
            self.pos_x = float(self.target.hurtbox.centerx)
            self.pos_y = float(self.target.hurtbox.centery)

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, min(255, int(255 * (1.0 - max(0.0, (p - 0.65) / 0.35)))))
        if alpha <= 8:
            return
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))

        # Expanding blue telekinesis shockwave ring
        if p < 0.55:
            rp = p / 0.55
            r = int(14 + 42 * rp)
            ra = int(220 * (1.0 - rp))
            ring_surf = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (0, 195, 255, ra), (r + 4, r + 4), r, 3)
            screen.blit(ring_surf, (sx - r - 4, sy - r - 4))

        heart = self.heart_img.copy()
        heart.set_alpha(alpha)
        screen.blit(heart, heart.get_rect(center=(sx, sy)))


class GroundBoneTrapVFX(BaseVFX):
    """
    Sans Attack 4 — Ground Bone Trap:
    - Phase 1 (0 .. warning_time): Flashing red/cyan Warning Zone along the landing floor/platform.
    - Phase 2 (warning_time .. warning_time + active_time): Instantly erupts a row of sharp pixel
      bones upward with a synced Active Hitbox (damage=1, tag='sans_bone_trap').
    - Phase 3 (retract): Destroys Hitbox and retracts the bones back into the floor.
    """

    def __init__(
        self,
        center_x,
        ground_y,
        width=224,
        bone_height=76,
        warning_time=0.52,
        active_time=0.52,
        retract_time=0.18,
        damage=1,
        blue=False,
        hitbox_list=None,
    ):
        total = warning_time + active_time + retract_time
        super().__init__(center_x, ground_y, duration=total, hitbox=None)
        self.ground_y = float(ground_y)
        self.trap_width = int(width)
        self.bone_height = int(bone_height)
        self.warning_time = float(warning_time)
        self.active_end = float(warning_time + active_time)
        self.retract_time = float(retract_time)
        self.damage = damage
        self.is_blue = bool(blue)
        self.attack_type = "blue" if self.is_blue else "white"
        self.hitbox_list = hitbox_list
        self.spawned_hb = False
        self.cur_height = 0

        base_img = _load_sans_asset("bone_cyan.png" if blue else "bone_white.png")
        self.bone_w = 24
        self.bone_img = pygame.transform.scale(base_img, (self.bone_w, self.bone_height))
        if self.is_blue:
            self.bone_img = self.bone_img.copy()
            self.bone_img.fill((0, 191, 255), special_flags=pygame.BLEND_RGB_MULT)
            self.bone_img.fill((0, 95, 165), special_flags=pygame.BLEND_RGB_ADD)

        self.num_bones = max(4, self.trap_width // 30)

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return

        if self.elapsed < self.warning_time:
            self.cur_height = 0
            return

        if self.elapsed < self.active_end:
            act_p = (self.elapsed - self.warning_time) / max(0.01, self.active_end - self.warning_time)
            rise_ratio = min(1.0, act_p / 0.16)
            self.cur_height = int(self.bone_height * rise_ratio)
            if not self.spawned_hb and self.cur_height >= 24:
                self.spawned_hb = True
                hb_rect = pygame.Rect(
                    int(round(self.pos_x - self.trap_width * 0.5)) + 6,
                    int(round(self.ground_y - self.bone_height + 6)),
                    self.trap_width - 12,
                    self.bone_height - 6,
                )
                hb = Hitbox(
                    owner="boss",
                    rect=hb_rect,
                    damage=self.damage,
                    knockback_x=0.0,
                    lifetime=None,
                    tag="sans_bone_trap",
                    attack_type=self.attack_type,
                )
                self.bind_hitbox(hb)
                if self.hitbox_list is not None:
                    self.hitbox_list.append(hb)
        else:
            if self.hitbox and self.hitbox.active:
                self.hitbox.destroy()
            rp = (self.elapsed - self.active_end) / max(0.01, self.retract_time)
            self.cur_height = max(0, int(self.bone_height * (1.0 - rp)))

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        gy = int(round(self.ground_y - camera_y))
        left_x = sx - self.trap_width // 2

        # Phase 1: Pulsing Red/Cyan Warning Zone Box
        if self.elapsed < self.warning_time:
            flash = int(self.elapsed * 18.0) % 2 == 0
            border_col = (255, 65, 85) if flash else (0, 215, 255)
            fill_surf = pygame.Surface((self.trap_width, self.bone_height), pygame.SRCALPHA)
            fill_surf.fill((255, 50, 75, 55) if flash else (0, 185, 255, 45))
            screen.blit(fill_surf, (left_x, gy - self.bone_height))
            pygame.draw.rect(
                screen,
                border_col,
                (left_x, gy - self.bone_height, self.trap_width, self.bone_height),
                2,
            )
            # Ground glowing warning strip
            pygame.draw.line(screen, border_col, (left_x, gy), (left_x + self.trap_width, gy), 4)
            return

        if self.cur_height < 4:
            return

        crop = pygame.Rect(0, 0, self.bone_w, min(self.bone_height, self.cur_height))
        sub = self.bone_img.subsurface(crop)
        spacing = self.trap_width / max(1, self.num_bones)
        for i in range(self.num_bones):
            bx = int(round(left_x + spacing * (i + 0.5) - self.bone_w * 0.5))
            screen.blit(sub, (bx, gy - crop.height))


# =============================================================================
# Boss Intro Cutscene VFX & New Vergil Moveset VFX
# =============================================================================


class SansIntroVFX(BaseVFX):
    """
    Upgraded Undertale Sans Boss Intro Cutscene VFX (paired with 1.40x Camera Zoom-in):
    - 0.00 .. 0.36s: Rapid classic Undertale black-screen encounter flashes.
    - 0.45 .. 1.75s: Subtle Blue Soul energy pulse ring beneath Sans's feet.
    - 0.85 .. 1.90s: Rotating bright cyan & golden-yellow cross-star eye flare on Sans's left eye.
    """

    def __init__(self, sans_boss, duration=2.0):
        super().__init__(sans_boss.pos_x, sans_boss.pos_y - 72.0, duration=duration, hitbox=None)
        self.boss = sans_boss
        self._blink_surf = None
        self._ring_surf = pygame.Surface((200, 80), pygame.SRCALPHA)

    def update(self, dt=1 / 60):
        super().update(dt)
        if self.boss is not None:
            f_dir = getattr(self.boss, "facing_dir", -1)
            self.pos_x = float(self.boss.pos_x + f_dir * 6.0)
            self.pos_y = float(self.boss.pos_y - 74.0)

    def draw(self, screen, camera_x=0, camera_y=0):
        t = self.elapsed
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))

        # 1. Blue Soul wave expanding beneath Sans's feet
        if 0.45 <= t <= 1.85 and self.boss is not None:
            rp = ((t - 0.45) / 0.70) % 1.0
            rx = int(18 + 62 * rp)
            ry = int(6 + 18 * rp)
            ra = int(185 * (1.0 - rp))
            self._ring_surf.fill((0, 0, 0, 0))
            pygame.draw.ellipse(
                self._ring_surf,
                (0, 195, 255, ra),
                (100 - rx, 40 - ry, rx * 2, ry * 2),
                2,
            )
            bx = int(round(self.boss.pos_x - camera_x))
            by = int(round(self.boss.pos_y - camera_y))
            screen.blit(self._ring_surf, (bx - 100, by - 40))

        # 2. Rotating Cyan & Golden-Yellow Cross-Star Eye Flare
        if 0.85 <= t <= 1.92:
            ep = (t - 0.85) / 1.07
            intensity = math.sin(min(1.0, ep) * math.pi)
            if intensity > 0.05:
                col = (55, 235, 255) if int(t * 20.0) % 2 == 0 else (255, 225, 55)
                arm = int(38 * intensity)
                rot = t * 5.2
                for k in range(4):
                    ang = rot + k * (math.pi * 0.5)
                    ex = int(sx + math.cos(ang) * arm)
                    ey = int(sy + math.sin(ang) * arm)
                    pygame.draw.line(screen, col, (sx, sy), (ex, ey), 3)
                # Diagonal secondary rays
                arm2 = int(20 * intensity)
                for k in range(4):
                    ang = rot + math.pi * 0.25 + k * (math.pi * 0.5)
                    ex = int(sx + math.cos(ang) * arm2)
                    ey = int(sy + math.sin(ang) * arm2)
                    pygame.draw.line(screen, (235, 252, 255), (sx, sy), (ex, ey), 2)
                pygame.draw.circle(screen, (255, 255, 255), (sx, sy), max(3, int(8 * intensity)))

    def draw_screen_overlay(self, screen):
        t = self.elapsed
        if t > 0.36:
            return
        if int(t / 0.06) % 2 == 0:
            sw, sh = screen.get_size()
            if self._blink_surf is None or self._blink_surf.get_size() != (sw, sh):
                self._blink_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._blink_surf.fill((0, 0, 0, 225))
            screen.blit(self._blink_surf, (0, 0))


class VergilIntroRiftVFX(BaseVFX):
    """
    Upgraded DMC5 Vergil Boss Intro Cutscene VFX (paired with 1.40x Camera Zoom-in):
    - 0.00 .. 1.25s: Vertical blue-violet Dimensional Rift crackling with electric arcs.
    - 1.25 .. 1.95s: Yamato sheathe-click metallic flash + expanding blue-white shockwave
      ring + drifting blue-violet energy particles!
    """

    def __init__(self, vergil_boss, duration=2.0):
        super().__init__(vergil_boss.pos_x, vergil_boss.pos_y - 54.0, duration=duration, hitbox=None)
        self.boss = vergil_boss
        self._canvas = pygame.Surface((260, 260), pygame.SRCALPHA)
        self.particles = []
        for i in range(22):
            ang = (i / 22.0) * math.tau + random.uniform(-0.15, 0.15)
            spd = random.uniform(45.0, 115.0)
            sz = random.choice([2, 3, 4])
            col = random.choice([(95, 235, 255), (155, 95, 255), (235, 252, 255)])
            self.particles.append((ang, spd, sz, col))

    def update(self, dt=1 / 60):
        super().update(dt)
        if self.boss is not None:
            self.pos_x = float(self.boss.pos_x)
            self.pos_y = float(self.boss.pos_y - 54.0)

    def draw(self, screen, camera_x=0, camera_y=0):
        t = self.elapsed
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        surf = self._canvas
        surf.fill((0, 0, 0, 0))
        cx, cy = 130, 130

        # 1. Vertical Dimensional Rift with crackling blue-violet electric arcs
        if t < 1.28:
            rp = math.sin(min(1.0, t / 1.28) * math.pi)
            rw = max(4, int(38 * rp))
            rh = max(28, int(172 * min(1.0, t / 0.35)))
            pygame.draw.ellipse(surf, (85, 50, 230, int(185 * rp)), (cx - rw, cy - rh // 2, rw * 2, rh))
            pygame.draw.ellipse(
                surf,
                (115, 230, 255, int(235 * rp)),
                (cx - rw // 2, cy - rh // 2 + 8, max(2, rw), max(8, rh - 16)),
            )
            pygame.draw.line(surf, (245, 252, 255, int(245 * rp)), (cx, cy - rh // 2), (cx, cy + rh // 2), 2)

            # Crackling jagged electric arcs around rift
            seed_step = int(t * 22.0)
            for k in range(5):
                y_off = -rh // 2 + int(((k + 0.5) / 5.0) * rh)
                side = 1 if (k + seed_step) % 2 == 0 else -1
                ax1 = cx + side * (rw // 2)
                ax2 = cx + side * (rw + 18 + ((seed_step * 7 + k * 13) % 16))
                ay2 = cy + y_off + (((seed_step + k) % 3) - 1) * 14
                pygame.draw.line(surf, (135, 240, 255, int(225 * rp)), (ax1, cy + y_off), (ax2, ay2), 2)

        # 2. Yamato Sheathe-Click Metallic Glint + Expanding Shockwave & Drifting Particles
        if 1.24 <= t <= 1.98:
            gp = (t - 1.24) / 0.74
            g_int = math.sin(min(1.0, gp) * math.pi)
            fade = max(0.0, 1.0 - gp)

            # Expanding blue-white shockwave rings
            r1 = int(18 + 106 * gp)
            r2 = int(10 + 74 * gp)
            pygame.draw.circle(surf, (125, 240, 255, int(235 * fade)), (cx, cy), min(124, r1), 3)
            pygame.draw.circle(surf, (165, 105, 255, int(195 * fade)), (cx, cy), min(124, r2), 2)

            # Drifting blue-violet particles
            for ang, spd, sz, col in self.particles:
                px = int(cx + math.cos(ang) * spd * gp)
                py = int(cy + math.sin(ang) * spd * gp)
                if 0 <= px < 260 and 0 <= py < 260:
                    pygame.draw.rect(surf, (*col, int(240 * fade)), (px - sz // 2, py - sz // 2, sz, sz))

            # Sharp horizontal Yamato blade flash
            gx = cx + getattr(self.boss, "facing_dir", -1) * 14
            gy = cy + 6
            arm = int(56 * g_int)
            pygame.draw.line(surf, (95, 235, 255, 245), (gx - arm, gy), (gx + arm, gy), 3)
            pygame.draw.line(surf, (255, 255, 255, 255), (gx, gy - arm // 2), (gx, gy + arm // 2), 2)

        screen.blit(surf, (sx - cx, sy - cy))


class RisingSlashVFX(BaseVFX):
    """Vergil Attack A (High Time / Rising Slash) — upward blue-violet crescent arc."""

    def __init__(self, anchor_entity, forward_offset=38.0, vertical_offset=-58.0, flip=False, duration=0.22, hitbox=None):
        super().__init__(anchor_entity.pos_x, anchor_entity.pos_y + vertical_offset, duration=duration, hitbox=hitbox)
        self.anchor_entity = anchor_entity
        self.forward_offset = float(forward_offset)
        self.vertical_offset = float(vertical_offset)
        self.flip = flip
        self._canvas = pygame.Surface((130, 140), pygame.SRCALPHA)

    def update(self, dt=1 / 60):
        super().update(dt)
        if self.anchor_entity and self.anchor_entity.alive():
            f_dir = -1 if self.flip else 1
            self.pos_x = self.anchor_entity.pos_x + f_dir * self.forward_offset
            self.pos_y = self.anchor_entity.pos_y + self.vertical_offset
            if self.hitbox and self.hitbox.active:
                self.hitbox.rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))

    def draw(self, screen, camera_x=0, camera_y=0):
        p = self.progress
        alpha = max(0, int(255 * (1.0 - p * 0.85)))
        if alpha <= 8:
            return
        surf = self._canvas
        surf.fill((0, 0, 0, 0))
        f_dir = -1 if self.flip else 1
        cx, cy = 65, 70
        pts = []
        for i in range(11):
            ang = math.radians(-115 + i * 21)
            rx = math.cos(ang) * 44 * f_dir
            ry = math.sin(ang) * 56
            pts.append((int(cx + rx), int(cy + ry)))
        pygame.draw.lines(surf, (135, 75, 255, int(alpha * 0.75)), False, pts, 12)
        pygame.draw.lines(surf, (75, 225, 255, alpha), False, pts, 6)
        pygame.draw.lines(surf, (245, 252, 255, alpha), False, pts, 2)
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        screen.blit(surf, (sx - cx, sy - cy))


class SingleJudgementCutVFX(BaseVFX):
    """
    Vergil Attack B — Single Judgement Cut Sphere spawned directly at the player's coordinates:
    - 0.0 .. windup_time: Pulsing blue-violet warning sphere.
    - windup_time .. duration: Rapid internal cyan-white slash burst + synced Hitbox.
    """

    def __init__(self, x, y, radius=88, windup_time=0.46, active_time=0.28, damage=18, hitbox_list=None):
        super().__init__(x, y, duration=windup_time + active_time, hitbox=None)
        self.radius = int(radius)
        self.windup_time = float(windup_time)
        self.active_time = float(active_time)
        self.damage = damage
        self.hitbox_list = hitbox_list
        self.spawned_hb = False
        self._canvas = pygame.Surface((radius * 2 + 16, radius * 2 + 16), pygame.SRCALPHA)
        self.chords = []
        for _ in range(16):
            a1 = random.uniform(0.0, math.tau)
            a2 = a1 + random.uniform(math.pi * 0.6, math.pi * 1.4)
            self.chords.append((a1, a2))

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return
        if not self.spawned_hb and self.elapsed >= self.windup_time:
            self.spawned_hb = True
            hb_rect = pygame.Rect(0, 0, int(self.radius * 1.55), int(self.radius * 1.55))
            hb_rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))
            hb = Hitbox(
                owner="boss",
                rect=hb_rect,
                damage=self.damage,
                knockback_x=180.0,
                lifetime=self.active_time,
                tag="vergil_judgement_cut",
            )
            self.bind_hitbox(hb)
            if self.hitbox_list is not None:
                self.hitbox_list.append(hb)

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        r = self.radius
        c = r + 8
        surf = self._canvas
        surf.fill((0, 0, 0, 0))

        if self.elapsed < self.windup_time:
            wp = self.elapsed / max(0.01, self.windup_time)
            a = int(90 + 135 * abs(math.sin(self.elapsed * 20.0)))
            pygame.draw.circle(surf, (45, 55, 165, int(45 + 45 * wp)), (c, c), int(r * (0.45 + 0.55 * wp)))
            pygame.draw.circle(surf, (115, 225, 255, a), (c, c), r, 2)
        else:
            ap = (self.elapsed - self.windup_time) / max(0.01, self.active_time)
            fade = max(0.0, 1.0 - ap)
            pygame.draw.circle(surf, (30, 50, 155, int(135 * fade)), (c, c), r)
            pygame.draw.circle(surf, (135, 240, 255, int(245 * fade)), (c, c), r, 3)
            step = int(self.elapsed * 30.0)
            for k in range(8):
                a1, a2 = self.chords[(step + k * 2) % len(self.chords)]
                p1 = (int(c + math.cos(a1) * r), int(c + math.sin(a1) * r))
                p2 = (int(c + math.cos(a2) * r), int(c + math.sin(a2) * r))
                pygame.draw.line(surf, (145, 85, 255, int(190 * fade)), p1, p2, 5)
                pygame.draw.line(surf, (235, 252, 255, int(250 * fade)), p1, p2, 2)

        screen.blit(surf, (sx - c, sy - c))


class SummonedSwordVFX(BaseVFX):
    """
    Vergil Attack C — Summoned Sword (Mirage Blade):
    - Hovers & aims at the player with a cyan sightline during windup.
    - Launches at high speed (680 px/s) with a synced parryable Hitbox.
    """

    def __init__(self, x, y, target_x, target_y, windup=0.42, speed=680.0, duration=1.25, damage=12, hitbox_list=None):
        super().__init__(x, y, duration=windup + duration, hitbox=None)
        self.windup = float(windup)
        self.speed = float(speed)
        self.damage = damage
        self.hitbox_list = hitbox_list
        self.launched = False

        dx = float(target_x) - float(x)
        dy = float(target_y) - float(y)
        dist = max(1.0, math.hypot(dx, dy))
        self.vx = (dx / dist) * self.speed
        self.vy = (dy / dist) * self.speed
        self.angle_rad = math.atan2(dy, dx)

        # Build crisp glowing cyan pixel Mirage Blade pointing right, then rotate
        blade = pygame.Surface((46, 14), pygame.SRCALPHA)
        pygame.draw.polygon(blade, (35, 165, 255, 210), [(2, 7), (12, 2), (44, 7), (12, 12)])
        pygame.draw.polygon(blade, (220, 252, 255, 255), [(8, 7), (15, 5), (42, 7), (15, 9)])
        pygame.draw.rect(blade, (95, 235, 255, 240), (10, 1, 3, 12))
        self.blade_img = pygame.transform.rotate(blade, -math.degrees(self.angle_rad))
        self.rect = self.blade_img.get_rect(center=(int(x), int(y)))

    def update(self, dt=1 / 60):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.destroy()
            return
        if self.elapsed < self.windup:
            return
        if not self.launched:
            self.launched = True
            from audio_manager import get_audio

            get_audio().play_sfx("mirage_blade")
            hb_rect = pygame.Rect(0, 0, 28, 22)
            hb_rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))
            kb = 200.0 if self.vx >= 0 else -200.0
            hb = Hitbox(
                owner="boss",
                rect=hb_rect,
                damage=self.damage,
                knockback_x=kb,
                lifetime=None,
                tag="vergil_summoned_sword",
            )
            self.bind_hitbox(hb)
            if self.hitbox_list is not None:
                self.hitbox_list.append(hb)

        self.pos_x += self.vx * dt
        self.pos_y += self.vy * dt
        self.rect.center = (int(round(self.pos_x)), int(round(self.pos_y)))
        if self.hitbox and self.hitbox.active:
            self.hitbox.rect.center = self.rect.center

    def draw(self, screen, camera_x=0, camera_y=0):
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        if self.elapsed < self.windup:
            ex = int(sx + math.cos(self.angle_rad) * 280)
            ey = int(sy + math.sin(self.angle_rad) * 280)
            pygame.draw.line(screen, (60, 225, 255), (sx, sy), (ex, ey), 1)
        screen.blit(self.blade_img, self.blade_img.get_rect(center=(sx, sy)))


# =============================================================================
# Indie Cross Dimensional Cross-Star Rift VFX (Tutorial Ending & Arrival Drop)
# =============================================================================

class DimensionalRiftVFX(BaseVFX):
    """
    Indie Cross Episode 1–inspired 4-Point Cross-Star Dimensional Rift:
    - World Layer: Black-Red / Bright-Cyan glowing 4-point cross-star tear,
      floating glitch pixel squares, and gravity suction rings.
    - Screen Overlay Layer (swallow mode): High-Contrast Red/Black/White Impact Frames
      & Screen Shatter fracture lines at swallow climax!
    """

    def __init__(self, x, y, duration=4.35, mode="swallow"):
        super().__init__(x, y, duration=duration, hitbox=None)
        self.mode = mode  # "swallow" or "arrival"
        self.scale = 0.12 if mode == "swallow" else 1.25
        self.pull_active = False
        self.impact_active = False
        self.shatter_lines = []
        self.pixel_particles = []
        for _ in range(42):
            ang = random.uniform(0.0, math.tau)
            dist = random.uniform(28.0, 165.0)
            size = random.choice((4, 6, 8, 10))
            col = random.choice(
                ((255, 45, 70), (255, 255, 255), (60, 240, 255), (18, 10, 22))
            )
            self.pixel_particles.append([ang, dist, random.uniform(1.6, 4.0), size, col])

        # Precompute screen-space shatter crack rays from center
        for i in range(20):
            ang = (i / 20.0) * math.tau + random.uniform(-0.12, 0.12)
            self.shatter_lines.append((ang, random.uniform(160.0, 560.0), random.choice((2, 3, 4))))

    def update(self, dt=1 / 60):
        super().update(dt)
        t = self.elapsed
        if self.mode == "swallow":
            if t < 1.60:
                # Stage 1 (0.0s .. 1.6s): Slow spatial anomaly tear & pixel particle gathering
                p = t / 1.60
                self.scale = 0.12 + 0.78 * (1.0 - (1.0 - p) ** 2)
                self.pull_active = False
                self.impact_active = False
            elif t < 3.40:
                # Stage 2 (1.6s .. 3.4s): Cross-star expansion + gravity suction rings & centripetal speed lines
                p = (t - 1.60) / 1.80
                pulse = 0.12 * math.sin(t * 16.0)
                self.scale = 0.90 + 2.65 * (p * p) + pulse
                self.pull_active = True
                self.impact_active = False
            else:
                # Stage 3 (3.4s .. 4.3s): Swallow climax + High-Contrast Impact Frames & Screen Shatter!
                p = min(1.0, (t - 3.40) / max(0.01, self.duration - 3.40))
                self.scale = 3.55 + 2.45 * p
                self.pull_active = True
                self.impact_active = True
        else:
            # Arrival mode in main_world.tmx: shrink cleanly after player drops out
            p = min(1.0, t / max(0.01, self.duration))
            self.scale = max(0.0, 1.35 * (1.0 - p * p))
            self.pull_active = False
            self.impact_active = False

        # Animate orbiting/pulling pixel glitch squares
        pull_speed = 115.0 if (self.mode == "swallow" and t >= 1.60) else (22.0 if self.mode == "swallow" else -48.0)
        for part in self.pixel_particles:
            part[0] += part[2] * dt
            if self.mode == "swallow":
                part[1] -= pull_speed * dt
                if part[1] < 12.0:
                    part[1] = random.uniform(105.0, 185.0)
                elif part[1] > 190.0:
                    part[1] = random.uniform(35.0, 95.0)
            else:
                part[1] += 48.0 * dt

    def _star_points(self, cx, cy, outer_r, inner_r, jitter=0.0):
        pts = []
        for i in range(8):
            ang = i * (math.pi * 0.25)
            r = (outer_r if i % 2 == 0 else inner_r) + random.uniform(-jitter, jitter)
            pts.append((int(round(cx + math.cos(ang) * r)), int(round(cy + math.sin(ang) * r))))
        return pts

    def draw(self, screen, camera_x=0, camera_y=0):
        if self.scale <= 0.04:
            return
        sx = int(round(self.pos_x - camera_x))
        sy = int(round(self.pos_y - camera_y))
        base_r = 56.0 * self.scale
        inner_r = 14.0 * self.scale

        # 1. Gravity suction rings
        for ring_i in range(3):
            phase = ((self.elapsed * 2.1 + ring_i * 0.33) % 1.0)
            r_ring = int(max(6, base_r * (1.65 - phase * 1.35)))
            col = (255, 55, 80) if ring_i % 2 == 0 else (65, 240, 255)
            pygame.draw.circle(screen, col, (sx, sy), r_ring, 2)

        # 1b. Centripetal suction speed lines during Stage 2 expansion & pull
        if self.pull_active and not self.impact_active:
            for idx in range(14):
                ang = (idx / 14.0) * math.tau + self.elapsed * 1.4
                r_out = base_r * 1.85 + 24.0 * math.sin(self.elapsed * 12.0 + idx)
                r_in = max(18.0, base_r * 0.85)
                x1 = int(round(sx + math.cos(ang) * r_out))
                y1 = int(round(sy + math.sin(ang) * r_out))
                x2 = int(round(sx + math.cos(ang) * r_in))
                y2 = int(round(sy + math.sin(ang) * r_in))
                lcol = (255, 65, 90) if idx % 2 == 0 else (70, 240, 255)
                pygame.draw.line(screen, lcol, (x1, y1), (x2, y2), 2)

        # 2. Orbiting pixel glitch squares
        for ang, dist, _, sz, col in self.pixel_particles:
            px = int(round(sx + math.cos(ang) * dist * min(1.8, 0.55 + self.scale * 0.45)))
            py = int(round(sy + math.sin(ang) * dist * min(1.8, 0.55 + self.scale * 0.45)))
            pygame.draw.rect(screen, col, (px - sz // 2, py - sz // 2, sz, sz))

        # 3. 4-Point Cross-Star Dimensional Rift (Smooth low-frequency breathing glow, zero strobe)
        breath = 1.0 + 0.05 * math.sin(self.elapsed * 2.5 * math.tau)
        jit = 1.2 * min(1.5, self.scale)
        pts_cyan = self._star_points(sx, sy, base_r * 1.18 * breath, inner_r * 1.25 * breath, jitter=jit)
        pts_red = self._star_points(sx, sy, base_r * 1.04 * breath, inner_r * 1.08 * breath, jitter=jit * 0.6)
        pts_core = self._star_points(sx, sy, base_r * 0.76, inner_r * 0.72, jitter=0.0)

        pygame.draw.polygon(screen, (45, 195, 225), pts_cyan)
        pygame.draw.polygon(screen, (195, 28, 52), pts_red)
        pygame.draw.polygon(screen, (10, 6, 14), pts_core)
        pygame.draw.polygon(screen, (220, 170, 185), pts_core, 2)

    def draw_screen_overlay(self, screen):
        """
        Smooth, eye-friendly crimson-to-black alpha fade with subtle fracture lines
        (completely eliminates high-frequency red/black/white strobe flashing).
        """
        if not self.impact_active:
            return
        w, h = screen.get_width(), screen.get_height()
        cx, cy = w // 2, h // 2
        p = max(0.0, min(1.0, (self.elapsed - 3.40) / max(0.01, self.duration - 3.40)))
        ease = p * p * (3.0 - 2.0 * p)  # Smoothstep easing

        # Smooth transition from deep crimson veil -> pitch black (zero per-frame strobe)
        r_col = int(round(95 * (1.0 - ease) + 8 * ease))
        g_col = int(round(12 * (1.0 - ease) + 6 * ease))
        b_col = int(round(24 * (1.0 - ease) + 12 * ease))
        alpha = int(round(85 + 170 * ease))

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((r_col, g_col, b_col, max(0, min(255, alpha))))
        screen.blit(overlay, (0, 0))

        # Steady, smoothly fading dimensional fracture rays & central breathing cross-star
        crack_alpha = int(round(190 * (1.0 - ease * 0.75)))
        if crack_alpha > 12:
            crack_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for idx, (ang, length, thick) in enumerate(self.shatter_lines):
                scaled_len = length * (0.55 + 0.55 * ease)
                ex = int(cx + math.cos(ang) * scaled_len)
                ey = int(cy + math.sin(ang) * scaled_len)
                col = (210, 42, 68, crack_alpha) if idx % 2 == 0 else (65, 205, 230, crack_alpha)
                pygame.draw.line(crack_surf, col, (cx, cy), (ex, ey), thick)
            star_r = max(18.0, 210.0 * (1.0 - 0.65 * ease))
            pts = self._star_points(cx, cy, star_r, star_r * 0.16, jitter=0.0)
            pygame.draw.polygon(crack_surf, (215, 38, 64, crack_alpha), pts)
            pygame.draw.polygon(
                crack_surf,
                (12, 8, 16, min(255, crack_alpha + 40)),
                self._star_points(cx, cy, star_r * 0.55, star_r * 0.09, jitter=0.0),
            )
            screen.blit(crack_surf, (0, 0))






