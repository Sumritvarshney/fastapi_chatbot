from pymongo import MongoClient


client = MongoClient("mongodb://localhost:27017/")

try:
    
    client.admin.command('ping')
    print("✅ Local MongoDB is running and connected!")

    
    db = client["my_app_database"]
    users_collection = db["users"]

    print(f"Ready to work with Database: '{db.name}' and Collection: '{users_collection.name}'")

except Exception as e:
    print(f"❌ Connection failed: {e}")