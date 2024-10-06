import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# in this game, players have to guess where a given location is
# the player who is closest to it gains a point

class CityPlayerData():
    websocket: WebSocket
    guess: Tuple[float, float]
    points: float
    city: str
    distance: float
    acknowledged: bool
    is_alive: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.guess = None
        self.points = 0
        self.city = None
        self.distance = None
        self.acknowledged = False
        self.is_alive = False

ROUNDS = 10

class CityGameData():
    players: Dict[str, CityPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    closest_city: str
    closest_lat_lng: List[float]
    max_lat: float
    min_lat: float
    max_lng: float
    min_lng: float
    lat: float
    lng: float

    # init
    def __init__(self):
        self.players = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.closest_city = ""
        self.closest_lat_lng = [0, 0]
        self.max_lat = 90
        self.min_lat = -90
        self.max_lng = 180
        self.min_lng = -180
        self.lat = 0
        self.lng = 0

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

    def randomise_lat_lng(self):
        self.lat = np.random.uniform(self.min_lat, self.max_lat)
        self.lng = np.random.uniform(self.min_lng, self.max_lng)

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "guess": self.players[player_name].guess if self.players[player_name].guess is not None else None,
                "acknowledged": self.players[player_name].acknowledged,
                "city": self.players[player_name].city if self.players[player_name].city is not None else None,
                "distance": self.players[player_name].distance if self.players[player_name].distance is not None else None
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
                    player_name = data["name"]
                    max_lat = data["max_lat"]
                    min_lat = data["min_lat"]
                    max_lng = data["max_lng"]
                    min_lng = data["min_lng"]
                    self.max_lat = max_lat
                    self.min_lat = min_lat
                    self.max_lng = max_lng
                    self.min_lng = min_lng
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    await self.handle_start()

                elif method == "play":
                    guess = data["guess"]
                    city = data["city"]
                    player_name = data["name"]
                    print(f"{player_name} played {city}")

                    self.closest_city = data["closest_city"]
                    self.closest_lat_lng = data["closest_lat_lng"]
                    self.players[player_name].guess = guess
                    self.players[player_name].city = city
                    await self.notify_all_players("play", {})
                    print(self.get_live_players())
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

        self.players[player_name] = CityPlayerData(websocket)
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
                "lat": self.lat,
                "lng": self.lng,
                "round_id": self.round_id,
                "closest_city": self.closest_city,
                "closest_lat_lng": self.closest_lat_lng,
                "is_active": self.is_active,
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

        for player_name in self.players:
            self.players[player_name].is_alive = True

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

        self.lat = None
        self.lng = None
        
        # let all the calculations happen before notifying
        self.randomise_lat_lng()
        await self.notify_all_players("next", {
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"

        max_distance = CityGameData.calculate_distance_in_km(self.min_lat, self.min_lng, self.max_lat, self.max_lng)
        gained = {}

        # players get points based on their distance of their guess to the actual location
        for player_name in self.get_live_players():
            player = self.players[player_name]
            player.distance = CityGameData.calculate_distance_in_km(player.guess[0], player.guess[1], self.lat, self.lng)
            
            # points should be max 100
            gained[player_name] = {
                "points": int(100 - ((player.distance / max_distance) * 100)) if player.city != self.closest_city else 100,
                "city": player.city,
            }
            player.points += gained[player_name]["points"]

        # most popular city
        city_counts = {}
        for player_name in self.get_live_players():
            player = self.players[player_name]
            if player.city not in city_counts:
                city_counts[player.city] = 0
            city_counts[player.city] += 1
        
        max_count = max(city_counts.values())
        most_popular_cities = [city for city in city_counts if city_counts[city] == max_count]
        failed_players = set()
        if len(most_popular_cities) == 1 and len(self.get_live_players()) > 1:
            # players lose 50 points if they guess the most popular city
            for player_name in self.get_live_players():
                player = self.players[player_name]
                if player.city == most_popular_cities[0]:
                    failed_players.add(player_name)

        for player_name in failed_players:
            self.players[player_name].points -= 50
            gained[player_name]["points"] -= 50

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "gained": gained,
            "most_popular_city": most_popular_cities[0] if len(most_popular_cities) == 1 and len(self.get_live_players()) > 1 else -1,
            "failed": list(failed_players)
        })

        self.round_id += 1
        print("finished evaluating")

class CityData():
    city_data: Dict[str, CityGameData]

    # init
    def __init__(self):
        self.city_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.city_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.city_data:
            self.city_data[game_id] = CityGameData()
        
        return self.city_data[game_id]