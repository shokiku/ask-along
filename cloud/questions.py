"""動画から「子への質問」を作る中心の処理。Mac のコマンド(tools/make_questions.py)と Lambda(cloud/handler.py)の両方から使う。

作り方:
1. 場面(ショット)の区切りを見つける。クラウドでは Rekognition の場面検出(StartSegmentDetection の SHOT)を使う。
   ffmpeg の scene 判定は、カメラを素早く振る切り替わりを見落とした(Caminandes 3 の 44〜50 秒。
   Rekognition は 44.0-47.3 と 47.5-49.8 に分けた。2026-10-03 に比較)。Mac で試すときは ffmpeg でもよい。
2. MIN_SHOT_SEC 秒以上続く場面から、本編を COUNT 等分した目安の時刻に近いものを選ぶ。
   カードは、その場面が映っている間(場面の終わりの CARD_WINDOW_SEC 秒前から、場面の終わりまで)だけ出す。
   場面の終わりの直前に出して12秒出し続けると、カードの質問と画面が食い違ったため
   (2026-10-03 エミュレータで確認: 「ペンギン」の質問のときにリャマが映っていた)。
3. カードが出ている間の静止画を FRAMES_PER_MOMENT 枚、Nova に渡し、「この絵について質問を1つ」と頼む。
   ffmpeg では、カメラを素早く振る切り替わりを見つけられない(Caminandes 3 の 42.7〜49.9 秒で、リャマから
   ペンギンに変わるのを見落とした。2026-10-03)。そこで Nova に「3枚とも同じ場面か」も答えさせ、
   違えばその区間は使わず、次に近い区間を試す(MAX_TRIES 回まで)。

経緯(2026-10-03 に Big Buck Bunny で実測。詳しくは docs/design.md の「検証の記録」):
- 動画をそのまま Nova に渡すと場面を取り違え、11件中3件しか使えなかった。静止画にして9/10になった。
- あらすじをいつも渡すと、映っていない前の場面を書いた。あらすじは recall の型のときだけ渡す。
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

REGION = "us-east-1"
# Nova Pro の推論プロファイル(list-inference-profiles で確認)。
# Nova 2 Lite では質問が「How does Big Bunny feel?」ばかりになったため Pro にした。
MODEL_ID = "us.amazon.nova-pro-v1:0"
COUNT = 10  # 作る質問の数(短い動画では MIN_GAP_SEC で減る)
START_SEC = 20  # これより前には出さない(冒頭は質問する材料が少ない)
MIN_GAP_SEC = 15  # 質問どうしの最短の間隔(20 では Caminandes 3 で2件しか作れなかった)
SCENE_THRESHOLD = 0.3  # ffmpeg の場面の切り替わりの判定のしきい値
MIN_SHOT_SEC = 4.0  # 質問を出す場面の最短の長さ(5.0 では短い作品で候補が足りなかった)
CARD_WINDOW_SEC = 8.0  # カードを出しておく最長の時間(場面の終わりまで)
CARD_START_AFTER_CUT_SEC = 1.5  # 場面が始まってからカードを出すまでの最短の時間
FRAMES_PER_MOMENT = 5  # 1つの質問に見せる静止画の枚数(カードが出ている間から均等に取る)。3枚では途中で映るものが変わるのを見落とした
MAX_TRIES = 4  # 同じ場面でない区間に当たったとき、次に近い区間を試す回数
GROUNDED_TRIES = 2  # 映っていない登場人物を質問に入れたとき、作り直させる回数
# 質問の型を順番に割り当てる(任せると同じ型ばかりになったため)
TYPE_CYCLE = ["open", "wh", "completion", "recall", "distancing"]

PROMPT = """You are helping a parent co-view a wordless cartoon with their 3-year-old child.
Research (Strouse et al., 2013) shows that when parents pause and ask dialogic questions, preschoolers learn more from video.

The images are frames from the scene that is on screen while the question is shown, in time order.
Characters in this film (use these names): {characters}
What happened earlier in the film:
{story_so_far}

Write ONE question of type "{qtype}". The CROWD question types from dialogic reading are:
- "completion": a sentence with a blank ("___") the child completes, about what is on screen
- "recall": the child remembers something that happened earlier in the film
- "open": the child describes what they see or how a character feels
- "wh": a what / where / who / why question about what is on screen
- "distancing": connect what is on screen to the child's own life

Rules:
- Short, simple English a 3-year-old understands (at most 10 words).
- Ask only about things clearly visible in these images (or, for "recall", in the story so far).
- Be specific: name the character, object, action or feeling.
- Do not name what you are not sure of. Use simple words such as "the bunny", "the llama", "the bird", "the little animal".
- Describe the scene only from these images. Do not copy descriptions from the story so far.
- Never ask generic questions like "Have you ever seen a bunny before?". A "distancing" question must link a specific action or feeling on screen to the child's life (e.g. "Do you like to smell flowers too?").
- A "completion" sentence must describe exactly what is visible in these images.

- The question must be about something visible in EVERY image.

First check: do all images show the same scene with the same main character? If not, set "same_scene" to false.

Return only JSON, no other text:
{{"same_scene": true, "scene": "one sentence describing exactly what is visible in these images", "question": "..."}}"""


def video_duration(ffmpeg: str, video: Path) -> float:
    """ffmpeg の出力の "Duration: 00:09:56.46" から長さ(秒)を読む(ffprobe が無い環境でも動くように)。"""
    log = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", log).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def shots_by_ffmpeg(ffmpeg: str, video: Path, until: float) -> list[tuple[float, float]]:
    """ffmpeg の scene 判定で場面の区切りを見つけ、(始まり, 終わり) の一覧を返す(Mac で試す用)。"""
    log = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video), "-t", str(until), "-an",
         "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    boundaries = [0.0] + [float(t) for t in re.findall(r"pts_time:([0-9.]+)", log)] + [until]
    return list(zip(boundaries, boundaries[1:]))


def shots_by_rekognition(rekognition, bucket: str, key: str, poll_sec: int = 5) -> list[tuple[float, float]]:
    """Rekognition の場面検出(SHOT)で、(始まり, 終わり) の一覧を返す。動画は S3 にあること。"""
    import time
    job = rekognition.start_segment_detection(
        Video={"S3Object": {"Bucket": bucket, "Name": key}}, SegmentTypes=["SHOT"])["JobId"]
    shots, token = [], None
    while True:
        kwargs = {"JobId": job, "MaxResults": 1000, **({"NextToken": token} if token else {})}
        result = rekognition.get_segment_detection(**kwargs)
        if result["JobStatus"] == "IN_PROGRESS":
            time.sleep(poll_sec)
            continue
        if result["JobStatus"] != "SUCCEEDED":
            raise RuntimeError(f"Rekognition の場面検出が失敗しました: {result.get('StatusMessage')}")
        shots += [(seg["StartTimestampMillis"] / 1000, seg["EndTimestampMillis"] / 1000)
                  for seg in result["Segments"]]
        token = result.get("NextToken")
        if not token:
            return shots


def candidate_windows(shots: list[tuple[float, float]], story_end: float) \
        -> tuple[list[tuple[float, float]], list[float]]:
    """カードを出せる区間 (出す時刻, 消す時刻) の一覧と、質問を出したい目安の時刻の一覧を返す。"""
    windows = [(max(start + CARD_START_AFTER_CUT_SEC, end - CARD_WINDOW_SEC), end - 0.2)
               for start, end in shots
               if end - start >= MIN_SHOT_SEC and start >= START_SEC and end <= story_end]
    count = max(1, min(COUNT, int((story_end - START_SEC) // MIN_GAP_SEC)))
    step = (story_end - START_SEC) / count
    targets = [START_SEC + step * (k + 1) for k in range(count)]
    return windows, targets


def grab_frames(ffmpeg: str, video: Path, window: tuple[float, float], workdir: Path) -> list[bytes]:
    show, hide = window
    frames = []
    for i in range(FRAMES_PER_MOMENT):
        # 場面の終わりぎりぎりの絵は次の場面にかかることがあった(「誰も映っていない」と判定された)ので 0.4 秒手前まで
        t = show + (hide - 0.4 - show) * i / (FRAMES_PER_MOMENT - 1)
        out = workdir / f"f_{show:.1f}_{i}.jpg"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(out)], check=True)
        frames.append(out.read_bytes())
    return frames


DESCRIBE_PROMPT = """These images are frames from a cartoon, in time order.
Characters in this film (use these names): {characters}
For EACH image separately, list the characters and the clearly visible objects (at most 5 objects), and what the characters are doing (one short sentence).
Use the given character names. Do not guess: if you are not sure, leave it out.
Return only JSON, no other text:
{{"frames": [{{"characters": ["..."], "objects": ["..."], "actions": "..."}}]}}"""

GROUNDED_PROMPT = """You are helping a parent co-view a wordless cartoon with their 3-year-old child.
Research (Strouse et al., 2013) shows that when parents pause and ask dialogic questions, preschoolers learn more from video.

On screen for the whole time the question is shown:
- characters: {characters}
- objects: {objects}
- what happens: {actions}
What happened earlier in the film:
{story_so_far}

Write ONE question of type "{qtype}". The CROWD question types from dialogic reading are:
- "completion": a sentence with a blank ("___") the child completes, about what is on screen
- "recall": the child remembers something that happened earlier in the film
- "open": the child describes what they see or how a character feels
- "wh": a what / where / who / why question about what is on screen
- "distancing": connect what is on screen to the child's own life

Rules:
- Use ONLY the characters and objects listed above (or, for "recall", the earlier events).
- Short, simple English a 3-year-old understands (at most 10 words). Be specific.
- Never ask generic questions like "Have you ever seen a bunny before?".

Return only JSON, no other text:
{{"question": "..."}}"""


def _converse_json(bedrock, model_id: str, content: list[dict], max_tokens: int) -> tuple[dict, dict]:
    response = bedrock.converse(modelId=model_id, messages=[{"role": "user", "content": content}],
                                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2})
    text = "".join(c.get("text", "") for c in response["output"]["message"]["content"])
    return _first_json(text), response["usage"]


def _first_json(text: str) -> dict:
    """文中の最初の JSON オブジェクトを読む(JSON のあとに説明文が続くことがあるため)。"""
    start = text.find("{")
    if start < 0:
        raise ValueError(f"モデルから JSON が返ってきませんでした: {text}")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def ask_grounded(bedrock, frames: list[bytes], story_so_far: str, qtype: str,
                 characters: str = "", model_id: str = MODEL_ID) -> tuple[dict, dict]:
    """2段階で質問を作る。1) 絵ごとに映っているものを書かせる。2) 全部の絵に映っているものだけで質問を作らせる。
    途中で映るものが変わる区間で、1枚にしか映っていないものを聞く誤りを防ぐため(2026-10-03 の比較で見つかった)。
    全部の絵に共通する登場人物がいなければ、same_scene=False として質問を作らない。"""
    content = [{"image": {"format": "jpeg", "source": {"bytes": f}}} for f in frames]
    content.append({"text": DESCRIBE_PROMPT.format(characters=characters or "(not given)")})
    described, usage1 = _converse_json(bedrock, model_id, content, 2500)
    per_frame = described.get("frames", [])
    if len(per_frame) != len(frames):
        return {"same_scene": False, "scene": f"絵の数と説明の数が合わない: {per_frame}"}, usage1

    def common(field: str) -> list[str]:
        sets = [{x.strip().lower() for x in (f.get(field) or []) if x} for f in per_frame]
        return sorted(set.intersection(*sets)) if sets else []

    chars, objs = common("characters"), common("objects")
    scene = " / ".join(f.get("actions") or "" for f in per_frame)
    if not chars:
        return {"same_scene": False, "scene": scene}, usage1
    # 質問に、全部の絵に映っていない登場人物の名前が入っていたら作り直させる(GROUNDED_TRIES 回まで)
    absent = [n for n in character_names(characters) if n not in " ".join(chars)]
    usage = dict(usage1)
    for _ in range(GROUNDED_TRIES):
        item, usage2 = _converse_json(bedrock, model_id, [{"text": GROUNDED_PROMPT.format(
            characters=", ".join(chars), objects=", ".join(objs) or "(none)", actions=scene,
            story_so_far=story_so_far, qtype=qtype)}], 200)
        usage = {k: usage[k] + usage2[k] for k in ("inputTokens", "outputTokens")}
        mentioned = [n for n in absent if re.search(rf"\b{re.escape(n)}\b", item["question"].lower())]
        if not mentioned:
            # 「The flying squirrel is hanging on the ___. (branch)」のように答えを括弧で付けることがあったので外す
            question = re.sub(r"\s*\([^)]*\)\s*$", "", item["question"]).strip()
            return {"same_scene": True, "scene": scene, "question": question}, usage
    return {"same_scene": False, "scene": f"映っていない登場人物を質問に入れ続けた: {mentioned}"}, usage


def character_names(characters: str) -> list[str]:
    """登場人物の指定 "llama: brown, long neck; penguin: small, black and white" から名前だけを取り出す。"""
    return [part.split(":")[0].strip().lower() for part in characters.split(";") if part.strip()]


def ask_nova(bedrock, frames: list[bytes], story_so_far: str, qtype: str,
             characters: str = "", model_id: str = MODEL_ID) -> tuple[dict, dict]:
    content = [{"image": {"format": "jpeg", "source": {"bytes": f}}} for f in frames]
    content.append({"text": PROMPT.format(story_so_far=story_so_far, qtype=qtype,
                                          characters=characters or "(not given)")})
    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 300, "temperature": 0.2},
    )
    text = "".join(c.get("text", "") for c in response["output"]["message"]["content"])
    return _first_json(text), response["usage"]


def generate(bedrock, ffmpeg: str, video: Path, story_end: float | None = None,
             shots: list[tuple[float, float]] | None = None, characters: str = "", log=print) -> dict:
    """動画から質問の一覧を作る。返り値はアプリが読む JSON の形。
    shots を渡さなければ ffmpeg で場面を区切る(Mac で試す用)。クラウドでは Rekognition の結果を渡す。"""
    end = video_duration(ffmpeg, video)
    if story_end:
        end = min(end, story_end)
    if shots is None:
        shots = shots_by_ffmpeg(ffmpeg, video, end)
    windows, targets = candidate_windows(shots, end)
    min_gap = max(MIN_GAP_SEC, (end - START_SEC) / len(targets) / 2)

    questions, story = [], []
    tokens_in = tokens_out = 0
    with tempfile.TemporaryDirectory() as tmp:
        for target in targets:
            qtype = TYPE_CYCLE[len(questions) % len(TYPE_CYCLE)]
            # あらすじは recall の型のときだけ渡す(いつも渡すと、映っていない前の場面を書いたため)
            story_so_far = (" ".join(story) or "(this is the beginning of the film)") if qtype == "recall" \
                else "(not needed for this question)"
            last_shown = questions[-1]["t_ms"] / 1000 if questions else None
            nearby = sorted((w for w in windows if last_shown is None or w[0] - last_shown >= min_gap),
                            key=lambda w: abs(w[0] - target))[:MAX_TRIES]
            item = window = None
            for window in nearby:
                # 2段階(絵ごとに映っているものを書かせ、全部に映っているものだけで質問を作る)。
                # 2026-10-03 の比較(docs/eval_round1〜3)で、誤りが一番少なかった
                try:
                    item, usage = ask_grounded(bedrock, grab_frames(ffmpeg, video, window, Path(tmp)),
                                               story_so_far, qtype, characters)
                except ValueError as e:  # JSONDecodeError も含む。返事が壊れていたら、その区間は使わない
                    log(f"{window[0]:6.1f}-{window[1]:6.1f}s  返事が読めないので飛ばす: {e}")
                    item = None
                    continue
                tokens_in += usage["inputTokens"]
                tokens_out += usage["outputTokens"]
                if item.get("same_scene", False):
                    break
                log(f"{window[0]:6.1f}-{window[1]:6.1f}s  同じ場面ではないので飛ばす: {item.get('scene')}")
                item = None
            if item is None:
                continue
            story.append(item["scene"])
            questions.append({"t_ms": int(window[0] * 1000), "until_ms": int(window[1] * 1000),
                              "type": qtype, "question": item["question"],
                              "nova_question": item["question"], "scene": item["scene"], "review": "draft"})
            log(f"{window[0]:6.1f}-{window[1]:6.1f}s  [{qtype}] {item['question']}  / {item['scene']}")

    return {"model": MODEL_ID, "tokens": {"input": tokens_in, "output": tokens_out}, "questions": questions}
