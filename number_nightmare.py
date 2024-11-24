from typing import Any, Dict
from hedge_game_instance import HedgeGameInstance
from redis_client import RedisClient
import numpy as np

OPTIONS_SIZE = 5
ROUNDS = 10

class NumberNightmareGameInstance(HedgeGameInstance):
    satisfy_counts: Dict[str, int]

    def __init__(self, instance_id: str, redis_client: RedisClient, deck_size: int=100):
        super().__init__(instance_id, redis_client)
        self.deck_size = deck_size
        self.options = []
        self.satisfy_counts = {}

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played": self.players[player_name].played if self.players[player_name].played is not None else None,
                "satisfy_count": self.satisfy_counts.get(player_name, 0),
            } for player_name in self.players
        }
    
    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        await super().notify_all_players(method, { **data })

    def create_options(self):
        # random options
        self.options = np.random.permutation(self.deck_size).tolist()[:OPTIONS_SIZE]

    async def handle_next(self):
        print("handling next")
        # end game if round_id > ROUNDS
        # send end message with winner, based on points
        if self.round_id > ROUNDS:
            winner = max(self.players, key=lambda x: self.players[x].points)
            await self.notify_all_players("end", {
                "winner": winner
            })
            self.is_active = False
            self.game_state = "lobby"
            return

        self.game_state = "start"

        for player_name in self.players:
            self.players[player_name].is_alive = True

        for player_name in self.get_live_players():
            self.players[player_name].played = None
            self.satisfy_counts[player_name] = 0
            self.players[player_name].acknowledged = False
        
        # let all the calculations happen before notifying
        self.create_options()
        await self.notify_all_players("next", {
            "options": self.options,
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # subtract score if a player has played the most popular card
        played_numbers = [player.played for player in self.players.values()]

        # if a player played a number that someone else played, they lose 3 points
        failed_players = []
        for player_name in self.players:
            if played_numbers.count(self.players[player_name].played) > 1:
                self.players[player_name].points -= 3
                failed_players.append(player_name)
        
        # add points based on satisfy count
        for player_name in self.players:
            self.players[player_name].points += self.satisfy_counts.get(player_name, 0)

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "failed_players": failed_players,
        })

        self.round_id += 1
        print("finished evaluating")