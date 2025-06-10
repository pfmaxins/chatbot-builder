import json
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import text

import redis
redis_client = redis.Redis(
    host="redis-9mm",
    port=6379,
    db=0,
    decode_responses=True
)

load_dotenv()

from scripts.assistant_class import Assistant
assistant = Assistant()

class MessageRequest(BaseModel):
    message: str
    phone_number: str
    typeUrl: Optional[str] = None

class MessageResponse(BaseModel):
    response: str
    typeUrl: Optional[str] = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat", response_model=MessageResponse)
async def process_message(request: MessageRequest):
    try:
        phone = request.phone_number
        state_json = redis_client.get(phone)

        # Load state from Redis if available
        if state_json is None:
            state = assistant.default_state
        else:
            state = json.loads(state_json)

        response_text, updated_state, typeUrl = assistant.get_response(request.message, state)

        redis_client.set(phone, json.dumps(updated_state))

        return MessageResponse(response=response_text, typeUrl=typeUrl)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(500, "Internal Server Error")

@app.get("/health")
def health_check():
    health = {"database": False, "redis": False}
    try:
        health["redis"] = redis_client.ping()
    except Exception as e:
        health["redis"] = f"Error: {e}"
    return health

@app.get("/get_conversation", response_model=Dict[str, List[Dict[str, str]]])
def get_conversation():
    result = {}
    for key in redis_client.keys():
        try:
            s = redis_client.get(key)
            if s:
                msgs = json.loads(s).get("messages", [])
                result[key] = msgs
        except:
            pass
    return result

@app.get("/get_conversation/{session_hash}", response_model=Dict[str, List[Dict[str, str]]])
def get_conversation_by_session(session_hash: str):
    try:
        state = redis_client.get(session_hash)
        if state:
            # Convert string to dict safely
            state_dict = json.loads(state)
            if "messages" in state_dict:
                return {session_hash: state_dict["messages"]}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        print(f"Error parsing session {session_hash}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)