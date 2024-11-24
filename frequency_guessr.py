import numpy as np
from guess_game_instance import GuessGameInstance

class FrequencyGameInstance(GuessGameInstance):
    def generate_random_target(self):
        note = np.random.random_sample() * 58 + 20
        self.target = int(440 * 2 ** ((note - 49) / 12))

    def get_score_of_guess(self, guess: int):
        log_diff = np.log2(guess / self.target)

        # assign a score that maxes at 100 and min at 0, based on distance
        score = 100 - min(100, 80 * abs(log_diff))
        return int(score)