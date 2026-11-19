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
    ):
        self.owner = owner  # "player" 或 "boss"
        self.rect = pygame.Rect(rect)
        self.damage = damage
        self.knockback_x = knockback_x
        self.lifetime = lifetime  # 若為 float 則自動倒數銷毀；若由 VFX/動畫控制則隨宿主銷毀
        self.elapsed = 0.0
        self.active = True
        self.tag = tag
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
    screen, camera_x, camera_y, player, boss, active_hitboxes, vfx_group=None
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
        self.hitbox_list = hitbox_list
        self.spawned_hb = False

        base_img = _load_sans_asset("bone_cyan.png" if cyan else "bone_white.png")
        self.bone_w = 24
        self.bone_img = pygame.transform.scale(base_img, (self.bone_w, self.max_height))
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
