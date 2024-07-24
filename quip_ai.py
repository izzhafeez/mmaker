import json
import random
import asyncio
from typing import List, Dict, Any
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from openai import OpenAI

user_example = """
Purpose: school of computing orientation.
Other information: they are fun loving people.
Quantity: 3.
"""

assistant_example = """
[
    "What you shouldn't say during a stand up meeting",
    "The best time to push to production",
    "The name of of an NFT platform designed for old people"
]
"""

def get_prompt(purpose, information, quantity):
  return f"""
  Purpose: {purpose}.
  Other information: the participants are {information}.
  Quantity: {quantity}.
  I want you to create prompts that allow the player to come up with a short 1-3 word funny response.
  The more bizarre the prompts, the better.
  """

def get_messages(prompt):
  return [
        {"role": "user", "content": user_example},
        {"role": "assistant", "content": assistant_example},
        {"role": "user", "content": prompt}
  ]
  
class QuipPlayerData():
    websocket: WebSocket
    points: int
    rounds_to_answer: List[int]
    vote: str
    acknowledged: bool
    gained_points: int

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.points = 0
        self.rounds_to_answer = []
        self.vote = None
        self.acknowledged = False
        self.gained_points = 0

class RoundData():
    prompt: str
    responses: Dict[str, str]
    votes: Dict[str, List[str]]

    def __init__(self, prompt: str):
        self.prompt = prompt
        self.responses = {}
        self.votes = {}

class QuipGameData():
    players: Dict[str, QuipPlayerData]
    spectators: Dict[str, QuipPlayerData]
    purpose: str
    information: str
    is_active: bool
    game_state: str
    rounds: List[RoundData]
    current_voting_round: int
    winner: str

    def __init__(self, openai_api_key: str):
        self.players = {}
        self.spectators = {}
        self.is_active = False
        self.game_state = "lobby"
        self.rounds = []
        self.client = OpenAI(
            api_key=openai_api_key
        )
        self.current_voting_round = 0
        self.winner = None

    def get_game_data(self):
        return {
            "players": self.get_player_data(),
            "spectators": {player_name: self.spectators[player_name].points for player_name in self.spectators},
            "is_active": self.is_active,
            "game_state": self.game_state,
            "rounds": [{
                "prompt": round_data.prompt,
                "responses": round_data.responses,
                "votes": round_data.votes
            } for round_data in self.rounds],
            "current_voting_round": self.current_voting_round,
            "winner": self.winner
        }
    
    async def generate_qa_questions(self):
        prompt = get_prompt(self.purpose, self.information, len(self.players))
        messages = get_messages(prompt)
        response = self.client.chat.completions.create(
          model="gpt-3.5-turbo",
          messages=messages,
          temperature=0.9,
        )

        content = response.choices[0].message.content
        print(content)
        rounds = json.loads(content)
        self.rounds = [RoundData(round) for round in rounds]
        total_tokens = response.usage.total_tokens
        return rounds, total_tokens

    def get_player_data(self):
        return {
            player_name: {
                "points": self.players[player_name].points,
                "prompts": [self.rounds[r].prompt for r in self.players[player_name].rounds_to_answer],
                "vote": self.players[player_name].vote,
                "acknowledged": self.players[player_name].acknowledged,
                "gained_points": self.players[player_name].gained_points
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
                    self.purpose = data["purpose"]
                    self.information = data["information"]
                    await self.handle_start()

                elif method == "play":
                    responses = data["responses"]
                    player_name = data["name"]
                    print(f"{player_name} played {responses}")

                    for i, response in enumerate(responses):
                        self.rounds[self.players[player_name].rounds_to_answer[i]].responses[player_name] = response

                    await self.notify_all_players("play", {})

                    print(self.rounds)
                    print([r.responses for r in self.rounds])

                    if all(len(r.responses) == 2 for r in self.rounds):
                        random.shuffle(self.rounds)
                        await self.handle_vote_start()
                
                elif method == "vote":
                    player_name = data["name"]
                    vote = data["vote"]
                    print(f"{player_name} voted for {vote}")

                    self.players[player_name].vote = vote
                    self.rounds[self.current_voting_round].votes[vote].append(player_name)

                    if all(player.vote is not None for player in self.players.values()):
                        await self.handle_vote_results()

                elif method == "acknowledge":
                    player_name = data["name"]
                    self.players[player_name].acknowledged = True
                    await self.notify_all_players("acknowledge", {})

                    if self.current_voting_round == len(self.rounds) - 1:
                        await self.handle_end()
                    
                    if all(player.acknowledged for player in self.players.values()):
                      self.current_voting_round += 1
                      await self.handle_vote_start()

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

        self.players[player_name] = QuipPlayerData(websocket)
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
        method = "start"
        if self.game_state == "vote_start":
            method = "vote_start"
        elif self.game_state == "vote_results":
            method = "vote_results"
        
        await websocket.send_json({
            "method": method,
            **self.get_game_data(),
        })

    async def handle_cannot_join(self, player_name: str, websocket: WebSocket):
        print(f"game already started, cannot join")
        self.spectators[player_name] = QuipPlayerData(websocket)
        await websocket.send_json({
            "method": "spectate",
            "message": "Game already started, but you can watch!",
            **self.get_game_data()
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
                **self.get_game_data(),
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
        self.current_voting_round = 0
        self.is_active = True
        self.winner = None
        self.game_state = "playing"
        await self.generate_qa_questions()

        # in each round, two random players will be chosen to answer
        # each player plays a total of 2 rounds
        player_names = list(self.players.keys())
        random.shuffle(player_names)

        # as left person
        for i, player_name in enumerate(player_names):
            self.players[player_name].rounds_to_answer = [i]
            self.rounds[i].votes[player_name] = []
          
        # rotate shift the player_names by one
        player_names = player_names[1:] + player_names[:1]

        # as right person
        for i, player_name in enumerate(player_names):
            self.players[player_name].rounds_to_answer.append(i % len(self.rounds))
            self.rounds[i % len(self.rounds)].votes[player_name] = []

        # notify players of their data
        for player_name in self.players:
            await self.notify_player(player_name, "start", {
                "prompts": [self.rounds[r].prompt for r in self.players[player_name].rounds_to_answer]
            })

    async def handle_vote_start(self):
        for player_name in self.players:
            self.players[player_name].vote = None
            self.players[player_name].acknowledged = False

        await self.notify_all_players("vote_start", {})

        self.game_state = "vote_start"

    async def handle_vote_results(self):
        self.game_state = "vote_results"

        # update scores based on the number of votes they received
        current_round = self.rounds[self.current_voting_round]
        for player_name in current_round.votes:
            gained_points = len(current_round.votes[player_name])
            self.players[player_name].points += gained_points
            self.players[player_name].gained_points = gained_points

        await self.notify_all_players("vote_results", {})

    async def handle_end(self):
        self.game_state = "end"

        self.current_voting_round = 0
        self.is_active = False
        self.winner = max(self.players, key=lambda x: self.players[x].points)
        await self.notify_all_players("end", {
            "winner": max(self.players, key=lambda x: self.players[x].points)
        })

class QuipData():
    games: Dict[str, QuipGameData]
    total_count: int

    # init
    def __init__(self):
        self.games = {}
        self.total_count = 0
    
    def has_reached_limit(self):
        return self.total_count >= 100000