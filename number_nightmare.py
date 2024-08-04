import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

class NumberPlayerData():
    websocket: WebSocket
    played_number: int
    satisfy_count: int
    points: int
    acknowledged: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.played_number = None
        self.satisfy_count = 0
        self.points = 0
        self.acknowledged = False

OPTIONS_SIZE = 5
ROUNDS = 10

class NumberGameData():
    players: Dict[str, NumberPlayerData]
    spectators: Dict[str, NumberPlayerData]
    is_active: bool
    deck_size: int
    round_id: int
    game_state: str
    options: List[int]

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.options = []
        self.deck_size = 0

    def create_options(self):
        # random options
        self.options = np.random.permutation(self.deck_size).tolist()[:OPTIONS_SIZE]

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played_number": self.players[player_name].played_number if self.players[player_name].played_number is not None else None,
                "satisfy_count": self.players[player_name].satisfy_count,
            } for player_name in self.players
        }
    
    def get_live_players(self):
        return [player_name for player_name in self.players]

    async def handle_client(self, websocket: WebSocket):
        data = {}
        try:
            while True:
                data = await websocket.receive_json()
                method = data["method"]

                if method == "join":
                    player_name = data["name"]
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    deck_size = data["deck_size"]
                    await self.handle_start(deck_size)

                elif method == "play":
                    player_name = data["name"]
                    played_number = data["played_number"]
                    satisfy_count = data["satisfy_count"]
                    print(f"{player_name} played {played_number}, earning {satisfy_count} points")
                    self.players[player_name].played_number = played_number
                    self.players[player_name].satisfy_count = satisfy_count
                    await self.notify_all_players("play", {})

                    if all(self.players[player_name].played_number is not None for player_name in self.get_live_players()):
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
        
        if player_name in self.players and self.is_active:
            print(f"reconnecting player {player_name}")
            self.players[player_name].websocket = websocket
            await self.handle_reconnect_start(player_name, websocket)
            return
        
        if player_name not in self.players and self.is_active:
            await self.handle_cannot_join(player_name, websocket)
            return

        self.players[player_name] = NumberPlayerData(websocket)
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

    async def handle_reconnect_start(self, player_name: str, websocket: WebSocket):
        await websocket.send_json({
            "method": self.game_state,
            "round_id": self.round_id,
            "options": self.options,
            "players": self.get_player_data(),
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = NumberPlayerData(websocket)
        await websocket.send_json({
            "method": "spectate",
            "message": "Game already started, but you can watch!",
            "players": self.get_player_data()
        })

    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        for player_name in self.players:
            if self.players[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)
        for player_name in self.spectators:
            if self.spectators[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        if player_name in self.players:
            websocket = self.players[player_name].websocket
        elif player_name in self.spectators:
            websocket = self.spectators[player_name].websocket
        try:
            await websocket.send_json({
                "method": method,
                "players": self.get_player_data(),
                "options": self.options,
                "round_id": self.round_id,
                **data
            })
        except Exception as e:
            print(f"Error sending to {player_name}: {e}. Disconnecting...")
            await self.handle_disconnect(player_name)

    async def handle_disconnect(self, player_name: str):
        if player_name in self.players:
            self.players[player_name].websocket = None
            if self.game_state == "lobby":
                await self.handle_leave(player_name)
            
        if player_name in self.spectators:
            self.spectators[player_name].websocket = None
            
        # if all players disconnected, reset game after a while
        await asyncio.sleep(5 * 60 * 60)
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

        live_players = self.get_live_players()

        if self.is_active and len(live_players) < 2:
            if len(live_players) == 1:
                await self.notify_all_players("end", {
                    "winner": live_players[0]
                })
            else:
                await self.notify_all_players("end", {
                    "winner": "No one"
                })
            self.is_active = False

        if len(self.players) == 0:
            self.__init__()

    async def handle_start(self, deck_size: int):
        self.is_active = True
        self.deck_size = deck_size
        self.round_id = 1
        # reset all player points
        for player_name in self.players:
            self.players[player_name].points = 0

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

        for player_name in self.get_live_players():
            self.players[player_name].played_number = None
            self.players[player_name].satisfy_count = 0
            self.players[player_name].acknowledged = False

        live_players = self.get_live_players()

        if len(live_players) < 2:
            winner = "No one"
            if len(live_players) == 1:
                winner = live_players[0]
            await self.notify_all_players("end", {
                "winner": winner
            })
            self.is_active = False
            self.game_state = "lobby"
            return
        
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
        played_numbers = [player.played_number for player in self.players.values()]

        # if a player played a number that someone else played, they lose 3 points
        failed_players = []
        for player_name in self.players:
            if played_numbers.count(self.players[player_name].played_number) > 1:
                self.players[player_name].points -= 3
                failed_players.append(player_name)
        
        # add points based on satisfy count
        for player_name in self.players:
            self.players[player_name].points += self.players[player_name].satisfy_count

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "failed_players": failed_players,
        })

        self.round_id += 1
        print("finished evaluating")

class NumberData():
    games_data: Dict[str, NumberGameData]

    # init
    def __init__(self):
        self.games_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.games_data

    def get_game_data(self, game_id: str):
        if game_id not in self.games_data:
            self.games_data[game_id] = NumberGameData()
        
        return self.games_data[game_id]