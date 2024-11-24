import asyncio
from typing import Dict, Any
from abc import abstractmethod
import numpy as np
from redis_client import RedisClient
from game_instance import GameInstance, GamePlayer

class GuessGamePlayer(GamePlayer):
    guess: Any
    added_score: int
    points: int
    acknowledged: bool

    # init
    def __init__(self):
        super().__init__()
        self.guess = None
        self.added_score = 0
        self.points = 0
        self.acknowledged = False

ROUNDS = 10

class GuessGameInstance(GameInstance):
    target: Any
    players: Dict[str, GuessGamePlayer]

    # init
    def __init__(self, instance_id: str, redis_client: RedisClient):
        super().__init__(instance_id, redis_client)
        self.target = None

    # create a random target
    @abstractmethod
    def generate_random_target(self):
        pass
    
    @abstractmethod
    def get_score_of_guess(self, guess: Any):
        pass

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "guess": self.players[player_name].guess if self.players[player_name].guess is not None else None,
                "added_score": self.players[player_name].added_score if self.players[player_name].added_score is not None else None,
                "acknowledged": self.players[player_name].acknowledged
            } for player_name in self.players
        }
    
    def get_live_players(self):
        return [player_name for player_name in self.players if self.players[player_name].is_alive]

    async def handle_redis_message(self, data: Dict[str, Any]):
        print(f"handling redis message: {data}")
        print('players', self.players, self.websocket_connections)
        method = data["method"]

        if method == "join":
            await self.handle_join(data["name"])

        elif method == "leave":
            await self.handle_leave(data["name"])

        elif method == "start":
            await self.handle_start(data["seed"])

        elif method == "play":
            await self.handle_play(data["name"], data["guess"])

        elif method == "acknowledge":
            await self.handle_acknowledge(data["name"])

    async def handle_join(self, player_name: str):
        self.players[player_name] = GuessGamePlayer()
        await self.notify_all_players("join", {
            "name": player_name
        })

    async def handle_play(self, name: str, guess: Any):
        self.players[name].guess = guess
        await self.notify_all_players("play", {})

        if all(self.players[player_name].guess is not None for player_name in self.get_live_players()):
            await self.handle_evaluate()

    async def handle_acknowledge(self, name: str):
        self.players[name].acknowledged = True
        await self.notify_all_players("acknowledge", {})

        if all(self.players[player_name].acknowledged for player_name in self.get_live_players()):
            await self.handle_next()

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        await super().notify_player(player_name, method, { "target": self.target, **data })

    async def handle_leave(self, player_name: str):
        if player_name not in self.players:
            return
        
        self.players.pop(player_name)
        await self.notify_all_players("leave", {
            "name": player_name,
        })

        if self.game_state == "start":
            if all(self.players[player_name].guess is not None for player_name in self.get_live_players()):
                await self.handle_evaluate()

        elif self.game_state == "evaluate":
            if all(self.players[player_name].acknowledged for player_name in self.get_live_players()):
                await self.handle_next()

        if len(self.players) == 0:
            self.__init__(self.instance_id, self.redis_client)

    async def handle_start(self, seed: float):
        self.is_active = True
        self.round_id = 1
        np.random.seed(seed)

        # reset all player points
        for player_name in self.players:
            self.players[player_name].points = 0
            self.players[player_name].is_alive = True

        # wait a while before handle next
        await asyncio.sleep(1)
        await self.handle_next()

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
        
        for player_name in self.players:
            self.players[player_name].is_alive = True

        self.game_state = "start"

        for player_name in self.get_live_players():
            self.players[player_name].guess = None
            self.players[player_name].added_score = None
            self.players[player_name].acknowledged = False
        
        # let all the calculations happen before notifying
        self.generate_random_target()
        await self.notify_all_players("next", {})
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # evaluate the points of each player
        for player_name in self.get_live_players():
            guess = self.players[player_name].guess
            if guess is None:
                continue
            score = self.get_score_of_guess(guess)
            self.players[player_name].points += score
            self.players[player_name].added_score = score

        await self.notify_all_players("evaluate", {})

        self.round_id += 1
        print("finished evaluating")