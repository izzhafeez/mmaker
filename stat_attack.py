import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

class PlayerData():
    websocket: WebSocket
    deck: List[int]
    hand: List[int]
    played_hand: List[Tuple[int, float]]
    is_alive: bool
    buffer: int

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.deck = []
        self.hand = []
        self.buffer = -1
        self.played_hand = []
        self.is_alive = True

    async def draw(self, hand_size: int):
        if len(self.deck) < hand_size:
            self.is_alive = False
            await self.websocket.send_json({
                "method": "lose",
            })
            return
        try:
            self.hand = self.deck[:hand_size]
            self.deck = self.deck[hand_size:]
            if self.buffer != -1:
                self.hand.append(self.buffer)
                self.buffer = -1
            elif len(self.deck) > 0:
                self.hand.append(self.deck.pop(0))
            self.played_hand = []
        except Exception as e:
            print(f"Error drawing for: {e}")

class GameData():
    players: Dict[str, PlayerData]
    spectators: Dict[str, PlayerData]
    is_active: bool
    deck_size: int
    hand_size: int
    num_played: int
    round_id: int
    game_state: str
    is_higher: bool

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.hands = []
        self.round_id = -1
        self.game_state = "lobby"
        self.is_higher = False

    def get_player_card_counts(self):
        return {
            player_name: {
                "card_count": len(self.players[player_name].deck),
                "is_alive": self.players[player_name].is_alive,
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
                    await self.handle_join(player_name, websocket)

                elif method == "leave":
                    player_name = data["name"]
                    await self.handle_leave(player_name)

                elif method == "start":
                    deck_size = data["deck_size"]
                    hand_size = data["hand_size"]
                    await self.handle_start(deck_size, hand_size)

                elif method == "play":
                    hand = data["hand"]
                    player_name = data["name"]
                    if not self.players[player_name].is_alive:
                        continue

                    if len(self.players[player_name].played_hand) == 0:
                        self.num_played += 1
                    self.players[player_name].played_hand = hand
                    if self.num_played == len(self.get_live_players()):
                        await self.handle_evaluate()

                elif method == "select":
                    card_id = data["card_id"]
                    player_name = data["name"]
                    self.players[player_name].deck.append(card_id)
                    await self.handle_evaluate()

        except WebSocketDisconnect as e:
            player_name = data.get('name', '')
            if player_name:
                print(f"handling disconnect for {player_name}: {e}")
                await self.handle_disconnect(player_name)

    async def handle_connect(self, websocket: WebSocket):
        await websocket.send_json({
            "method": "connect",
            "players": self.get_player_card_counts()
        })

    async def handle_join(self, player_name: str, websocket: WebSocket):
        print(f"handling join for {player_name}")
        if player_name in self.players and not self.is_active:
            await self.handle_join_player_exists(player_name, websocket)
            return
        
        if player_name in self.players and self.is_active:
            print(f"reconnecting player {player_name}")
            self.players[player_name].websocket = websocket
            if self.game_state == "start":
                await self.handle_reconnect_start(player_name, websocket)
            elif self.game_state == "select":
                await self.handle_reconnect_select(player_name, websocket)
            return
        
        if player_name not in self.players and self.is_active:
            await self.handle_cannot_join(player_name, websocket)
            return

        self.players[player_name] = PlayerData(websocket)
        await self.notify_all_players("join", {
            "name": player_name
        })

    async def handle_join_player_exists(self, player_name: str, websocket: WebSocket):
        print(f"player {player_name} already exists")
        await websocket.send_json({
            "method": "join_error",
            "message": "Player already exists",
            "players": self.get_player_card_counts()
        })

    async def handle_reconnect_start(self, player_name: str, websocket: WebSocket):
        await websocket.send_json({
            "method": "next",
            "hand": self.players[player_name].hand,
            "players": self.get_player_card_counts(),
            "is_higher": self.is_higher
        })

    async def handle_reconnect_select(self, player_name: str, websocket: WebSocket):
        played_cards = []
        for player_name in self.players:
            played_card = self.players[player_name].played_hand[self.round_id]
            played_card['name'] = player_name
            played_cards.append(played_card) # card should be {name, card_id, card_value}

        # sort by card value
        played_cards.sort(key=lambda x: x['card_value'], reverse=True)
        winner = played_cards[0]['name']

        await websocket.send_json({
            "method": "select",
            "round_id": self.round_id,
            "winner": winner,
            "played_cards": played_cards,
            "is_higher": self.is_higher
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = PlayerData(websocket)
        await websocket.send_json({
            "method": "spectate",
            "message": "Game already started, but you can watch!",
            "players": self.get_player_card_counts()
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
                "players": self.get_player_card_counts(),
                "is_higher": self.is_higher,
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

    async def handle_start(self, deck_size: int, hand_size: int):
        self.is_active = True
        self.deck_size = deck_size
        self.hand_size = hand_size
        shuffled_deck = np.random.permutation(deck_size).tolist()
        # revive all players
        for player_name in self.players:
            self.players[player_name].is_alive = True

        # split deck and send to players
        n_players = len(self.players)

        # need at least 2 players
        if n_players < 2:
            await self.notify_all_players("start_error", {
                "message": "Need at least 2 players"
            })
            return

        print(f"starting game with {n_players} players")
        cards_per_player = deck_size // n_players
        for i, player_name in enumerate(self.players):
            start = i * cards_per_player
            end = (i + 1) * cards_per_player
            self.players[player_name].deck = shuffled_deck[start:end]
        
        # let all the calculations happen before notifying
        for player_name in self.players:
            await self.notify_player(player_name, "start", {})

        # wait a while before handle next
        await asyncio.sleep(1)
        await self.handle_next()

    async def handle_next(self):
        print("handling next")
        self.is_higher = not self.is_higher
        self.num_played = 0
        self.round_id = -1
        self.game_state = "start"

        for player_name in self.get_live_players():
            await self.players[player_name].draw(self.hand_size)
            self.players[player_name].played_hand = []

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
        for player_name in self.players:
            await self.notify_player(player_name, "next", {
                "hand": self.players[player_name].hand,
                "is_higher": self.is_higher
            })
        for player_name in self.spectators:
            await self.notify_player(player_name, "next", {
                "hand": [],
                "is_higher": self.is_higher
            })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.round_id += 1
        if self.round_id >= self.hand_size:
            for player_name in self.get_live_players():
                if len(self.players[player_name].played_hand) == self.hand_size + 1:
                    self.players[player_name].buffer = self.players[player_name].played_hand[-1]["card_id"]
            await self.handle_next()
            return

        played_cards = []
        for player_name in self.get_live_players():
            played_card = self.players[player_name].played_hand[self.round_id]
            played_card['name'] = player_name
            played_cards.append(played_card) # card should be {name, card_id, card_value}

        # sort by card value
        played_cards.sort(key=lambda x: x['card_value'], reverse=self.is_higher)
        if played_cards[0]['card_value'] == played_cards[1]['card_value']:
            winner = ""
            winning_value = played_cards[0]['card_value']
            for card in played_cards:
                if card['card_value'] != winning_value:
                    break
                self.players[card['name']].deck.append(card['card_id'])
        else:
            winner = played_cards[0]['name']

        # notify all players
        await self.notify_all_players("select", {
            "round_id": self.round_id,
            "winner": winner,
            "played_cards": played_cards
        })

        self.game_state = "select"
        print("finished evaluating")

        if winner == "":
            await asyncio.sleep(5)
            await self.handle_evaluate()

class StatAttackData():
    games_data: Dict[str, Dict[str, GameData]]

    # init
    def __init__(self):
        self.games_data = {}

    def game_data_exists(self, game_type: str, game_id: str):
        return game_type in self.games_data and game_id in self.games_data[game_type]

    def get_game_data(self, game_type: str, game_id: str):
        if game_type not in self.games_data:
            self.games_data[game_type] = {}
        
        if game_id not in self.games_data[game_type]:
            self.games_data[game_type][game_id] = GameData()
        
        return self.games_data[game_type][game_id]