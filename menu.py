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
            elif event.key == pygame.K_RETURN and self.selected >= num_sliders:
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
