from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uuid
import time
import json
import sqlite3
from datetime import datetime

app = FastAPI(title="TicTacToe Online")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

matchmaking_queue = []
lobbies = {}

class JoinMatchmaking(BaseModel):
    username: str

class GameMove(BaseModel):
    lobby_id: str
    cell: int
    player_id: str

def check_winner(board):
    """Проверка победы"""
    wins = [
        [0,1,2], [3,4,5], [6,7,8],  
        [0,3,6], [1,4,7], [2,5,8],  
        [0,4,8], [2,4,6]            
    ]
    for line in wins:
        if board[line[0]] == board[line[1]] == board[line[2]] != " ":
            return board[line[0]]
    if " " not in board:
        return "D"  
    return None

@app.get("/")
async def root():
    return {"message": "🎮 TicTacToe Online API ✅"}

@app.get("/api/health")
async def health():
    return {"status": "alive", "lobbies": len(lobbies)}

@app.post("/api/join_matchmaking")
async def join_matchmaking(data: JoinMatchmaking):
    global matchmaking_queue
    
    player_id = str(uuid.uuid4())
    player = {"id": player_id, "username": data.username, "timestamp": time.time()}
    matchmaking_queue.append(player)
    
    if len(matchmaking_queue) >= 2:
        player1 = matchmaking_queue.pop(0)
        player2 = matchmaking_queue.pop(0)
        
        lobby_id = str(uuid.uuid4())[:8]
        global lobbies
        lobbies[lobby_id] = {
            "lobby_id": lobby_id,
            "player1": player1["id"],
            "player1_name": player1["username"],
            "player2": player2["id"],
            "player2_name": player2["username"],
            "score": {"X": 0, "O": 0},
            "current_game": 0,
            "games": [{
                "board": [" "] * 9,
                "current_turn": player1["id"],
                "winner": None
            }],
            "created_at": time.time()
        }
        
        return {
            "status": "found",
            "lobby_id": lobby_id,
            "opponent": player2["username"],
            "you_are": "X"
        }
    
    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

@app.get("/api/match_status")
async def match_status():
    global matchmaking_queue
    return {
        "status": "waiting" if matchmaking_queue else "empty", 
        "players_in_queue": len(matchmaking_queue)
    }

@app.get("/api/game/{lobby_id}")
async def get_game(lobby_id: str):
    global lobbies
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")
    return lobby

@app.post("/api/game/{lobby_id}/move")
async def make_move(lobby_id: str, move: GameMove):
    global lobbies
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")
    
    current_game = lobby["current_game"]
    game = lobby["games"][current_game]
    
    if game["current_turn"] != move.player_id:
        raise HTTPException(403, "❌ Not your turn!")
    if game["board"][move.cell] != " ":
        raise HTTPException(400, "❌ Cell occupied!")
    
    symbol = "X" if lobby["player1"] == move.player_id else "O"
    game["board"][move.cell] = symbol
    game["current_turn"] = lobby["player2"] if lobby["player1"] == move.player_id else lobby["player1"]
    
    winner = check_winner(game["board"])
    new_game = False
    
    if winner:
        game["winner"] = winner
        lobby["score"][winner] += 1
        lobby["current_game"] += 1
        
        if lobby["current_game"] < 5: 
            lobby["games"].append({
                "board": [" "] * 9,
                "current_turn": lobby["player1"],
                "winner": None
            })
            new_game = True
    
    return {
        "success": True,
        "winner": winner,
        "new_game": new_game,
        "score": lobby["score"]
    }

@app.delete("/api/lobby/{lobby_id}")
async def delete_lobby(lobby_id: str):
    global lobbies
    if lobby_id in lobbies:
        del lobbies[lobby_id]
        return {"success": True}
    raise HTTPException(404, "Lobby not found")
