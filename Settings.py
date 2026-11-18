import os
import pygame

WIDTH = 1280
HEIGHT = 720
FPS = 60

# ---------- 像素字體路徑與全域載入器 ----------
PIXEL_FONT_Candidates = (
    "assets/fonts/Uranus_Pixel_11Px.ttf",
    "Uranus_Pixel_11Px.ttf",
)
_FONT_CACHE = {}


def get_pixel_font(size: int) -> pygame.font.Font:
    """
    載入全域點陣像素字體 (支援繁體中文與英文)，並快取不同字級的 Font 實例。
    搭配 font.render(text, False, color) 關閉抗鋸齒以保持銳利像素邊緣。
    """
    size = max(11, int(size))
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    if not pygame.font.get_init():
        pygame.font.init()

    font_obj = None
    for path in PIXEL_FONT_Candidates:
        if os.path.exists(path):
            try:
                font_obj = pygame.font.Font(path, size)
                break
            except Exception:
                pass

    if font_obj is None:
        font_obj = pygame.font.SysFont(None, size)

    _FONT_CACHE[size] = font_obj
    return font_obj


# ---------- 物理與地面設定 ----------
GROUND_Y = 770          # 地圖主要地面基準高度 (對應 map_learning.tmx 的地面層)
GRAVITY = 1500.0        # 重力加速度 (px / s^2)
PLAYER_JUMP_VELOCITY = 620.0  # 固定跳躍初速度 (px / s)，每次起跳高度完全固定
PLAYER_SPEED = 280.0    # 玩家水平移動速度 (px / s)

# ---------- 空中下劈 (Downward Slash / Pogo) 與命中滯空設定 ----------
PLAYER_POGO_VELOCITY = 390.0          # 下劈命中目標後的向上反彈初速度 (px / s)
PLAYER_AIR_STAY_DURATION = 0.28       # 下劈命中後的空中滯留減重力時間 (秒)
PLAYER_AIR_STAY_GRAVITY_SCALE = 0.22  # 空中滯留期間的重力縮放比例
MAX_POGO_BOUNCES = 2                  # 單次滯空期間最多可透過下劈連續彈跳的次數上限

# ---------- 完美格擋、1.5 秒增傷 Buff、鏡頭縮放與子彈時間設定 ----------
PARRY_WINDOW = 0.15           # 完美格擋判定時間窗 (秒)
PARRY_COOLDOWN = 0.20         # 防禦冷卻時間 (秒)
PARRY_BUFF_MULTIPLIER = 1.35  # 完美格擋成功後的攻擊傷害倍率 (1.35x)
PARRY_BUFF_DURATION = 1.50    # 完美格擋增傷 Buff 持續時間 (慢動作結束後完整持續 1.5 秒)
PARRY_ZOOM_SCALE = 1.15       # 完美格擋觸發時的鏡頭放大倍率 (1.15x)
PARRY_ZOOM_RECOVERY_SPEED = 1.8  # 慢動作結束後鏡頭平滑縮回 1.0 倍的速率
BLOCK_DAMAGE_FACTOR = 0.30    # 一般格擋承受傷害比例 (減免 70% 傷害)
BLOCK_KNOCKBACK_SPEED = 260.0 # 一般格擋擊退初速度 (px / s)
PLAYER_IFRAME_DURATION = 0.60 # 玩家受擊後的無敵幀時間 (秒)

HITSTOP_DURATION = 0.08       # 完美格擋觸發瞬間的畫面凍結停頓感 (Unscaled 秒)
BULLET_TIME_SCALE = 0.20      # 完美格擋觸發時的慢動作時間倍率
BULLET_TIME_DURATION = 0.80   # 子彈時間持續真實秒數 (Unscaled Time)
BULLET_TIME_RECOVERY_SPEED = 2.5  # 子彈時間結束後平滑恢復至 1.0 的速率

# ---------- Debug 視覺化顏色設定 ----------
COLOR_DEBUG_HURTBOX = (0, 230, 60)      # 綠色：受擊框 (Hurtbox)
COLOR_DEBUG_HITBOX = (255, 40, 40)      # 紅色：攻擊判定框 (Active Hitbox)
COLOR_DEBUG_PARRY = (0, 220, 255)       # 亮藍/青色：完美格擋判定框
COLOR_DEBUG_BLOCK = (40, 120, 255)      # 深藍色：一般防禦判定框
COLOR_DEBUG_COLLISION = (255, 220, 0)   # 黃色：物理移動碰撞框 (Collision Box)
