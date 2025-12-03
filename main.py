from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import uuid
import time
from datetime import datetime

app = FastAPI(title="TicTacToe Online", version="3.0")

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
    player_id: str
    cell: int

def check_winner(board):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for line in wins:
        if board[line[0]] == board[line[1]] == board[line[2]] != " ":
            return board[line[0]]
    if " " not in board:
        return "D"
    return None

def get_winning_line(board):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for line in wins:
        if board[line[0]] == board[line[1]] == board[line[2]] != " ":
            return line
    return None

def cleanup_old_lobbies():
    global lobbies
    now = time.time()
    expired = [lid for lid, l in lobbies.items() if now - l["created_at"] > 300]
    for lid in expired:
        del lobbies[lid]

@app.get("/")
async def root():
    return {"message": "TicTacToe Online API v3"}

@app.post("/api/join_matchmaking")
async def join_matchmaking(data: JoinMatchmaking):
    global matchmaking_queue, lobbies
    cleanup_old_lobbies()

    player_id = str(uuid.uuid4())
    player = {"id": player_id, "username": data.username, "timestamp": time.time()}

    matchmaking_queue = [p for p in matchmaking_queue if time.time() - p["timestamp"] < 30]
    matchmaking_queue.append(player)

    if len(matchmaking_queue) >= 2:
        p1 = matchmaking_queue.pop(0)
        p2 = matchmaking_queue.pop(0)
        lobby_id = str(uuid.uuid4())[:8]
        lobbies[lobby_id] = {
            "lobby_id": lobby_id,
            "player1": p1["id"], "player1_name": p1["username"],
            "player2": p2["id"], "player2_name": p2["username"],
            "score": {"X": 0, "O": 0},
            "current_game": 0,
            "games": [{
                "board": [" "] * 9,
                "current_turn": p1["id"],
                "winner": None
            }],
            "created_at": time.time()
        }
        if player["id"] == p1["id"]:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p2["username"], "you_are": "X"}
        else:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p1["username"], "you_are": "O"}

    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

@app.get("/api/find_game/{username}")
async def find_game(username: str):
    cleanup_old_lobbies()
    for lobby in lobbies.values():
        if lobby["player1_name"] == username or lobby["player2_name"] == username:
            you_are = "X" if lobby["player1_name"] == username else "O"
            opp = lobby["player2_name"] if you_are == "X" else lobby["player1_name"]
            return {"status": "found", "lobby_id": lobby["lobby_id"], "opponent": opp, "you_are": you_are}
    return {"status": "waiting"}

@app.get("/api/game/{lobby_id}")
async def get_game(lobby_id: str):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby: raise HTTPException(404, "Lobby not found")

    current_game = lobby["games"][lobby["current_game"]]
    if current_game["winner"] and current_game["winner"] != "D":
        lobby["winning_line"] = get_winning_line(current_game["board"])
    else:
        lobby["winning_line"] = None
    return lobby

@app.post("/api/game/{lobby_id}/move")
async def make_move(lobby_id: str, move: GameMove):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby: raise HTTPException(404, "Lobby not found")

    game = lobby["games"][lobby["current_game"]]
    if game["current_turn"] != move.player_id:
        raise HTTPException(403, "Не ваш ход!")
    if game["board"][move.cell] != " ":
        raise HTTPException(400, "Клетка занята!")

    symbol = "X" if lobby["player1"] == move.player_id else "O"
    game["board"][move.cell] = symbol
    game["current_turn"] = lobby["player2"] if symbol == "X" else lobby["player1"]

    winner = check_winner(game["board"])

    if winner:
        game["winner"] = winner
        if winner != "D":
            lobby["score"][winner] += 1
            lobby["winning_line"] = get_winning_line(game["board"])
        else:
            lobby["winning_line"] = None

        if lobby["current_game"] < 4:  # до 5 игр
            lobby["current_game"] += 1
            lobby["games"].append({
                "board": [" "] * 9,
                "current_turn": lobby["player1"],
                "winner": None
            })
            lobby["winning_line"] = None
    else:
        lobby["winning_line"] = None

    return lobby  # ← ВОЗВРАЩАЕМ ВСЁ!

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
