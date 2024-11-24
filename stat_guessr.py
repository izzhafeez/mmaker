import numpy as np
from redis_client import RedisClient
from guess_game_instance import GuessGameInstance

class StatGuessrGameInstance(GuessGameInstance):
    def __init__(self, instance_id: str, redis_client: RedisClient, deck_size: int=0, field_size: int=0):
        super().__init__(instance_id, redis_client)
        self.deck_size = deck_size
        self.field_size = field_size
        self.target = {
            "item_id": 0,
            "field_id": 0
        }

    def generate_random_target(self):
        item_id = np.random.randint(0, self.deck_size)
        field_id = np.random.randint(0, self.field_size)
        self.target = {
            "item_id": item_id,
            "field_id": field_id
        }

    def get_score_of_guess(self, guess: float):
        log_diff = np.log2(guess / self.value)

        # assign a score that maxes at 100 and min at 0, based on distance
        score = 100 - min(100, 80 * abs(log_diff))
        return int(score)
    
    async def handle_play(self, name: str, guess: float):
        self.value = guess['value']
        await super().handle_play(name, guess['guess'])