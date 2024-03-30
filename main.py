from typing import Dict, List
from pymongo import MongoClient
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated
from functools import lru_cache
import math
from bson.objectid import ObjectId

class RecRequest(BaseModel):
    tags: Dict[str, int]
    lat: float
    lng: float

class CreateRequest(BaseModel):
    dates: List[str]
    meetupName: str
    hostName: str
    passwordHash: str

class DateRequest(BaseModel):
    name: str
    free: List[str]

class ConfirmDateRequest(BaseModel):
    date: str
    passwordHash: str

class PreferenceRequest(BaseModel):
    name: str
    startTime: str
    endTime: str
    startLocation: str
    endLocation: str

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
        "date": "",
        "recommendations": []
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
    
    if meetup["password_hash"] != request.passwordHash:
        return { "error": "Password incorrect" }
    
    client.meetupmaker["meetup"].update_one({ "_id": ObjectId(meetup_id) },
                                            { "$set": { "date": request.date } })
    return {
        "date": request.date
    }

@app.post("/api/recommend/{}")
def recommend_halal(rec_request: RecRequest, settings: Annotated[Settings, Depends(get_settings)]):
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsCAFile=isrgrootx1.pem"
    client = MongoClient(connection)

    tags = rec_request.tags
    results = client.meetupmaker.halal.find({
        "$or": [{"tag": tag} for tag in tags]
    })

    record_tags = {}
    for result in results:
        for place in result["places"]:
            record = convert_result_to_record(place)
            if record not in record_tags:
                record_tags[record] = []
            record_tags[record].append(result["tag"])

    record_scores = {}
    def evaluate_record(record):
        if record in record_scores:
            return record_scores[record]
        dist = 111.33*((rec_request.lat-record[2])**2 + (rec_request.lng-record[3])**2)**0.5
        tag_score = sum((1+math.log(tags[tag])) for tag in record_tags[record])
        record_scores[record] = tag_score / (1 + dist)
        return record_scores[record]  

    return sorted(record_tags.keys(), key=lambda r: evaluate_record(r), reverse=True)[:50]
        
    
    
def convert_result_to_record(result):
    return (
        result["name"],
        result["location"],
        result["lat"],
        result["lng"],
    )