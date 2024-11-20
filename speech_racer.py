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
        self.player_accuracy: Dict[str, float] = {}
        self.player_wpm: Dict[str, float] = {}
        self.time_entered = time_entered
        asyncio.create_task(self.start_game())

        connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
        client = MongoClient(connection)

        if difficulty == "easy":
            # id [1, 100] means easy
            self.text = client.speechracer.texts.aggregate([{"$match": {"id": {"$lte": 100}}}, {"$sample": {"size": 1}}]).next()
        elif difficulty == "medium":
            # [101, 300] means medium
            self.text = client.speechracer.texts.aggregate([{"$match": {"id": {"$gt": 100, "$lte": 300}}}, {"$sample": {"size": 1}}]).next()
        elif difficulty == "hard":
            # [301, 600] means hard
            self.text = client.speechracer.texts.aggregate([{"$match": {"id": {"$gt": 300, "$lte": 600}}}, {"$sample": {"size": 1}}]).next()
        else:
            # [601, 9999] means hard
            self.text = client.speechracer.texts.aggregate([{"$match": {"id": {"$gt": 600}}}, {"$sample": {"size": 1}}]).next()

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
                elif method == "complete":
                    # contains name, accuracy, wpm
                    player_name = data.get("name")
                    self.player_accuracy[player_name] = data.get("accuracy")
                    self.player_wpm[player_name] = data.get("wpm")
                    
                    # only send data of completed players
                    data_of_completed_players = {}
                    for player in self.player_accuracy:
                        data_of_completed_players[player] = [self.player_accuracy[player], self.player_wpm[player]]
                    await self.notify_all_players("complete", {
                        'completed_data': data_of_completed_players
                    })
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