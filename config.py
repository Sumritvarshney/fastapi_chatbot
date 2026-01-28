from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "Times_Internet")
client=MongoClient(MONGO_URL)
db=client[DB_NAME]
users_collections=db["users"]
items_collection=db["items"]