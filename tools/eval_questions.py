"""質問の作り方を比べる(精度の測定)。

同じ場面の区間(Rekognition の結果を S3 の shots/ から読む)に対して、設定ごとに質問を作る。
判定は人が行う: 区間ごとの3枚の絵を横に並べた画像(sheet_<film>.png、上から区間の順)と、質問の一覧を見比べる。
(別のモデルに判定させる予定だったが、Claude はアカウントで Anthropic の利用申請が要り、使えなかった。2026-10-03)

使い方:
    tools/.venv/bin/python tools/eval_questions.py out_dir
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cloud"))
import questions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUCKET = "askalong-166690002196-use1"
WINDOWS_PER_FILM = 8

FILMS = [
    {"id": "bbb", "video": ROOT / "media/BigBuckBunny_640x360.m4v", "story_end": 488,
     "characters": "bunny: a big gray-white rabbit; red squirrel: mean, red fur; flying squirrel: mean, brown; "
                   "chinchilla: mean, gray; butterfly: pink; bird: purple"},
    {"id": "caminandes3", "video": ROOT / "media/caminandes3_720p.mp4", "story_end": 135,
     "characters": "llama: brown, long neck, big eyes; penguin: small, black and white"},
]

CONFIGS = {
    # 1回目: nova-2-lite+names 10/14。2回目: nova-pro+names+2step 9/11(3枚の絵)。3回目は5枚の絵と名前の確認を足した
    "nova-pro+names+2step": {"model": "us.amazon.nova-pro-v1:0", "characters": True, "grounded": True},
    "nova-2-lite+names+2step": {"model": "us.amazon.nova-2-lite-v1:0", "characters": True, "grounded": True},
}




def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    session = boto3.Session(profile_name="default")
    bedrock = session.client("bedrock-runtime", region_name=questions.REGION)
    s3 = session.client("s3", region_name=questions.REGION)
    ffmpeg = shutil.which("ffmpeg")
    results = {name: [] for name in CONFIGS}

    with tempfile.TemporaryDirectory() as tmp:
        for film in FILMS:
            shots = json.loads(s3.get_object(Bucket=BUCKET, Key=f"shots/{film['id']}.json")["Body"].read())
            windows, _ = questions.candidate_windows([tuple(s) for s in shots], film["story_end"])
            step = max(1, len(windows) // WINDOWS_PER_FILM)
            chosen = windows[::step][:WINDOWS_PER_FILM]
            sheet_rows = []
            for i, window in enumerate(chosen):
                frames = questions.grab_frames(ffmpeg, film["video"], window, Path(tmp))
                qtype = questions.TYPE_CYCLE[i % len(questions.TYPE_CYCLE)]
                story = "(earlier events of the film)" if qtype == "recall" else "(not needed for this question)"
                for name, cfg in CONFIGS.items():
                    ask = questions.ask_grounded if cfg["grounded"] else questions.ask_nova
                    item, _ = ask(bedrock, frames, story, qtype,
                                  film["characters"] if cfg["characters"] else "", cfg["model"])
                    results[name].append({"film": film["id"], "row": i, "window": window, "type": qtype, **item})
                    shown = item.get("question") if item.get("same_scene", False) else "(同じ場面ではないので出さない)"
                    print(f"{film['id']:12} #{i} {window[0]:6.1f}s [{qtype:10}] {name:18} {shown}")
                sheet_rows.append(frames)
            write_sheet(ffmpeg, sheet_rows, out / f"sheet_{film['id']}.png", Path(tmp))

    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


def write_sheet(ffmpeg: str, rows: list[list[bytes]], path: Path, tmp: Path) -> None:
    """区間ごとに絵を横に並べ、区間を縦に積んだ1枚の画像を作る。"""
    files = []
    for r, frames in enumerate(rows):
        for c, data in enumerate(frames):
            f = tmp / f"sheet_{r:02d}_{c}.jpg"
            f.write_bytes(data)
            files.append(f)
    inputs = sum((["-i", str(f)] for f in files), [])
    per_row = len(rows[0])
    n = len(rows) * per_row
    scale = ";".join(f"[{k}:v]scale=256:144[s{k}]" for k in range(n))
    grid = "".join(f"[s{k}]" for k in range(n)) + f"xstack=inputs={n}:layout=" + "|".join(
        f"{(k % per_row) * 256}_{(k // per_row) * 144}" for k in range(n))
    subprocess.run([ffmpeg, "-v", "error", "-y", *inputs, "-filter_complex", f"{scale};{grid}", str(path)], check=True)


if __name__ == "__main__":
    main(sys.argv[1])
