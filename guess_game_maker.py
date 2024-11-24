from typing import Dict
import asyncio

from guess_game_instance import GuessGameInstance
from frequency_guessr import FrequencyGameInstance
from color_guessr import ColorGuessrGameInstance
from blurry_battle import BlurryBattleGameInstance
from stat_guessr import StatGuessrGameInstance
from location_guessr import LocationGuessrGameInstance
from redis_client import RedisClient

class GuessGameMaker():
    game_data: Dict[str, GuessGameInstance]

    # init
    def __init__(self, redis_client: RedisClient):
        self.game_data = {}
        self.redis_client = redis_client

    async def get_game_data(self, game_type: str, game_id: str, redis_client: RedisClient, deck_size: int = None, field_size: int = None, max_distance: float = None):
        instance_id = f'{game_type}-{game_id}'
        if instance_id not in self.game_data:
            if game_type == "frequency-guessr":
                self.game_data[instance_id] = FrequencyGameInstance(instance_id, redis_client)
            elif game_type == "color-guessr":
                self.game_data[instance_id] = ColorGuessrGameInstance(instance_id, redis_client)
            elif game_type == "blurry-battle":
                self.game_data[instance_id] = BlurryBattleGameInstance(instance_id, redis_client, deck_size=deck_size)
            elif game_type == "stat-guessr":
                self.game_data[instance_id] = StatGuessrGameInstance(instance_id, redis_client, deck_size=deck_size, field_size=field_size)
            elif game_type == "location-guessr":
                self.game_data[instance_id] = LocationGuessrGameInstance(instance_id, redis_client, deck_size=deck_size, max_distance=max_distance)
            asyncio.create_task(self.game_data[instance_id].start_redis())
        return self.game_data[instance_id]