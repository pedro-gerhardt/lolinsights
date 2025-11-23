import os
import json
import time
import requests
import boto3
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from flask_swagger_ui import get_swaggerui_blueprint

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
REGION_PLATFORM = "br1"
REGION_ROUTING = "americas"
S3_BUCKET = os.getenv("S3_BUCKET")  # bucket that receives lambda cache (read-only)
S3_KEY_ROTATION = os.getenv("S3_KEY_ROTATION", "cache/champion_rotation.json")  # key to read rotation JSON
ROTATION_MAX_AGE_SECONDS = 7 * 24 * 3600  # 1 week

_s3_client = None
def get_s3():
    global _s3_client
    if _s3_client is None:
        try:
            _s3_client = boto3.client("s3")
        except Exception:
            _s3_client = None
    return _s3_client

# --- ROTA DINÂMICA DO SWAGGER SPEC ---
# O Swagger UI vai ler essa rota em vez do arquivo estático
@app.route('/swagger-spec')
def swagger_spec_dynamic():
    # 1. Descobre o IP atual
    current_ip = get_public_ip()
    
    # 2. Renderiza o arquivo YAML trocando {{ server_ip }} pelo valor real
    return render_template('swagger.yaml', server_ip=current_ip)

# --- CONFIGURAÇÃO DO SWAGGER UI ---
SWAGGER_URL = '/swagger'
# IMPORTANTE: A API_URL agora aponta para a rota python, não para o arquivo estático
API_URL = '/swagger-spec' 

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "LolInsights API"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

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
    league_url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
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
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code == 404: return jsonify({"isPlaying": False, "gameId": None, "championId": None, "championName": None, "startTime": None})
    if resp.status_code != 200: return jsonify(resp.json()), resp.status_code
    data = resp.json()
    my_participant = next((p for p in data['participants'] if p.get('puuid') == puuid), None)
    champ_id = my_participant['championId'] if my_participant else 0
    return jsonify({"isPlaying": True, "gameId": data['gameId'], "championId": champ_id, "championName": get_champion_name(champ_id), "startTime": data['gameStartTime']})

@app.route('/api/v1/champions/rotation', methods=['GET'])
def champion_rotation():
    # Try cached file in S3 first
    s3 = get_s3()
    cache_miss = True
    if s3 and S3_BUCKET:
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY_ROTATION)
            raw = obj['Body'].read().decode('utf-8')
            cached = json.loads(raw)
            ts = cached.get('timestamp', 0)
            age = time.time() - ts
            if age <= ROTATION_MAX_AGE_SECONDS and 'freeChampions' in cached:
                return jsonify({"source": "cache", "freeChampions": cached['freeChampions']})
            # Cache exists but stale; treat as hit (no rewrite) and refetch Riot
            cache_miss = False
        except Exception:
            pass

    # Fetch from Riot API as fallback or refresh
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/platform/v3/champion-rotations"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200:
        return jsonify(resp.json()), resp.status_code
    data = resp.json()
    resolved_champs = [{"id": cid, "name": get_champion_name(cid)} for cid in data.get('freeChampionIds', [])]

    return jsonify({"source": "riot", "freeChampions": resolved_champs})

def get_public_ip():
    """
    Tenta obter o IP público da EC2 usando IMDSv2.
    Retorna 'localhost' se falhar (ex: rodando localmente).
    """
    try:
        # 1. Obter o Token de Sessão (Obrigatório no IMDSv2)
        token_url = "http://169.254.169.254/latest/api/token"
        headers = {"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
        token = requests.put(token_url, headers=headers, timeout=2).text

        # 2. Usar o token para pegar o IP Público
        meta_url = "http://169.254.169.254/latest/meta-data/public-ipv4"
        header_auth = {"X-aws-ec2-metadata-token": token}
        public_ip = requests.get(meta_url, headers=header_auth, timeout=2).text
        
        return public_ip
    except Exception:
        # Se der erro (timeout), assume que estamos rodando local
        return "localhost"

if __name__ == '__main__':
    # Busca o IP antes de iniciar
    current_ip = get_public_ip()
    port = 6969
    
    print("-" * 40)
    print(f"🚀 SERVIDOR INICIADO!")
    print(f"🏠 Local:   http://localhost:{port}")
    if current_ip != "localhost":
        print(f"☁️  AWS EC2: http://{current_ip}:{port}")
    print("-" * 40)
    
    # Adicionei um endpoint para checar o IP via API
    @app.route('/api/v1/config', methods=['GET'])
    def get_server_config():
        return jsonify({
            "server_ip": current_ip,
            "environment": "aws" if current_ip != "localhost" else "local"
        })

    app.run(host='0.0.0.0', port=port)
