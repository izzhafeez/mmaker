import numpy as np
from redis_client import RedisClient
from guess_game_instance import GuessGameInstance

class BlurryBattleGameInstance(GuessGameInstance):
    def __init__(self, instance_id: str, redis_client: RedisClient, deck_size: int=0):
        super().__init__(instance_id, redis_client)
        self.deck_size = deck_size

    def generate_random_target(self):
        self.target = np.random.randint(0, self.deck_size)

    def get_score_of_guess(self, guess: str):
        # if exact match, return 1
        if self.answer == guess:
            return 1.5
        # if not, assign score based on jacard similarity
        answer_letter_set = set(self.answer)
        guess_letter_set = set(guess)
        intersection = answer_letter_set.intersection(guess_letter_set)
        union = answer_letter_set.union(guess_letter_set)
        score = len(intersection) / len(union)
        return round(score, 2)
    
    async def handle_play(self, name: str, guess: float):
        self.answer = guess['answer']
        await super().handle_play(name, guess['guess'])