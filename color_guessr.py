import numpy as np

from guess_game_instance import GuessGameInstance

class ColorGuessrGameInstance(GuessGameInstance):
    def generate_random_target(self):
        # random red value
        red = np.random.randint(0, 256)
        red_as_hex = hex(red)[2:]
        if len(red_as_hex) == 1:
            red_as_hex = f"0{red_as_hex}"
        # random green value
        green = np.random.randint(0, 256)
        green_as_hex = hex(green)[2:]
        if len(green_as_hex) == 1:
            green_as_hex = f"0{green_as_hex}"

        # random blue value
        blue = np.random.randint(0, 256)
        blue_as_hex = hex(blue)[2:]
        if len(blue_as_hex) == 1:
            blue_as_hex = f"0{blue_as_hex}"

        self.target = f"{red_as_hex}{green_as_hex}{blue_as_hex}"

    def get_score_of_guess(self, guess: str):
        red = int(guess[:2], 16)
        green = int(guess[2:4], 16)
        blue = int(guess[4:], 16)
        correct_red = int(self.target[:2], 16)
        correct_green = int(self.target[2:4], 16)
        correct_blue = int(self.target[4:], 16)
        distance = np.sqrt((red - correct_red) ** 2 + (green - correct_green) ** 2 + (blue - correct_blue) ** 2)

        # assign a score that maxes at 100 and min at 0, based on distance
        score = 100 - distance / (256 * np.sqrt(3)) * 100
        return int(score)