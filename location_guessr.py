from typing import Any, Dict
import numpy as np
from redis_client import RedisClient
from guess_game_instance import GuessGameInstance

class LocationGuessrGameInstance(GuessGameInstance): 
    def __init__(self, instance_id: str, redis_client: RedisClient, deck_size: int=0, max_distance: float=0):
        super().__init__(instance_id, redis_client)
        self.deck_size = deck_size
        self.max_distance = max_distance
        self.player_distances: Dict[str, float] = {}
        self.target = 0

    def generate_random_target(self):
        self.target = np.random.randint(0, self.deck_size)

    def calculate_distance_in_km(x1: float, y1: float, x2: float, y2: float):
        R = 6371
        x1 = np.radians(x1)
        y1 = np.radians(y1)
        x2 = np.radians(x2)
        y2 = np.radians(y2)
        delta_x = x2 - x1
        delta_y = y2 - y1
        a = np.sin(delta_x/2) * np.sin(delta_x/2) + np.cos(x1) * np.cos(x2) * np.sin(delta_y/2) * np.sin(delta_y/2)
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        return R * c
    
    def get_score_of_guess(self, guess: Any):
        x2, y2 = guess
        distance = LocationGuessrGameInstance.calculate_distance_in_km(self.target_coords[0], self.target_coords[1], x2, y2)
        print(distance, self.max_distance)
        score = 100 - ((distance / self.max_distance) * 100)
        return int(score)
    
    async def handle_play(self, name: str, guess: Any):
        self.target_coords = guess['target_coords']
        self.player_distances[name] = LocationGuessrGameInstance.calculate_distance_in_km(self.target_coords[0], self.target_coords[1], guess['guess'][0], guess['guess'][1])
        await super().handle_play(name, guess['guess'])

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "guess": self.players[player_name].guess,
                "distance": self.player_distances.get(player_name, 0),
                "added_score": self.players[player_name].added_score,
                "acknowledged": self.players[player_name].acknowledged
            } for player_name in self.players
        }