import pygame
import sys
import Player

class Game:
    def __init__(self):
        pygame.init()

        pygame.display.set_caption("Final Project")
        self.screen = pygame.display.set_mode((640, 480))

        self.clock = pygame.time.Clock()

        self.background = pygame.image.load("asset/Legacy-Fantasy - High Forest 2.3/Background/Background.png")

        self.all_sprite = pygame.sprite.Group()

        self.player1 = Player.Player()
        
        self.all_sprite.add(self.player1)


    def run(self):
        while True:
            self.screen.blit(self.background, (100, 100))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.player1.attack()

            self.all_sprite.update()
            self.all_sprite.draw(self.screen)
            self.player1.attack_hitbox(self.all_sprite, self.screen)
            pygame.display.update()

            self.clock.tick(60)
            

Game().run()