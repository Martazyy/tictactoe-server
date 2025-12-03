# main.py — полный сервер TicTacToe Online (версия 3.0 — с авто-рестартом раундов)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import time
import asyncio
from datetime import datetime

app = FastAPI(title="TicTacToe Online", version="3.0")

# Разрешаем подключение с Android и любого фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные хранилища
matchmaking_queue: List[Dict[str, Any]] = []
lobbies: Dict[str, Dict[str, Any]] = {}

# === Модели ===
class JoinMatchmaking(BaseModel):
    username: str

class GameMove(BaseModel):
    lobby_id: str
    player_id: str
    cell: int

# === Вспомогательные функции ===
def check_winner(board: List[str]) -> str | None:
    wins = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ]
    for a, b, c in wins:
        if board[a] == board[b] == board[c] != " ":
            return board[a]
    if " " not in board:
        return "D"  # Ничья
    return None

def get_winning_line(board: List[str]):
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
    now = time.time()
    expired = [lid for lid, lobby in lobbies.items() if now - lobby["created_at"] > 300]
    for lid in expired:
        del lobbies[lid]
        print(f"Удалено старое лобби: {lid}")

# АВТОМАТИЧЕСКИЙ НОВЫЙ РАУНД ЧЕРЕЗ 2 СЕКУНДЫ
async def start_new_round(lobby_id: str):
    await asyncio.sleep(2.0)  # Ждём 2 секунды после победы
    if lobby_id not in lobbies:
        return
    
    lobby = lobbies[lobby_id]
    lobby["games"].append({
        "board": [" "] * 9,
        "current_turn": lobby["player1"],  # X всегда начинает
        "winner": None
    })
    lobby["current_game"] += 1
    lobby["winning_line"] = None  # Убираем подсветку
    print(f"Новый раунд в лобби {lobby_id} | Раунд #{lobby['current_game'] + 1}")

# === Маршруты ===

@app.get("/")
async def root():
    return {"message": "TicTacToe Online API v3.0 — Автоматические раунды каждые 2 сек"}

@app.get("/api/health")
async def health():
    cleanup_old_lobbies()
    return {
        "status": "alive",
        "active_lobbies": len(lobbies),
        "players_in_queue": len(matchmaking_queue),
        "timestamp": datetime.now().isoformat()
    }

# Вход в очередь поиска игры
@app.post("/api/join_matchmaking")
async def join_matchmaking(data: JoinMatchmaking):
    cleanup_old_lobbies()
    
    player_id = str(uuid.uuid4())
    player = {
        "id": player_id,
        "username": data.username,
        "timestamp": time.time()
    }

    # Убираем дубли и старых игроков
    global matchmaking_queue
    matchmaking_queue = [p for p in matchmaking_queue if time.time() - p["timestamp"] < 30]
    if any(p["username"] == data.username for p in matchmaking_queue):
        return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

    matchmaking_queue.append(player)

    # Если есть 2 игрока — создаём лобби
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

        print(f"Создано лобби {lobby_id}: {p1['username']} (X) vs {p2['username']} (O)")

        if p1["id"] == player_id:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p2["username"], "you_are": "X"}
        else:
            return {"status": "found", "lobby_id": lobby_id, "opponent": p1["username"], "you_are": "O"}

    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

# Поиск игры по имени (для восстановления соединения)
@app.get("/api/find_game/{username}")
async def find_game(username: str):
    cleanup_old_lobbies()
    
    # Проверяем очередь
    for p in matchmaking_queue[:]:
        if p["username"] == username:
            return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

    # Ищем в активных лобби
    for lobby_id, lobby in lobbies.items():
        if lobby["player1_name"] == username:
            return {
                "status": "found",
                "lobby_id": lobby_id,
                "opponent": lobby["player2_name"],
                "you_are": "X"
            }
        if lobby["player2_name"] == username:
            return {
                "status": "found",
                "lobby_id": lobby_id,
                "opponent": lobby["player1_name"],
                "you_are": "O"
            }

    return {"status": "not_found"}

# Получить текущее состояние игры
@app.get("/api/game/{lobby_id}")
async def get_game(lobby_id: str):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(status_code=404, detail="Lobby not found")

    # Обновляем winning_line только для текущего раунда
    current_idx = lobby["current_game"]
    if current_idx < len(lobby["games"]):
        game = lobby["games"][current_idx]
        if game.get("winner") and game["winner"] != "D":
            lobby["winning_line"] = get_winning_line(game["board"])
        else:
            lobby["winning_line"] = None
    else:
        lobby["winning_line"] = None

    return lobby

# Сделать ход
@app.post("/api/game/{lobby_id}/move")
async def make_move(lobby_id: str, move: GameMove):
    cleanup_old_lobbies()
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    game = lobby["games"][lobby["current_game"]]

    # Проверка хода
    if game["current_turn"] != move.player_id:
        raise HTTPException(403, "Не ваш ход!")
    if game["board"][move.cell] != " ":
        raise HTTPException(400, "Клетка занята!")

    # Делаем ход
    symbol = "X" if lobby["player1"] == move.player_id else "O"
    game["board"][move.cell] = symbol
    game["current_turn"] = lobby["player2"] if symbol == "X" else lobby["player1"]

    winner = check_winner(game["board"])
    response = {
        "success": True,
        "symbol": symbol,
        "cell": move.cell
    }

    if winner:
        game["winner"] = winner
        if winner != "D":
            lobby["score"][winner] += 1
            line = get_winning_line(game["board"])
            lobby["winning_line"] = line
            response["winning_line"] = line

        response.update({
            "winner": winner,
            "game_ended": True,
            "final_score": lobby["score"],
            "new_game_in_seconds": 2
        })

        print(f"Победа {winner} в лобби {lobby_id} | Счёт: {lobby['score']} | Новый раунд через 2 сек")

        # ВАЖНО: запускаем новый раунд через 2 секунды
        asyncio.create_task(start_new_round(lobby_id))

    else:
        lobby["winning_line"] = None

    return response

# Удаление лобби (опционально)
@app.delete("/api/lobby/{lobby_id}")
async def delete_lobby(lobby_id: str):
    if lobby_id in lobbies:
        del lobbies[lobby_id]
        return {"success": True}
    raise HTTPException(404, "Lobby not found")

# Запуск: uvicorn main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0", port=8000, reload=True)
