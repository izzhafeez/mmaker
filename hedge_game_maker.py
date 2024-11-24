from typing import Dict
import asyncio

from hedge_game_instance import HedgeGameInstance
from data_hedger import DataHedgerGameInstance
from midpoint_master import MidpointMasterGameInstance
from city_hedger import CityHedgerGameInstance
from number_nightmare import NumberNightmareGameInstance
from redis_client import RedisClient

class HedgeGameMaker():
    game_data: Dict[str, HedgeGameInstance]

    # init
    def __init__(self, redis_client: RedisClient):
        self.game_data = {}
        self.redis_client = redis_client

    async def get_game_data(self, game_type: str, game_id: str, redis_client: RedisClient, deck_size: int = None, mongo_client=None, country: str='', min_lat: float=0, max_lat: float=0, min_lng: float=0, max_lng: float=0):
        instance_id = f'{game_type}-{game_id}'
        if instance_id not in self.game_data:
            if game_type == "data-hedger":
                self.game_data[instance_id] = DataHedgerGameInstance(instance_id, redis_client, deck_size=deck_size)
            elif game_type == "midpoint-master":
                self.game_data[instance_id] = MidpointMasterGameInstance(instance_id, redis_client)
            elif game_type == "city-hedger":
                self.game_data[instance_id] = CityHedgerGameInstance(instance_id, redis_client, mongo_client=mongo_client, country=country, min_lat=min_lat, max_lat=max_lat, min_lng=min_lng, max_lng=max_lng)
            elif game_type == "number-nightmare":
                self.game_data[instance_id] = NumberNightmareGameInstance(instance_id, redis_client, deck_size=deck_size)
            asyncio.create_task(self.game_data[instance_id].start_redis())
        return self.game_data[instance_id]