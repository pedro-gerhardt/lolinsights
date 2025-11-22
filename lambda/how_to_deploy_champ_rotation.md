# Champion Rotation Lambda Deployment & Weekly Schedule

Deploy `champion_rotation.py` as an AWS Lambda function and schedule it to run **every Wednesday at 06:00 (America/Sao_Paulo)**.

> Prerequisites:
> - Use AWS **CloudShell** to create the Lambda.
> - Use the AWS Console (UI) to create the EventBridge schedule.
> - Use the existing IAM role `LabRole` for everything.
> - Have an S3 bucket with read/write access for that role to the rotation object key.

---

## 1. CloudShell: Prepare Code Bundle

In CloudShell (already authenticated with an assumed role), run:

```bash
# 1. Clone or upload the repo
git clone https://github.com/pedro-gerhardt/lolinsights
cd lolinsights

# 2. Create a build directory for vendoring 'requests'
mkdir build
cp lambda/champion_rotation.py build/
pip install --target build requests

# 3. Zip the Lambda payload
cd build
zip -r ../champion_rotation.zip .
cd ..
```

## 2. CloudShell: Create Lambda Function

Export required environment variables (replace placeholders):
```bash
export RIOT_API_KEY="<YOUR_RIOT_KEY>"
export S3_BUCKET="<your-bucket>"
export S3_KEY="cache/champion_rotation.json"  # optional override
```

Retrieve the role ARN and create the function:

```bash
LABROLE_ARN=$(aws iam get-role --role-name LabRole --query 'Role.Arn' --output text)

aws lambda create-function \
  --function-name champion-rotation-fetch \
  --runtime python3.12 \
  --role "$LABROLE_ARN" \
  --handler champion_rotation.lambda_handler \
  --timeout 30 \
  --memory-size 256 \
  --zip-file fileb://champion_rotation.zip \
  --environment "Variables={RIOT_API_KEY=$RIOT_API_KEY,S3_BUCKET=$S3_BUCKET,S3_KEY=$S3_KEY,REGION_PLATFORM=br1}"
```

Verify deployment:
```bash
aws lambda get-function --function-name champion-rotation-fetch
```

Invoke test:
```bash
aws lambda invoke --function-name champion-rotation-fetch out.json
cat out.json
echo "Listing object:"; aws s3 ls s3://$S3_BUCKET/$S3_KEY || echo "Object not found yet"
echo "Downloading object for inspection:"; aws s3 cp s3://$S3_BUCKET/$S3_KEY /tmp/rotation.json && head -c 300 /tmp/rotation.json
```

Expect a `statusCode` 200 with a count of free champions and the S3 object `/$S3_KEY` present containing JSON: `{ "timestamp": <epoch>, "freeChampions": [...] }`.

## 3. Create Weekly Schedule (Wednesday 06:00 São Paulo)

Target cadence: run once per week at **06:00 America/Sao_Paulo**.

### Create EventBridge Schedule (UI)
1. Open EventBridge → Schedules → Create schedule.
2. Name: `ChampionRotationWed0600SP`.
3. Type: Recurring schedule.
4. Pattern: Cron; set Time zone `America/Sao_Paulo`; set 06:00 Wednesday.
  - Fields: Minutes `0`, Hours `6`, Day-of-week `WED`. Leave others default.
5. Target: Lambda function `champion-rotation-fetch` (ensure execution role is `LabRole`).
6. Create schedule (Console auto-adds invoke permission).
7. Confirm in Lambda → Configuration → Triggers.

## 4. Validation
1. EventBridge → Schedules/Rules: weekly rule enabled.
2. Lambda → Configuration → Triggers shows the weekly schedule.
3. (After next Wednesday 06:00 São Paulo / 09:00 UTC) CloudWatch Logs shows a new invocation.
4. S3 object timestamp updates shortly after run.
