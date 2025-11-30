from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uuid
import time
import json
from datetime import datetime

app = FastAPI(title="🎮 TicTacToe Online API", version="2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⭐ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
matchmaking_queue = []
lobbies = {}

class JoinMatchmaking(BaseModel):
    username: str

class GameMove(BaseModel):
    lobby_id: str
    player_id: str
    cell: int

def check_winner(board):
    """Проверка победы"""
    wins = [
        [0,1,2], [3,4,5], [6,7,8], # Горизонтали
        [0,3,6], [1,4,7], [2,5,8], # Вертикали
        [0,4,8], [2,4,6] # Диагонали
    ]
    for line in wins:
        if board[line[0]] == board[line[1]] == board[line[2]] != " ":
            return board[line[0]]
    if " " not in board:
        return "D" # Ничья
    return None

def cleanup_old_lobbies():
    """Очистка старых лобби (>5 минут)"""
    global lobbies
    current_time = time.time()
    expired = []
    for lobby_id, lobby in lobbies.items():
        if current_time - lobby["created_at"] > 300: # 5 минут
            expired.append(lobby_id)
    for lobby_id in expired:
        del lobbies[lobby_id]
        print(f"🧹 Удалено старое лобби: {lobby_id}")

@app.get("/")
async def root():
    return {"message": "🎮 TicTacToe Online API ✅", "status": "alive"}

@app.get("/api/health")
async def health():
    cleanup_old_lobbies()
    return {
        "status": "alive",
        "lobbies": len(lobbies),
        "queue": len(matchmaking_queue),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/queue_status")
async def queue_status():
    global matchmaking_queue
    cleanup_old_lobbies()
   
    active_queue = [p for p in matchmaking_queue if time.time() - p["timestamp"] < 30]
   
    print(f"📊 СТАТУС ОЧЕРЕДИ: {len(active_queue)} игроков")
    return {
        "queue_size": len(active_queue),
        "active_players": [p["username"] for p in active_queue]
    }

@app.post("/api/join_matchmaking")
async def join_matchmaking(data: JoinMatchmaking):
    global matchmaking_queue
   
    player_id = str(uuid.uuid4())
    player = {
        "id": player_id,
        "username": data.username,
        "timestamp": time.time()
    }
   
    # ⭐ НЕ ДУБЛИРУЕМ ИГРОКОВ
    for p in matchmaking_queue:
        if p["username"] == data.username and (time.time() - p["timestamp"]) < 10:
            print(f"⏳ Игрок {data.username} уже в очереди")
            return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}
   
    # ⭐ ОЧИСТКА СТАРЫХ
    matchmaking_queue = [p for p in matchmaking_queue if time.time() - p["timestamp"] < 30]
   
    matchmaking_queue.append(player)
    print(f"👥 Очередь: {len(matchmaking_queue)} игроков - {data.username}")
   
    # ⭐ СОЗДАЁМ ПАРУ ПРИ 2+ ИГРОКАХ
    if len(matchmaking_queue) >= 2:
        player1 = matchmaking_queue.pop(0)
        player2 = matchmaking_queue.pop(0)
       
        lobby_id = str(uuid.uuid4())[:8]
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
                "current_turn": player1["id"], # X начинает
                "winner": None
            }],
            "created_at": time.time()
        }
       
        print(f"🎮 ✅ ЛОББИ {lobby_id}: {player1['username']} (X) vs {player2['username']} (O)")
       
        # ⭐ ВОЗВРАЩАЕМ ЛОББИ ТЕКУЩЕМУ ИГРОКУ
        if player1["id"] == player_id:
            return {
                "status": "found",
                "lobby_id": lobby_id,
                "opponent": player2["username"],
                "you_are": "X"
            }
        elif player2["id"] == player_id:
            return {
                "status": "found",
                "lobby_id": lobby_id,
                "opponent": player1["username"],
                "you_are": "O"
            }
   
    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

@app.get("/api/find_game/{username}")
async def find_game(username: str):
    """🔥 НАЙТИ ГОТОВОЕ ЛОББИ ПО ИМЕНИ ИГРОКА"""
    global lobbies, matchmaking_queue
    
    cleanup_old_lobbies()
    
    # 1. Проверяем, есть ли этот игрок в очереди
    for player in matchmaking_queue:
        if player["username"] == username:
            # Если в очереди 2+ игрока - создаем лобби
            if len(matchmaking_queue) >= 2:
                player1 = matchmaking_queue.pop(0)
                player2 = matchmaking_queue.pop(0)
               
                lobby_id = str(uuid.uuid4())[:8]
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
               
                print(f"🎮 ✅ ЛОББИ {lobby_id}: {player1['username']} (X) vs {player2['username']} (O)")
               
                if player1["username"] == username:
                    return {
                        "status": "found",
                        "lobby_id": lobby_id,
                        "opponent": player2["username"],
                        "you_are": "X"
                    }
                else:
                    return {
                        "status": "found",
                        "lobby_id": lobby_id,
                        "opponent": player1["username"],
                        "you_are": "O"
                    }
            else:
                return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}
    
    # 2. Ищем готовое лобби для этого игрока
    for lobby_id, lobby in lobbies.items():
        if (lobby["player1_name"] == username or lobby["player2_name"] == username) and \
           (time.time() - lobby["created_at"] < 60):  # 1 минута
           
            print(f"🔍 НАЙДЕНО ЛОББИ {lobby_id} для {username}")
           
            if lobby["player1_name"] == username:
                return {
                    "status": "found",
                    "lobby_id": lobby_id,
                    "opponent": lobby["player2_name"],
                    "you_are": "X"
                }
            else:
                return {
                    "status": "found",
                    "lobby_id": lobby_id,
                    "opponent": lobby["player1_name"],
                    "you_are": "O"
                }
    
    return {"status": "waiting", "players_in_queue": len(matchmaking_queue)}

@app.get("/api/game/{lobby_id}")
async def get_game(lobby_id: str):
    global lobbies
    cleanup_old_lobbies()
   
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(status_code=404, detail="Lobby not found")
   
    print(f"🔍 {lobby_id}: запрос состояния")
    return lobby

@app.post("/api/game/{lobby_id}/move")
async def make_move(lobby_id: str, move: GameMove):
    global lobbies
    cleanup_old_lobbies()
   
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(status_code=404, detail="Lobby not found")
   
    current_game = lobby["current_game"]
    if current_game >= len(lobby["games"]):
        raise HTTPException(status_code=400, detail="Game not found")
   
    game = lobby["games"][current_game]
   
    # ПРОВЕРКИ
    if game["current_turn"] != move.player_id:
        raise HTTPException(status_code=403, detail=f"❌ Не ваш ход!")
    if game["board"][move.cell] != " ":
        raise HTTPException(status_code=400, detail="❌ Клетка занята!")
   
    # СИМВОЛ
    symbol = "X" if lobby["player1"] == move.player_id else "O"
    game["board"][move.cell] = symbol
   
    # ПЕРЕКЛЮЧЕНИЕ ХОДА
    game["current_turn"] = lobby["player2"] if symbol == "X" else lobby["player1"]
   
    # ПРОВЕРКА ПОБЕДЫ/НИЧЬИ
    winner = check_winner(game["board"])
    response = {"success": True, "symbol": symbol, "cell": move.cell}
   
    if winner:
        game["winner"] = winner
        if winner != "D":  # Не ничья
            lobby["score"][winner] = lobby["score"].get(winner, 0) + 1
       
        print(f"🏆 {lobby_id}: {winner} {'победил' if winner != 'D' else 'ничья'}! Счёт: {lobby['score']}")
       
        # ⭐ ПОКАЗЫВАЕМ РЕЗУЛЬТАТ
        response["winner"] = winner
        response["game_ended"] = True
        response["final_score"] = lobby["score"]
        
        # ✅ НОВАЯ ИГРА (до 5 игр)
        if lobby["current_game"] < 4:
            lobby["current_game"] += 1
            lobby["games"].append({
                "board": [" "] * 9,
                "current_turn": lobby["player1"],  # X всегда начинает
                "winner": None
            })
            response["new_game_available"] = True
            response["next_game_index"] = lobby["current_game"]
        else:
            response["series_ended"] = True
    else:
        print(f"✅ {lobby_id}: {symbol} в клетку {move.cell}")
   
    return response

@app.delete("/api/lobby/{lobby_id}")
async def delete_lobby(lobby_id: str):
    global lobbies
    if lobby_id in lobbies:
        del lobbies[lobby_id]
        print(f"🗑️ Лобби удалено: {lobby_id}")
        return {"success": True}
    raise HTTPException(status_code=404, detail="Lobby not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
