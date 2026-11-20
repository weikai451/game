import os
import pygame


class AudioManager:
    """
    Centralized Combat, Environment & UI Audio Manager:
    - Loads all 29 SFX from `assets/audio/` with calibrated volumes and per-SFX
      anti-overlap throttling (min_interval_ms) to prevent clipping/distortion.
    - Plays SF6-style 3-layer Perfect Parry SFX unaffected by game time_scale.
    - Manages looping Boss BGM (`sans_theme.ogg` / `.mp3` / `.wav`) with smooth fadeout.
    """

    # (volume, min_interval_ms)
    SFX_CONFIG = {
        # Combat & Parry
        "slash": (0.45, 70),
        "down_slash": (0.50, 70),
        "hit": (0.56, 60),
        "block": (0.65, 80),
        "perfect_parry": (0.92, 120),
        # Player Movement & Damage
        "footstep": (0.28, 230),
        "jump": (0.42, 90),
        "land": (0.45, 110),
        "pogo_bounce": (0.68, 90),
        "player_hurt": (0.62, 120),
        "player_death": (0.78, 400),
        # Slimer
        "slime_hop": (0.36, 220),
        "slime_hit": (0.52, 80),
        "slime_death": (0.64, 100),
        # Sans
        "encounter": (0.62, 200),
        "bone_shoot": (0.42, 90),
        "blaster_charge": (0.50, 180),
        "blaster_fire": (0.68, 180),
        "blue_soul_slam": (0.66, 200),
        "sans_dodge": (0.58, 120),
        # Vergil
        "sheathe": (0.74, 150),
        "vergil_teleport": (0.58, 140),
        "yamato_slash": (0.60, 90),
        "mirage_blade": (0.46, 85),
        "jce_shatter": (0.86, 250),
        # UI & World
        "prompt_pop": (0.32, 320),
        "checkpoint_heal": (0.68, 250),
        "portal_warp": (0.68, 300),
        "level_clear": (0.72, 350),
    }

    def __init__(self, audio_dir="assets/audio"):
        self.audio_dir = audio_dir
        self.enabled = False
        self.sounds = {}
        self._last_play_ms = {}
        self.current_bgm = None
        self._current_bgm_base_vol = 0.40

        # Independent Volume Channels (0.0 .. 1.0), adjustable live from ESC Pause Menu
        self.master_volume = 1.0
        self.bgm_volume = 1.0
        self.sfx_volume = 1.0

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(24)
            self.enabled = True
            self._load_all_sfx()
        except Exception as exc:
            print(f"[AudioManager] Mixer unavailable ({exc}); running muted.")
            self.enabled = False

    def get_channel_volume(self, channel: str) -> float:
        if channel == "master":
            return self.master_volume
        if channel == "bgm":
            return self.bgm_volume
        if channel == "sfx":
            return self.sfx_volume
        return 1.0

    def set_channel_volume(self, channel: str, value: float):
        clamped = round(max(0.0, min(1.0, float(value))), 2)
        if channel == "master":
            self.master_volume = clamped
        elif channel == "bgm":
            self.bgm_volume = clamped
        elif channel == "sfx":
            self.sfx_volume = clamped
        self.apply_volumes()

    def apply_volumes(self):
        """Immediately apply Master * BGM / Master * SFX multipliers to live audio."""
        if not self.enabled:
            return
        sfx_mult = self.master_volume * self.sfx_volume
        for name, snd in self.sounds.items():
            base_vol = self.SFX_CONFIG.get(name, (0.5, 50))[0]
            snd.set_volume(max(0.0, min(1.0, base_vol * sfx_mult)))
        try:
            bgm_vol = max(
                0.0, min(1.0, self._current_bgm_base_vol * self.master_volume * self.bgm_volume)
            )
            pygame.mixer.music.set_volume(bgm_vol)
        except Exception:
            pass

    def _load_all_sfx(self):
        for name, (vol, _) in self.SFX_CONFIG.items():
            for ext in (".wav", ".ogg"):
                path = os.path.join(self.audio_dir, f"{name}{ext}")
                if os.path.exists(path):
                    try:
                        snd = pygame.mixer.Sound(path)
                        snd.set_volume(vol * self.master_volume * self.sfx_volume)
                        self.sounds[name] = snd
                        break
                    except Exception as exc:
                        print(f"[AudioManager] Failed loading {path}: {exc}")

    def play_sfx(self, name: str):
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        now_ms = pygame.time.get_ticks()
        _, min_interval = self.SFX_CONFIG.get(name, (0.5, 50))
        last_ms = self._last_play_ms.get(name, -9999)
        if now_ms - last_ms < min_interval:
            return
        self._last_play_ms[name] = now_ms
        snd.play()

    def _resolve_bgm_path(self, track_name: str):
        for ext in (".ogg", ".mp3", ".wav"):
            path = os.path.join(self.audio_dir, f"{track_name}{ext}")
            if os.path.exists(path):
                return path
        return None

    def play_bgm(self, track_name="sans_theme", volume=0.40, loops=-1):
        """Start looping BGM if not already playing this track."""
        if not self.enabled:
            return
        if self.current_bgm == track_name and pygame.mixer.music.get_busy():
            return
        path = self._resolve_bgm_path(track_name)
        if path is None:
            return
        try:
            self._current_bgm_base_vol = float(volume)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(
                max(0.0, min(1.0, self._current_bgm_base_vol * self.master_volume * self.bgm_volume))
            )
            pygame.mixer.music.play(loops=loops)
            self.current_bgm = track_name
            print(f"[AudioManager] Playing BGM: {path} (base_vol={volume:.2f})")
        except Exception as exc:
            print(f"[AudioManager] Failed playing BGM {path}: {exc}")

    def stop_bgm(self, fadeout_ms=900):
        """Smoothly fade out and stop any active BGM."""
        if not self.enabled:
            return
        if self.current_bgm is not None or pygame.mixer.music.get_busy():
            try:
                if fadeout_ms > 0:
                    pygame.mixer.music.fadeout(fadeout_ms)
                else:
                    pygame.mixer.music.stop()
            except Exception:
                pass
        self.current_bgm = None


_AUDIO_INSTANCE = None


def get_audio() -> AudioManager:
    global _AUDIO_INSTANCE
    if _AUDIO_INSTANCE is None:
        _AUDIO_INSTANCE = AudioManager()
    return _AUDIO_INSTANCE
