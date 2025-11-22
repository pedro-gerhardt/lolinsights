# lolinsights

## Champion Rotation Caching Architecture

To avoid hitting the Riot API for the weekly champion rotation on every request, the project now uses an AWS Lambda + S3 cache flow:

1. An AWS Lambda function (`lambda/champion_rotation.py`) runs on an EventBridge schedule (e.g. every 10 hours).
2. It fetches the current champion rotation from the Riot API, resolves champion IDs to names using Data Dragon, and writes a JSON file to S3.
3. JSON schema stored in S3 (key defaults to `cache/champion_rotation.json`):
	 ```json
	 {
		 "timestamp": 1730000000,
		 "freeChampions": [
			 {"id": 11, "name": "Master Yi"},
			 {"id": 157, "name": "Yasuo"}
		 ]
	 }
	 ```
4. The backend endpoint `/api/v1/champions/rotation` attempts to read this object from S3 first.
5. If the file exists and is younger than 48 hours, it serves the cached data (`source: cache`).
6. If missing, stale (>48h), or unreadable, it falls back to the Riot API, serves fresh data (`source: riot`), and attempts to refresh the S3 cache.

### Environment Variables

Backend expects:
- `RIOT_API_KEY` – Riot Developer API key.
- `S3_BUCKET` – Name of S3 bucket used for cache (optional; if absent backend always hits Riot).
- `S3_KEY_ROTATION` – Key for rotation JSON (default `cache/champion_rotation.json`).

Lambda expects additionally:
- `S3_BUCKET`, `S3_KEY` (same purpose as above) and optional `REGION_PLATFORM`.

### Scheduling the Lambda
Use EventBridge rule (cron or rate expression) like:
```
rate(10 hours)
```
Ensure the Lambda IAM role has `s3:PutObject` on the bucket/key.

### Notes
- Max age for cache is 48h to be robust if Lambda stops running.
- Riot champion rotation typically updates weekly; the 10h refresh is conservative.
- Logging indicates whether data came from cache or Riot.

