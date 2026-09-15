import pygame
from Animator import AnimatedSprite

class Player(pygame.sprite.Sprite):
    def __init__(self):

        super().__init__()

        self.player_speed = 5
        self.player_hp = 100
        self.player_stamina = 100

        self.is_attacking = False
        self.animator = AnimatedSprite()
        self.animator.load_animation("idle", "asset/Legacy-Fantasy - High Forest 2.3/Character/Idle/Idle-Sheet.png", 4)
        self.animator.load_animation("Run", "asset/Legacy-Fantasy - High Forest 2.3/Character/Run/Run-Sheet.png", 8)
        self.animator.load_animation("Attack", "asset/Legacy-Fantasy - High Forest 2.3/Character/Attack-01/Attack-01-Sheet.png", 8)

        self.animator.play("idle")

        self.image = self.animator.update_get_image()
        self.rect = self.image.get_rect(center = (320, 240))


    def attack(self):

        if not self.is_attacking:
            self.is_attacking = True


    def update(self):

        keys = pygame.key.get_pressed()

        is_moving = False



        if keys[pygame.K_w] or keys[pygame.K_s] or keys[pygame.K_a] or keys[pygame.K_d]:
            is_moving = True
            if keys[pygame.K_w]: self.rect.y -= self.player_speed
            if keys[pygame.K_s]: self.rect.y += self.player_speed
            if keys[pygame.K_a]: self.rect.x -= self.player_speed
            if keys[pygame.K_d]: self.rect.x += self.player_speed

        new_state = "idle"

        if self.is_attacking:
            new_state = "Attack"
            attack_length = len(self.animator.animation["Attack"])

            if self.animator.current_frames >= attack_length - 0.25:
                self.is_attacking = False
        elif is_moving:
            new_state = "Run"

        self.animator.play(new_state)
        self.image = self.animator.update_get_image()

                