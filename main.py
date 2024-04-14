import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict, Tuple
from pymongo import MongoClient
from fastapi import FastAPI, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated
from functools import lru_cache
import math
import random
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import heapq
import numpy as np
import json
import uvicorn

class RecRequest(BaseModel):
    tags: Dict[str, int]
    lat: float
    lng: float

class CreateRequest(BaseModel):
    dates: List[str]
    meetupName: str
    hostName: str
    passwordHash: int

class DateRequest(BaseModel):
    name: str
    free: List[str]

class ConfirmDateRequest(BaseModel):
    date: str

class ConfirmTimingRequest(BaseModel):
    timing: str
    location: str

class PreferenceRequest(BaseModel):
    name: str
    startTime: str
    endTime: str
    startLat: float
    startLng: float
    endLat: float
    endLng: float

class RecommendRequest(BaseModel):
    name: str

class LikeRequest(BaseModel):
    name: str
    timing: str
    location: str

class QuizRequest(BaseModel):
    name: str
    score: int

class Settings(BaseSettings):
    mongo_password: str
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()
 
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
# ssl_context.load_cert_chain('/cert.pem', keyfile='/cert.pem')
 
@app.get("/")
def read_root():
    return {"message": "Hello from Koyeb"}

@app.get("/api/apps/meetupmaker/tags")
def get_tags(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker.halal.find().distinct("tag")

@app.get("/api/apps/meetupmaker/mrts")
def get_mrts(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return [m for m in client.meetupmaker.mrt.find({}, {'_id': False})]

@app.post("/api/apps/meetupmaker/create")
def create_meetup(create_request: CreateRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    result = client.meetupmaker["meetup"].insert_one({
        "meetup_name": create_request.meetupName,
        "host_name": create_request.hostName,
        "password_hash": create_request.passwordHash,
        "dates": create_request.dates,
        "participants": {},
        "preferences": {},
        "date": "",
        "recommendations": [],
        "timing": "",
        "location": {}
    })
    return { "id": str(result.inserted_id) }

@app.get("/api/apps/meetupmaker/dates/{meetup_id}")
def get_dates(meetup_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) }, {'_id': False})

@app.post("/api/apps/meetupmaker/dates/{meetup_id}")
def join_meetup(meetup_id: str, date_request: DateRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    if meetup is None:
        return { "error": "Meetup not found" }

    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { f"participants.{date_request.name}": date_request.free } })
    return {
        "participants": client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) }, {'_id': False})["participants"]
    }

@app.post("/api/apps/meetupmaker/confirm_date/{meetup_id}")
def confirm_meetup(meetup_id: str, request: ConfirmDateRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    if meetup is None:
        return { "error": "Meetup not found" }
    
    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { "date": request.date } })
    return {
        "date": request.date
    }

@app.post("/api/apps/meetupmaker/preferences/{meetup_id}")
def add_preferences(meetup_id: str, request: PreferenceRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    if meetup is None:
        return { "error": "Meetup not found" }
    
    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { f"preferences.{request.name}": {
                                                "start_time": request.startTime,
                                                "end_time": request.endTime,
                                                "start_lat": request.startLat,
                                                "start_lng": request.startLng,
                                                "end_lat": request.endLat,
                                                "end_lng": request.endLng
                                            }}})
    
MINUTES_PER_KM = 3

@app.post("/api/apps/meetupmaker/recommend/{meetup_id}")
def recommend(meetup_id: str, request: RecommendRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)

    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    if meetup is None:
        return { "error": "Meetup not found" }
    
    preferences = meetup["preferences"]

    timings = {}
    for name, pref in preferences.items():
        start = datetime.strptime(pref["start_time"], "%H:%M")
        end = datetime.strptime(pref["end_time"], "%H:%M")
        adjusted_start = start + timedelta(minutes=15-(start.minute%15))
        adjusted_end = end - timedelta(minutes=end.minute%15)
        while adjusted_start <= adjusted_end:
            timing = adjusted_start.strftime("%H:%M")
            if timing not in timings:
                timings[timing] = []
            timings[timing].append(name)
            adjusted_start += timedelta(minutes=15)

    destinations = client.meetupmaker["malls"].find({}, {"_id": False})
    destinations_dict = {destination["name"]: destination for destination in destinations}

    best_timings = sorted(timings.items(), key=lambda x: len(x[1]), reverse=True)
    recommendations = []
    blacklisted_destinations = set()
    for timing, people in best_timings:
        timing_as_datetime = datetime.strptime(timing, "%H:%M")
        destination_scores = {}
        for person in people:
            start_lat = preferences[person]["start_lat"]
            start_lng = preferences[person]["start_lng"]
            end_lat = preferences[person]["end_lat"]
            end_lng = preferences[person]["end_lng"]
            start_time = datetime.strptime(preferences[person]["start_time"], "%H:%M")
            end_time = datetime.strptime(preferences[person]["end_time"], "%H:%M")
            time_since_start = (timing_as_datetime - start_time).seconds // 60
            total_duration = (end_time - start_time).seconds // 60
            lat = start_lat + (end_lat - start_lat) * time_since_start / total_duration
            lng = start_lng + (end_lng - start_lng) * time_since_start / total_duration

            for name, destination in destinations_dict.items():
                if name in blacklisted_destinations:
                    continue

                distance = 111.33*math.sqrt((lat - destination["lat"]) ** 2 + (lng - destination["lng"]) ** 2)
                if distance > 20:
                    continue

                if name not in destination_scores:
                    destination_scores[name] = 0
                
                # add sigmoid that favours closer destinations
                destination_scores[name] += 1 / (1 + math.exp(0.1 * distance))

        for name in destination_scores:
            destination_scores[name] *= (1 + math.log(1+destinations_dict[name]["dist_score"], 10)) * (1 + math.log(1+destinations_dict[name]["stores"], 10)) * (1 + random.random())
            
        worst_destinations = heapq.nsmallest(len(destination_scores) // 4, destination_scores.items(), key=lambda x: x[1])
        for name, _ in worst_destinations:
            blacklisted_destinations.add(name)
        best_destinations = heapq.nlargest(10, destination_scores.items(), key=lambda x: x[1])
        best_timing_destinations = [(timing, destination, score) for destination, score in best_destinations]
        recommendations.extend(best_timing_destinations)

    sorted_recommendations = sorted(recommendations, key=lambda x: x[2], reverse=True)
    recommendations_as_dicts = [
        {
            "timing": recommendation[0],
            "location": recommendation[1],
            "score": recommendation[2],
            "likes": []
        } for recommendation in sorted_recommendations
    ]
    current_recommendations = meetup["recommendations"]
    liked_recommendations = [recommendation for recommendation in current_recommendations if len(recommendation["likes"]) > 0]
    # new recommendations should be of size 20
    new_recommendations = liked_recommendations
    new_recommendations_set = set()
    for rec in liked_recommendations:
        new_recommendations_set.add((rec["timing"], rec["location"]))
    for recommendation in recommendations_as_dicts:
        if len(new_recommendations) == 20:
            break
        if (recommendation["timing"], recommendation["location"]) not in new_recommendations_set:
            new_recommendations.append(recommendation)
            new_recommendations_set.add((recommendation["timing"], recommendation["location"]))
    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { "recommendations": new_recommendations }})
    return {
        "recommendations": new_recommendations
    }        

@app.post("/api/apps/meetupmaker/like/{meetup_id}")
def like(meetup_id: str, request: LikeRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    
    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    new_recommendations = []
    recommendations = meetup["recommendations"]
    for recommendation in recommendations:
        if recommendation["timing"] == request.timing and recommendation["location"] == request.location:
            if request.name not in recommendation["likes"]:
                recommendation["likes"].append(request.name)
            else:
                recommendation["likes"].remove(request.name)
        new_recommendations.append(recommendation)

    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { "recommendations": new_recommendations }})
    
    return {
        "message": "Success"
    }

@app.post("/api/apps/meetupmaker/confirm_timing/{meetup_id}")
def confirm_timing(meetup_id: str, request: ConfirmTimingRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)

    meetup = client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) })
    if meetup is None:
        return { "error": "Meetup not found" }
    
    location_details = client.meetupmaker["malls"].find_one({ "name": request.location })
    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { "timing": request.timing,
                                                        "location": { 
                                                            "name": request.location,
                                                            "lat": location_details["lat"],
                                                            "lng": location_details["lng"]
                                                         } } })
    
    return {
        "timing": request.timing,
        "location": request.location
    }

@app.post('/api/quizzes/{quiz_type}/{quiz_name}')
def quiz_score(quiz_type: str, quiz_name: str, request: QuizRequest, settings: Annotated[Settings, Depends(get_settings)]):
  connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
  client = MongoClient(connection)
  name = request.name
  score = request.score

  quiz = client.quiz[quiz_type].find_one({ 'quiz_name': quiz_name })
  if not quiz:
    client.quiz[quiz_type].insert_one({
      'quiz_name': quiz_name,
      'players': [],
      'plays': 0
    })
    quiz = client.quiz[quiz_type].find_one({ 'quiz_name': quiz_name })

  if not name:
    client.quiz[quiz_type].update_one({
      'quiz_name': quiz_name
    }, {
      '$set': {
        'plays': quiz['plays'] + 1
      }
    })
    return {}

  players = quiz['players']
  # save only the top 10 players
  player_data = {
    'name': name,
    'score': score,
  }

  player_found = False
  for player in players:
    if player['name'] == name:
      if player['score'] < score:
        player['score'] = score
        players.sort(key=lambda x: (x['score']))
      player_found = True

  if len(players) < 10 and not player_found:
    players.append(player_data)
    players.sort(key=lambda x: (x['score']))
  else:
    players.append(player_data)
    players.sort(key=lambda x: (x['score']))
    players.pop()
  
  client.quiz[quiz_type].update_one({
    'quiz_name': quiz_name
  }, {
    '$set': {
      'players': players,
      'plays': quiz['plays'] + 1
    }
  })
  return {
    'players': players,
    'plays': quiz['plays'] + 1
  }

@app.get('/api/quizzes/{quiz_type}/{quiz_name}')
def get_map_quiz(quiz_type: str, quiz_name: str, settings: Annotated[Settings, Depends(get_settings)]):
  connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
  client = MongoClient(connection)
  result = client.quiz[quiz_type].find_one({
    'quiz_name': quiz_name
  }, {"_id": 0})
  if not result:
    client.quiz[quiz_type].insert_one({
      'quiz_name': quiz_name,
      'players': [],
      'plays': 0
    })
    return {
      'quiz_name': quiz_name,
      'players': [],
      'plays': 0
    }
  
  # return sorted based on decreasing score
  players = result['players']
  players.sort(key=lambda x: (x['score']), reverse=True)
  return {
    'quiz_name': quiz_name,
    'players': players,
    'plays': result['plays']
  }

class PlayerData():
    websocket: WebSocket
    deck: List[int]
    hand: List[int]
    played_hand: List[Tuple[int, float]]
    is_alive: bool

    # init
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.deck = []
        self.hand = []
        self.played_hand = []
        self.is_alive = True

    def draw(self, hand_size: int):
        if len(self.deck) < hand_size:
            self.is_alive = False
            self.websocket.send_json({
                "method": "lose"
            })
            return
        self.hand = self.deck[:hand_size]
        self.deck = self.deck[hand_size:]
        self.played_hand = []

class GameData():
    players: Dict[str, PlayerData]
    is_active: bool
    deck_size: int
    hand_size: int
    num_played: int
    round_id: int
    game_state: str

    # init
    def __init__(self):
        self.players = {}
        self.is_active = False
        self.hands = []
        self.round_id = -1
        self.game_state = "start"

    def get_player_card_counts(self):
        return {
            player_name: len(self.players[player_name].deck) for player_name in self.players
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
        if player_name in self.players and not self.is_active:
            print(f"player {player_name} already exists")
            await websocket.send_json({
                "method": "join_error",
                "message": "Player already exists",
                "players": self.get_player_card_counts()
            })
            return
        
        if player_name in self.players and self.is_active:
            print(f"reconnecting player {player_name}")
            self.players[player_name].websocket = websocket
            if self.game_state == "start":
                await websocket.send_json({
                    "method": "next",
                    "hand": self.players[player_name].hand,
                    "players": self.get_player_card_counts()
                })

            elif self.game_state == "select":
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
                    "played_cards": played_cards
                })
            return
        
        if player_name not in self.players and self.is_active:
            print(f"game already started, cannot join")
            await websocket.send_json({
                "method": "join_error",
                "message": "Game already started",
                "players": self.get_player_card_counts()
            })
            return

        self.players[player_name] = PlayerData(websocket)
        await self.notify_all_players("join", {
            "name": player_name
        })

    async def notify_all_players(self, method: str, data: Dict[str, Any]):
        for player_name in self.players:
            if self.players[player_name].websocket is not None:
                await self.notify_player(player_name, method, data)

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        websocket = self.players[player_name].websocket
        try:
            await websocket.send_json({
                "method": method,
                "players": self.get_player_card_counts(),
                **data
            })
        except Exception as e:
            print(f"Error sending to {player_name}: {e}. Disconnecting...")
            await self.handle_disconnect(player_name)

    async def handle_disconnect(self, player_name: str):
        if player_name not in self.players:
            return
        
        self.players[player_name].websocket = None
        
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

    async def handle_start(self, deck_size: int, hand_size: int):
        self.is_active = True
        self.deck_size = deck_size
        self.hand_size = hand_size
        shuffled_deck = np.random.permutation(deck_size).tolist()
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
        self.num_played = 0
        self.round_id = -1
        self.game_state = "start"
        live_players = self.get_live_players()

        if len(live_players) < 2:
            await self.notify_all_players("end", {
                "winner": live_players[0]
            })
            self.is_active = False
            return

        for player_name in self.players:
            self.players[player_name].draw(self.hand_size)
            self.players[player_name].played_hand = []
        
        # let all the calculations happen before notifying
        for player_name in self.players:
            await self.notify_player(player_name, "next", {
                "hand": self.players[player_name].hand,
            })
        print("finished next")

    async def handle_evaluate(self):
        print("evaluating")
        self.round_id += 1
        if self.round_id >= self.hand_size:
            await self.handle_next()
            return

        played_cards = []
        for player_name in self.players:
            played_card = self.players[player_name].played_hand[self.round_id]
            played_card['name'] = player_name
            played_cards.append(played_card) # card should be {name, card_id, card_value}

        # sort by card value
        played_cards.sort(key=lambda x: x['card_value'], reverse=True)
        winner = played_cards[0]['name']

        # notify all players
        await self.notify_all_players("select", {
            "round_id": self.round_id,
            "winner": winner,
            "played_cards": played_cards
        })

        self.game_state = "select"
        print("finished evaluating")

class GamesData():
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

games_data = GamesData()

@app.websocket("/api/games/stat-attack/{game_type}/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_type: str, game_id: str):
    await websocket.accept()

    if not games_data.game_data_exists(game_type, game_id):
        await websocket.send_json({
            "method": "connect_error"
        })

    game_data: GameData = games_data.get_game_data(game_type, game_id)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)
    
    
def convert_result_to_record(result):
    return (
        result["name"],
        result["location"],
        result["lat"],
        result["lng"],
    )