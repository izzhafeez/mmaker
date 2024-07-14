import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

class PlayedCard():
    card_id: int
    data: List[float]

    # init
    def __init__(self, card_id: int, data: List[float]):
        self.card_id = card_id
        self.data = data

class ColorPlayerData():
    websocket: WebSocket
    played_color: str
    added_score: int
    points: int

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.played_color = None
        self.points = 0
        self.added_score = 0

ROUNDS = 10

class ColorGameData():
    players: Dict[str, ColorPlayerData]
    spectators: Dict[str, ColorPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    color: str

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.color = None

    def create_random_color_code(self):
        # random red value
        red = np.random.randint(0, 256)
        red_as_hex = hex(red)[2:]
        # random green value
        green = np.random.randint(0, 256)
        green_as_hex = hex(green)[2:]
        # random blue value
        blue = np.random.randint(0, 256)
        blue_as_hex = hex(blue)[2:]
        self.color = f"{red_as_hex}{green_as_hex}{blue_as_hex}"

    def get_score_of_color(self, color: str):
        red = int(color[:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:], 16)
        correct_red = int(self.color[:2], 16)
        correct_green = int(self.color[2:4], 16)
        correct_blue = int(self.color[4:], 16)
        distance = np.sqrt((red - correct_red) ** 2 + (green - correct_green) ** 2 + (blue - correct_blue) ** 2)

        # assign a score that maxes at 100 and min at 0, based on distance
        score = 100 - distance / (256 * np.sqrt(3)) * 100
        return int(score)

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played_color": self.players[player_name].played_color if self.players[player_name].played_color is not None else None,
                "added_score": self.players[player_name].added_score if self.players[player_name].added_score is not None else None,
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
                    await self.handle_start()

                elif method == "play":
                    played_color = data["color"]
                    player_name = data["name"]
                    print(f"{player_name} played {played_color}")

                    if self.players[player_name].played_color == None:
                        self.num_played += 1
                    self.players[player_name].played_color = played_color
                    if self.num_played == len(self.get_live_players()):
                        await self.handle_evaluate()

                elif method == "acknowledge":
                    print("acknowledged")
                    self.num_played += 1
                    if self.num_played == len(self.get_live_players()):
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

        self.players[player_name] = ColorPlayerData(websocket)
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
        print(f"reconnecting player {player_name}")
        await websocket.send_json({
            "method": self.game_state,
            "round_id": self.round_id,
            "color": self.color,
            "players": self.get_player_data(),
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = ColorPlayerData(websocket)
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
                "color": self.color,
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

    async def handle_start(self):
        self.is_active = True
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

        self.num_played = 0
        self.game_state = "start"

        for player_name in self.get_live_players():
            self.players[player_name].played_color = None

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
        self.create_random_color_code()
        await self.notify_all_players("next", {
            "color": self.color,
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # evaluate the points of each player
        for player_name in self.get_live_players():
            played_color = self.players[player_name].played_color
            if played_color is None:
                continue
            score = self.get_score_of_color(played_color)
            self.players[player_name].points += score
            self.players[player_name].added_score = score

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "color": self.color,
        })

        self.round_id += 1
        self.num_played = 0
        print("finished evaluating")

class ColorData():
    math_data: Dict[str, ColorGameData]

    # init
    def __init__(self):
        self.math_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.math_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.math_data:
            self.math_data[game_id] = ColorGameData()
        
        return self.math_data[game_id]