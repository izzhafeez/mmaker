from typing import Any, Dict, List
from pymongo import MongoClient
import pymongo
from fastapi import FastAPI, Depends, WebSocket
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
import asyncio
from redis_client import RedisClient
from stat_attack import StatAttackData, GameData
from math_attack import MathAttackData, MathGameData
from guess_game_instance import GuessGameInstance
from guess_game_maker import GuessGameMaker
from hedge_game_instance import HedgeGameInstance
from hedge_game_maker import HedgeGameMaker
from convo_starter import generate_cs_questions, ConvoStarterData
from burning_bridges import generate_bb_questions, BurningBridgesData
from truth_or_dare import generate_tod_questions, TruthDareData
from quip_ai import QuipData, QuipGameData
from speech_racer import SpeechRacer

from openai import OpenAI

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
    openai_api_key: str
    cities_mongo_password: str
    redis_host: str
    redis_password: str
    redis_port: int
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()

settings = Settings()
 
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

@app.get("/api/apps/meetup-maker/tags")
def get_tags(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker.halal.find().distinct("tag")

@app.get("/api/apps/meetup-maker/mrts")
def get_mrts(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return [m for m in client.meetupmaker.mrt.find({}, {'_id': False})]

@app.post("/api/apps/meetup-maker/create")
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

@app.get("/api/apps/meetup-maker/dates/{meetup_id}")
def get_dates(meetup_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) }, {'_id': False})

@app.post("/api/apps/meetup-maker/dates/{meetup_id}")
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

@app.post("/api/apps/meetup-maker/confirm_date/{meetup_id}")
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

@app.post("/api/apps/meetup-maker/preferences/{meetup_id}")
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

@app.post("/api/apps/meetup-maker/recommend/{meetup_id}")
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

@app.post("/api/apps/meetup-maker/like/{meetup_id}")
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

@app.post("/api/apps/meetup-maker/confirm_timing/{meetup_id}")
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
        players.sort(key=lambda x: (x['score']), reverse=True)
      player_found = True

  if len(players) < 10 and not player_found:
    players.append(player_data)
    players.sort(key=lambda x: (x['score']), reverse=True)
  else:
    players.append(player_data)
    players.sort(key=lambda x: (x['score']), reverse=True)
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


games_data = StatAttackData()

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
    
math_data = MathAttackData()

@app.websocket("/api/games/math-attack/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    print(f"connecting to {game_id}")
    await websocket.accept()

    if not math_data.game_data_exists(game_id):
        await websocket.send_json({
            "method": "CONNECT_ERROR"
        })

    game_data: MathGameData = math_data.get_game_data(game_id)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

redis_client = RedisClient(settings.redis_host, settings.redis_password, settings.redis_port)
mongo_client = MongoClient(f"mongodb+srv://half2720:{settings.cities_mongo_password}@cities.0jtsf.mongodb.net/?retryWrites=true&w=majority&appName=Cities&tlsCAFile=isrgrootx1.pem")

g_game_maker = GuessGameMaker(redis_client)

@app.websocket("/api/games/frequency-guessr/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: GuessGameInstance = await g_game_maker.get_game_data('frequency-guessr', game_id, redis_client)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/color-guessr/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    print(f"connecting to color-guessr {game_id}")
    await websocket.accept()

    print("getting game data")
    game_data: GuessGameInstance = await g_game_maker.get_game_data('color-guessr', game_id, redis_client)
    print("connecting")
    await game_data.handle_connect(websocket)
    print("connected")
    await game_data.handle_client(websocket)
    print("handled")

@app.websocket("/api/games/blurry-battle/{game_id}/{deck_size}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, deck_size: int):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: GuessGameInstance = await g_game_maker.get_game_data('blurry-battle', game_id, redis_client, deck_size=deck_size)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/stat-guessr/{game_id}/{deck_size}/{field_size}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, deck_size: int, field_size: int):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: GuessGameInstance = await g_game_maker.get_game_data('stat-guessr', game_id, redis_client, deck_size=deck_size, field_size=field_size)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/location-guessr/{game_id}/{deck_size}/{max_distance}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, deck_size: int, max_distance: float):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: GuessGameInstance = await g_game_maker.get_game_data('location-guessr', game_id, redis_client, deck_size=deck_size, max_distance=max_distance)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

h_game_maker = HedgeGameMaker(redis_client)

@app.websocket("/api/games/data-hedger/{game_id}/{deck_size}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, deck_size: int):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: HedgeGameInstance = await h_game_maker.get_game_data('data-hedger', game_id, redis_client, deck_size=deck_size)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/midpoint-master/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: HedgeGameInstance = await h_game_maker.get_game_data('midpoint-master', game_id, redis_client)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/number-nightmare/{game_id}/{deck_size}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, deck_size: int):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: HedgeGameInstance = await h_game_maker.get_game_data('number-nightmare', game_id, redis_client, deck_size=deck_size)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

@app.websocket("/api/games/city-hedger/{game_id}/{country}/{min_lat}/{max_lat}/{min_lng}/{max_lng}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, country: str, min_lat: float, max_lat: float, min_lng: float, max_lng: float):
    print(f"connecting to {game_id}")
    await websocket.accept()

    game_data: HedgeGameInstance = await h_game_maker.get_game_data('city-hedger', game_id, redis_client, mongo_client=mongo_client, country=country, min_lat=min_lat, max_lat=max_lat, min_lng=min_lng, max_lng=max_lng)
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

convo_data = ConvoStarterData()

class ConvoStarterRequest(BaseModel):
    purpose: str
    information: str
    quantity: int

@app.post("/api/games/convo-starter/{game_id}/generate")
async def generate_cs_questions_at_id(game_id: str, request: ConvoStarterRequest, settings: Annotated[Settings, Depends(get_settings)]):
    if convo_data.has_reached_limit():
        return {
            "error": "Limit reached"
        }

    client = OpenAI(
        api_key=settings.openai_api_key,
    )
    questions, total_tokens = await generate_cs_questions(client, request.purpose, request.information, request.quantity)
    print(questions)
    if game_id not in convo_data.games:
        convo_data.games[game_id] = []
    convo_data.games[game_id].extend(questions)
    convo_data.total_count += total_tokens

    return {
        "questions": convo_data.games[game_id],
    }

class UpdateConvoStarterRequest(BaseModel):
    questions: List[str]

@app.post("/api/games/convo-starter/{game_id}/update")
async def update_cs_questions_at_id(game_id: str, request: UpdateConvoStarterRequest):
    convo_data.games[game_id] = request.questions

    return {
        "questions": convo_data.games[game_id],
    }

@app.get("/api/games/convo-starter/{game_id}")
async def get_cs_questions_at_id(game_id: str):
    if game_id not in convo_data.games:
        return {
            "questions": []
        }
    
    return {
        "questions": convo_data.games[game_id],
    }

burning_data = BurningBridgesData()

class BurningBridgesRequest(BaseModel):
    purpose: str
    information: str
    quantity: int

@app.post("/api/games/burning-bridges/{game_id}/generate")
async def generate_bb_questions_at_id(game_id: str, request: BurningBridgesRequest, settings: Annotated[Settings, Depends(get_settings)]):
    if burning_data.has_reached_limit():
        return {
            "error": "Limit reached"
        }

    client = OpenAI(
        api_key=settings.openai_api_key,
    )
    questions, total_tokens = await generate_bb_questions(client, request.purpose, request.information, request.quantity)
    print(questions)
    if game_id not in burning_data.games:
        burning_data.games[game_id] = []
    burning_data.games[game_id].extend(questions)
    burning_data.total_count += total_tokens

    return {
        "questions": burning_data.games[game_id],
    }

class UpdateBurningBridgesRequest(BaseModel):
    questions: List[str]

@app.post("/api/games/burning-bridges/{game_id}/update")
async def update_bb_questions_at_id(game_id: str, request: UpdateBurningBridgesRequest):
    burning_data.games[game_id] = request.questions

    return {
        "questions": burning_data.games[game_id],
    }

@app.get("/api/games/burning-bridges/{game_id}")
async def get_bb_questions_at_id(game_id: str):
    if game_id not in burning_data.games:
        return {
            "questions": []
        }
    
    return {
        "questions": burning_data.games[game_id],
    }

tod_data = TruthDareData()

class TruthDareRequest(BaseModel):
    purpose: str
    information: str
    quantity: int

@app.post("/api/games/truth-or-dare/{game_id}/generate")
async def generate_tod_questions_at_id(game_id: str, request: TruthDareRequest, settings: Annotated[Settings, Depends(get_settings)]):
    if tod_data.has_reached_limit():
        return {
            "error": "Limit reached"
        }

    client = OpenAI(
        api_key=settings.openai_api_key,
    )
    truths, dares, total_tokens = await generate_tod_questions(client, request.purpose, request.information, request.quantity)
    print(truths, dares)
    if game_id not in tod_data.games:
        tod_data.games[game_id] = {
            "truths": [],
            "dares": []
        }
    tod_data.games[game_id]["truths"].extend(truths)
    tod_data.games[game_id]["dares"].extend(dares)
    tod_data.total_count += total_tokens

    return {
        "truths": tod_data.games[game_id]["truths"],
        "dares": tod_data.games[game_id]["dares"]
    }

class UpdateTruthDareRequest(BaseModel):
    truths: List[str]
    dares: List[str]

@app.post("/api/games/truth-or-dare/{game_id}/update")
async def update_tod_questions_at_id(game_id: str, request: UpdateTruthDareRequest):
    tod_data.games[game_id] = {
        "truths": request.truths,
        "dares": request.dares
    }

    return {
        "truths": tod_data.games[game_id]["truths"],
        "dares": tod_data.games[game_id]["dares"]
    }

@app.get("/api/games/truth-or-dare/{game_id}")
async def get_tod_questions_at_id(game_id: str):
    if game_id not in tod_data.games:
        return {
            "truths": [],
            "dares": []
        }
    
    return {
        "truths": tod_data.games[game_id]["truths"],
        "dares": tod_data.games[game_id]["dares"]
    }

quip_data = QuipData()

class QuipAIRequest(BaseModel):
    purpose: str
    information: str

@app.websocket("/api/games/quip-ai/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    print(f"connecting to {game_id}")
    await websocket.accept()

    if game_id not in quip_data.games:
        await websocket.send_json({
            "method": "CONNECT_ERROR"
        })
        quip_data.games[game_id] = QuipGameData(settings.openai_api_key)

    game_data: QuipGameData = quip_data.games[game_id]
    await game_data.handle_connect(websocket)
    await game_data.handle_client(websocket)

game_instances: Dict[str, SpeechRacer] = {}
for diff in ['easy', 'medium', 'difficult', 'very_difficult']:
    for i in range(6):
        key = f"{diff}-{i}"
        game_instances[key] = SpeechRacer(diff, get_settings())

# difficulty goes easy medium hard
@app.websocket("/api/speechracer/{difficulty}/{name}")
async def websocket_endpoint(websocket: WebSocket, difficulty: str, name: str):
    await websocket.accept()

    time_entered = datetime.now()
    minute = time_entered.minute
    minute = minute % 6
    key = f"{difficulty}-{minute}"

    game_instance = game_instances[key]

    if game_instance.is_inactive:
        await game_instance.generate_text()
        asyncio.create_task(game_instance.start_game())

    print(game_instance, key)

    await game_instance.handle_connection(websocket, name)
    await game_instance.handle_client(websocket, name)

class CityRequest(BaseModel):
    name: str
    code: str

# cities app
# gets cities from mongodb
@app.get("/api/apps/cities")
def get_by_name(city_request: CityRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://half2720:{settings.cities_mongo_password}@cities.0jtsf.mongodb.net/?retryWrites=true&w=majority&appName=Cities&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    name = f'^{city_request.name}$' or ''
    code = f'^{city_request.code}$' or ''
    return [c for c in client.place_names.cities.find({'name': {'$regex': name, '$options': 'i'}, 'code': {'$regex': code, '$options': 'i'}})]

class CountryBoundRequest(BaseModel):
    code: str

@app.get("/api/apps/cities/get-country-bound")
def get_country_bound(country_bound_request: CountryBoundRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://half2720:{settings.cities_mongo_password}@cities.0jtsf.mongodb.net/?retryWrites=true&w=majority&appName=Cities&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    code = country_bound_request.code or ''
    # find min and max lat and lng of all cities in the country without retrieving all cities
    pipeline = [
        {"$match": {"code": code}},  # Match the specific country by its code
        {
            "$group": {
                "_id": None,
                "minLat": {"$min": "$lat"},
                "maxLat": {"$max": "$lat"},
                "minLng": {"$min": "$lng"},
                "maxLng": {"$max": "$lng"}
            }
        }
    ]
    result = list(client.place_names.cities.aggregate(pipeline))
    
    if result:
        bounds = result[0]
        return {
            "minLat": bounds["minLat"],
            "maxLat": bounds["maxLat"],
            "minLng": bounds["minLng"],
            "maxLng": bounds["maxLng"]
        }
    else:
        return {"error": "No data found for the given country code."}

class CommentRequest(BaseModel):
    key: str
    poster: str
    datetime: str
    content: str
    # data is a json object and is optional
    data: Dict[str, Any] = {}
    # reply of is optional
    replyOf: int = None
    is_edit: int = 0
    
@app.post("/api/comments")
def post_comment(request: CommentRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    if request.is_edit:
        comment = client.meetupmaker["comments"].find_one({ "key": request.key, "poster": request.poster })
        if comment:
            client.meetupmaker["comments"].update_one({ "key": request.key, "poster": request.poster },
                                                      { "$set": { "content": request.content, "data": request.data } })
            return { "id": str(comment["_id"]) }
    
    result = client.meetupmaker["comments"].insert_one({
        "key": request.key,
        "poster": request.poster,
        "datetime": request.datetime,
        "data": request.data, 
        "content": request.content,
        "replyOf": request.replyOf,
        "likes": 0
    })
    return { "id": str(result.inserted_id) }

@app.get("/api/comments/{key}")
def get_comments(key: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    comments = [
        {
            "id": str(comment["_id"]),
            "poster": comment.get("poster", ""),
            "datetime": comment.get("datetime", ""),
            "data": comment.get("data", {}),
            "content": comment.get("content", ""),
            "replyOf": comment.get("replyOf", None),
            "likes": comment.get("likes", 0)
        }
        for comment in client.meetupmaker.comments.find({ "key": key })
    ]
    return comments

@app.post("/api/comments/{comment_id}/like")
def like_comment(comment_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    result = client.meetupmaker["comments"].update_one({ "_id": ObjectId(comment_id) },
                                              { "$inc": { "likes": 1 } })
    
@app.post("/api/comments/{comment_id}/unlike")
def unlike_comment(comment_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    client.meetupmaker["comments"].update_one({ "_id": ObjectId(comment_id) },
                                              { "$inc": { "likes": -1 } })

# delete comment
@app.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    client.meetupmaker["comments"].delete_one({ "_id": ObjectId(comment_id) })

@app.get("/api/comments/{key}/{name}")
def get_comments_by_name(key: str, name: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    comment = client.meetupmaker["comments"].find_one({ "key": key, "poster": name }, { '_id': False })
    return comment

class RateRequest(BaseModel):
    name: str
    key: str
    data: Dict[str, Any]
    fields: List[str]

# each category has multiple fields where users can rate items on
# must keep track of current rating, as well as number of ratings
@app.post("/api/rate")
def rate(request: RateRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    key = request.key
    category = request.key.split("+")[0]
    item_name = request.key.split("+")[1]
    name = request.name
    fields = request.fields
    comment = client.meetupmaker["comments"].find_one({ "key": key, "poster": name })
    item = client.meetupmaker["ratings"].find_one({ "category": category, "item": item_name })

    if item is None:
        to_add = { "category": category, "item": item_name, "count": 0 }
        for field in fields:
            to_add[field] = 0
        client.meetupmaker["ratings"].insert_one(to_add)
        item = client.meetupmaker["ratings"].find_one({ "category": category, "item": item_name })
    
    if comment is None:
        item['count'] += 1
        for field in fields:
            item[field] = (item[field] * (item['count'] - 1) + request.data[field]) / item['count']
    else:
        for field in fields:
            item[field] = (item[field] * item['count'] - comment['data'][field] + request.data[field]) / item['count']

    print(item)

    client.meetupmaker["ratings"].update_one({ "category": category, "item": item_name }, { "$set": item })

# retrieve based on category and item
@app.get("/api/rate/{category}/{item}")
def retrieve_rating(category: str, item: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    rating = client.meetupmaker["ratings"].find_one({ "category": category, "item": item }, { '_id': False })
    return rating

RATING_PER_PAGE = 10
class RetrieveManyRatingRequest(BaseModel):
    category: str
    field: str
    is_asc: int
    search_term: str
    page: int
# retrieve many based on category, and sorted by some field
# search_term is regex
@app.post("/api/rate/many")
def retrieve_many_rating(request: RetrieveManyRatingRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    category = request.category
    field = request.field
    is_asc = request.is_asc
    page = request.page
    sort_order = pymongo.ASCENDING if is_asc else pymongo.DESCENDING
    search_term = request.search_term
    ratings = list(client.meetupmaker["ratings"].find({ "category": category, "item": { "$regex": search_term, "$options": "i" } }, { '_id': False }).sort(field, sort_order).skip((page-1) * RATING_PER_PAGE).limit(RATING_PER_PAGE))
    return ratings

class RetrieveRatingRequest(BaseModel):
    category: str

# retrieve all in category
@app.get("/api/rate/all")
def retrieve_all_rating(request: RetrieveRatingRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    category = request.category
    ratings = list(client.meetupmaker["ratings"].find({ "category": category }))
    return ratings