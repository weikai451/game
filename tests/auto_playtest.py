"""
Automated End-to-End QA & Soft-Lock Playtest for INDIE CROSS.
Runs headless (SDL_VIDEODRIVER=dummy, SDL_AUDIODRIVER=dummy), drives the real Game loop,
verifies every mechanic & state machine transition, detects soft-locks, and saves key
screenshots to tests/screenshots/ for visual inspection.
"""
import os
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame
from Game_state import State
from bosses.base_boss import BossState

SHOT_DIR = os.path.join(ROOT, "tests", "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)


def step(game, seconds, dt=1 / 60):
    frames = max(1, int(round(seconds / dt)))
    for _ in range(frames):
        game.handle_events()
        game.update(dt)
        game.draw()


def step_until(game, cond, max_sec, label, dt=1 / 60):
    elapsed = 0.0
    while elapsed < max_sec:
        if cond():
            return elapsed
        game.handle_events()
        game.update(dt)
        game.draw()
        elapsed += dt
    raise AssertionError(
        f"[SOFT-LOCK / TIMEOUT] '{label}' did not complete within {max_sec:.2f}s "
        f"(state={game.state}, map={game.map_name()}, "
        f"boss_state={getattr(game.boss, 'state', None)}, "
        f"player_pos=({game.player.pos_x:.1f},{game.player.pos_y:.1f}), "
        f"rift_active={game.rift_cutscene_active}, rift_stage={game.rift_cutscene_stage})"
    )


def save_shot(game, name):
    path = os.path.join(SHOT_DIR, name)
    pygame.image.save(game.screen, path)
    print(f"  [SHOT] Saved {name}")


def run_all_tests():
    import Main as main_mod

    game = main_mod.Game()
    assert pygame.display.get_caption()[0] == "INDIE CROSS", f"Bad caption: {pygame.display.get_caption()}"
    print("[PASS] 1. Game booted cleanly with caption 'INDIE CROSS'")

    # ---- 1. Main Menu ----
    step(game, 0.35)
    save_shot(game, "01_main_menu.png")
    assert not game.has_saved_checkpoint(), "Should have no checkpoint save initially"

    # Open & close SETTINGS
    game.in_menu_settings = True
    step(game, 0.15)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    step(game, 0.1)
    assert not game.in_menu_settings, "ESC should close Main Menu Settings"

    # Start Game -> Smooth fade-out directly into Stage 1 Tutorial (no Tutorial Prompt popup!)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    step_until(game, lambda: game.state == State.PLAYING and game.is_tutorial, 1.5, "Main Menu fade -> Stage 1 Tutorial")
    print("[PASS] 2. Main Menu, Settings panel & Smooth Fade-out -> Stage 1 Tutorial OK")

    # ---- 2. Tutorial 7 Zones ----
    tm = game.tutorial_manager
    assert tm is not None, "GuidedTutorialManager missing"

    # Zone 1: Jump onto Switch Crystal -> Gate 1 opens
    game.player.teleport(430, 495)
    step_until(game, lambda: tm.gate1_open, 1.0, "Zone 1 SwitchCrystal -> Gate 1")
    assert tm.crystal.activated, "SwitchCrystal should be activated"

    # Zone 2: Q-Dash through LaserBarrier without damage
    game.player.teleport(1070, 640)
    step(game, 0.1)
    hp_before_laser = game.player.player_hp
    game.player.flip = False
    game.player.start_dash()
    step_until(game, lambda: not game.player.is_dashing, 0.5, "Zone 2 Q-Dash finish")
    assert game.player.player_hp == hp_before_laser, "Dash i-frames should phase through LaserBarrier"

    # Zone 3: Slash Training Dummy -> Gate 2 opens
    game.player.teleport(1475, 640)
    game.player.flip = False
    step(game, 0.1)
    for _ in range(6):
        if tm.gate2_open:
            break
        game.player.attack(down_pressed=False)
        step(game, 0.35)
    assert tm.gate2_open, "Zone 3 Training Dummy destruction should open Gate 2"
    step_until(game, lambda: not game.player.is_attacking, 0.8, "Zone 3 attack recovery")

    # Zone 4: Air Pogo on Orb 1 & Orb 2
    game.player.teleport(1860, 540)
    game.player.on_ground = False
    game.player.attack(down_pressed=True)
    step(game, 0.30)
    assert game.player.pogo_bounce_count >= 1, "Zone 4 Downward Slash should trigger Pogo Bounce"

    # Zone 5: Parry Turret bolt hitbox persistence + 2x Perfect Parry -> Gate 3
    game.player.teleport(2360, 544)
    step(game, 0.2)
    # Wait for turret to fire a bolt
    step_until(game, lambda: len(tm.turret.owned_vfx) > 0, 3.0, "Zone 5 ParryTurret fire bolt")
    bolt = tm.turret.owned_vfx[0]
    save_shot(game, "02_tutorial_parry_turret.png")
    # Let bolt fly 1.25s (must NOT lose hitbox early like the old 1.1s double-tick bug!)
    # Move player out of the way briefly to test pure flight persistence
    game.player.teleport(2150, 544)
    step(game, 1.25)
    assert bolt.alive() and bolt.hitbox is not None and bolt.hitbox.active, (
        "ParryBoltVFX hitbox expired prematurely in mid-flight!"
    )

    # Now perform 2 Perfect Parries cleanly
    for parry_idx in range(2):
        tm.turret.clear_owned_attacks()
        tm.turret.state = "CHARGE"
        tm.turret.state_timer = 0.62
        game.player.teleport(2560, 544)
        game.player.flip = False
        step_until(game, lambda: len(tm.turret.owned_vfx) > 0, 0.5, f"Turret bolt #{parry_idx+1}")
        b = tm.turret.owned_vfx[0]
        # Wait until bolt approaches parry_box, then tap block for Perfect Parry
        step_until(game, lambda: b.pos_x <= game.player.pos_x + 48.0, 2.0, f"Bolt #{parry_idx+1} approach")
        game.player.start_block()
        step(game, 0.08)
        game.player.stop_block()
        step(game, 0.45)
    assert tm.gate3_open, f"Zone 5 Gate 3 should open after 2 Perfect Parries (count={tm.turret.parry_count})"

    # Verify post-parry attack cancel does not soft-lock
    game.player.attack(down_pressed=False)
    step_until(game, lambda: not game.player.is_attacking, 1.0, "Post-parry attack recovery")

    # Zone 6: Low-ceiling 304px Spikes pierce Dash + [R] Drink Flask -> Gate 4
    game.player.teleport(2940, 544)
    game.player.flip = False
    step(game, 0.1)
    game.player.start_dash()
    step_until(game, lambda: tm.test_spikes.triggered, 0.6, "Zone 6 TestHazardSpikes trigger through Dash")
    assert game.player.player_hp <= 75, f"Expected HP <= 75 after spike hit, got {game.player.player_hp}"
    step(game, 0.35)
    save_shot(game, "03_tutorial_flask_tunnel.png")

    # Drink flask on ground ([R])
    game.player.teleport(3350, 544)
    step(game, 0.1)
    hp_pre_flask = game.player.player_hp
    game.player.start_drink_flask()
    assert game.player.is_drinking, "Player should enter standing drink lock"
    step_until(game, lambda: not game.player.is_drinking, 1.3, "Zone 6 Flask drink unlock")
    assert game.player.player_hp == min(game.player.max_hp, hp_pre_flask + 20), "Flask should heal +20 HP"
    assert tm.gate4_open, "Zone 6 Gate 4 should open after drinking Flask"

    # Zone 7: Defeat 2 Slimers -> Gate 5 -> Checkpoint Refill -> Invisible Rift Cutscene
    for s in (tm.slimer_1, tm.slimer_2):
        while s.alive():
            s.take_damage(20)
    step_until(game, lambda: tm.gate5_open, 0.5, "Zone 7 Dual Slimers -> Gate 5")

    # Checkpoint [E] refills HP & 3 Flasks
    game.player.teleport(4388, 544)
    step(game, 0.1)
    game.handle_interact_key()
    assert game.player.flasks == 3 and game.player.player_hp == 100, "Checkpoint should refill HP & 3 Flasks"

    # Trigger invisible Indie Cross Rift Cutscene at x >= 4620
    game.player.teleport(4635, 544)
    step_until(game, lambda: game.rift_cutscene_active, 0.5, "Zone 7 Invisible Rift trigger")
    step_until(game, lambda: not game.rift_cutscene_active and game.is_main_world(), 6.5, "5.2s Indie Cross Rift -> main_world")
    print("[PASS] 3. All 7 Tutorial Zones, ParryBolt persistence, Flask Tunnel & 5.2s Rift Cutscene OK")

    # ---- 3. Main World Checkpoint Enemy Persistence + Sans 3-Phase & Death ----
    step(game, 0.3)
    assert len(game.regular_enemies) == 4, f"Expected 4 Outpost Slimers, got {len(game.regular_enemies)}"
    # Defeat first 2 Slimers & save at Checkpoint 1
    mobs = list(game.regular_enemies)
    for m in mobs[:2]:
        m.kill()
    game.player.teleport(1188, 640)
    step(game, 0.1)
    game.handle_interact_key()
    assert len(game.saved_cleared_enemies.get("main_world.tmx", ())) == 2, "Should persist 2 cleared Slimers on save"
    # Simulate respawn -> only 2 remaining Slimers should spawn!
    game.respawn_regular_enemies()
    assert len(game.regular_enemies) == 2, f"Saved cleared Slimers should NOT resurrect (got {len(game.regular_enemies)})"
    print("[PASS] 4. Checkpoint enemy persistence verified (2 saved-cleared Slimers stayed dead)")

    # Walk to peaceful Sans & press [E] Talk
    sans = game.boss
    assert sans is not None and sans.waiting_for_dialogue, "Sans should spawn peacefully waiting"
    game.player.teleport(3000, 656)
    step(game, 0.1)
    assert sans.can_talk(game.player), "Player should be in [E] Talk range of Sans"
    game.handle_interact_key()
    assert game.dialogue_box.active, "Pressing [E] near Sans should open Pre-Boss Dialogue"

    # Advance through all 4 Undertale dialogue lines
    for _ in range(12):
        if not game.dialogue_box.active:
            break
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        step(game, 0.12)
    assert not game.dialogue_box.active, "Dialogue should close cleanly"
    assert sans.state == BossState.INTRO, f"Sans should enter INTRO after dialogue, got {sans.state}"

    # Complete Sans 4.0s INTRO + Title Card
    step_until(game, lambda: sans.state != BossState.INTRO, 5.2, "Sans INTRO + Title Card")
    assert sans.max_stamina == 30, f"Sans max_stamina should be 30, got {sans.max_stamina}"

    # Trigger Sans Phase 2 (stamina <= 20) -> ATTACK_6 Chain Teleport Bone Assault
    sans.stamina = 20
    step(game, 0.25)
    assert sans.teleport_phase_unlocked and sans.state == BossState.ATTACK_6, (
        f"Sans should enter Phase 2 ATTACK_6 at stamina=20 (state={sans.state})"
    )
    save_shot(game, "04_sans_phase2_combat.png")
    # Let full Chain Teleport Bone Assault run (tests GroundBoneTrapVFX + blink blackout!)
    step_until(game, lambda: sans.state != BossState.ATTACK_6, 5.0, "Sans ATTACK_6 Chain Teleport completion")

    # Test Sans Telekinesis Slam stays inside Judgement Hall [2160, 3580]
    sans.change_state(BossState.ATTACK_4)
    step(game, 0.65)
    assert 2160.0 <= game.player.pos_x <= 3580.0, f"Telekinesis teleported player out of arena! x={game.player.pos_x}"

    # Trigger Sans Phase 3 (stamina <= 10) -> 360° Gaster Blaster Ultimate
    sans.stamina = 10
    step(game, 0.15)
    assert sans.phase == 3 and sans.phase2_triggered, f"Sans should reach Phase 3 at stamina=10 (phase={sans.phase})"
    step_until(game, lambda: sans.state == BossState.SANS_ULTIMATE, 1.5, "Sans Phase 3 -> SANS_ULTIMATE")
    step(game, 0.6)
    save_shot(game, "05_sans_phase3_hud.png")

    # Fatal hit on Sans -> DYING Cutscene (9999999 + Grillby's + fade-out) -> boss_defeated['sans']
    sans.stamina = 0
    sans.invincible = False
    sans.hit_invuln_timer = 0.0
    sans.take_damage(12)
    assert sans.state == BossState.DYING, f"Sans should enter DYING on fatal blow, got {sans.state}"
    step_until(game, lambda: game.boss_defeated.get("sans", False), 6.5, "Sans 5.0s DYING Cutscene")
    print("[PASS] 5. Sans [E] Talk, 3 Phases (30/20/10), Chain Teleport, Telekinesis Clamp & DYING Cutscene OK")

    # ---- 4. Vergil Arena (Title Card, 3-Phase Progression & DYING Cutscene) ----
    game.new_game(map_path="map/boss1_arena.tmx", is_tutorial=False, keep_progress=True)
    vergil = game.boss
    assert vergil is not None and vergil.state == BossState.INTRO, "Vergil should spawn in INTRO"
    step_until(game, lambda: getattr(vergil, "title_card_active", False), 2.5, "Vergil INTRO -> Title Card")
    step(game, 0.95)
    save_shot(game, "06_vergil_title_card.png")
    step_until(game, lambda: vergil.state != BossState.INTRO, 2.5, "Vergil Title Card finish")

    # Phase 2 (hp <= 133) -> Rapid Trick Slash & Mirage Blades
    vergil.hp = 130.0
    step(game, 0.15)
    assert vergil.phase == 2 and vergil.state == BossState.ATTACK_7, (
        f"Vergil should enter Phase 2 ATTACK_7 at hp=130 (phase={vergil.phase}, state={vergil.state})"
    )
    step(game, 1.5)

    # Phase 3 (hp <= 66) -> Sin Devil Trigger Aura + Judgement Cut End
    vergil.hp = 60.0
    step(game, 0.15)
    assert vergil.phase == 3 and vergil.phase3_triggered, f"Vergil should enter Phase 3 at hp=60 (phase={vergil.phase})"
    step_until(game, lambda: vergil.state == BossState.JUDGEMENT_CUT_END, 1.5, "Vergil Phase 3 -> JUDGEMENT_CUT_END")
    step(game, 1.3)
    save_shot(game, "07_vergil_phase3_hud.png")

    # Fatal hit on Vergil -> DYING Cutscene (kneel + sheathe + walk into blue-violet rift)
    vergil.invincible = False
    vergil.hit_invuln_timer = 0.0
    vergil.take_damage(100)
    assert vergil.state == BossState.DYING, f"Vergil should enter DYING on fatal blow, got {vergil.state}"
    step_until(game, lambda: game.boss_defeated.get("vergil", False), 6.0, "Vergil 4.4s DYING Cutscene")
    step_until(game, lambda: game.state == State.ENDING, 3.0, "Post-Vergil 2.0s -> State.ENDING ('THE END')")
    save_shot(game, "08_ending_screen.png")
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    step(game, 0.1)
    assert game.state == State.MENU, f"Pressing ENTER on THE END should return to MENU (got {game.state})"
    print("[PASS] 6. Vergil Dimension-Slash Title Card, 3 Phases, DYING Cutscene & THE END Screen OK")

    pygame.quit()
    print("\n=== ALL AUTOMATED PLAYTEST CHECKS PASSED (ZERO CRASHES / ZERO SOFT-LOCKS) ===")


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception:
        traceback.print_exc()
        pygame.quit()
        sys.exit(1)
