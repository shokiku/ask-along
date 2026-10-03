"""Mac の上で、動画から「子への質問」を作る(クラウドと同じ処理 cloud/questions.py を使う)。

使い方:
    tools/.venv/bin/python tools/make_questions.py media/BigBuckBunny_640x360.m4v out.json 488

3つ目の引数は本編の終わりの秒数(終わりのクレジットに質問を出さないため)。Big Buck Bunny は 488 秒(フレームを見て確認)。
製品では、この処理は AWS の Lambda が動かす(cloud/handler.py)。これは開発中に試すためのもの。
"""
import json
import shutil
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cloud"))
import questions  # noqa: E402


def main(video_path: str, out_path: str, story_end: float | None = None) -> None:
    bedrock = boto3.Session(profile_name="default").client("bedrock-runtime", region_name=questions.REGION)
    result = questions.generate(bedrock, shutil.which("ffmpeg"), Path(video_path), story_end)
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"質問 {len(result['questions'])} 件 → {out_path}  トークン {result['tokens']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else None)
