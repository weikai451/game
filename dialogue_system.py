import os
import pygame
from Settings import WIDTH, HEIGHT, get_pixel_font
from audio_manager import get_audio


class DialogueBox:
    """
    Undertale-Style Pre-Boss Pixel Dialogue Box:
    - Classic black box with crisp 4px white pixel border anchored at bottom-center.
    - Left-side Sans pixel portrait (cached once from assets/sprites/sans/sans_idle.png).
    - Typewriter character-by-character reveal with low retro `sans_blip` voice SFX.
    - Press SPACE / ENTER / Left Click to complete current line or advance to next line.
    """

    def __init__(self):
        self.active = False
        self.lines = []
        self.line_index = 0
        self.char_progress = 0.0
        self.chars_per_sec = 32.0
        self._last_char_count = 0
        self.on_complete = None

        self.font = get_pixel_font(22)
        self.hint_font = get_pixel_font(15)
        self.portrait = self._load_sans_portrait()

    def _load_sans_portrait(self):
        path = os.path.join("assets", "sprites", "sans", "sans_idle.png")
        if os.path.exists(path):
            try:
                sheet = pygame.image.load(path).convert_alpha()
                fw = sheet.get_width() // 4
                fh = sheet.get_height()
                head = sheet.subsurface(pygame.Rect(0, 0, fw, min(fh, int(fh * 0.58)))).copy()
                return pygame.transform.scale(head, (84, 62))
            except Exception:
                pass
        return None

    def start(self, lines, on_complete=None):
        self.lines = list(lines)
        self.line_index = 0
        self.char_progress = 0.0
        self._last_char_count = 0
        self.on_complete = on_complete
        self.active = bool(self.lines)

    def _current_line(self):
        if 0 <= self.line_index < len(self.lines):
            return self.lines[self.line_index]
        return ""

    def advance(self):
        """Instant-complete the current line, or advance to the next line / close."""
        if not self.active:
            return
        line = self._current_line()
        if int(self.char_progress) < len(line):
            self.char_progress = float(len(line))
            self._last_char_count = len(line)
            return

        self.line_index += 1
        if self.line_index >= len(self.lines):
            self.active = False
            cb = self.on_complete
            self.on_complete = None
            if cb is not None:
                cb()
        else:
            self.char_progress = 0.0
            self._last_char_count = 0

    def handle_event(self, event):
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_SPACE,
            pygame.K_RETURN,
            pygame.K_e,
        ):
            self.advance()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.advance()
            return True
        return False

    def update(self, raw_dt):
        if not self.active:
            return
        line = self._current_line()
        if int(self.char_progress) < len(line):
            self.char_progress = min(
                float(len(line)), self.char_progress + self.chars_per_sec * raw_dt
            )
            cur_count = int(self.char_progress)
            if cur_count > self._last_char_count:
                ch = line[cur_count - 1]
                if ch not in (" ", "*", "."):
                    get_audio().play_sfx("sans_blip")
                self._last_char_count = cur_count

    def draw(self, screen):
        if not self.active:
            return
        box_w = WIDTH - 220
        box_h = 156
        box_x = (WIDTH - box_w) // 2
        box_y = HEIGHT - box_h - 36

        pygame.draw.rect(screen, (0, 0, 0), (box_x, box_y, box_w, box_h))
        pygame.draw.rect(screen, (255, 255, 255), (box_x, box_y, box_w, box_h), 4)

        text_x = box_x + 28
        if self.portrait is not None:
            p_rect = self.portrait.get_rect(center=(box_x + 74, box_y + box_h // 2))
            pygame.draw.rect(
                screen, (18, 22, 34), (box_x + 20, box_y + 24, 108, box_h - 48)
            )
            pygame.draw.rect(
                screen, (220, 230, 245), (box_x + 20, box_y + 24, 108, box_h - 48), 2
            )
            screen.blit(self.portrait, p_rect)
            text_x = box_x + 152

        line = self._current_line()
        visible = line[: int(self.char_progress)]
        # Highlight the final iconic line in crisp red-tinted white if it's the last line
        is_last = self.line_index == len(self.lines) - 1
        text_col = (255, 235, 235) if is_last else (255, 255, 255)
        txt_surf = self.font.render(visible, False, text_col)
        screen.blit(txt_surf, (text_x, box_y + 48))

        if int(self.char_progress) >= len(line):
            blink = (pygame.time.get_ticks() // 380) % 2 == 0
            if blink:
                hint = self.hint_font.render(
                    "[SPACE / ENTER / Click] Continue >>", False, (190, 225, 255)
                )
                screen.blit(
                    hint, (box_x + box_w - hint.get_width() - 22, box_y + box_h - 32)
                )
