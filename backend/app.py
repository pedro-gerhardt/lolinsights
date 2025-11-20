import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# --- NOVO: Importar o blueprint do Swagger ---
from flask_swagger_ui import get_swaggerui_blueprint

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
REGION_PLATFORM = "br1"
REGION_ROUTING = "americas"

# --- NOVO: Configuração do Swagger UI ---
SWAGGER_URL = '/swagger'  # A URL onde a doc vai ficar (ex: localhost:6969/swagger)
API_URL = '/static/swagger.yaml'  # Onde o arquivo YAML está (na pasta static)

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "LolInsights API"
    }
)

# Registra a rota do Swagger no Flask
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
# ----------------------------------------

# ... (MANTENHA AQUI TODO O CÓDIGO DO CACHE DE CAMPEÕES E LOAD_CHAMPION_DATA) ...
CHAMPION_MAP = {}
def load_champion_data():
    # ... (código igual ao anterior) ...
    global CHAMPION_MAP
    try:
        ver_resp = requests.get("https://ddragon.leagueoflegends.com/api/versions.json")
        latest_version = ver_resp.json()[0]
        dd_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json"
        data = requests.get(dd_url).json()
        CHAMPION_MAP = {int(v['key']): v['name'] for k, v in data['data'].items()}
        print(f"DataDragon: {len(CHAMPION_MAP)} campeões carregados.")
    except Exception as e:
        print(f"Erro ao carregar DataDragon: {e}")

load_champion_data()

def get_headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_champion_name(champ_id):
    return CHAMPION_MAP.get(champ_id, "Unknown")


# ... (MANTENHA TODOS OS SEUS ENDPOINTS IGUAIS ABAIXO) ...

@app.route('/api/v1/players/identify/<game_name>/<tag_line>', methods=['GET'])
def identify_player(game_name, tag_line):
    # ... (Lógica igual) ...
    url = f"https://{REGION_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200: return jsonify(resp.json()), resp.status_code
    data = resp.json()
    return jsonify({
        "puuid": data.get("puuid"),
        "gameName": data.get("gameName"),
        "tagLine": data.get("tagLine")
    })

@app.route('/api/v1/players/<puuid>/summary', methods=['GET'])
def player_summary(puuid):
    # ... (Lógica igual) ...
    sum_url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    sum_resp = requests.get(sum_url, headers=get_headers())
    if sum_resp.status_code != 200: return jsonify(sum_resp.json()), sum_resp.status_code
    summoner_id = sum_resp.json()['id']

    league_url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    league_resp = requests.get(league_url, headers=get_headers())
    
    summary = {"tier": "UNRANKED", "rank": "", "leaguePoints": 0, "wins": 0, "losses": 0, "winrate": "0%"}
    for entry in league_resp.json():
        if entry['queueType'] == 'RANKED_SOLO_5x5':
            wins = entry['wins']
            losses = entry['losses']
            total = wins + losses
            winrate = f"{int((wins/total)*100)}%" if total > 0 else "0%"
            summary = {"tier": entry['tier'], "rank": entry['rank'], "leaguePoints": entry['leaguePoints'], "wins": wins, "losses": losses, "winrate": winrate}
            break
    return jsonify(summary)

@app.route('/api/v1/players/<puuid>/mastery', methods=['GET'])
def player_mastery(puuid):
    # ... (Lógica igual) ...
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200: return jsonify(resp.json()), resp.status_code
    data = resp.json()[:5]
    result = []
    for m in data:
        result.append({"championId": m['championId'], "championName": get_champion_name(m['championId']), "masteryLevel": m['championLevel'], "points": m['championPoints']})
    return jsonify(result)

@app.route('/api/v1/players/<puuid>/matches', methods=['GET'])
def match_history(puuid):
    # ... (Lógica igual) ...
    count = request.args.get('count', default=5, type=int)
    ids_url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
    ids_resp = requests.get(ids_url, headers=get_headers())
    if ids_resp.status_code != 200: return jsonify(ids_resp.json()), ids_resp.status_code
    match_ids = ids_resp.json()
    matches_data = []
    for mid in match_ids:
        detail_url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{mid}"
        m_resp = requests.get(detail_url, headers=get_headers())
        if m_resp.status_code == 200:
            m_data = m_resp.json()
            info = m_data['info']
            participant = next((p for p in info['participants'] if p['puuid'] == puuid), None)
            if participant:
                matches_data.append({"matchId": mid, "champion": participant['championName'], "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}", "result": "Victory" if participant['win'] else "Defeat", "timestamp": info['gameEndTimestamp']})
    return jsonify(matches_data)

@app.route('/api/v1/matches/<match_id>', methods=['GET'])
def match_details(match_id):
    url = f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    resp = requests.get(url, headers=get_headers())
    return jsonify(resp.json()), resp.status_code

@app.route('/api/v1/players/<puuid>/live', methods=['GET'])
def live_game(puuid):
    # ... (Lógica igual) ...
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/spectator/v4/active-games/by-summoner/{puuid}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 404: return jsonify({"isPlaying": False, "gameId": None, "championId": None, "championName": None, "startTime": None})
    if resp.status_code != 200: return jsonify(resp.json()), resp.status_code
    data = resp.json()
    my_participant = next((p for p in data['participants'] if p.get('puuid') == puuid), None)
    champ_id = my_participant['championId'] if my_participant else 0
    return jsonify({"isPlaying": True, "gameId": data['gameId'], "championId": champ_id, "championName": get_champion_name(champ_id), "startTime": data['gameStartTime']})

@app.route('/api/v1/champions/rotation', methods=['GET'])
def champion_rotation():
    # ... (Lógica igual) ...
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/platform/v3/champion-rotations"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200: return jsonify(resp.json()), resp.status_code
    data = resp.json()
    resolved_champs = [{"id": cid, "name": get_champion_name(cid)} for cid in data['freeChampionIds']]
    return jsonify({"freeChampions": resolved_champs})

if __name__ == '__main__':
    # Host 0.0.0.0 permite acesso externo (importante se for jogar na AWS depois)
    app.run(host='0.0.0.0', port=6969)