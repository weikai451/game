import pygame
from Settings import WIDTH, HEIGHT, get_pixel_font


class Menu:
    """可以用鍵盤或滑鼠選擇的選單（主選單、暫停選單都能用），全文字採用點陣像素字體"""

    def __init__(self, title, options, fill_background=True):
        self.title = title
        self.fill_background = fill_background
        self.options = options
        self.selected = 0

        self.title_font = get_pixel_font(66)
        self.option_font = get_pixel_font(33)

        self.color_normal = (180, 180, 190)
        self.color_selected = (255, 220, 100)

    def option_rect(self, i):
        """第 i 個選項的按鈕範圍"""
        w, h = 340, 60
        x = (WIDTH - w) // 2
        y = 330 + i * 80
        return pygame.Rect(x, y, w, h)

    def handle_event(self, event):
        """處理輸入。選定某個選項時回傳它的名字，否則回傳 None"""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self.options)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(self.options)
            elif event.key == pygame.K_RETURN:
                return self.options[self.selected]

        elif event.type == pygame.MOUSEMOTION:
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    self.selected = i

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    return self.options[i]

        return None

    def draw(self, screen):
        if self.fill_background:
            screen.fill((20, 20, 40))

        # 關閉抗鋸齒 (antialias=False) 保持銳利像素字體邊緣
        title_img = self.title_font.render(self.title, False, (255, 255, 255))
        screen.blit(title_img, title_img.get_rect(center=(WIDTH // 2, 200)))

        for i, text in enumerate(self.options):
            rect = self.option_rect(i)
            if i == self.selected:
                color = self.color_selected
                pygame.draw.rect(screen, (60, 60, 90), rect, border_radius=12)
                pygame.draw.rect(screen, color, rect, 3, border_radius=12)
            else:
                color = self.color_normal
            img = self.option_font.render(text, False, color)
            screen.blit(img, img.get_rect(center=rect.center))
