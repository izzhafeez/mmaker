import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# in this game, players have to guess where a given location is
# the player who is second closest to it gains a point

class LocationPlayerData():
    websocket: WebSocket
    guess: Tuple[float, float]
    points: int
    distance: float
    acknowledged: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.guess = None
        self.points = 0
        self.distance = None
        self.acknowledged = False

ROUNDS = 10

class LocationGameData():
    players: Dict[str, LocationPlayerData]
    spectators: Dict[str, LocationPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    location_id: int
    actual: Tuple[float, float]
    num_of_locations: int
    second_closest: str
    distance: float

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.location_id = None
        self.actual = None
        self.num_of_locations = None
        self.second_closest = None
        self.distance = None

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

    def randomise_location(self):
        self.location_id = np.random.randint(0, self.num_of_locations)

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "guess": self.players[player_name].guess if self.players[player_name].guess is not None else None,
                "acknowledged": self.players[player_name].acknowledged,
                "distance": self.players[player_name].distance if self.players[player_name].distance is not None else None
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
                    num_of_locations = data["num_of_locations"]
                    self.num_of_locations = num_of_locations
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    await self.handle_start()

                elif method == "play":
                    guess = data["guess"]
                    player_name = data["name"]
                    self.actual = data["actual"]
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
        
        if player_name in self.players and self.is_active:
            print(f"reconnecting player {player_name}")
            self.players[player_name].websocket = websocket
            await self.handle_reconnect_start(player_name, websocket)
            return
        
        if player_name not in self.players and self.is_active:
            await self.handle_cannot_join(player_name, websocket)
            return

        self.players[player_name] = LocationPlayerData(websocket)
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
            "players": self.get_player_data(),
            "location": self.location_id,
            "second_closest": self.second_closest,
            "distance": self.distance,
            "round_id": self.round_id,
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = LocationPlayerData(websocket)
        await websocket.send_json({
            "method": "spectate",
            "message": "Game already started, but you can watch!",
            "players": self.get_player_data()
        })

    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        print(f"notifying all players with {method}")
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
                "location": self.location_id,
                "second_closest": self.second_closest,
                "distance": self.distance,
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

        self.game_state = "start"

        for player_name in self.get_live_players():
            self.players[player_name].guess = None
            self.players[player_name].acknowledged = False
            self.players[player_name].distance = None

        self.actual = None
        self.second_closest = None
        self.distance = None
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
        self.randomise_location()
        await self.notify_all_players("next", {
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # rank the players in terms of distance from actual, and keep the distances in player.distance
        for player_name in self.get_live_players():
            player = self.players[player_name]
            player.distance = LocationGameData.calculate_distance_in_km(player.guess[0], player.guess[1], self.actual[0], self.actual[1])

        sorted_players = sorted(self.get_live_players(), key=lambda x: self.players[x].distance)

        # second closest player gets a point
        second_closest = sorted_players[1]
        self.players[second_closest].points += 1
        self.second_closest = second_closest
        self.distance = self.players[second_closest].distance

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
        })

        self.round_id += 1
        print("finished evaluating")

class LocationData():
    math_data: Dict[str, LocationGameData]

    # init
    def __init__(self):
        self.math_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.math_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.math_data:
            self.math_data[game_id] = LocationGameData()
        
        return self.math_data[game_id]