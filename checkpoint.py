import math
import xml.etree.ElementTree as ET
import pygame
from VFX import draw_floating_prompt_box

# 若在 Tiled 使用「點」工具，則自動展開成此大小的觸發區 (底部中央 = 點的位置)
DEFAULT_ZONE_W = 64
DEFAULT_ZONE_H = 128


class Checkpoint:
    """
    存檔點 (Checkpoint)：
    - 玩家靠近進入 interaction_rect 時，於正上方顯示像素浮動小視窗 `[E] 保存並恢復`
    - 玩家按下 E 鍵時：記錄重生點、回滿玩家血量、重置關卡敵人/Boss，並短暫顯示 `已保存並回滿血量！`
    """

    def __init__(self, order, rect, name=""):
        self.order = order
        self.rect = pygame.Rect(rect)
        # 擴展互動感應範圍，讓玩家靠近時即可舒適觸發提示視窗
        self.interaction_rect = self.rect.inflate(48, 24)
        self.name = name or f"Checkpoint {order}"

        self.can_interact = False
        self.activated = False
        self.feedback_timer = 0.0
        self.anim_timer = 0.0

    @property
    def spawn_pos(self):
        """重生座標 (腳底中央)"""
        return self.rect.midbottom

    def update(self, raw_dt, player_rect):
        self.anim_timer += raw_dt
        if self.feedback_timer > 0.0:
            self.feedback_timer = max(0.0, self.feedback_timer - raw_dt)
        self.can_interact = self.interaction_rect.colliderect(player_rect)

    def trigger_save(self):
        """當玩家在範圍內按下 E 鍵時呼叫"""
        self.activated = True
        self.feedback_timer = 1.85

    def draw(self, screen, camera_x, camera_y, font, is_active=False):
        """繪製檢查點像素石碑/靈魂營火與正上方的浮動互動小視窗"""
        bx, by = self.rect.midbottom
        sx = int(round(bx - camera_x))
        sy = int(round(by - camera_y))
        lit = is_active or self.activated

        # 1. 繪製像素風靈魂祭壇底座與石碑
        pygame.draw.rect(screen, (45, 52, 68), (sx - 18, sy - 6, 36, 6))
        pygame.draw.rect(screen, (72, 82, 105), (sx - 14, sy - 10, 28, 4))
        pygame.draw.rect(screen, (55, 64, 84), (sx - 8, sy - 38, 16, 28))
        pygame.draw.polygon(
            screen,
            (72, 82, 105),
            [(sx - 8, sy - 38), (sx + 8, sy - 38), (sx, sy - 48)],
        )

        # 2. 點亮狀態：燃燒翠綠與亮青色像素靈魂火焰
        if lit:
            pulse = int(math.sin(self.anim_timer * 7.0) * 3)
            glow_surf = pygame.Surface((56, 56), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (60, 255, 150, 55), (28, 28), 22 + pulse)
            pygame.draw.circle(glow_surf, (90, 240, 255, 95), (28, 28), 12)
            screen.blit(glow_surf, (sx - 28, sy - 54))

            # 石碑中央發光核心與跳動像素火苗
            pygame.draw.rect(screen, (65, 255, 145), (sx - 3, sy - 32, 6, 16))
            pygame.draw.rect(
                screen, (190, 255, 230), (sx - 2, sy - 30 + (pulse // 2), 4, 10)
            )
        else:
            # 未點亮狀態：暗藍微光核心
            pygame.draw.rect(screen, (65, 110, 155), (sx - 2, sy - 30, 4, 12))

        # 3. 若玩家位於互動範圍內 (或剛完成存檔)，於檢查點正上方繪製浮動小視窗
        if self.can_interact or self.feedback_timer > 0.0:
            prompt_y = self.rect.top - 10
            if self.feedback_timer > 0.0:
                draw_floating_prompt_box(
                    screen,
                    bx,
                    prompt_y,
                    camera_x,
                    camera_y,
                    "SAVED",
                    font,
                    border_color=(75, 255, 145),
                    text_color=(180, 255, 205),
                )
            else:
                draw_floating_prompt_box(
                    screen,
                    bx,
                    prompt_y,
                    camera_x,
                    camera_y,
                    "[E]",
                    font,
                    border_color=(90, 230, 255),
                    text_color=(245, 252, 255),
                )

    def draw_debug(self, screen, camera_x, camera_y, font=None, active=False):
        r = self.rect.move(-camera_x, -camera_y)
        ir = self.interaction_rect.move(-camera_x, -camera_y)
        color = (255, 220, 60) if active else (80, 200, 255)
        pygame.draw.rect(screen, color, r, 2)
        pygame.draw.rect(screen, (60, 255, 140), ir, 1)
        if font is not None:
            label = font.render(f"CP {self.order}", False, color)
            screen.blit(label, (r.x + 4, r.y + 4))


def load_checkpoints(tmx_path, layer_name="checkpoints"):
    """
    直接解析 .tmx (XML)，讀取名為 layer_name 的物件圖層。
    :return: 依 order 排序的 Checkpoint 清單
    """
    try:
        root = ET.parse(tmx_path).getroot()
    except (OSError, ET.ParseError) as e:
        print(f"[檢查點] 無法讀取 {tmx_path}: {e}")
        return []

    found = []
    for group in root.iter("objectgroup"):
        if (group.get("name") or "").strip().lower() != layer_name.lower():
            continue

        off_x = float(group.get("offsetx", 0))
        off_y = float(group.get("offsety", 0))

        for obj in group.findall("object"):
            props = {
                p.get("name"): p.get("value")
                for p in obj.findall("properties/property")
            }
            obj_id = int(obj.get("id", 0))
            x = float(obj.get("x", 0)) + off_x
            y = float(obj.get("y", 0)) + off_y
            w = float(obj.get("width", 0))
            h = float(obj.get("height", 0))

            if w <= 0 or h <= 0:
                rect = pygame.Rect(0, 0, DEFAULT_ZONE_W, DEFAULT_ZONE_H)
                rect.midbottom = (round(x), round(y))
            else:
                rect = pygame.Rect(round(x), round(y), round(w), round(h))

            try:
                order = int(float(props.get("order")))
            except (TypeError, ValueError):
                order = obj_id

            name = obj.get("name") or props.get("name") or ""
            found.append(Checkpoint(order, rect, name))

    found.sort(key=lambda c: c.order)
    print(f"[檢查點] 從 {tmx_path} 載入 {len(found)} 個檢查點")
    return found
