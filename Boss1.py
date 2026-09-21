import pygame
from Animator import AnimatedSprite

class Vergil(pygame.sprite.Sprite):
    def __init__(self):

        super().__init__()
        
        self.animation_speed = {
            "Run": 0.2,
            "idle": 0.1,
            "Attack": 0.4
        }
        
        self.is_attacking = False
        self.flip = False
        self.animator = AnimatedSprite()
        self.animator.load_animation("idle", "asset/Vergil/vergil_idle.png", 4, 0.12)
        self.animator.load_animation("Run", "asset/Legacy-Fantasy - High Forest 2.3/Character/Run/Run-Sheet.png", 8, 1.0)
        self.animator.load_animation("Attack", "asset/Legacy-Fantasy - High Forest 2.3/Character/Attack-01/Attack-01-Sheet.png", 8, 1.0)
        
        self.animator.play("idle")
        
        self.image = self.animator.update_get_image(self.animation_speed["idle"])
        self.rect = self.image.get_rect(center = (320, 240))

    def update(self):

        is_moving = False

        new_state = "idle"  

        if self.is_attacking:
            new_state = "Attack"
            if self.animator.current_frames == 0 and self.animator.current_state == "Attack":
                self.is_attacking = False
        elif is_moving:
            new_state = "Run"

        current_fspeed = self.animation_speed[new_state]
        self.animator.play(new_state)
        self.image = self.animator.update_get_image(current_fspeed)

        if self.flip:
            self.image = pygame.transform.flip(self.image, True, False)
