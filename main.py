from typing import Dict
from pymongo import MongoClient
from fastapi import FastAPI, Request, Depends
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Annotated
from functools import lru_cache
import math
import os
import certifi

class RecRequest(BaseModel):
    tags: Dict[str, int]
    lat: float
    lng: float

class Settings(BaseSettings):
    mongo_password: str

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()
 
app = FastAPI()
 
@app.get("/")
def read_root():
    return {"message": "Hello from Koyeb"}

@app.post("/recommend")
def recommend(rec_request: RecRequest, settings: Annotated[Settings, Depends(get_settings)]):
    ca = certifi.where()
    connection = f"mongodb+srv://admin:{settings.mongo_password}@cluster0.1jxisbd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    client = MongoClient(connection, tlsCAFile=ca)

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