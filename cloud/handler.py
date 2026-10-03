"""Ask-Along のクラウド側(AWS Lambda)。

関数は2つで、同じ zip を使う:
- on_upload: S3 の videos/<id>.mp4 に動画が置かれたら動く。Rekognition で場面を区切り、Nova で質問を作り、
  questions/<id>.json に置く。
  本編の終わりの秒数は、動画のメタデータ x-amz-meta-story-end で渡す(終わりのクレジットに質問を出さないため)。
  登場人物は x-amz-meta-characters で渡す("llama: brown, long neck; penguin: small, black and white")。
  配信事業者が作品を登録するときに入れる想定(名前が無いと、Nova がペンギンを「鳥」と呼んだ)。
- api: Lambda の関数 URL。テレビのアプリが呼ぶ。
  GET ?action=titles          … 作品の一覧(題名・動画の一時 URL・質問ができているか)
  GET ?action=questions&id=X  … その作品の質問の一覧
  POST {"action": "review", "id": X, "reviews": [{"t_ms": ..., "review": "kept" | "rejected"}]}
                              … 配信の担当者が見直した結果を保存する。外した質問はアプリに出ない
  POST {"action": "skip", "id": X, "t_ms": ...}
                              … 親がテレビで質問を飛ばした(戻るボタン)。SKIPS_TO_REJECT 回で出さなくなる
  動画は公開せず、6時間だけ有効な署名つき URL で渡す。
"""
import base64
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import unquote_plus

import boto3
import imageio_ffmpeg

import questions

BUCKET = os.environ["BUCKET"]
VIDEO_PREFIX = "videos/"
QUESTION_PREFIX = "questions/"
SHOT_PREFIX = "shots/"  # Rekognition の場面検出の結果(作り直すときに検出をやり直さないため)
URL_EXPIRES_SEC = 6 * 3600
SKIPS_TO_REJECT = 3  # 合わない質問を、親が飛ばした回数がこれに達したら出さない

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=questions.REGION)
rekognition = boto3.client("rekognition", region_name=questions.REGION)


def on_upload(event, _context):
    for record in event["Records"]:
        key = unquote_plus(record["s3"]["object"]["key"])
        title_id = Path(key).stem
        head = s3.head_object(Bucket=BUCKET, Key=key)
        story_end = head["Metadata"].get("story-end")
        shots = questions.shots_by_rekognition(rekognition, BUCKET, key)
        s3.put_object(Bucket=BUCKET, Key=f"{SHOT_PREFIX}{title_id}.json", Body=json.dumps(shots).encode(),
                      ContentType="application/json")
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / Path(key).name
            s3.download_file(BUCKET, key, str(video))
            result = questions.generate(bedrock, imageio_ffmpeg.get_ffmpeg_exe(), video,
                                        float(story_end) if story_end else None, shots=shots,
                                        characters=head["Metadata"].get("characters", ""))
        result["title"] = head["Metadata"].get("title", title_id)
        s3.put_object(Bucket=BUCKET, Key=f"{QUESTION_PREFIX}{title_id}.json",
                      Body=json.dumps(result, ensure_ascii=False).encode(), ContentType="application/json")
        print(f"{title_id}: 質問 {len(result['questions'])} 件、トークン {result['tokens']}")


def api(event, _context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "POST":
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):  # Content-Type が JSON でないと、関数 URL は本文を base64 で渡す
            body = base64.b64decode(body).decode()
        return _post(json.loads(body))
    params = event.get("queryStringParameters") or {}
    action = params.get("action")
    if action == "titles":
        return _json(200, {"titles": _titles()})
    if action == "questions" and params.get("id"):
        try:
            body = s3.get_object(Bucket=BUCKET, Key=f"{QUESTION_PREFIX}{params['id']}.json")["Body"].read()
        except s3.exceptions.NoSuchKey:
            return _json(404, {"error": "questions not ready"})
        return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": body.decode()}
    return _json(400, {"error": "unknown action"})


def _post(body: dict) -> dict:
    action = body.get("action")
    if action not in ("review", "skip") or not body.get("id"):
        return _json(400, {"error": "unknown action"})
    key = f"{QUESTION_PREFIX}{body['id']}.json"
    try:
        doc = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return _json(404, {"error": "questions not ready"})
    if action == "review":
        decisions = {r["t_ms"]: r["review"] for r in body.get("reviews", [])
                     if r.get("review") in ("kept", "rejected")}
        for q in doc["questions"]:
            if q["t_ms"] in decisions:
                q["review"] = decisions[q["t_ms"]]
        result = {"saved": len(decisions)}
    else:
        q = next((q for q in doc["questions"] if q["t_ms"] == body.get("t_ms")), None)
        if q is None:
            return _json(404, {"error": "question not found"})
        q["skips"] = q.get("skips", 0) + 1
        if q["skips"] >= SKIPS_TO_REJECT:
            q["review"] = "rejected"
        result = {"skips": q["skips"], "review": q["review"]}
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(doc, ensure_ascii=False).encode(),
                  ContentType="application/json")
    return _json(200, result)


def _titles() -> list[dict]:
    ready = {Path(o["Key"]).stem for o in _list(QUESTION_PREFIX)}
    titles = []
    for obj in _list(VIDEO_PREFIX):
        title_id = Path(obj["Key"]).stem
        meta = s3.head_object(Bucket=BUCKET, Key=obj["Key"])["Metadata"]
        titles.append({
            "id": title_id,
            "title": meta.get("title", title_id),
            "video_url": s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": obj["Key"]},
                                                   ExpiresIn=URL_EXPIRES_SEC),
            "questions_ready": title_id in ready,
        })
    return sorted(titles, key=lambda t: t["title"])


def _list(prefix: str) -> list[dict]:
    return [o for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])
            if not o["Key"].endswith("/")]


def _json(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}
