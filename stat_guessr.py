import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

class StatPlayerData():
    websocket: WebSocket
    guess: float
    added_score: int
    points: int
    acknowledged: bool
    is_alive: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.guess = None
        self.points = 0
        self.added_score = 0
        self.acknowledged = False
        self.is_alive = False

ROUNDS = 10

class StatGameData():
    players: Dict[str, StatPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    item_count: int
    field_count: int
    item: int
    field: int
    value: int

    # init
    def __init__(self):
        self.players = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.item_count = None
        self.field_count = None
        self.item_id = None
        self.field_id = None
        self.value = None

    def select_random_item_and_field(self):
        self.item_id = np.random.randint(0, self.item_count)
        self.field_id = np.random.randint(0, self.field_count)

    def get_score_of_value(self, value: float):
        log_diff = np.log2(value / self.value)

        # assign a score that maxes at 100 and min at 0, based on distance
        score = 100 - min(100, 80 * abs(log_diff))
        return int(score)

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

    async def handle_client(self, websocket: WebSocket):
        data = {}
        try:
            while True:
                data = await websocket.receive_json()
                method = data["method"]

                if method == "join":
                    self.item_count = data["item_count"]
                    self.field_count = data["field_count"]
                    player_name = data["name"]
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    await self.handle_start()

                elif method == "play":
                    self.value = data["value"]
                    guess = data["guess"]
                    player_name = data["name"]
                    print(f"{player_name} played {guess}")

                    self.players[player_name].guess = guess

                    await self.notify_all_players("play", {})

                    if all(self.players[player_name].guess is not None for player_name in self.get_live_players()):
                        await self.handle_evaluate()

                elif method == "acknowledge":
                    print("acknowledged")
                    player_name = data["name"]
                    self.players[player_name].acknowledged = True

                    await self.notify_all_players("acknowledge", {})

                    if all(self.players[player_name].acknowledged for player_name in self.get_live_players()):
                        await self.handle_next()

        except WebSocketDisconnect as e:
            player_name = data.get('name', '')
            if player_name:
                print(f"handling disconnect for {player_name}: {e}")
                await self.handle_disconnect(player_name)

    async def handle_connect(self, websocket: WebSocket):
        await websocket.send_json({
            "method": "connect",
            "players": self.get_player_data()
        })

    async def handle_join(self, player_name: str, websocket: WebSocket):
        print(f"handling join for {player_name}")
        if player_name in self.players and not self.is_active:
            await self.handle_join_player_exists(player_name, websocket)
            return

        self.players[player_name] = StatPlayerData(websocket)
        await self.notify_all_players("join", {
            "name": player_name
        })

    async def handle_join_player_exists(self, player_name: str, websocket: WebSocket):
        print(f"player {player_name} already exists")
        await websocket.send_json({
            "method": "join_error",
            "message": "Player already exists",
            "players": self.get_player_data()
        })

    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        print(f"notifying all players with {method}")
        for player_name in self.players:
            if self.players[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        if player_name in self.players:
            websocket = self.players[player_name].websocket
        try:
            await websocket.send_json({
                "method": method,
                "players": self.get_player_data(),
                "round_id": self.round_id,
                "item_id": self.item_id,
                "field_id": self.field_id,
                "value": self.value,
                **data
            })
        except Exception as e:
            print(f"Error sending to {player_name}: {e}. Disconnecting...")
            await self.handle_disconnect(player_name)

    async def handle_disconnect(self, player_name: str):
        if player_name in self.players:
            self.players[player_name].websocket = None
            await self.handle_leave(player_name)
            
        # if all players disconnected, reset game after a while
        await asyncio.sleep(60)
        if all([player.websocket is None for player in self.players.values()]):
            self.__init__()
            return

    async def handle_leave(self, player_name: str):
        if player_name not in self.players:
            return
        
        self.players.pop(player_name)
        print(f"player {player_name} left")
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
            self.__init__()

    async def handle_start(self):
        self.is_active = True
        self.round_id = 1
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

        self.game_state = "start"

        for player_name in self.players:
            self.players[player_name].is_alive = True

        for player_name in self.get_live_players():
            self.players[player_name].guess = None
            self.players[player_name].added_score = None
            self.players[player_name].acknowledged = False
        
        # let all the calculations happen before notifying
        self.select_random_item_and_field()
        await self.notify_all_players("next", {
            "value": self.value,
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # evaluate the points of each player
        for player_name in self.get_live_players():
            guess = self.players[player_name].guess
            if guess is None:
                continue
            score = self.get_score_of_value(guess)
            self.players[player_name].points += score
            self.players[player_name].added_score = score

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "value": self.value,
        })

        self.round_id += 1
        print("finished evaluating")

class StatData():
    stat_data: Dict[str, StatGameData]

    # init
    def __init__(self):
        self.stat_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.stat_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.stat_data:
            self.stat_data[game_id] = StatGameData()
        
        return self.stat_data[game_id]