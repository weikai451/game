import math
import random
import pygame
from Settings import WIDTH, HEIGHT, get_pixel_font
from audio_manager import get_audio


class Menu:
    """
    Pixel-art Menu supporting both standard buttons and interactive Volume Sliders
    (keyboard Up/Down/Left/Right + mouse click & drag). All text rendered with antialias=False.
    """

    def __init__(self, title, options, fill_background=True, sliders=None):
        self.title = title
        self.fill_background = fill_background
        self.options = list(options)
        self.sliders = list(sliders) if sliders else []
        self.selected = 0
        self._dragging_slider = None

        self.title_font = get_pixel_font(62)
        self.option_font = get_pixel_font(30)
        self.slider_font = get_pixel_font(20)
        self.hint_font = get_pixel_font(15)

        self.color_normal = (185, 190, 205)
        self.color_selected = (255, 220, 100)

    def _total_items(self):
        return len(self.sliders) + len(self.options)

    def slider_row_rect(self, idx):
        w, h = 500, 44
        x = (WIDTH - w) // 2
        y = 215 + idx * 54
        return pygame.Rect(x, y, w, h)

    def slider_track_rect(self, idx):
        row = self.slider_row_rect(idx)
        return pygame.Rect(row.x + 215, row.y + 14, 210, 16)

    def option_rect(self, i):
        """Button bounds for the i-th standard option."""
        if self.sliders:
            w, h = 340, 52
            x = (WIDTH - w) // 2
            base_y = 215 + len(self.sliders) * 54 + 24
            y = base_y + i * 64
        else:
            w, h = 340, 60
            x = (WIDTH - w) // 2
            y = 330 + i * 80
        return pygame.Rect(x, y, w, h)

    def _set_slider_from_mouse(self, idx, mouse_x, play_preview=False):
        track = self.slider_track_rect(idx)
        ratio = max(0.0, min(1.0, (mouse_x - track.x) / max(1, track.width)))
        # Snap to 5% steps for crisp UX
        snapped = round(ratio * 20) / 20.0
        key = self.sliders[idx]["key"]
        audio = get_audio()
        prev = audio.get_channel_volume(key)
        audio.set_channel_volume(key, snapped)
        if play_preview and abs(snapped - prev) >= 0.01 and key in ("master", "sfx"):
            audio.play_sfx("prompt_pop")

    def _nudge_slider(self, idx, delta):
        key = self.sliders[idx]["key"]
        audio = get_audio()
        cur = audio.get_channel_volume(key)
        new_val = round(max(0.0, min(1.0, cur + delta)) * 20) / 20.0
        audio.set_channel_volume(key, new_val)
        if key in ("master", "sfx"):
            audio.play_sfx("prompt_pop")

    def handle_event(self, event):
        """Handle keyboard/mouse input. Returns selected option name or None."""
        total = self._total_items()
        num_sliders = len(self.sliders)

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % total
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % total
            elif event.key in (pygame.K_LEFT, pygame.K_a) and self.selected < num_sliders:
                self._nudge_slider(self.selected, -0.05)
            elif event.key in (pygame.K_RIGHT, pygame.K_d) and self.selected < num_sliders:
                self._nudge_slider(self.selected, 0.05)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.selected >= num_sliders:
                return self.options[self.selected - num_sliders]

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging_slider is not None:
                self._set_slider_from_mouse(
                    self._dragging_slider, event.pos[0], play_preview=False
                )
            else:
                for i in range(num_sliders):
                    if self.slider_row_rect(i).collidepoint(event.pos):
                        self.selected = i
                        return None
                for i in range(len(self.options)):
                    if self.option_rect(i).collidepoint(event.pos):
                        self.selected = num_sliders + i
                        return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(num_sliders):
                row = self.slider_row_rect(i)
                track = self.slider_track_rect(i).inflate(14, 14)
                if track.collidepoint(event.pos) or row.collidepoint(event.pos):
                    self.selected = i
                    self._dragging_slider = i
                    self._set_slider_from_mouse(i, event.pos[0], play_preview=True)
                    return None
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    return self.options[i]

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging_slider is not None:
                key = self.sliders[self._dragging_slider]["key"]
                if key in ("master", "sfx"):
                    get_audio().play_sfx("prompt_pop")
                self._dragging_slider = None

        return None

    def draw(self, screen):
        if self.fill_background:
            screen.fill((20, 20, 40))

        title_y = 128 if self.sliders else 200
        title_img = self.title_font.render(self.title, False, (255, 255, 255))
        screen.blit(title_img, title_img.get_rect(center=(WIDTH // 2, title_y)))

        audio = get_audio()
        num_sliders = len(self.sliders)

        # 1. Draw Pixel Volume Sliders (Master / BGM / SFX)
        for i, sl in enumerate(self.sliders):
            row = self.slider_row_rect(i)
            track = self.slider_track_rect(i)
            is_sel = (self.selected == i)
            val = audio.get_channel_volume(sl["key"])
            pct = int(round(val * 100))

            bg_col = (48, 54, 82) if is_sel else (26, 30, 48)
            border_col = self.color_selected if is_sel else (90, 100, 130)
            pygame.draw.rect(screen, bg_col, row, border_radius=6)
            pygame.draw.rect(screen, border_col, row, 2 if is_sel else 1, border_radius=6)

            lbl_col = self.color_selected if is_sel else (210, 218, 235)
            lbl_surf = self.slider_font.render(sl["label"], False, lbl_col)
            screen.blit(lbl_surf, (row.x + 14, row.centery - lbl_surf.get_height() // 2))

            # Track background & filled portion
            pygame.draw.rect(screen, (16, 18, 28), track, border_radius=3)
            fill_w = int(round(track.width * val))
            if fill_w > 0:
                fill_col = (90, 230, 255) if is_sel else (70, 175, 225)
                pygame.draw.rect(
                    screen, fill_col, (track.x, track.y, fill_w, track.height), border_radius=3
                )
            pygame.draw.rect(screen, (200, 220, 240), track, 1, border_radius=3)

            # Pixel handle knob
            knob_x = track.x + fill_w
            knob_rect = pygame.Rect(knob_x - 5, track.y - 4, 10, track.height + 8)
            pygame.draw.rect(
                screen, (255, 240, 160) if is_sel else (225, 235, 245), knob_rect, border_radius=2
            )

            pct_surf = self.slider_font.render(f"{pct:3d}%", False, (245, 250, 255))
            screen.blit(pct_surf, (track.right + 12, row.centery - pct_surf.get_height() // 2))

        if self.sliders:
            hint = self.hint_font.render(
                "LEFT/RIGHT or Drag Slider to Adjust Volume", False, (150, 170, 200)
            )
            screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 188)))

        # 2. Draw Standard Menu Buttons
        for i, text in enumerate(self.options):
            rect = self.option_rect(i)
            if self.selected == num_sliders + i:
                color = self.color_selected
                pygame.draw.rect(screen, (60, 60, 90), rect, border_radius=10)
                pygame.draw.rect(screen, color, rect, 3, border_radius=10)
            else:
                color = self.color_normal
            img = self.option_font.render(text, False, color)
            screen.blit(img, img.get_rect(center=rect.center))


class MainMenu:
    """
    INDIE CROSS Dimensional Rift Main Menu (Pure Pygame Pixel Art, antialias=False):
    - Deep void background (#07080F) with drifting cyan (#00D8FF) & crimson (#FF2A4B) pixel squares.
    - Central low-frequency breathing 4-point Cross-Star Dimensional Rift (zero strobe).
    - Chromatic dual-shadow 'INDIE CROSS' pixel logo + thin cyan-white divider line.
    - Clean options: START GAME, CONTINUE (enabled only with Checkpoint save), SETTINGS, QUIT.
    - Keyboard + Mouse dual input with smooth slide offset & rotating pixel Star Cursor.
    """

    OPTIONS = ("START GAME", "CONTINUE", "SETTINGS", "QUIT")

    def __init__(self):
        self.selected = 0
        self.elapsed = 0.0
        self.hover_offsets = [0.0 for _ in self.OPTIONS]

        self.logo_font = get_pixel_font(84)
        self.option_font = get_pixel_font(30)

        # Pre-generate 48 drifting void pixel squares
        self.particles = []
        for _ in range(48):
            self.particles.append(
                [
                    random.uniform(0, WIDTH),
                    random.uniform(0, HEIGHT),
                    random.uniform(-10.0, 10.0),
                    random.uniform(-24.0, -7.0),
                    random.choice((4, 4, 6, 6, 8)),
                    random.choice(
                        (
                            (0, 216, 255),
                            (0, 170, 225),
                            (255, 42, 75),
                            (215, 35, 65),
                            (130, 145, 185),
                        )
                    ),
                    random.uniform(0.0, math.tau),
                ]
            )

    def _is_enabled(self, idx, has_save):
        if self.OPTIONS[idx] == "CONTINUE":
            return bool(has_save)
        return True

    def option_rect(self, idx):
        w, h = 340, 48
        x = (WIDTH - w) // 2
        y = 350 + idx * 60
        return pygame.Rect(x, y, w, h)

    def update(self, dt):
        self.elapsed += dt
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[1] < -12:
                p[1] = HEIGHT + 10
                p[0] = random.uniform(0, WIDTH)
            elif p[0] < -12:
                p[0] = WIDTH + 10
            elif p[0] > WIDTH + 12:
                p[0] = -10

        for i in range(len(self.OPTIONS)):
            target = 14.0 if i == self.selected else 0.0
            self.hover_offsets[i] += (target - self.hover_offsets[i]) * min(1.0, dt * 14.0)

    def _step_selection(self, delta, has_save):
        n = len(self.OPTIONS)
        cur = self.selected
        for _ in range(n):
            cur = (cur + delta) % n
            if self._is_enabled(cur, has_save):
                if cur != self.selected:
                    self.selected = cur
                    get_audio().play_sfx("prompt_pop")
                return

    def handle_event(self, event, has_save=False):
        if not self._is_enabled(self.selected, has_save):
            self.selected = 0

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self._step_selection(-1, has_save)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._step_selection(1, has_save)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self._is_enabled(self.selected, has_save):
                    get_audio().play_sfx("sheathe")
                    return self.OPTIONS[self.selected]

        elif event.type == pygame.MOUSEMOTION:
            for i in range(len(self.OPTIONS)):
                if self._is_enabled(i, has_save) and self.option_rect(i).collidepoint(event.pos):
                    if self.selected != i:
                        self.selected = i
                        get_audio().play_sfx("prompt_pop")
                    break

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.OPTIONS)):
                if self._is_enabled(i, has_save) and self.option_rect(i).collidepoint(event.pos):
                    self.selected = i
                    get_audio().play_sfx("sheathe")
                    return self.OPTIONS[i]

        return None

    def _star_points(self, cx, cy, outer_r, inner_r, rot_rad=0.0):
        pts = []
        for i in range(8):
            ang = rot_rad + i * (math.pi * 0.25)
            r = outer_r if i % 2 == 0 else inner_r
            pts.append((int(round(cx + math.cos(ang) * r)), int(round(cy + math.sin(ang) * r))))
        return pts

    def draw_void_background(self, screen):
        """Render the animated #07080F void, drifting pixel squares & central breathing Cross-Star Rift."""
        screen.fill((7, 8, 15))
        t = self.elapsed

        # 1. Drifting cyan & crimson pixel-square particles
        for px, py, _, _, sz, col, phase in self.particles:
            twinkle = 0.60 + 0.40 * math.sin(t * 2.2 + phase)
            c = (int(col[0] * twinkle), int(col[1] * twinkle), int(col[2] * twinkle))
            pygame.draw.rect(screen, c, (int(px), int(py), sz, sz))

        # 2. Central low-frequency breathing 4-Point Cross-Star Rift (smooth 0.45Hz pulse, zero strobe)
        cx, cy = WIDTH // 2, 224
        breath = 1.0 + 0.08 * math.sin(t * 0.45 * math.tau)
        rot = math.sin(t * 0.35) * 0.08

        # Subtle concentric void rings
        for ring_i in range(2):
            r_rad = int((118 + ring_i * 42) * breath)
            r_col = (18, 52, 74) if ring_i == 0 else (46, 14, 28)
            pygame.draw.circle(screen, r_col, (cx, cy), r_rad, 2)

        pts_cyan = self._star_points(cx, cy, 132.0 * breath, 24.0 * breath, rot_rad=rot)
        pts_red = self._star_points(cx, cy, 112.0 * breath, 19.0 * breath, rot_rad=-rot * 0.6)
        pts_core = self._star_points(cx, cy, 78.0 * breath, 12.0 * breath, rot_rad=0.0)

        pygame.draw.polygon(screen, (0, 175, 215), pts_cyan)
        pygame.draw.polygon(screen, (215, 34, 62), pts_red)
        pygame.draw.polygon(screen, (7, 8, 15), pts_core)
        pygame.draw.polygon(screen, (150, 235, 255), pts_core, 1)

    def draw(self, screen, has_save=False):
        self.draw_void_background(screen)
        t = self.elapsed

        # 1. Chromatic Dual-Shadow Pixel Title: 'INDIE CROSS' (antialias=False)
        title_cx, title_cy = WIDTH // 2, 222
        red_shadow = self.logo_font.render("INDIE CROSS", False, (230, 46, 77))
        cyan_shadow = self.logo_font.render("INDIE CROSS", False, (0, 216, 255))
        main_logo = self.logo_font.render("INDIE CROSS", False, (255, 255, 255))

        screen.blit(red_shadow, red_shadow.get_rect(center=(title_cx - 5, title_cy + 3)))
        screen.blit(cyan_shadow, cyan_shadow.get_rect(center=(title_cx + 5, title_cy + 3)))
        screen.blit(main_logo, main_logo.get_rect(center=(title_cx, title_cy)))

        # 2. Thin cyan-white gradient horizontal divider line beneath title
        div_y = 292
        half_w = 220
        for step in range(half_w):
            ratio = 1.0 - (step / half_w)
            r_c = int(225 * ratio * ratio)
            g_c = int(245 * ratio)
            b_c = int(255 * ratio)
            if b_c > 8:
                pygame.draw.rect(screen, (r_c, g_c, b_c), (title_cx + step, div_y, 1, 2))
                pygame.draw.rect(screen, (r_c, g_c, b_c), (title_cx - step, div_y, 1, 2))

        # 3. Clean Interactive Menu Options + Rotating Pixel Star Cursor
        for i, label in enumerate(self.OPTIONS):
            rect = self.option_rect(i)
            enabled = self._is_enabled(i, has_save)
            is_sel = (i == self.selected) and enabled
            slide_x = int(round(self.hover_offsets[i]))

            if not enabled:
                col = (88, 92, 112)
            elif is_sel:
                col = (225, 250, 255)
            else:
                col = (165, 175, 198)

            txt_surf = self.option_font.render(label, False, col)
            txt_rect = txt_surf.get_rect(center=(rect.centerx + slide_x, rect.centery))

            if is_sel:
                # Subtle cyan glow shadow behind active text
                glow_surf = self.option_font.render(label, False, (0, 165, 210))
                screen.blit(glow_surf, (txt_rect.x + 2, txt_rect.y + 2))
                # Rotating / pulsing 4-point pixel Star Cursor on the left
                star_cx = txt_rect.left - 24
                star_cy = txt_rect.centery
                star_r = 10.0 + 2.0 * math.sin(t * 6.0)
                star_pts = self._star_points(star_cx, star_cy, star_r, 3.0, rot_rad=t * 2.2)
                pygame.draw.polygon(screen, (0, 216, 255), star_pts)
                pygame.draw.circle(screen, (255, 255, 255), (star_cx, star_cy), 2)

            screen.blit(txt_surf, txt_rect)
