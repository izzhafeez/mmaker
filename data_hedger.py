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

class HedgerPlayerData():
    websocket: WebSocket
    played_card: PlayedCard
    points: int
    acknowledged: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.played_card = None
        self.points = 0
        self.acknowledged = False

OPTIONS_SIZE = 10
ROUNDS = 10

class HedgerGameData():
    players: Dict[str, HedgerPlayerData]
    spectators: Dict[str, HedgerPlayerData]
    is_active: bool
    deck_size: int
    round_id: int
    game_state: str
    options: List[int]
    is_higher: bool

    # init
    def __init__(self):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.round_id = 1
        self.game_state = "lobby"
        self.options = []
        self.deck_size = 0
        self.is_higher = True

    def create_options(self):
        # random options
        self.options = np.random.permutation(self.deck_size).tolist()[:OPTIONS_SIZE]

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played_card": self.players[player_name].played_card.card_id if self.players[player_name].played_card is not None else None
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
                    deck_size = data["deck_size"]
                    await self.handle_start(deck_size)

                elif method == "play":
                    card_id = data["card_id"]
                    data_points = data["data"]
                    played_card = PlayedCard(card_id, data_points)
                    player_name = data["name"]
                    print(f"{player_name} played {played_card.card_id} with data {played_card.data}")
                    self.players[player_name].played_card = played_card
                    await self.notify_all_players("play", {})

                    if all(self.players[player_name].played_card is not None for player_name in self.get_live_players()):
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
            if self.game_state == "start":
                await self.handle_reconnect_start(player_name, websocket)
            return
        
        if player_name not in self.players and self.is_active:
            await self.handle_cannot_join(player_name, websocket)
            return

        self.players[player_name] = HedgerPlayerData(websocket)
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
        await websocket.send_json({
            "method": self.game_state,
            "round_id": self.round_id,
            "options": self.options,
            "players": self.get_player_data(),
            "is_higher": self.is_higher
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = HedgerPlayerData(websocket)
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
                "is_higher": self.is_higher,
                "options": self.options,
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

    async def handle_start(self, deck_size: int):
        self.is_active = True
        self.deck_size = deck_size
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

        self.is_higher = not self.is_higher
        self.game_state = "start"

        for player_name in self.get_live_players():
            self.players[player_name].played_card = None
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
        
        # let all the calculations happen before notifying
        self.create_options()
        await self.notify_all_players("next", {
            "options": self.options,
            "is_higher": self.is_higher,
            "round_id": self.round_id,
        })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # subtract score if a player has played the most popular card
        card_ids = [player.played_card.card_id for player in self.players.values()]
        card_id_counts = {card_id: card_ids.count(card_id) for card_id in card_ids}

        most_popular_card = None
        highest_count = max(card_id_counts.values())
        number_of_cards_with_highest_count = len([card_id for card_id in card_id_counts if card_id_counts[card_id] == highest_count])

        # if there is a single card that is most popular
        if number_of_cards_with_highest_count == 1:
            most_popular_card = max(card_id_counts, key=card_id_counts.get)
        

        # if a player played the most popular card, subtract score
        failed_players = []
        for player_name in self.players:
            if self.players[player_name].played_card.card_id == most_popular_card:
                self.players[player_name].points -= 3
                failed_players.append(player_name)

        # add score if player played the highest card
        num_of_data_fields = len(self.players[list(self.players.keys())[0]].played_card.data)
        
        # for each field, add score to the player with the highest value
        winners = []
        for i in range(num_of_data_fields):
            field_winners = {
                "best_value": None,
                "winners": []
            }
            value_list = [player.played_card.data[i] for player in self.players.values()]
            if self.is_higher:
                best_value = max(value_list, default=float('-inf'))
                field_winners["best_value"] = best_value
            else:  
                best_value = min(value_list, default=float('inf'))
                field_winners["best_value"] = best_value
            for player_name in self.players:
                if self.players[player_name].played_card.data[i] == best_value:
                    self.players[player_name].points += 1
                    field_winners["winners"].append(player_name)
            winners.append(field_winners)

        await self.notify_all_players("evaluate", {
            "players": self.get_player_data(),
            "winners": winners,
            "failed_players": failed_players,
            "most_popular_card": most_popular_card if most_popular_card is not None else -1,
        })

        self.round_id += 1
        print("finished evaluating")

class HedgerData():
    games_data: Dict[str, Dict[str, HedgerGameData]]

    # init
    def __init__(self):
        self.games_data = {}

    def game_data_exists(self, game_type: str, game_id: str):
        return game_type in self.games_data and game_id in self.games_data[game_type]

    def get_game_data(self, game_type: str, game_id: str):
        if game_type not in self.games_data:
            self.games_data[game_type] = {}
        
        if game_id not in self.games_data[game_type]:
            self.games_data[game_type][game_id] = HedgerGameData()
        
        return self.games_data[game_type][game_id]