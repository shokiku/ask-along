"""デモ動画(英語、3分以内)を組み立てる。

素材:
- slides/*.png  … 説明のスライド(slides/*.html を Chrome で撮ったもの)
- slides/cap_*.png … デモ映像に重ねる字幕(背景は透明)
- raw/seg1.mp4, raw/seg2.mp4 … Android TV エミュレータで撮った操作の録画(adb shell screenrecord、音なし)
  raw/seg*_cfr.mp4 … 上をキーフレームの多い形式に変換したもの(切り出しに使う)
- audio/*.mp3 … Amazon Polly のナレーション(narration.json の文)

使い方: ../tools/.venv/bin/python build.py   → build/ask-along-demo.mp4
"""
import json
import subprocess
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
OUT = HERE / "build"
FPS = 30
GAP = 0.25  # ナレーションどうしの最短の間(秒)

# デモ部分の語り。映像の中でその動きが起きる時刻(デモ部分の先頭からの秒)に合わせて置く
DEMO_LINES = [
    ("d1", 0.5, "Pick a show."),
    ("d2", 8.0, "As you watch, a question for your child appears, about what is on screen right now."),
    ("d3", 10.0, "Press OK, and the show pauses while your child answers."),
    ("d4", 16.0, "Press OK again to keep watching."),
    ("d5", 25.0, "If a question doesn't fit, press Back to skip it. "
                 "Skips are reported, and a question skipped three times is removed."),
]
# デモ部分の映像: (ファイル, 開始秒, 終了秒)。raw/events*.txt の時刻から選んだ
# 録画そのもの(raw/seg*.mp4)はキーフレームが少なく、途中から切ると冒頭が黒くなったので、
# 毎秒キーフレームを入れた *_cfr.mp4(ffmpeg -vf fps=30 -g 30)を使う
DEMO_CLIPS = [("raw/seg1_cfr.mp4", 3, 10), ("raw/seg2_cfr.mp4", 18, 35), ("raw/seg2_cfr.mp4", 66, 74)]
# デモ部分の字幕: (画像, 表示開始, 表示終了) デモ部分の先頭からの秒
DEMO_CAPTIONS = [("cap_list", 0, 7), ("cap_card", 7, 10), ("cap_ask", 10, 16), ("cap_resume", 16, 20),
                 ("cap_card", 24, 26), ("cap_skip", 26, 32)]


def run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def synthesize(polly, text: str, path: Path) -> None:
    if not path.exists():
        r = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural")
        path.write_bytes(r["AudioStream"].read())


def slide_part(name: str, out: Path, pad: float = 1.0) -> None:
    """スライド1枚とそのナレーションで1つの部分を作る。"""
    audio = HERE / "audio" / f"{name}.mp3"
    length = duration(audio) + pad if audio.exists() else 5.0
    audio_in = ["-i", str(audio)] if audio.exists() else ["-f", "lavfi", "-t", str(length), "-i", "anullsrc=r=44100:cl=stereo"]
    run("-loop", "1", "-framerate", str(FPS), "-t", f"{length:.2f}", "-i", str(HERE / "slides" / f"{name}.png"),
        *audio_in, "-filter_complex", f"[1:a]apad,atrim=0:{length:.2f}[a]", "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out))


def demo_part(polly, out: Path) -> None:
    # ナレーションの置き場所: 予定の時刻と、前の語りの終わりの遅い方
    placed, cursor = [], 0.0
    for name, at, text in DEMO_LINES:
        path = HERE / "audio" / f"{name}.mp3"
        synthesize(polly, text, path)
        start = max(at, cursor + GAP)
        placed.append((path, start))
        cursor = start + duration(path)
    video_len = sum(e - s for _, s, e in DEMO_CLIPS)
    total = max(video_len, cursor + 0.5)

    inputs, filters = [], []
    for i, (f, s, e) in enumerate(DEMO_CLIPS):
        inputs += ["-ss", str(s), "-t", str(e - s), "-i", str(HERE / f)]
        filters.append(f"[{i}:v]scale=1920:1080,fps={FPS},setsar=1[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(DEMO_CLIPS))) + f"concat=n={len(DEMO_CLIPS)}:v=1:a=0[vc]")
    # 語りが映像より長いときは、最後の絵を止めて待つ
    filters.append(f"[vc]tpad=stop_mode=clone:stop_duration={total - video_len + 0.1:.2f}[vp]")
    last, n = "vp", len(DEMO_CLIPS)
    for j, (cap, s, e) in enumerate(DEMO_CAPTIONS):
        inputs += ["-i", str(HERE / "slides" / f"{cap}.png")]
        filters.append(f"[{last}][{n + j}:v]overlay=0:0:enable='between(t,{s},{e})'[o{j}]")
        last = f"o{j}"
    base = n + len(DEMO_CAPTIONS)
    for k, (path, start) in enumerate(placed):
        inputs += ["-i", str(path)]
        ms = int(start * 1000)
        filters.append(f"[{base + k}:a]adelay={ms}|{ms},aresample=44100[a{k}]")
    filters.append("".join(f"[a{k}]" for k in range(len(placed))) +
                   f"amix=inputs={len(placed)}:normalize=0,apad,atrim=0:{total:.2f}[aout]")
    run(*inputs, "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", "[aout]",
        "-t", f"{total:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    polly = boto3.Session(profile_name="default").client("polly", region_name="us-east-1")
    parts = []
    for name in ["a_title", "b_problem", "c_solution"]:
        parts.append(OUT / f"{name}.mp4")
        slide_part(name, parts[-1])
    parts.append(OUT / "d_demo.mp4")
    demo_part(polly, parts[-1])
    for name in ["e_how", "f_next", "g_credits"]:
        parts.append(OUT / f"{name}.mp4")
        slide_part(name, parts[-1], pad=1.0)
    listing = OUT / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    final = OUT / "ask-along-demo.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(final))
    print(f"{final}  {duration(final):.1f} 秒")
    for p in parts:
        print(f"  {p.name:16} {duration(p):5.1f} 秒")


if __name__ == "__main__":
    main()
