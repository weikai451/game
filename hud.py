import pygame
from Settings import WIDTH, HEIGHT, get_pixel_font


class HUD:
    def __init__(self, player, boss=None, is_tutorial=False):
        self.player = player
        self.boss = boss
        self.is_tutorial = is_tutorial

        # Global pixel fonts (rendered with antialias=False)
        self.font_big = get_pixel_font(55)
        self.font_mid = get_pixel_font(33)
        self.font_small = get_pixel_font(22)
        self.font_hud = get_pixel_font(16)

        self.player_display_hp = float(getattr(player, "player_hp", 100))
        self.boss_display_hp = (
            float(getattr(boss, "boss_health", 100)) if boss else 0.0
        )

    def reset(self, player, boss=None, is_tutorial=False):
        """Reset bound Player, Boss, and state when starting a new game or switching maps"""
        self.player = player
        self.boss = boss
        self.is_tutorial = is_tutorial
        self.player_display_hp = float(getattr(player, "player_hp", 100))
        self.boss_display_hp = (
            float(getattr(boss, "boss_health", 100)) if boss else 0.0
        )

    def update(self, raw_dt):
        """Update smooth HP transition bars (both damage decay and checkpoint heal fill)"""
        decay_speed = 42.0 * raw_dt
        heal_speed = 140.0 * raw_dt
        self.player_display_hp = self._smooth_hp(
            self.player_display_hp,
            self.player.player_hp,
            decay_speed,
            heal_speed,
        )
        if self.boss is not None and hasattr(self.boss, "boss_health"):
            self.boss_display_hp = self._smooth_hp(
                self.boss_display_hp,
                self.boss.boss_health,
                decay_speed,
                heal_speed,
            )

    def _smooth_hp(self, current_disp, target_hp, down_step, up_step):
        target_f = float(target_hp)
        if current_disp > target_f:
            return max(target_f, current_disp - down_step)
        if current_disp < target_f:
            return min(target_f, current_disp + up_step)
        return target_f

    def draw_text(self, screen, text, font, color, center):
        """Render crisp pixel text (antialias=False)"""
        img = font.render(text, False, color)
        screen.blit(img, img.get_rect(center=center))

    def draw_gameplay_hud(self, screen):
        """
        Draw fixed top-level HUD on screen (called after 1.15x World Zoom-in)
        """
        self._draw_player_hp(screen)
        if (
            not self.is_tutorial
            and self.boss is not None
            and getattr(self.boss, "alive", lambda: False)()
        ):
            self._draw_boss_hp(screen)

    def _draw_player_hp(self, screen):
        """Draw top-left Player HP bar with smooth damage trail and heal fill animation"""
        x, y = 24, 25
        bar_w, bar_h = 300, 24
        max_hp = getattr(self.player, "max_hp", 100)
        actual_hp = max(self.player.player_hp, 0)
        disp_hp = max(0.0, min(float(max_hp), self.player_display_hp))
        god_mode = getattr(self.player, "god_mode", False)

        is_healing = disp_hp < actual_hp - 0.1
        main_hp = disp_hp if is_healing else float(actual_hp)
        trail_hp = float(actual_hp) if is_healing else max(disp_hp, float(actual_hp))

        main_ratio = main_hp / max_hp
        trail_ratio = trail_hp / max_hp

        # 1. Background bar
        pygame.draw.rect(screen, (35, 35, 45), (x, y, bar_w, bar_h), border_radius=4)
        # 2. Transition bar (Amber for damage trail, Emerald for checkpoint heal preview)
        if trail_ratio > 0:
            trail_col = (80, 255, 160) if is_healing else (245, 190, 65)
            pygame.draw.rect(
                screen,
                trail_col,
                (x, y, int(bar_w * trail_ratio), bar_h),
                border_radius=4,
            )
        # 3. Current HP bar
        bar_color = (50, 205, 110) if god_mode else (215, 45, 55)
        if main_ratio > 0:
            pygame.draw.rect(
                screen,
                bar_color,
                (x, y, int(bar_w * main_ratio), bar_h),
                border_radius=4,
            )
        # 4. Border
        border_color = (100, 255, 140) if god_mode else (240, 240, 245)
        pygame.draw.rect(
            screen, border_color, (x, y, bar_w, bar_h), 2, border_radius=4
        )

        # 5. HP numerical label (antialias=False)
        shown_int_hp = int(round(main_hp))
        hp_str = f"PLAYER HP: {shown_int_hp} / {max_hp} ({int(main_ratio * 100)}%)"
        txt_surf = self.font_hud.render(hp_str, False, (255, 255, 255))
        screen.blit(txt_surf, (x + 10, y + 4))

        # 6. Parry / Buff / Controls status badge (no remaining buff seconds shown)
        next_y = y + bar_h + 6
        is_parrying = getattr(self.player, "is_parrying", False)
        parry_buff = getattr(self.player, "parry_damage_buff", False)
        is_blocking = getattr(self.player, "is_blocking", False)

        if is_parrying:
            badge_text = "* PERFECT PARRY WINDOW *"
            badge_color = (80, 245, 255)
        elif parry_buff:
            badge_text = ">> PARRY BUFF: 1.35x ATK DMG <<"
            badge_color = (255, 205, 55)
        elif is_blocking:
            badge_text = "GUARDING (70% DMG REDUCTION)"
            badge_color = (120, 180, 255)
        else:
            badge_text = "LMB: Attack | Air S+LMB: Pogo | RMB/J: Parry | E: Interact"
            badge_color = (210, 215, 225)

        badge_surf = self.font_hud.render(badge_text, False, badge_color)
        screen.blit(badge_surf, (x, next_y))

        # 7. [DEBUG: GOD MODE] indicator when debug mode is active
        if god_mode:
            god_surf = self.font_hud.render(
                "[DEBUG: GOD MODE]", False, (80, 255, 120)
            )
            badge_bg = pygame.Rect(
                x, next_y + 22, god_surf.get_width() + 16, god_surf.get_height() + 8
            )
            pygame.draw.rect(screen, (20, 45, 30), badge_bg, border_radius=4)
            pygame.draw.rect(screen, (80, 255, 120), badge_bg, 2, border_radius=4)
            screen.blit(god_surf, (badge_bg.x + 8, badge_bg.y + 4))

    def _draw_boss_hp(self, screen):
        """
        Draw top-center Boss HP bar and state label (x = (WIDTH - bar_w) // 2, y = 25)
        """
        if self.boss is None:
            return

        max_hp = getattr(self.boss, "max_health", 100)
        cur_hp = max(self.boss.boss_health, 0)
        disp_hp = max(self.boss_display_hp, cur_hp)

        bar_w, bar_h = 520, 24
        x = (WIDTH - bar_w) // 2
        y = 25

        intro_scale = max(0.0, min(1.0, getattr(self.boss, "intro_progress", 1.0)))
        cur_ratio = (cur_hp / max_hp) * intro_scale
        disp_ratio = (disp_hp / max_hp) * intro_scale

        pygame.draw.rect(screen, (35, 30, 45), (x, y, bar_w, bar_h), border_radius=4)
        if disp_ratio > 0:
            pygame.draw.rect(
                screen,
                (245, 215, 255),
                (x, y, int(bar_w * disp_ratio), bar_h),
                border_radius=4,
            )
        if cur_ratio > 0:
            pygame.draw.rect(
                screen,
                (165, 35, 185),
                (x, y, int(bar_w * cur_ratio), bar_h),
                border_radius=4,
            )
        pygame.draw.rect(
            screen, (245, 245, 250), (x, y, bar_w, bar_h), 2, border_radius=4
        )

        hp_val_str = (
            f"{cur_hp:.1f}"
            if abs(cur_hp - round(cur_hp)) > 0.05
            else f"{int(round(cur_hp))}"
        )
        boss_name = getattr(self.boss, "boss_name", "SANS")
        hp_label = f"{boss_name}: {hp_val_str} / {int(max_hp)} ({int(cur_ratio * 100)}%)"
        self.draw_text(
            screen, hp_label, self.font_hud, (255, 255, 255), (WIDTH // 2, y + bar_h // 2)
        )

        # Optional compact Stamina Bar directly under HP Bar (e.g. Undertale Sans 10-Dodge Stamina)
        next_label_y = y + bar_h + 14
        max_stam = getattr(self.boss, "max_stamina", 0)
        if max_stam > 0:
            cur_stam = max(0, getattr(self.boss, "stamina", 0))
            stam_ratio = (cur_stam / max_stam) * intro_scale
            s_w = 340
            s_h = 14
            sx = (WIDTH - s_w) // 2
            sy = y + bar_h + 5

            pygame.draw.rect(screen, (24, 28, 42), (sx, sy, s_w, s_h), border_radius=3)
            if stam_ratio > 0:
                fill_col = (255, 215, 60) if cur_stam > 3 else (75, 235, 255)
                pygame.draw.rect(
                    screen,
                    fill_col,
                    (sx, sy, max(2, int(s_w * stam_ratio)), s_h),
                    border_radius=3,
                )
            pygame.draw.rect(
                screen, (215, 235, 250), (sx, sy, s_w, s_h), 1, border_radius=3
            )
            stam_txt = f"STAMINA: {cur_stam} / {max_stam}"
            self.draw_text(
                screen, stam_txt, self.font_hud, (15, 18, 28), (WIDTH // 2 + 1, sy + s_h // 2 + 1)
            )
            self.draw_text(
                screen, stam_txt, self.font_hud, (255, 255, 255), (WIDTH // 2, sy + s_h // 2)
            )
            next_label_y = sy + s_h + 13

        boss_state = getattr(self.boss, "state", "BOSS")
        title = f"{boss_state}"
        attack_phase = getattr(self.boss, "attack_phase", "NONE")
        if attack_phase != "NONE":
            title += f" [{attack_phase}]"
        self.draw_text(
            screen, title, self.font_hud, (20, 20, 30), (WIDTH // 2 + 1, next_label_y)
        )
        self.draw_text(
            screen, title, self.font_hud, (235, 225, 255), (WIDTH // 2, next_label_y - 1)
        )

    # =========================================================================
    # Tutorial Prompt Dialog (TUTORIAL_PROMPT) & Guided Stage Banner
    # =========================================================================

    def draw_tutorial_prompt(self, screen, selected_option=0):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 185))
        screen.blit(overlay, (0, 0))

        box_w, box_h = 760, 400
        box_x = (WIDTH - box_w) // 2
        box_y = (HEIGHT - box_h) // 2
        dialog_rect = pygame.Rect(box_x, box_y, box_w, box_h)

        pygame.draw.rect(screen, (22, 26, 38), dialog_rect, border_radius=12)
        pygame.draw.rect(screen, (80, 130, 190), dialog_rect, 3, border_radius=12)

        self.draw_text(
            screen,
            "ENTER GUIDED TUTORIAL?",
            self.font_mid,
            (255, 215, 80),
            (WIDTH // 2, box_y + 65),
        )
        self.draw_text(
            screen,
            "5-Stage Interactive Training: Move, Jump, Pogo Slash, Perfect Parry & Portals",
            self.font_hud,
            (180, 205, 230),
            (WIDTH // 2, box_y + 145),
        )

        btn_w, btn_h = 280, 56
        btn_y = box_y + 240
        gap = 40
        yes_x = WIDTH // 2 - btn_w - gap // 2
        no_x = WIDTH // 2 + gap // 2

        yes_rect = pygame.Rect(yes_x, btn_y, btn_w, btn_h)
        no_rect = pygame.Rect(no_x, btn_y, btn_w, btn_h)

        is_yes = selected_option == 0
        yes_bg = (40, 110, 170) if is_yes else (32, 38, 52)
        yes_border = (100, 220, 255) if is_yes else (70, 80, 100)
        yes_text_color = (255, 255, 255) if is_yes else (170, 180, 200)
        pygame.draw.rect(screen, yes_bg, yes_rect, border_radius=8)
        pygame.draw.rect(
            screen, yes_border, yes_rect, 3 if is_yes else 1, border_radius=8
        )
        self.draw_text(
            screen,
            "YES (Play Tutorial)",
            self.font_small,
            yes_text_color,
            yes_rect.center,
        )

        is_no = selected_option == 1
        no_bg = (160, 55, 65) if is_no else (32, 38, 52)
        no_border = (255, 120, 130) if is_no else (70, 80, 100)
        no_text_color = (255, 255, 255) if is_no else (170, 180, 200)
        pygame.draw.rect(screen, no_bg, no_rect, border_radius=8)
        pygame.draw.rect(
            screen, no_border, no_rect, 3 if is_no else 1, border_radius=8
        )
        self.draw_text(
            screen,
            "NO (Skip to Main Game)",
            self.font_small,
            no_text_color,
            no_rect.center,
        )

        self.draw_text(
            screen,
            "LEFT / RIGHT or A / D: Select  |  ENTER: Confirm  |  Mouse Click Supported",
            self.font_hud,
            (130, 155, 185),
            (WIDTH // 2, box_y + 355),
        )

        return {"YES": yes_rect, "NO": no_rect}

    def draw_tutorial_stage_banner(
        self, screen, stage_title, primary_hint, secondary_hint="", completed=False
    ):
        """
        Draw the active Guided Tutorial stage banner at the top-center of the screen.
        """
        panel_w, panel_h = 720, 86
        panel_x = (WIDTH - panel_w) // 2
        panel_y = 18
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_surf.fill((14, 18, 32, 225))
        screen.blit(panel_surf, (panel_x, panel_y))

        border_col = (80, 255, 145) if completed else (90, 205, 255)
        pygame.draw.rect(screen, (32, 46, 74), panel_rect.inflate(4, 4), 2, border_radius=6)
        pygame.draw.rect(screen, border_col, panel_rect, 2, border_radius=6)

        title_col = (100, 255, 160) if completed else (255, 220, 85)
        self.draw_text(
            screen,
            stage_title,
            self.font_small,
            title_col,
            (WIDTH // 2, panel_y + 24),
        )
        self.draw_text(
            screen,
            primary_hint,
            self.font_hud,
            (240, 248, 255),
            (WIDTH // 2, panel_y + 50),
        )
        if secondary_hint:
            self.draw_text(
                screen,
                secondary_hint,
                self.font_hud,
                (120, 230, 255),
                (WIDTH // 2, panel_y + 70),
            )
