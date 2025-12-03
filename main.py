from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uuid
import time
import asyncio
from datetime import datetime

app = FastAPI(title="TicTacToe Online API", version="2.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные
matchmaking_queue = []
lobbies = {}

class JoinMatchmaking(BaseModel):
    username: str

class GameMove(BaseModel):
    lobby_id: str
    player_id: str
    cell: int

def check_winner(board):
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

def get_winning_line(board):
    wins = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ]
    for line in wins:
        if board[line[0]] == board[line[1]] == board[line[2]] != " ":
            return line
    return None

def cleanup_old_lobbies():
    global lobbies
    current_time = time.time()
    expired = [lid for lid, lobby in lobbies.items() if current_time - lobby["created_at"] > 300]
    for lid in expired:
        del lobbies[lid]
        print(f"Удалено старое лобби: {lid}")

# НОВАЯ ФУНКЦИЯ: отложенный запуск нового раунда
async def start_new_round_delayed(lobby_id: str, delay: float = 3.0):
    await asyncio.sleep(delay)
    if lobby_id not in lobbies:
        return
    lobby = lobbies[lobby_id]
    lobby["games"].append({
        "board": [" "] * 9,
        "current_turn": lobby["player1"],  # X всегда начинает
        "winner": None
    })
    lobby["current_game"] += 1
    # переходим на новую игру
    lobby["winning_line"] = None     # убираем подсветку
    print(f"Новый раунд в лобби {lobby_id}! Игра #{lobby['current_game']}")

@app.get("/")
async def root():
    return {"message": "TicTacToe Online API v2.4", "status": "alive"}

@app.get("/api/health")
async def health():
    cleanup_old_lobbies()
    return {
        "status": "ok",
        "lobbies": len(lobbies),
        "queue": len(matchmaking_queue),
        "time": datetime.now().isoformat()
    }

# === МАТЧМЕЙКИНГ ===
@app.post("/api/join_matchmaking")
async def join_matchmaking(data: JoinMatchmaking):
    global matchmaking_queue
    player_id = str(uuid.uuid4())
    player = {"id": player_id, "username": data.username, "timestamp": time.time()}

    # Убираем дубли
    matchmaking_queue = [p for p in matchmaking_queue if time.time() - p["timestamp"] < 30]
    if any(p["username"] == data.username for p in matchmaking_queue):
        return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

    matchmaking_queue.append(player)

    if len(matchmaking_queue) >= 2:
        p1 = matchmaking_queue.pop(0)
        p2 = matchmaking_queue.pop(0)
        lobby_id = str(uuid.uuid4())[:8]
        lobbies[lobby_id] = {
            "lobby_id": lobby_id,
            "player1": p1["id"],
            "player1_name": p1["username"],
            "player2": p2["id"],
            "player2_name": p2["username"],
            "score": {"X": 0, "O": 0},
            "current_game": 0,
            "games": [{
                "board": [" "] * 9,
                "current_turn": p1["id"],
                "winner": None
            }],
            "winning_line": None,
            "created_at": time.time()
        }
        print(f"ЛОББИ {lobby_id}: {p1['username']} (X) vs {p2['username']} (O)")
        if p1["id"] == player_id:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p2["username"], "you_are": "X"}
        else:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p1["username"], "you_are": "O"}

    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

# === ПОЛУЧИТЬ СОСТОЯНИЕ ИГРЫ ===
@app.get("/api/game/{lobby_id}")
async def get_game(lobby_id: str):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")
    return lobby

# === СДЕЛАТЬ ХОД ===
@app.post("/api/game/{lobby_id}/move")
async def make_move(lobby_id: str, move: GameMove):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    game = lobby["games"][lobby["current_game"]]
    if game["current_turn"] != move.player_id:
        raise HTTPException(403, "Не ваш ход!")
    if game["board"][move.cell] != " ":
        raise HTTPException(400, "Клетка занята!")

    symbol = "X" if lobby["player1"] == move.player_id else "O"
    game["board"][move.cell] = symbol
    game["current_turn"] = lobby["player2"] if symbol == "X" else lobby["player1"]

    winner = check_winner(game["board"])
    response = {"success": True, "symbol": symbol, "cell": move.cell}

    if winner:
        game["winner"] = winner
        if winner != "D":
            lobby["score"][winner] += 1
            winning_line = get_winning_line(game["board"])
            lobby["winning_line"] = winning_line
            response["winning_line"] = winning_line

        response.update({
            "winner": winner,
            "game_ended": True,
            "final_score": lobby["score"],
            "new_game_in": 3.0
        })

        # ВАЖНО: запускаем новый раунд через 3 секунды
        asyncio.create_task(start_new_round_delayed(lobby_id, delay=3.0))

        print(f"Победа: {winner} в лобби {lobby_id} | Счёт: {lobby['score']} | Новый раунд через 3с")
    else:
        lobby["winning_line"] = None  # на всякий случай

    return response

# === УДАЛИТЬ ЛОББИ ===
@app.delete("/api/lobby/{lobby_id}")
async def delete_lobby(lobby_id: str):
    if lobby_id in lobbies:
        del lobbies[lobby_id]
        return {"success": True}
    raise HTTPException(404, "Lobby not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
