"""作品を登録する(配信事業者が作品を載せる操作の代わり)。動画を S3 に置くと、クラウドが質問を作る。

使い方:
    tools/.venv/bin/python tools/register_video.py <id> <動画ファイル or "-"(置いてある動画のメタデータだけ変える)> \
        --title "Caminandes 3: Llamigos" --story-end 135 \
        --characters "llama: brown, long neck, big eyes; penguin: small, black and white"

- story-end: 本編の終わりの秒数(終わりのクレジットに質問を出さないため)
- characters: 登場人物の名前と見た目。名前が無いと、Nova がペンギンを「鳥」と呼んだ
"""
import argparse
from pathlib import Path

import boto3

BUCKET = "askalong-166690002196-use1"
REGION = "us-east-1"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("id")
    p.add_argument("video")
    p.add_argument("--title", required=True)
    p.add_argument("--story-end", required=True, type=float)
    p.add_argument("--characters", required=True)
    a = p.parse_args()

    s3 = boto3.Session(profile_name="default").client("s3", region_name=REGION)
    metadata = {"title": a.title, "story-end": str(a.story_end), "characters": a.characters}
    existing = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"videos/{a.id}.").get("Contents", [])]
    if a.video == "-":
        if len(existing) != 1:
            raise SystemExit(f"videos/{a.id}.* が1つに決まりません: {existing}")
        key = existing[0]
        # 自分自身に上書きコピーすると ObjectCreated が起き、質問が作り直される
        s3.copy_object(Bucket=BUCKET, Key=key, CopySource={"Bucket": BUCKET, "Key": key},
                       Metadata=metadata, MetadataDirective="REPLACE")
    else:
        key = f"videos/{a.id}{Path(a.video).suffix}"
        s3.upload_file(a.video, BUCKET, key, ExtraArgs={"Metadata": metadata})
    print(f"登録しました: s3://{BUCKET}/{key}  {metadata}")


if __name__ == "__main__":
    main()
