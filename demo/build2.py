"""デモ動画 第2版(2026-10-07)を組み立てる。静止したスライドを使わず、実際の画面と実データだけで見せる。

前の版(build.py)は説明をスライド1枚 × ナレーションの長さで作り、117秒のうち約78秒が静止画だった。
見直しの記録: review/01-rules-and-current.md, review/02-criteria-gap-plan.md, review/storyboard.html

素材:
- raw/seg1_cfr.mp4 … 作品の一覧画面(2026-10-04 録画)
- raw/seg3_cfr.mp4 … Big Buck Bunny、質問カード・OK で一時停止・再開・Back で飛ばす(2026-10-04 録画、今のカードの見た目)
- raw/seg4_cfr.mp4 … Caminandes 3、2枚の質問カード(2026-10-07 録画、raw/events4.txt)
- assets/vine, assets/squirrel_bird … Nova が実際に見た5枚(cloud/questions.grab_frames で同じ区間から取り直したもの)
- 本番のログ: CloudWatch /aws/lambda/askalong-on-upload 2026-10-03 の Big Buck Bunny の実行(LOG_LINES に英訳して書き写した)
- narration2.json … ナレーションの文(Amazon Polly, Joanna neural)

使い方: ../tools/.venv/bin/python build2.py   → build2/ask-along-demo-v2.mp4
"""
import json
import subprocess
from pathlib import Path

import boto3
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "build2"
AUDIO = HERE / "audio2"
W, H, FPS = 1920, 1080, 30
ORANGE = (255, 138, 61)
BG = (17, 19, 23)
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
NARR = json.loads((HERE / "narration2.json").read_text())
EMU_LABEL = "Recorded on the Android TV emulator (API 31)"


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index={"regular": 0, "bold": 1, "medium": 10, "light": 7}[weight])


def mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO, size)


def run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


# ---------- ナレーション ----------
def speak(polly, name: str, text: str) -> tuple[Path, list[float]]:
    """mp3 と、文ごとの開始時刻(秒)を返す。時刻は Polly の speech marks。"""
    mp3, marks = AUDIO / f"{name}.mp3", AUDIO / f"{name}.marks.json"
    if not mp3.exists():
        r = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural")
        mp3.write_bytes(r["AudioStream"].read())
    if not marks.exists():
        r = polly.synthesize_speech(Text=text, OutputFormat="json", VoiceId="Joanna", Engine="neural",
                                    SpeechMarkTypes=["sentence"])
        marks.write_text(r["AudioStream"].read().decode())
    starts = [json.loads(line)["time"] / 1000 for line in marks.read_text().splitlines() if line.strip()]
    return mp3, starts


# ---------- 画面に重ねる文字(透明な PNG) ----------
def caption_png(text: str, path: Path, sub: str = "") -> Path:
    """左下の字幕。前の版の字幕(slides/cap_*.html)と同じ見た目。"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f, fs = font(44, "bold"), font(30)
    tw = d.textlength(text, font=f)
    sw = d.textlength(sub, font=fs) if sub else 0
    bw, bh = max(tw, sw) + 72, 88 + (46 if sub else 0)
    x, y = 96, H - 84 - bh
    d.rounded_rectangle((x, y, x + bw, y + bh), 18, fill=(16, 19, 24, 225))
    d.rectangle((x, y, x + 10, y + bh), fill=ORANGE + (255,))
    d.text((x + 36, y + 20), text, font=f, fill="white")
    if sub:
        d.text((x + 36, y + 76), sub, font=fs, fill=(200, 205, 214))
    im.save(path)
    return path


def label_png(path: Path) -> Path:
    """製品の画面の右下に「エミュレータで撮った」と小さく出す(偽らないため)。"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(24)
    tw = d.textlength(EMU_LABEL, font=f)
    d.rounded_rectangle((W - tw - 72, H - 64, W - 36, H - 24), 10, fill=(0, 0, 0, 150))
    d.text((W - tw - 54, H - 58), EMU_LABEL, font=f, fill=(220, 220, 220))
    im.save(path)
    return path


def stat_png(path: Path, big: str, line1: str, line2: str, src: str, y: int) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((140, y), big, font=font(120, "bold"), fill=ORANGE)
    d.text((140, y + 150), line1, font=font(46, "medium"), fill="white")
    d.text((140, y + 206), line2, font=font(46, "medium"), fill="white")
    d.text((140, y + 270), src, font=font(28), fill=(185, 190, 200))
    im.save(path)
    return path


def center_png(path: Path, text: str, size: int = 96) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(size, "bold")
    tw = d.textlength(text, font=f)
    d.rounded_rectangle(((W - tw) / 2 - 48, H / 2 - size / 2 - 36, (W + tw) / 2 + 48, H / 2 + size / 2 + 44), 24,
                        fill=(12, 14, 18, 200))
    d.text(((W - tw) / 2, H / 2 - size / 2), text, font=f, fill="white")
    im.save(path)
    return path


def brand_png(path: Path) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((60, 50, 470, 130), 16, fill=(16, 19, 24, 210))
    d.text((90, 64), "Ask-Along", font=font(48, "bold"), fill=ORANGE)
    im.save(path)
    return path


# ---------- 映像の場面 ----------
def footage_scene(out: Path, clips: list[tuple[str, float, float]], overlays: list[tuple[Path, float, float]],
                  audio: list[tuple[Path, float]], darken: bool = False, min_len: float = 0.0) -> float:
    """録画を切ってつなぎ、文字を重ね、ナレーションを置く。長さを返す。"""
    inputs, filters = [], []
    for i, (f, s, e) in enumerate(clips):
        inputs += ["-ss", str(s), "-t", str(e - s), "-i", str(HERE / f)]
        filters.append(f"[{i}:v]scale={W}:{H},fps={FPS},setsar=1[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[vc]")
    last = "vc"
    if darken:
        filters.append("[vc]eq=brightness=-0.28:saturation=0.7[vd]")
        last = "vd"
    n = len(clips)
    for j, (png, s, e) in enumerate(overlays):
        inputs += ["-i", str(png)]
        filters.append(f"[{last}][{n + j}:v]overlay=0:0:enable='between(t,{s},{e})'[o{j}]")
        last = f"o{j}"
    base = n + len(overlays)
    length = max(sum(e - s for _, s, e in clips), min_len)
    cursor = -1.0
    for k, (mp3, at) in enumerate(audio):
        inputs += ["-i", str(mp3)]
        at = max(at, cursor + 0.25)  # 前の語りと重ならないように
        cursor = at + duration(mp3)
        ms = int(at * 1000)
        filters.append(f"[{base + k}:a]adelay={ms}|{ms},aresample=44100[a{k}]")
    filters.append("".join(f"[a{k}]" for k in range(len(audio))) +
                   f"amix=inputs={len(audio)}:normalize=0,apad,atrim=0:{length:.2f}[aout]")
    run(*inputs, "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", "[aout]",
        "-t", f"{length:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "18",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out))
    return length


def render_scene(out: Path, length: float, draw_frame, mp3: Path | None, audio_at: float = 0.0,
                 zoom: float = 0.05) -> None:
    """PIL で1コマずつ描いて ffmpeg に流す。描いた絵に、場面の長さをかけてゆっくり寄る(止まって見えないように)。"""
    audio_in = ["-i", str(mp3)] if mp3 else ["-f", "lavfi", "-t", f"{length:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
    ms = int(audio_at * 1000)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", *audio_in,
                          "-filter_complex", f"[1:a]adelay={ms}|{ms},aresample=44100,apad,atrim=0:{length:.2f}[a]",
                          "-map", "0:v", "-map", "[a]", "-t", f"{length:.2f}",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-ar", "44100",
                          "-ac", "2", str(out)], stdin=subprocess.PIPE)
    for i in range(int(length * FPS)):
        im = draw_frame(i / FPS)
        z = 1 + zoom * i / (length * FPS)
        if z > 1:
            cw, ch = W / z, H / z
            im = im.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {out}")


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ---------- 仕組みの場面: 本番の実行ログ ----------
# CloudWatch Logs /aws/lambda/askalong-on-upload、2026-10-03 の Big Buck Bunny の実行(RequestId ba756e66…)。
# (実行開始からの秒, 表示する行)。日本語で出していた行は英訳した。それ以外は原文のまま短くした。
LOG_LINES = [
    (0.0, "INIT_START Runtime Version: python:3.12.mainlinev2.v43"),
    (0.4, "START RequestId: ba756e66-e71f-49a4-a689-178050390623"),
    (85.9, "skipped 65.3-69.2s: Nova returned 4 descriptions for 5 frames"),
    (89.0, "[open]        57.6-60.4s  What is the bunny looking at in the tree?"),
    (93.1, "[wh]         114.2-117.7s  Why is the bunny jumping?"),
    (96.4, "[completion] 157.5-160.6s  The bunny is looking up at the ___."),
    (100.2, "[recall]     201.3-203.9s  What did bunny do before flying squirrel started chasing bird?"),
    (105.2, "[distancing] 245.0-250.5s  Have you ever held something like a vine before?"),
    (110.2, "[open]       302.2-305.0s  How do you think the flying squirrel feels while flying?"),
    (115.4, "skipped 347.5-355.3s: no character in every frame (2 of 5 descriptions empty)"),
    (121.5, "[wh]         363.1-370.9s  Why is the bunny pointing at the chinchilla?"),
    (125.1, "[completion] 401.2-404.7s  The flying squirrel is standing on a branch and then ___ in the air."),
    (129.3, "[recall]     437.7-440.3s  What was the flying squirrel trying to catch earlier?"),
    (151.5, "skipped 472.8-479.9s: unreadable model response"),
    (155.8, "[distancing] 467.7-471.1s  What do you think bunny likes about flowers?"),
    (155.9, "bbb: 10 questions, tokens in 48,517 / out 2,097"),
    (155.9, "REPORT Duration: 155461.29 ms  Memory Size: 2048 MB  Max Memory Used: 387 MB"),
]
RUN_END = 155.9
SHOTS = json.loads((HERE / "assets/shots_bbb.json").read_text())  # S3 shots/bbb.json(2026-10-03 15:38 UTC)
PIPE = ["Amazon S3\nupload", "AWS Lambda", "Amazon\nRekognition", "Amazon Nova Pro\ndescribe, then ask", "S3\nquestions.json",
        "Fire TV app"]


def draw_pipeline(d: ImageDraw.ImageDraw, active: set[int], y: int = 70) -> None:
    bw, gap = 262, 40
    x0 = (W - (bw * len(PIPE) + gap * (len(PIPE) - 1))) / 2
    for i, name in enumerate(PIPE):
        x = x0 + i * (bw + gap)
        on = i in active
        d.rounded_rectangle((x, y, x + bw, y + 104), 14, fill=(44, 30, 20) if on else (28, 31, 37),
                            outline=ORANGE if on else (60, 64, 72), width=4 if on else 2)
        for k, line in enumerate(name.split("\n")):
            f = font(26, "bold" if on else "medium")
            tw = d.textlength(line, font=f)
            d.text((x + (bw - tw) / 2, y + 18 + k * 34 + (17 if "\n" not in name else 0)), line, font=f,
                   fill=(255, 190, 140) if on else (170, 175, 185))
        if i < len(PIPE) - 1:
            ax = x + bw + 6
            d.line((ax, y + 52, ax + gap - 12, y + 52), fill=(120, 125, 135), width=3)
            d.polygon([(ax + gap - 12, y + 44), (ax + gap - 4, y + 52), (ax + gap - 12, y + 60)], fill=(120, 125, 135))


def how_scene(polly, out: Path) -> None:
    mp3, starts = speak(polly, "s4_how", NARR["s4_how"])
    length = duration(mp3) + 0.8
    # 文ごとに光らせる箱: 本番の実行 / S3→Lambda / Rekognition / Nova / 飛ばす / できあがり
    active_by_sentence = [set(), {0, 1}, {2}, {3}, {3}, {4, 5}]
    log_from, log_to = 0.6, length - 1.2  # 実行の 0〜155.9 秒を、この区間に縮めて流す(下で2区間に分ける)
    note = ["CloudWatch Logs  /aws/lambda/askalong-on-upload  — real run, 2026-10-03 15:36:38–15:39:14 UTC",
            f"time-compressed from 2:36 to 0:{int(log_to - log_from):02d}; Japanese messages translated to English"]
    fm, fh, fs = mono(25), font(30, "bold"), font(24)

    def frame(t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        k = max([i for i, s in enumerate(starts) if t >= s - 0.1] or [0])
        draw_pipeline(d, active_by_sentence[min(k, len(active_by_sentence) - 1)])
        # ログの窓
        x0, y0, x1, y1 = 100, 230, W - 100, H - 70
        d.rounded_rectangle((x0, y0, x1, y1), 16, fill=(10, 11, 14), outline=(60, 64, 72), width=2)
        for k, line in enumerate(note):
            d.text((x0 + 30, y0 + 16 + k * 30), line, font=fs, fill=(150, 155, 165))
        # 実行の 0〜85.9 秒(Rekognition とフレーム取り出し)は「S3→Lambda」「Rekognition」の文の間に、
        # 85.9 秒以降(Nova が質問を作る)は「Nova」の文から最後までに流す。語りと画面の段階を合わせるため
        if t <= log_from:
            run_t = 0.0
        elif t < starts[3]:
            run_t = 85.9 * (t - log_from) / (starts[3] - log_from)
        else:
            run_t = 85.9 + (RUN_END - 85.9) * min((t - starts[3]) / (log_to - starts[3]), 1.0)
        mm, ss = divmod(int(run_t), 60)
        clock = f"Lambda elapsed {mm}:{ss:02d}"
        d.text((x1 - 30 - d.textlength(clock, font=fh), y0 + 20), clock, font=fh, fill=ORANGE)
        shown = [line for at, line in LOG_LINES if at <= run_t] if t > log_from else []
        if t > log_from and 0.5 < run_t < 85.9:
            shown = shown + [f"… Rekognition shot detection and frame extraction ({int(run_t)} s, no log output)"]
        # Rekognition が見つけたショットの区切り(本番の結果 shots/bbb.json)を、帯として左から出す
        if t > log_from:
            by = y1 - 110
            d.text((x0 + 30, by - 44), f"Amazon Rekognition shot detection: {len(SHOTS)} shots (shots/bbb.json)",
                   font=fs, fill=(150, 155, 165))
            reveal = min(run_t / 85.9, 1.0) * SHOTS[-1][1]
            span = (x1 - 30) - (x0 + 30)
            for n, (a0, a1) in enumerate(SHOTS):
                if a0 > reveal:
                    break
                sx0 = x0 + 30 + span * a0 / SHOTS[-1][1]
                sx1 = x0 + 30 + span * min(a1, reveal) / SHOTS[-1][1]
                d.rectangle((sx0, by, max(sx0 + 1, sx1 - 1), by + 50), fill=ORANGE if n % 2 else (140, 90, 50))
        for i, line in enumerate(shown[-13:]):
            color = (150, 220, 160) if line.startswith("[") else (255, 170, 120) if line.startswith("skipped") \
                else (120, 125, 135) if line.startswith("…") else (210, 214, 222)
            d.text((x0 + 30, y0 + 110 + i * 38), line, font=fm, fill=color)
        return im

    render_scene(out, length, frame, mp3)


def frames_scene(polly, out: Path) -> None:
    """Nova が見た5枚と、絵ごとの説明(本番のログの通り)と、できた質問。"""
    mp3, starts = speak(polly, "s4_frames", NARR["s4_frames"])
    length = duration(mp3) + 0.8
    pics = [Image.open(p).convert("RGB").resize((336, 189)) for p in sorted((HERE / "assets/vine").glob("*.jpg"))]
    desc = ["bunny is standing\nin the forest.", "bunny is standing\nin the forest.", "bunny is holding\na vine.",
            "bunny is holding\na vine.", "bunny is holding\na vine."]
    q = "Have you ever held something like a vine before?"

    def frame(t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((100, 70), "What Amazon Nova Pro saw — Big Buck Bunny, 245.0–250.5 s", font=font(44, "bold"), fill="white")
        d.text((100, 132), "Step 1: describe each frame (Nova's own words, from the run log)", font=font(30),
               fill=(170, 175, 185))
        gap = 24
        x0 = (W - (336 * 5 + gap * 4)) // 2
        for i, pic in enumerate(pics):
            a = ease((t - 0.3 - i * 0.45) / 0.4)
            if a <= 0:
                continue
            x = x0 + i * (336 + gap)
            y = 250 + int((1 - a) * 30)
            im.paste(pic, (x, y))
            if t > starts[1] - 0.2 if len(starts) > 1 else t > 3:
                for k, line in enumerate(desc[i].split("\n")):
                    d.text((x, y + 210 + k * 36), line, font=font(28, "medium"),
                           fill=(150, 220, 160) if "vine" in desc[i] else (210, 214, 222))
        if len(starts) > 2 and t > starts[2] - 0.2:
            a = ease((t - starts[2] + 0.2) / 0.5)
            d.text((100, 560), "Step 2: ask only if a character is in every frame:  bunny", font=font(30),
                   fill=(170, 175, 185))
            y = 640 + int((1 - a) * 40)
            d.rounded_rectangle((100, y, W - 100, y + 150), 20, fill=(30, 33, 40), outline=ORANGE, width=4)
            d.text((140, y + 22), "[distancing]", font=font(30, "bold"), fill=ORANGE)
            d.text((140, y + 70), q, font=font(50, "bold"), fill="white")
        return im

    render_scene(out, length, frame, mp3, zoom=0.03)


def results_scene(polly, out: Path) -> None:
    mp3, starts = speak(polly, "s5_results", NARR["s5_results"])
    length = duration(mp3) + 1.0
    good = [Image.open(p).convert("RGB").resize((256, 144)) for p in sorted((HERE / "assets/vine").glob("*.jpg"))]
    bad = [Image.open(p).convert("RGB").resize((256, 144)) for p in sorted((HERE / "assets/squirrel_bird").glob("*.jpg"))]
    rows = [(good, "✓", (95, 211, 139), "Have you ever held something like a vine before?", "matched: the bunny holds a vine"),
            (bad, "✗", (255, 107, 107), "What did bunny do before flying squirrel started chasing bird?",
             "wrong: there is no bird in any frame (it's a butterfly)")]
    mark = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 80)

    def frame(t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((100, 64), "Judged by us, frame by frame — Big Buck Bunny, final run (10 questions)", font=font(44, "bold"),
               fill="white")
        # 集計の帯(2文目から)
        if len(starts) > 1 and t > starts[1] - 0.2:
            parts = [(5, "matched", (95, 211, 139)), (3, "weak", (240, 190, 90)), (2, "wrong", (255, 107, 107))]
            x = 100
            a = ease((t - starts[1] + 0.2) / 1.2)
            for n, name, c in parts:
                wdt = int(170 * n * a)
                d.rounded_rectangle((x, 150, x + max(wdt, 1), 200), 8, fill=c)
                if a > 0.9:
                    d.text((x + 16, 156), f"{n} {name}", font=font(30, "bold"), fill=(20, 20, 20))
                x += 170 * n + 8
        for r, (pics, sym, color, question, note) in enumerate(rows):
            show_at = 0.4 if r == 0 else (starts[1] + 4.5 if len(starts) > 1 else 6)  # 「like this one」の辺り
            a = ease((t - show_at) / 0.6)
            if a <= 0:
                continue
            y = 260 + r * 400 + int((1 - a) * 30)
            d.text((100, y - 10), sym, font=mark, fill=color)
            for i, pic in enumerate(pics):
                im.paste(pic, (220 + i * 272, y))
            d.text((220, y + 160), question, font=font(40, "bold"), fill="white")
            d.text((220, y + 214), note, font=font(30, "medium"), fill=color)
        return im

    render_scene(out, length, frame, mp3)


def credits_scene(out: Path) -> None:
    lines = ["Ask-Along — github.com/shokiku/ask-along", "",
             "Big Buck Bunny — © Blender Foundation | peach.blender.org — CC BY 3.0",
             "Caminandes 3: Llamigos — © Blender Foundation | caminandes.com — CC BY",
             "Narration: Amazon Polly (Joanna, neural)",
             "App footage: Android TV emulator (API 31)",
             "Research: Strouse, O'Doherty & Troseth (2013), Developmental Psychology 49(12)",
             "Statistics: Common Sense Census: Media Use by Kids Zero to Eight (2025)"]
    length = 6.0

    def frame(t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        y0 = 760 - 260 * ease(t / length)  # ゆっくり上へ流す
        for i, line in enumerate(lines):
            f = font(40, "bold") if i == 0 else font(32)
            tw = d.textlength(line, font=f)
            d.text(((W - tw) / 2, y0 + i * 56), line, font=f, fill=ORANGE if i == 0 else (205, 210, 218))
        return im

    render_scene(out, length, frame, None, zoom=0)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    AUDIO.mkdir(exist_ok=True)
    tmp = OUT / "png"
    tmp.mkdir(exist_ok=True)
    polly = boto3.Session(profile_name="default").client("polly", region_name="us-east-1")
    emu = label_png(tmp / "emu.png")
    parts = []

    # 1. 掴み: Caminandes で質問カードが場面に合わせて出て、場面が変わると消える
    mp3, _ = speak(polly, "s1_hook", NARR["s1_hook"])
    end = max(57.6 + duration(mp3) + 0.6, 65.0)
    parts.append(OUT / "s1_hook.mp4")
    footage_scene(parts[-1], [("raw/seg4_cfr.mp4", 57.6, end)],
                  [(brand_png(tmp / "brand.png"), 0, 99), (emu, 0, 99),
                   # カードは 2.9 秒で出て、場面が変わる 5.45 秒で消える(raw/events4.txt: 60.5 と 63.05 から 57.6 を引いた)
                   (caption_png("When the scene changes, the card goes away", tmp / "cap_hide.png"), 5.45, 99)],
                  [(mp3, 0.3)])

    # 2. 課題: 再生を続けたまま暗くし、読み上げに合わせて数字を出す
    mp3, st = speak(polly, "s2_problem", NARR["s2_problem"])
    ln = duration(mp3) + 0.8
    s1 = stat_png(tmp / "st1.png", "74%", "of parents of kids 0–8 watch shows", "with them, at least sometimes",
                  "Common Sense Census 2025, n = 1,578", 120)
    s2 = stat_png(tmp / "st2.png", "81 families", "kids whose parents paused and asked", "scored highest on comprehension",
                  "Strouse et al., Developmental Psychology, 2013", 520)
    s3 = center_png(tmp / "st3.png", "What should I ask?")
    parts.append(OUT / "s2_problem.mp4")
    # 26 秒で再開したあと、一時停止中のカードが消えきるまで少し待ってから使う(26.5 だと 0.8 秒映った)
    footage_scene(parts[-1], [("raw/seg3_cfr.mp4", 28.0, 28.0 + ln)],
                  [(s1, st[0], st[2] - 0.1), (s2, st[1], st[2] - 0.1), (s3, st[2], ln), (emu, 0, ln)], [(mp3, 0.0)],
                  darken=True)

    # 3. デモ: 一覧 → カード → OK で停止 → OK で再開 → Back で飛ばす → 別の作品・別の型の質問
    caps = {name: caption_png(text, tmp / f"cap_{name}.png", sub) for name, text, sub in [
        ("list", "Pick a show", ""),
        ("card", "A question appears — about what's on screen now", ""),
        ("ask", "OK: pause while your child answers", ""),
        ("resume", "OK again: keep watching", ""),
        ("skip", "Back: skip a question that doesn't fit", "skipped 3 times: removed"),
        ("types", "5 question types, in rotation", "completion · recall · open-ended · wh- · distancing")]}
    lines = []
    for i, (at, text) in enumerate(NARR["s3_demo"]):
        mp3, _ = speak(polly, f"s3_d{i}", text)
        lines.append((mp3, at))
    parts.append(OUT / "s3_demo.mp4")
    # 一覧は Big Buck Bunny が選ばれている間だけ(0.3–2.8)。続く再生も Big Buck Bunny なので食い違わない。
    # 再開のあとは 3 秒で次へ(前の版は声も字幕も無い映像が 8 秒続いた)。2枚目のカードは録画では
    # seg3 の 67.4 秒に出て 68.6 秒に Back で消える(再レビューでフレームから測った)。
    # この並びでの時刻: カード 4.0、OK 6.0、再開 12.0、2枚目のカード 16.9、Back 18.1、Caminandes のカード 25.4
    footage_scene(parts[-1], [("raw/seg1_cfr.mp4", 0.3, 2.8), ("raw/seg3_cfr.mp4", 16.5, 29.0),
                              ("raw/seg3_cfr.mp4", 65.5, 73), ("raw/seg4_cfr.mp4", 0, 7.5)],
                  [(caps["list"], 0, 2.5), (caps["card"], 4.0, 5.95), (caps["ask"], 6.0, 11.95),
                   (caps["resume"], 12.0, 15.0), (caps["card"], 16.9, 18.05), (caps["skip"], 18.1, 22.4),
                   (caps["types"], 24.6, 99), (emu, 0, 99)], lines)

    # 4. 仕組み: 本番の実行ログ → Nova が見た5枚 → その質問がテレビに出たところ
    parts.append(OUT / "s4_how.mp4")
    how_scene(polly, parts[-1])
    parts.append(OUT / "s4_frames.mp4")
    frames_scene(polly, parts[-1])
    parts.append(OUT / "s4_tv.mp4")
    mp3, _ = speak(polly, "s4_tv", NARR["s4_tv"])
    # 19.0 から: カードは 18.0 で出ているので、4 秒ずっと映る
    footage_scene(parts[-1], [("raw/seg3_cfr.mp4", 19.0, 23.0)],
                  [(caption_png("…and on the TV, at that scene", tmp / "cap_tv.png"), 0, 4), (emu, 0, 4)],
                  [(mp3, 0.2)])

    # 5. 正直な結果
    parts.append(OUT / "s5_results.mp4")
    results_scene(polly, parts[-1])

    # 6. 次の一手と締め → クレジット
    mp3, st = speak(polly, "s6_close", NARR["s6_close"])
    ln = duration(mp3) + 1.0
    nxt = caption_png("Next: a “question track” for kids' streaming", tmp / "cap_next.png", "delivered like subtitles")
    logo = center_png(tmp / "logo.png", "Ask-Along — turn screen time into talk time", 72)
    parts.append(OUT / "s6_close.mp4")
    footage_scene(parts[-1], [("raw/seg4_cfr.mp4", 20, 20 + ln)],
                  [(nxt, 0, st[1] - 0.1), (logo, st[1], ln), (emu, 0, ln)], [(mp3, 0.0)])
    parts.append(OUT / "s7_credits.mp4")
    credits_scene(parts[-1])

    listing = OUT / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    final = OUT / "ask-along-demo-v2.mp4"
    joined = OUT / "joined.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined))
    run("-i", str(joined), "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-ar", "44100",
        "-b:a", "192k", "-movflags", "+faststart", str(final))
    print(f"{final}  {duration(final):.1f} 秒")
    for p in parts:
        print(f"  {p.name:16} {duration(p):5.1f} 秒")


if __name__ == "__main__":
    main()
