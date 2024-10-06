from fastapi import WebSocket, WebSocketDisconnect
from enum import Enum
from typing import List, Dict, Any
import numpy as np
import asyncio

class MathPlayerState(Enum):
    LOBBY = 'LOBBY'
    TURN = 'TURN'
    WAITING = 'WAITING'
    DEAD = 'DEAD'
    SPECTATING = 'SPECTATING'

class MathGameState(Enum):
    LOBBY = 'LOBBY'
    PLAYING = 'PLAYING'

class MathPlayerData():
    websocket: WebSocket
    hand: List[int]
    status: MathPlayerState

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.hand = []
        self.state = MathPlayerState.LOBBY

DECK_SIZE = 120
class MathDeckData():
    deck: List[int]
    current_index: int

    def __init__(self, deck_size: int = DECK_SIZE): 
        self.deck = np.random.permutation(deck_size).tolist()
        self.current_index = 0

    def draw(self):
        self.current_index = (self.current_index + 1) % len(self.deck)
        return self.deck[self.current_index]

    def get_size(self):
        return len(self.deck)

STARTING_NUMBER = 0
LOWEST_NUMBER = -100
HIGHEST_NUMBER = 100
class MathGameData():
    players: Dict[str, MathPlayerData]
    spectators: Dict[str, MathPlayerData]
    live_players: List[str]
    player: str
    deck: MathDeckData
    state: MathGameState
    number: List[int]
    last_played: int
    history: List[Dict[str, Any]]

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.live_players = []
        self.player = None
        self.deck = MathDeckData()
        self.state = MathGameState.LOBBY
        self.number = STARTING_NUMBER
        self.last_played = None
        self.history = []
    
    def next_player(self):
        self.players[self.player].state = MathPlayerState.WAITING
        self.player = None
        while self.player is None:
            self.player = self.live_players.pop(0)
            if self.players[self.player].state == MathPlayerState.DEAD:
                self.player = None
        self.players[self.player].state = MathPlayerState.TURN

    async def handle_client(self, websocket: WebSocket):
        data = {}
        try:
            while True:
                data = await websocket.receive_json()
                method = data["method"]
                print(f"received {method}")

                if method == "join":
                    deck_size = data["deck_size"]
                    if (deck_size != self.deck.get_size()):
                        self.deck = MathDeckData(deck_size=deck_size)
                    player_name = data["name"]
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    await self.handle_start()

                elif method == "play":
                    player_name = data["name"]
                    if self.players[player_name].state != MathPlayerState.TURN:
                        continue

                    card_id = data["card_id"]
                    self.last_played = card_id
                    self.number = data["number"]
                    if self.number > HIGHEST_NUMBER or self.number < LOWEST_NUMBER:
                        self.players[player_name].state = MathPlayerState.DEAD
                        await self.notify_player(self.player, "DEAD", {})
                    else:
                        self.live_players.append(player_name)

                    self.players[player_name].hand.remove(card_id)
                    self.players[player_name].hand.append(self.deck.draw())
                    self.history.append({
                        "player": player_name,
                        "card_id": card_id,
                        "number": self.number,
                    })

                    self.next_player()
                    await self.notify_all_players("PLAY", {
                        "last_player": player_name,
                    })

                    # check if game is over
                    if len(self.live_players) == 0:
                        await self.notify_all_players("END", {
                            "winner": self.player
                        })
                        self.state = MathGameState.LOBBY
                    else:
                        await asyncio.sleep(3)
                        await self.notify_player(self.player, "TURN", {})


        except WebSocketDisconnect as e:
            player_name = data.get('name', '')
            if player_name:
                print(f"handling disconnect for {player_name}: {e}")
                await self.handle_disconnect(player_name)

    async def handle_connect(self, websocket: WebSocket):
        print("handling connect")
        await websocket.send_json({
            "method": "CONNECT",
            "players": self.get_player_life_status()
        })

    def get_player_life_status(self):
        return {
            player_name: self.players[player_name].state.value for player_name in self.players
        }

    async def handle_join(self, player_name: str, websocket: WebSocket):
        print(f"handling join for {player_name}")
        if player_name in self.players and self.state == MathGameState.LOBBY:
            await self.handle_join_player_exists(player_name, websocket)
            return
        
        if player_name in self.players and self.state != MathGameState.LOBBY:
            print(f"reconnecting player {player_name}")
            await self.handle_reconnect(player_name, websocket)
            return
        
        if player_name not in self.players and self.state != MathGameState.LOBBY:
            await self.handle_cannot_join(player_name, websocket)
            return

        self.players[player_name] = MathPlayerData(websocket)
        await self.notify_all_players("JOIN", {
            "name": player_name
        })

    async def handle_join_player_exists(self, player_name: str, websocket: WebSocket):
        print(f"player {player_name} already exists")
        await websocket.send_json({
            "method": "JOIN_ERROR",
            "message": "Player already exists",
            "players": self.get_player_life_status()
        })

    async def handle_reconnect(self, player_name: str, websocket: WebSocket):
        self.players[player_name].websocket = websocket
        await self.notify_player(player_name, "RECONNECT", {})

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = MathPlayerData(websocket)
        await websocket.send_json({
            "method": "SPECTATE",
            "message": "Game already started, but you can watch!",
            "players": self.get_player_life_status()
        })

    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        for player_name in self.players:
            if self.players[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)
        for player_name in self.spectators:
            if self.spectators[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        print(f"Notifying {player_name} with {method}")
        if player_name in self.players:
            websocket = self.players[player_name].websocket
        elif player_name in self.spectators:
            websocket = self.spectators[player_name].websocket
        try:
            await websocket.send_json({
                "method": method,
                "players": self.get_player_life_status(),
                "player": self.player,
                "state": self.state.value,
                "number": self.number,
                "hand": self.players[player_name].hand,
                "last_played": self.last_played,
                "history": self.history,
                **data
            })
        except Exception as e:
            print(f"Error sending to {player_name}: {e}. Disconnecting...")
            await self.handle_disconnect(player_name)

    async def handle_disconnect(self, player_name: str):
        print(self.state)
        if player_name in self.players:
            self.players[player_name].websocket = None
            if self.state == MathGameState.LOBBY:
                await self.handle_leave(player_name)
            
        if player_name in self.spectators:
            self.spectators[player_name].websocket = None
            
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
        await self.notify_all_players("LEAVE", {
            "name": player_name,
        })

        if self.state == MathGameState.PLAYING and len(self.live_players) < 2:
            if len(self.live_players) == 1:
                await self.notify_all_players("END", {
                    "winner": self.live_players[0]
                })
            else:
                await self.notify_all_players("END", {
                    "winner": "No one"
                })
            self.state = MathGameState.LOBBY

        if len(self.players) == 0:
            self.__init__()

    async def handle_start(self):
        self.number = STARTING_NUMBER
        self.state = MathGameState.PLAYING

        # split deck and send to players
        n_players = len(self.players)

        # need at least 2 players
        if n_players < 2:
            await self.notify_all_players("START_ERROR", {
                "message": "Need at least 2 players"
            })
            return
        
        # revive all players
        for player_name in self.players:
            self.players[player_name].state = MathPlayerState.WAITING

        print(f"starting game with {n_players} players")
        # draw 3 cards per person
        for player_name in self.players:
            self.players[player_name].hand = [self.deck.draw() for _ in range(3)]

        self.live_players = list(self.players.keys())
        self.player = self.live_players.pop(0)
        self.players[self.player].state = MathPlayerState.TURN
        self.history = []

        # let all the calculations happen before notifying
        for player_name in self.players:
            if player_name == self.player:
                await self.notify_player(player_name, "TURN", {})
            else:
                await self.notify_player(player_name, "WAIT", {})

class MathAttackData():
    math_data: Dict[str, MathGameData]

    # init
    def __init__(self):
        self.math_data = {}

    def game_data_exists(self, game_id: str):
        return game_id in self.math_data

    def get_game_data(self, game_id: str):
        
        if game_id not in self.math_data:
            self.math_data[game_id] = MathGameData()
        
        return self.math_data[game_id]