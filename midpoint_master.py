import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
import math

# the game includes a 10 x 10 grid
# every turn, players choose a cell in the grid
# then, the midpoint of the grid is calculated
# players are awarded points based on how close their chosen cell is to the midpoint
# but if two players choose the same cell, they both lose points

class MidpointPlayerData():
    websocket: WebSocket
    played_coordinate: Tuple[int, int]
    points: int
    acknowledged: bool
    letter: str # letter for short identification

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.played_coordinate = None
        self.points = 0
        self.added_score = 0
        self.acknowledged = False
        self.letter = ""

ROUNDS = 10

class MidpointGameData():
    players: Dict[str, MidpointPlayerData]
    spectators: Dict[str, MidpointPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    midpoint: Tuple[int, int]
    played_grid: List[List[List[str]]]
    failed_players: List[str]

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.midpoint = None
        self.played_grid = [[[] for _ in range(10)] for _ in range(10)]
        self.failed_players = []

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played_coordinate": self.players[player_name].played_coordinate if self.players[player_name].played_coordinate is not None else None,
                "added_score": self.players[player_name].added_score if self.players[player_name].added_score is not None else None,
                "acknowledged": self.players[player_name].acknowledged,
                "letter": self.players[player_name].letter
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
                    played_coordinate = data["played_coordinate"]
                    player_name = data["name"]
                    print(f"{player_name} played {played_coordinate}")

                    self.players[player_name].played_coordinate = played_coordinate

                    await self.notify_all_players("play", {})

                    if all(self.players[player_name].played_coordinate is not None for player_name in self.get_live_players()):
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

        self.players[player_name] = MidpointPlayerData(websocket)
        self.players[player_name].letter = chr(65 + len(self.players) - 1)
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
            "players": self.get_player_data(),
            "midpoint": self.midpoint,
            "failed_players": self.failed_players if self.failed_players else None,
            "played_grid": self.played_grid if self.played_grid else None
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = MidpointPlayerData(websocket)
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
                "midpoint": self.midpoint,
                "failed_players": self.failed_players if self.failed_players else None,
                "played_grid": self.played_grid if self.played_grid else None,
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

        # reset all grids
        self.played_grid = [[[] for _ in range(10)] for _ in range(10)]

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
            self.players[player_name].played_coordinate = None
            self.players[player_name].added_score = None
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
        
        # for each cell in played_grid, if it's non-empty, then add a two letter "AA" into the cell
        for i in range(10):
            for j in range(10):
                if len(self.played_grid[i][j]) > 0:
                    self.played_grid[i][j] = ["AA"]
        
        # let all the calculations happen before notifying
        await self.notify_all_players("next", {
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # evaluate the points of each player
        # calculate the midpoint
        # award points based on distance to midpoint
        # subtract points if two players choose the same cell
        # notify players of their points
        # wait a while before handle next

        # calculate midpoint
        coordinates = [self.players[player_name].played_coordinate for player_name in self.get_live_players()]

        # played_grid is a 10x10 grid which captures who played each cell
        for player_name in self.get_live_players():
            played_coordinate = self.players[player_name].played_coordinate
            player_letter = self.players[player_name].letter
            self.played_grid[played_coordinate[0]][played_coordinate[1]].append(player_letter)

        x = np.array([coordinate[0] for coordinate in coordinates])
        y = np.array([coordinate[1] for coordinate in coordinates])

        self.midpoint = round(np.mean(x), 4), round(np.mean(y), 4)
        failed_players = []
        
        for player_name in self.get_live_players():
            player = self.players[player_name]
            player.played_coordinate = tuple(player.played_coordinate)
            player_distance = np.linalg.norm(np.array(player.played_coordinate) - np.array(self.midpoint))
            player.added_score = int(100 * math.exp(-player_distance / 10))
            player.points += player.added_score

            # check if two players chose the same cell
            if len(self.played_grid[player.played_coordinate[0]][player.played_coordinate[1]]) > 1:
                failed_players.append(player_name)
                player.points -= 50

        self.failed_players = failed_players

        await self.notify_all_players("evaluate", {})

        self.round_id += 1
        print("finished evaluating")

class MidpointData():
    math_data: Dict[str, MidpointGameData]

    # init
    def __init__(self):
        self.math_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.math_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.math_data:
            self.math_data[game_id] = MidpointGameData()
        
        return self.math_data[game_id]