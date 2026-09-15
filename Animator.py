import pygame

class AnimatedSprite:
    def __init__(self):

        self.animation = {}
        self.current_state = ""
        self.current_frames = 0

        self.animation_speed = {
            "Run": 0.2,
            "idle": 0.1,
            "Attack": 0.4
        }


    def load_animation(self, state_name, sheet_path, total_frames):

        sprite_sheet = pygame.image.load(sheet_path)
        frames = []

        frame_width = (sprite_sheet.get_width() // total_frames)
        total_height = sprite_sheet.get_height()

        for i in range(total_frames):
            crop_x = i * frame_width
            crop_y = 0

            rect = pygame.Rect(crop_x, crop_y, frame_width, total_height)
            frames.append(sprite_sheet.subsurface(rect))

        self.animation[state_name] = frames

    def play(self, state_name):

        if self.current_state != state_name:
            self.current_state = state_name
            self.current_frames = 0


    
    def update_get_image(self):

        current_list = self.animation[self.current_state]
        self.current_frames += self.animation_speed[self.current_state]

        if self.current_frames >= len(current_list):
            self.current_frames = 0

        return current_list[int(self.current_frames)]

        
            

        