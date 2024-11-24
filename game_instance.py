import asyncio
from typing import Dict, Any
from abc import ABC, abstractmethod
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
import numpy as np
from redis_client import RedisClient

class GamePlayer():
    is_alive: bool

    # init
    def __init__(self):
        self.is_alive = False

ROUNDS = 10

class GameInstance(ABC):
    instance_id: str
    players: Dict[str, GamePlayer]
    websocket_connections: Dict[str, WebSocket]
    is_active: bool
    round_id: int
    game_state: str
    redis_client: RedisClient
    seed: float

    # init
    def __init__(self, instance_id: str, redis_client: RedisClient):
        self.instance_id = instance_id
        self.players = {}
        self.websocket_connections = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.redis_client = redis_client
        self.seed = None

    async def start_redis(self):
        await self.redis_client.subscribe(self.instance_id, self.handle_redis_message)
        print(f"subscribed to {self.instance_id}")

    @abstractmethod
    def get_player_data(self):
        pass
    
    def get_live_players(self):
        return [player_name for player_name in self.players if self.players[player_name].is_alive]

    async def handle_client(self, websocket: WebSocket):
        data = {}
        print("handling client")
        try:
            while True:
                data = await websocket.receive_json()
                if data["method"] == "join":
                    name = data.get('name', '')
                    if name in self.websocket_connections:
                        await self.handle_join_player_exists(name, websocket)
                    else:
                        self.websocket_connections[name] = websocket
                await self.redis_client.publish(self.instance_id, data)

        except WebSocketDisconnect as e:
            player_name = data.get('name', '')
            if player_name:
                print(f"handling disconnect for {player_name}: {e}")
                await self.handle_disconnect(player_name)

    @abstractmethod
    async def handle_redis_message(self, data: Dict[str, Any]):
        pass

    async def handle_connect(self, websocket: WebSocket):
        await websocket.send_json({
            "method": "connect",
            "players": self.get_player_data()
        })

    async def handle_join(self, player_name: str):
        self.players[player_name] = GamePlayer()
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
        for player_name in self.websocket_connections:
            await self.notify_player(player_name, method, data)

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        if player_name not in self.websocket_connections:
            return

        websocket = self.websocket_connections[player_name]
        try:
            payload = {
                "method": method,
                "game_state": self.game_state,
                "round_id": self.round_id,
                "players": self.get_player_data(),
                **data
            }
            await websocket.send_json(payload)
        except Exception as e:
            print(f"Error sending to {player_name}: {e}. Disconnecting...")
            await self.handle_disconnect(player_name)

    async def handle_disconnect(self, player_name: str):
        print(f"handling disconnect for {player_name}")
        if player_name in self.players:
            del self.websocket_connections[player_name]
            await self.handle_leave(player_name)
            
        # if all players disconnected, reset game after a while
        await asyncio.sleep(60)
        if len(self.websocket_connections) == 0:
            self.__init__(self.instance_id, self.redis_client)
            return

    @abstractmethod
    async def handle_leave(self, player_name: str):
        pass