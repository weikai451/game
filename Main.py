import pygame
from Settings import (
    WIDTH,
    HEIGHT,
    FPS,
    GROUND_Y,
    BULLET_TIME_SCALE,
    BULLET_TIME_DURATION,
    BULLET_TIME_RECOVERY_SPEED,
)
from Game_state import State
from Map import GameMap
import Player
import Boss1
from VFX import draw_debug_boxes


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (WIDTH, HEIGHT), pygame.RESIZABLE | pygame.SCALED
        )
        pygame.display.set_caption("Final Project")
        self.clock = pygame.time.Clock()
        self.running = True

        self.font_big = pygame.font.SysFont(None, 90)
        self.font_small = pygame.font.SysFont(None, 36)
        self.font_hud = pygame.font.SysFont(None, 26)

        # 載入背景與地圖
        bg_img = pygame.image.load(
            "asset/Legacy-Fantasy - High Forest 2.3/Background/Background.png"
        ).convert()
        self.background = pygame.transform.scale(bg_img, (WIDTH, HEIGHT))
        self.game_map = GameMap("map_learning.tmx")

        self.pause_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.pause_overlay.fill((0, 0, 0, 150))

        self.bullet_time_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.bullet_time_overlay.fill((20, 90, 160, 48))

        # 鏡頭與狀態初始化
        self.camera_x = 0
        self.camera_y = 0
        self.state = State.MENU
        self.debug_mode = False  # 按 F1 或 TAB 切換顯示 Hitbox/Hurtbox/Parry 線框

        # 子彈時間 (Bullet Time) 與全域時間縮放
        self.time_scale = 1.0
        self.bullet_time_timer = 0.0

        # 初始化遊戲物件
        self.new_game()

    def new_game(self):
        """建立一局新遊戲（開始 / 重新開始都呼叫它）"""
        self.player = Player.Player(start_x=240, ground_y=GROUND_Y)
        self.boss = Boss1.Vergil(self.player, start_x=580, ground_y=GROUND_Y)
        self.all_sprites = pygame.sprite.Group(self.player, self.boss)
        self.enemies = pygame.sprite.Group(self.boss)
        self.vfx_group = pygame.sprite.Group()
        self.active_hitboxes = []

        # 子彈時間重置
        self.time_scale = 1.0
        self.bullet_time_timer = 0.0

        # HUD 血量殘影過渡 (Damage Follow Bar) 追蹤值
        self.player_display_hp = float(self.player.player_hp)
        self.boss_display_hp = float(self.boss.boss_health)

    def trigger_bullet_time(self):
        """完美格擋觸發：啟動子彈時間 (time_scale = 0.2，持續真實時間 0.8 秒)"""
        self.time_scale = BULLET_TIME_SCALE
        self.bullet_time_timer = BULLET_TIME_DURATION

    # ---------- UI 繪製輔助方法 ----------
    def draw_text(self, text, font, color, center):
        img = font.render(text, True, color)
        self.screen.blit(img, img.get_rect(center=center))

    def draw_player_hp(self):
        """
        畫面左上角繪製玩家 HUD 血量條：
        包含底框、平滑殘影過渡條 (Damage Follow Bar)、當前血量條、數值比例與防禦狀態提示。
        """
        x, y = 24, 24
        bar_w, bar_h = 300, 24
        max_hp = self.player.max_hp
        cur_hp = max(self.player.player_hp, 0)
        disp_hp = max(self.player_display_hp, cur_hp)

        cur_ratio = cur_hp / max_hp
        disp_ratio = disp_hp / max_hp

        # 1. 底色框
        pygame.draw.rect(self.screen, (35, 35, 45), (x, y, bar_w, bar_h), border_radius=4)
        # 2. 扣血殘影過渡條 (亮橘黃色)
        if disp_ratio > 0:
            pygame.draw.rect(
                self.screen,
                (245, 190, 65),
                (x, y, int(bar_w * disp_ratio), bar_h),
                border_radius=4,
            )
        # 3. 當前血量條 (鮮紅色)
        if cur_ratio > 0:
            pygame.draw.rect(
                self.screen,
                (215, 45, 55),
                (x, y, int(bar_w * cur_ratio), bar_h),
                border_radius=4,
            )
        # 4. 外框線
        pygame.draw.rect(
            self.screen, (240, 240, 245), (x, y, bar_w, bar_h), 2, border_radius=4
        )

        # 5. 血量數值與比例呈現
        hp_str = f"PLAYER HP: {cur_hp} / {max_hp} ({int(cur_ratio * 100)}%)"
        txt_surf = self.font_hud.render(hp_str, True, (255, 255, 255))
        self.screen.blit(txt_surf, (x + 10, y + 4))

        # 6. 格擋狀態與按鍵提示
        if self.player.is_parrying:
            badge_text = "★ PERFECT PARRY WINDOW ★"
            badge_color = (80, 245, 255)
        elif self.player.is_blocking:
            badge_text = "GUARDING (70% DMG REDUCTION)"
            badge_color = (120, 180, 255)
        else:
            badge_text = "RMB / J / Shift: Parry & Guard | F1: Debug Boxes"
            badge_color = (210, 215, 225)

        badge_surf = self.font_hud.render(badge_text, True, badge_color)
        self.screen.blit(badge_surf, (x, y + bar_h + 6))

        # 7. 若有觸發完美格擋/一般格擋文字回饋，顯示於玩家頭頂對應螢幕位置
        if self.player.status_timer > 0.0 and self.player.status_text:
            sx = self.player.collision_rect.centerx - self.camera_x
            sy = self.player.collision_rect.top - 22 - self.camera_y
            color = (
                (90, 250, 255)
                if "PERFECT" in self.player.status_text
                else (255, 230, 120)
            )
            self.draw_text(self.player.status_text, self.font_hud, color, (sx, sy))

    def draw_boss_hp(self):
        """
        畫面頂部中央繪製大型 Boss 專用血量條與名稱：
        包含底色框、殘影過渡條 (Damage Follow Bar)、當前血量條、Boss 名稱與當前 AI 狀態。
        """
        max_hp = self.boss.max_health
        cur_hp = max(self.boss.boss_health, 0)
        disp_hp = max(self.boss_display_hp, cur_hp)

        bar_w, bar_h = 540, 22
        x = (WIDTH - bar_w) // 2
        y = 38

        cur_ratio = cur_hp / max_hp
        disp_ratio = disp_hp / max_hp

        # 1. Boss 名稱與狀態標題 (帶深色陰影確保清晰可讀)
        title = f"VERGIL — {self.boss.state}"
        if self.boss.attack_phase != "NONE":
            title += f" [{self.boss.attack_phase}]"
        self.draw_text(title, self.font_hud, (20, 20, 30), (WIDTH // 2 + 1, y - 13))
        self.draw_text(title, self.font_hud, (245, 240, 255), (WIDTH // 2, y - 14))

        # 2. 底色框
        pygame.draw.rect(self.screen, (35, 30, 45), (x, y, bar_w, bar_h), border_radius=4)
        # 3. 扣血殘影過渡條 (亮粉白/金色)
        if disp_ratio > 0:
            pygame.draw.rect(
                self.screen,
                (245, 215, 255),
                (x, y, int(bar_w * disp_ratio), bar_h),
                border_radius=4,
            )
        # 4. 當前血量條 (深紫紅色)
        if cur_ratio > 0:
            pygame.draw.rect(
                self.screen,
                (165, 35, 185),
                (x, y, int(bar_w * cur_ratio), bar_h),
                border_radius=4,
            )
        # 5. 外框線
        pygame.draw.rect(
            self.screen, (245, 245, 250), (x, y, bar_w, bar_h), 2, border_radius=4
        )

        # 6. 血量數值與比例文字
        hp_label = f"{cur_hp} / {max_hp} ({int(cur_ratio * 100)}%)"
        self.draw_text(
            hp_label, self.font_hud, (255, 255, 255), (WIDTH // 2, y + bar_h // 2)
        )

    # ---------- 主迴圈階段 ----------
    def handle_events(self):
        """1. 處理輸入事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            if event.type == pygame.KEYDOWN:
                # 切換 Debug 線框模式 (F1 或 TAB)
                if event.key in (pygame.K_F1, pygame.K_TAB):
                    self.debug_mode = not self.debug_mode

                if self.state == State.MENU and event.key == pygame.K_RETURN:
                    self.new_game()
                    self.state = State.PLAYING
                elif self.state == State.PLAYING and event.key == pygame.K_ESCAPE:
                    self.state = State.PAUSED
                elif self.state == State.PAUSED and event.key == pygame.K_ESCAPE:
                    self.state = State.PLAYING
                elif self.state == State.GAME_OVER and event.key == pygame.K_RETURN:
                    self.state = State.MENU

                # 遊戲進行中的玩家動作輸入
                elif self.state == State.PLAYING:
                    if event.key in (pygame.K_w, pygame.K_SPACE, pygame.K_UP):
                        self.player.jump()
                    elif event.key in (pygame.K_j, pygame.K_LSHIFT, pygame.K_k):
                        self.player.start_block()

            if event.type == pygame.KEYUP and self.state == State.PLAYING:
                if event.key in (pygame.K_j, pygame.K_LSHIFT, pygame.K_k):
                    self.player.stop_block()

            if event.type == pygame.MOUSEBUTTONDOWN and self.state == State.PLAYING:
                if event.button == 1:
                    self.player.attack()
                elif event.button == 3:
                    self.player.start_block()

            if event.type == pygame.MOUSEBUTTONUP and self.state == State.PLAYING:
                if event.button == 3:
                    self.player.stop_block()

    def resolve_combat_collisions(self):
        """
        處理所有啟用中 Hitbox 與目標 Hurtbox / ParryBox 的精確碰撞判定：
        - 透過 Hitbox.hit_targets 確保單次攻擊對同一目標只判定一次
        - 整合玩家的完美格擋 (觸發子彈時間) 與一般格擋
        """
        # 清理已銷毀的 Hitbox
        self.active_hitboxes = [hb for hb in self.active_hitboxes if hb.active]

        for hb in self.active_hitboxes:
            if not hb.active:
                continue

            # A. 玩家的攻擊 Hitbox -> 檢測 Boss Hurtbox
            if hb.owner == "player":
                for enemy in self.enemies:
                    if (
                        enemy.alive()
                        and hb.can_hit(enemy)
                        and hb.rect.colliderect(enemy.hurtbox)
                    ):
                        hb.register_hit(enemy)
                        enemy.be_attacked(hb.damage)

            # B. Boss 的攻擊 Hitbox -> 檢測玩家格擋框 (ParryBox) 或受擊框 (Hurtbox)
            elif hb.owner == "boss" and self.player.alive():
                if not hb.can_hit(self.player):
                    continue

                hit_parry_box = (
                    self.player.is_blocking
                    and hb.rect.colliderect(self.player.parry_box)
                )
                hit_hurtbox = hb.rect.colliderect(self.player.hurtbox)

                if hit_parry_box or hit_hurtbox:
                    hb.register_hit(self.player)
                    outcome = self.player.take_hit(
                        hb, attacker=self.boss, vfx_group=self.vfx_group
                    )
                    if outcome == "parry":
                        # 觸發完美格擋 -> 啟動子彈時間並打斷 Boss 當前近戰連段
                        self.trigger_bullet_time()
                        if self.boss.alive():
                            self.boss.on_parried()

    def update(self, raw_dt):
        """2. 更新遊戲邏輯 (整合 Unscaled raw_dt 與 Scaled dt = raw_dt * time_scale)"""
        if self.state == State.PLAYING:
            # A. 更新子彈時間計時器 (使用真實時間 raw_dt)
            if self.bullet_time_timer > 0.0:
                self.bullet_time_timer = max(0.0, self.bullet_time_timer - raw_dt)
                if self.bullet_time_timer <= 0.0:
                    # 平滑過渡恢復至 1.0
                    self.time_scale = min(
                        1.0,
                        self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt,
                    )
            elif self.time_scale < 1.0:
                self.time_scale = min(
                    1.0, self.time_scale + BULLET_TIME_RECOVERY_SPEED * raw_dt
                )

            # B. 計算乘上 time_scale 後的縮放時間差 scaled_dt
            scaled_dt = raw_dt * self.time_scale

            # C. 更新角色、Boss、特效與 Hitbox (皆乘上 scaled_dt)
            self.player.update(
                dt=scaled_dt,
                raw_dt=raw_dt,
                active_hitboxes=self.active_hitboxes,
                vfx_group=self.vfx_group,
                map_width=self.game_map.width,
            )
            if self.boss.alive():
                self.boss.update(
                    dt=scaled_dt,
                    active_hitboxes=self.active_hitboxes,
                    vfx_group=self.vfx_group,
                    map_width=self.game_map.width,
                )

            for vfx in list(self.vfx_group):
                vfx.update(scaled_dt)

            for hb in list(self.active_hitboxes):
                hb.update(scaled_dt)

            # D. 執行 Hitbox / Hurtbox / 完美格擋碰撞檢測
            self.resolve_combat_collisions()

            # E. 更新 HUD 血量條殘影過渡 (使用真實時間 raw_dt，不受慢動作影響)
            decay_speed = 38.0 * raw_dt
            if self.player_display_hp > self.player.player_hp:
                self.player_display_hp = max(
                    float(self.player.player_hp),
                    self.player_display_hp - decay_speed,
                )
            else:
                self.player_display_hp = float(self.player.player_hp)

            if self.boss_display_hp > self.boss.boss_health:
                self.boss_display_hp = max(
                    float(self.boss.boss_health),
                    self.boss_display_hp - decay_speed,
                )
            else:
                self.boss_display_hp = float(self.boss.boss_health)

            # F. 更新攝影機偏移
            self.camera_x, self.camera_y = self.game_map.get_camera_offset(
                self.player.collision_rect, WIDTH, HEIGHT
            )

            if self.player.player_hp <= 0:
                self.state = State.GAME_OVER

    def draw(self):
        """3. 繪製畫面"""
        if self.state == State.MENU:
            self.screen.fill((20, 20, 60))
            self.draw_text(
                "MY GAME", self.font_big, (255, 255, 255), (WIDTH // 2, 230)
            )
            self.draw_text(
                "Press ENTER to start",
                self.font_small,
                (200, 200, 200),
                (WIDTH // 2, 360),
            )
            self.draw_text(
                "Controls: A/D Move | W/SPACE Fixed Jump | LMB Attack | RMB/J/Shift Parry & Guard | F1 Debug",
                self.font_hud,
                (160, 190, 230),
                (WIDTH // 2, 430),
            )

        elif self.state in (State.PLAYING, State.PAUSED):
            self.screen.blit(self.background, (0, 0))
            self.game_map.draw(self.screen, self.camera_x, self.camera_y)

            # 1. 角色、Boss 扣掉鏡頭偏移以對齊地圖
            for sprite in self.all_sprites:
                if sprite.alive():
                    self.screen.blit(
                        sprite.image,
                        sprite.rect.move(-self.camera_x, -self.camera_y),
                    )

            # 2. 繪製所有攻擊與格擋視覺特效 (VFX)
            for vfx in self.vfx_group:
                vfx.draw(self.screen, self.camera_x, self.camera_y)

            # 3. 子彈時間濾鏡氛圍效果
            if self.time_scale < 0.95:
                self.screen.blit(self.bullet_time_overlay, (0, 0))
                self.draw_text(
                    f"BULLET TIME ({self.time_scale:.1f}x)",
                    self.font_small,
                    (100, 240, 255),
                    (WIDTH // 2, 85),
                )

            # 4. Debug 模式：繪製 Hurtbox (綠)、Hitbox (紅)、格擋框 (藍)、移動框 (黃)
            if self.debug_mode:
                draw_debug_boxes(
                    self.screen,
                    self.camera_x,
                    self.camera_y,
                    self.player,
                    self.boss,
                    self.active_hitboxes,
                )
                debug_info = "DEBUG [F1]: Green=Hurtbox | Red=Active Hitbox | Cyan/Blue=Parry/Block | Yellow=Collision"
                dbg_surf = self.font_hud.render(debug_info, True, (255, 255, 100))
                self.screen.blit(dbg_surf, (WIDTH - dbg_surf.get_width() - 20, 16))

            # 5. 最上層繪製固定 HUD 血量條 (不受鏡頭偏移或子彈時間影響)
            self.draw_player_hp()
            self.draw_boss_hp()

            if not self.boss.alive():
                self.draw_text(
                    "VICTORY! BOSS DEFEATED",
                    self.font_big,
                    (255, 215, 80),
                    (WIDTH // 2, HEIGHT // 2 - 40),
                )

            if self.state == State.PAUSED:
                self.screen.blit(self.pause_overlay, (0, 0))
                self.draw_text(
                    "PAUSED",
                    self.font_big,
                    (255, 255, 255),
                    (WIDTH // 2, HEIGHT // 2),
                )

        elif self.state == State.GAME_OVER:
            self.screen.fill((80, 20, 20))
            self.draw_text(
                "GAME OVER", self.font_big, (255, 255, 255), (WIDTH // 2, 280)
            )
            self.draw_text(
                "Press ENTER to return to menu",
                self.font_small,
                (220, 220, 220),
                (WIDTH // 2, 420),
            )

        pygame.display.flip()

    def run(self):
        while self.running:
            # 計算每幀真實時間差 raw_dt (秒)，並設置上限避免視窗拖曳造成物理暴衝
            raw_dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(raw_dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
