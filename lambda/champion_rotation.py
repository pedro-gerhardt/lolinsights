import os
import json
import time
import boto3
import requests

"""
Environment variables expected:
  RIOT_API_KEY - Riot developer API key
  S3_BUCKET    - Target S3 bucket name
  S3_KEY       - Object key (path) to write, e.g. "cache/champion_rotation.json"
  REGION_PLATFORM - e.g. "br1" (defaults br1)

The JSON structure stored:
  {
    "timestamp": 1730000000,  # epoch seconds when fetched
    "freeChampions": [
       {"id": 11, "name": "Master Yi"}, ...
    ]
  }
"""

REGION_PLATFORM = os.getenv("REGION_PLATFORM", "br1")
REGION_ROUTING = os.getenv("REGION_ROUTING", "americas")

_session = boto3.session.Session()
s3 = _session.client("s3")

CHAMPION_MAP = {}

def load_champion_map():
    global CHAMPION_MAP
    try:
        ver_resp = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=5)
        ver_resp.raise_for_status()
        latest_version = ver_resp.json()[0]
        dd_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json"
        data = requests.get(dd_url, timeout=10).json()
        CHAMPION_MAP = {int(v['key']): v['name'] for k, v in data['data'].items()}
    except Exception as e:
        print(f"Failed loading DataDragon: {e}")
        CHAMPION_MAP = {}


def resolve_name(cid: int) -> str:
    return CHAMPION_MAP.get(cid, "Unknown")


def fetch_rotation(riot_api_key: str):
    url = f"https://{REGION_PLATFORM}.api.riotgames.com/lol/platform/v3/champion-rotations"
    headers = {"X-Riot-Token": riot_api_key}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"Riot API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    resolved = [{"id": cid, "name": resolve_name(cid)} for cid in data.get("freeChampionIds", [])]
    return resolved


def write_to_s3(bucket: str, key: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def lambda_handler(event, context):
    riot_key = os.getenv("RIOT_API_KEY")
    bucket = os.getenv("S3_BUCKET")
    key = os.getenv("S3_KEY", "cache/champion_rotation.json")

    if not riot_key:
        return {"statusCode": 500, "body": json.dumps({"error": "Missing RIOT_API_KEY"})}
    if not bucket:
        return {"statusCode": 500, "body": json.dumps({"error": "Missing S3_BUCKET"})}

    load_champion_map()
    try:
        rotation = fetch_rotation(riot_key)
        payload = {"timestamp": int(time.time()), "freeChampions": rotation}
        write_to_s3(bucket, key, payload)
        return {"statusCode": 200, "body": json.dumps({"count": len(rotation)})}
    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

if __name__ == "__main__":
    # Local debug helper
    class Dummy: pass
    print(lambda_handler({}, Dummy()))
