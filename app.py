import threading
import time
from flask import Flask, render_template, request, abort, make_response, redirect, url_for
from parser import HLTVMatchesParser
from predictor import get_analyst_predictions, get_ai_prediction

app = Flask(__name__)
app.secret_key = "your-secret-key-here"

MATCHES_CACHE = []
LAST_UPDATE = 0
CACHE_TTL = 300  # 5 минут
lock = threading.Lock()

def remove_duplicates(matches):
    seen = set()
    unique = []
    for m in matches:
        mid = m["id"]
        if mid not in seen:
            seen.add(mid)
            unique.append(m)
    return unique

def update_matches():
    global MATCHES_CACHE, LAST_UPDATE
    while True:
        try:
            parser = HLTVMatchesParser(headless=True, timeout=30)
            matches = parser.get_matches()
            parser.close()
            with lock:
                MATCHES_CACHE = remove_duplicates(matches)
                LAST_UPDATE = time.time()
                print(f"[CACHE] Обновлено {len(MATCHES_CACHE)} матчей (после удаления дублей)")
        except Exception as e:
            print(f"[ERROR] Не удалось обновить матчи: {e}")
        time.sleep(CACHE_TTL)

threading.Thread(target=update_matches, daemon=True).start()

def get_favorite_teams():
    favs = request.cookies.get("favorite_teams", "")
    return [t.strip() for t in favs.split(",") if t.strip()]

def is_favorite_only():
    return request.cookies.get("only_favorites", "false").lower() == "true"

@app.route("/")
def index():
    with lock:
        matches = MATCHES_CACHE.copy()
    favorite_teams = get_favorite_teams()
    only_favorites = is_favorite_only()

    if only_favorites and favorite_teams:
        matches = [m for m in matches if m["team1"] in favorite_teams or m["team2"] in favorite_teams]

    live_matches = [m for m in matches if m["live"]]
    upcoming_matches = [m for m in matches if not m["live"]]

    return render_template(
        "index.html",
        live_matches=live_matches,
        upcoming_matches=upcoming_matches,
        favorite_teams=favorite_teams,
        only_favorites=only_favorites,
        last_update=LAST_UPDATE,
    )

@app.route("/team/<team_name>")
def team_profile(team_name):
    with lock:
        matches = MATCHES_CACHE.copy()
    team_matches = [m for m in matches if m["team1"] == team_name or m["team2"] == team_name]
    if not team_matches:
        abort(404, description="Команда не найдена или нет матчей")

    live = [m for m in team_matches if m["live"]]
    upcoming = [m for m in team_matches if not m["live"]]

    favorite_teams = get_favorite_teams()
    is_fav = team_name in favorite_teams

    logo = None
    for m in team_matches:
        if m["team1"] == team_name and m.get("team1Logo"):
            logo = m["team1Logo"]
            break
        if m["team2"] == team_name and m.get("team2Logo"):
            logo = m["team2Logo"]
            break

    return render_template(
        "team.html",
        team_name=team_name,
        logo=logo,
        live_matches=live,
        upcoming_matches=upcoming,
        is_favorite=is_fav,
        favorite_teams=favorite_teams,
    )

@app.route("/tournaments")
def tournaments_list():
    with lock:
        matches = MATCHES_CACHE.copy()
    tournaments = {}
    for m in matches:
        eid = m.get("eventId")
        if not eid:
            continue
        if eid not in tournaments:
            tournaments[eid] = {"eventId": eid, "name": m["event"], "count": 0}
        tournaments[eid]["count"] += 1
    tour_list = sorted(tournaments.values(), key=lambda x: x["name"])
    return render_template("tournaments.html", tournaments=tour_list)

@app.route("/tournament/<event_id>")
def tournament_matches(event_id):
    with lock:
        matches = [m for m in MATCHES_CACHE if m.get("eventId") == event_id]
    if not matches:
        abort(404, description="Турнир не найден или нет матчей")
    live = [m for m in matches if m["live"]]
    upcoming = [m for m in matches if not m["live"]]
    favorite_teams = get_favorite_teams()
    return render_template(
        "tournament.html",
        event_name=matches[0]["event"],
        live_matches=live,
        upcoming_matches=upcoming,
        favorite_teams=favorite_teams,
    )

@app.route("/set_favorite")
def set_favorite():
    team = request.args.get("team", "").strip()
    if not team:
        return "Team parameter required", 400
    favs = get_favorite_teams()
    if team in favs:
        favs.remove(team)
    else:
        favs.append(team)
    resp = make_response(redirect(request.referrer or url_for("index")))
    resp.set_cookie("favorite_teams", ",".join(favs), max_age=60*60*24*365, path="/")
    return resp

@app.route("/toggle_only_favorites")
def toggle_only_favorites():
    current = is_favorite_only()
    new_val = "false" if current else "true"
    resp = make_response(redirect(request.referrer or url_for("index")))
    resp.set_cookie("only_favorites", new_val, max_age=60*60*24*365, path="/")
    return resp

@app.route("/match/<match_id>")
def match_detail(match_id):
    with lock:
        match = next((m for m in MATCHES_CACHE if m["id"] == match_id), None)
    if not match:
        abort(404, description="Матч не найден")

    # Загружаем детали матча (составы, карты)
    match_details = None
    if match.get("url"):
        try:
            detail_parser = HLTVMatchesParser(headless=True, timeout=30)
            match_details = detail_parser.fetch_match_details(match["url"])
            detail_parser.close()
        except Exception as e:
            print(f"[ERROR] Не удалось загрузить детали матча: {e}")

    analysts = get_analyst_predictions(match_id, match["team1"], match["team2"])
    ai_pred = get_ai_prediction(match["team1"], match["team2"])
    favorite_teams = get_favorite_teams()

    return render_template(
        "match.html",
        match=match,
        analysts=analysts,
        ai_prediction=ai_pred,
        favorite_teams=favorite_teams,
        match_details=match_details,
    )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)