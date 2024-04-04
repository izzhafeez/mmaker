from typing import Dict, List
from pymongo import MongoClient
from fastapi import FastAPI, Request, Depends
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
 
@app.get("/")
def read_root():
    return {"message": "Hello from Koyeb"}

@app.get("/api/tags")
def get_tags(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker.halal.find().distinct("tag")

@app.get("/api/mrts")
def get_mrts(settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return [m for m in client.meetupmaker.mrt.find({}, {'_id': False})]

@app.post("/api/create")
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

@app.get("/api/dates/{meetup_id}")
def get_dates(meetup_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)
    return client.meetupmaker["meetup"].find_one({ "_id": ObjectId(meetup_id) }, {'_id': False})

@app.post("/api/dates/{meetup_id}")
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

@app.post("/api/confirm_date/{meetup_id}")
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

@app.post("/api/preferences/{meetup_id}")
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

@app.post("/api/recommend/{meetup_id}")
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

@app.post("/api/like/{meetup_id}")
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

@app.post("/api/confirm_timing/{meetup_id}")
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

@app.post('/api/quiz/{quiz_type}/{quiz_name}')
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

@app.get('/api/quiz/{quiz_type}/{quiz_name}')
def get_map_quiz(quiz_type: str, quiz_name: str, settings: Annotated[Settings, Depends(get_settings)]):
  connection = f"mongodb+srv://admin:{'di1ayXVEx7Gib0Do'}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
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
  return result
    
    
def convert_result_to_record(result):
    return (
        result["name"],
        result["location"],
        result["lat"],
        result["lng"],
    )