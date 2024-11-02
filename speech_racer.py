import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import WebSocket
from pymongo import MongoClient
from fastapi.websockets import WebSocketDisconnect

class SpeechRacer:
    def __init__(self, time_entered: datetime, difficulty: str, settings):
        self.players: Dict[str, WebSocket] = {}
        self.player_progresses: Dict[str, int] = {}
        self.time_entered = time_entered
        asyncio.create_task(self.start_game())

        connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
        client = MongoClient(connection)
        self.text = client.speechracer.texts.aggregate([{"$sample": {"size": 1}}]).next()

    async def handle_connection(self, websocket: WebSocket, name: str):
        self.players[name] = websocket
        self.player_progresses[name] = 0
        # time to next minute
        time_remaining = 60 - datetime.now().second
        await self.notify_all_players("connect", { "time_remaining": time_remaining })

    async def handle_client(self, websocket: WebSocket, name: str):
        data = {}
        try:
            while True:
                data = await websocket.receive_json()
                method = data.get("method")
                if method == "progress":
                    player_name = data.get("name")
                    self.player_progresses[player_name] = data.get("progress")
                    await self.notify_all_players("progress", {})
        except WebSocketDisconnect as _:
            print(f"Player disconnected")
            self.players.pop(name)
            self.player_progresses.pop(name)
            await self.notify_all_players("disconnect", {
                "name": name
            })
        
    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        for player in self.players.values():
            await player.send_json({
                "method": method,
                "players": self.player_progresses,
                **data
            })
        
    async def start_game(self):
        time_remaining = 60 - datetime.now().second
        # await asyncio.sleep(4)
        await asyncio.sleep(time_remaining)
        await self.notify_all_players("start", {"text": self.text["text"], "source": self.text["source"]})
        await asyncio.sleep(3600)
        await self.notify_all_players("end", {})