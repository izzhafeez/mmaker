import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

class BlurryPlayerData():
    websocket: WebSocket
    guess: str
    added_score: int
    points: int
    acknowledged: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.guess = None
        self.points = 0
        self.added_score = 0
        self.acknowledged = False

ROUNDS = 10

class BlurryGameData():
    players: Dict[str, BlurryPlayerData]
    spectators: Dict[str, BlurryPlayerData]
    is_active: bool
    round_id: int
    game_state: str
    answer_id: int
    answer: str
    deck_size: int

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.answer_id = 0
        self.answer = None
        self.deck_size = 0

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "guess": self.players[player_name].guess if self.players[player_name].guess is not None else None,
                "added_score": self.players[player_name].added_score if self.players[player_name].added_score is not None else None,
                "acknowledged": self.players[player_name].acknowledged
            } for player_name in self.players
        }
    
    def select_random_answer_id(self):
        self.answer_id = np.random.randint(0, self.deck_size)

    def get_closeness_of_answer(answer: str, guess: str):
        # if exact match, return 1
        if answer == guess:
            return 2
        # if not, assign score based on jacard similarity
        answer_letter_set = set(answer)
        guess_letter_set = set(guess)
        intersection = answer_letter_set.intersection(guess_letter_set)
        union = answer_letter_set.union(guess_letter_set)
        score = len(intersection) / len(union)
        return round(score, 2)
    
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
                    await self.handle_start(data["deck_size"])

                elif method == "play":
                    guess = data["guess"]
                    player_name = data["name"]
                    self.answer = data["answer"]
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

        self.players[player_name] = BlurryPlayerData(websocket)
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
            "answer_id": self.answer_id,
            "players": self.get_player_data(),
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = BlurryPlayerData(websocket)
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
                "answer_id": self.answer_id,
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

        if len(self.players) == 0:
            self.__init__()

    async def handle_start(self, deck_size: int):
        self.is_active = True
        self.round_id = 1
        self.deck_size = deck_size
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
            self.players[player_name].added_score = None
            self.players[player_name].acknowledged = False
        
        # let all the calculations happen before notifying
        self.select_random_answer_id()
        await self.notify_all_players("next", {
            "answer_id": self.answer_id,
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
            score = BlurryGameData.get_closeness_of_answer(self.answer, guess)
            self.players[player_name].points += score
            self.players[player_name].added_score = score

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "answer_id": self.answer_id,
        })

        self.round_id += 1
        print("finished evaluating")

class BlurryData():
    games_data: Dict[str, Dict[str, BlurryGameData]]

    # init
    def __init__(self):
        self.games_data = {}

    def game_data_exists(self, game_type: str, game_id: str):
        return game_type in self.games_data and game_id in self.games_data[game_type]

    def get_game_data(self, game_type: str, game_id: str):
        if game_type not in self.games_data:
            self.games_data[game_type] = {}
        
        if game_id not in self.games_data[game_type]:
            self.games_data[game_type][game_id] = BlurryGameData()
        
        return self.games_data[game_type][game_id]