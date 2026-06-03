import random

# База имён выдуманных аналитиков (в будущем можно заменить на реальных)
ANALYSTS = [
    "Thorin", "SPUNJ", "YNk", "Maniac", "Pimp",
    "Mauisnake", "Richard Lewis", "Bubzkji", "Nooky",
]

def get_analyst_predictions(match_id, team1, team2):
    """
    Возвращает список прогнозов от аналитиков.
    Сейчас генерирует случайные данные.
    В будущем — парсинг прогнозов с HLTV или других ресурсов.
    """
    predictions = []
    for analyst in random.sample(ANALYSTS, k=random.randint(1, 3)):
        winner = random.choice([team1, team2, "Ничья"])
        confidence = random.randint(50, 100)
        predictions.append({
            "analyst": analyst,
            "winner": winner,
            "confidence": confidence,
            "comment": f"Уверен в победе {winner} на {confidence}%"
        })
    return predictions

def get_ai_prediction(team1, team2):
    """
    Заглушка ИИ-прогноза.
    В будущем — вызов модели, которая агрегирует статистику, форму команд и т.д.
    """
    # Случайный выбор с небольшим смещением в пользу первой команды
    winner = team1 if random.random() > 0.4 else team2
    probability = round(random.uniform(55, 75), 1)
    return {
        "predicted_winner": winner,
        "win_probability": probability,
        "explanation": "Модель на основе исторических данных считает, что "
                       f"{winner} имеет преимущество в {probability}%."
    }