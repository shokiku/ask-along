# Ask-Along

**Turn screen time into talk time.** Ask-Along is a Fire TV app that shows a parent a short question for their child about the scene on screen. Press **OK** to pause while the child answers, **OK** again to keep watching, **Back** to skip a question that doesn't fit.

Questions are generated in the cloud: Amazon Rekognition splits the video into shots, and Amazon Nova Pro (Amazon Bedrock) writes a question that only mentions what is visible in every sampled frame of that shot. Cards are shown only while that shot is on screen.

Built for the *Build, Ship, Shape: Amazon Developer Hackathon 2026* (Fire TV track).

Demo video: https://youtu.be/QZy19c3A6oM

## Why
Parents often watch shows with their young kids (74% at least sometimes, Common Sense Census 2025). In a trial with 81 families of 3-year-olds, children whose parents paused and asked dialogic questions scored higher on story comprehension and vocabulary (Strouse et al., *Developmental Psychology*, 2013). Ask-Along gives the parent the question at the right moment.

## Architecture
```
video ──► Amazon S3 (videos/<id>.mp4, metadata: title, story-end, characters)
              │ ObjectCreated
              ▼
         AWS Lambda  askalong-on-upload  (cloud/handler.py · cloud/questions.py)
              ├─ Amazon Rekognition  StartSegmentDetection (SHOT)  → shots/<id>.json
              ├─ ffmpeg: 5 frames from the part of each chosen shot where the card is shown
              └─ Amazon Nova Pro (Bedrock Converse): 1) describe each frame  2) ask only about what is in every frame
              ▼
         Amazon S3  questions/<id>.json  (t_ms, until_ms, type, question)
              ▲
         AWS Lambda  askalong-api  (function URL)
              │  GET  ?action=titles            → titles + presigned video URLs
              │  GET  ?action=questions&id=X    → questions
              │  POST {"action":"skip",...}     → skip count; 3 skips remove a question
              ▼
Fire TV app (app/) — Kotlin, Media3 ExoPlayer + MediaSession, D-pad UI
```

## Repository layout
| Path | What |
|---|---|
| `app/` | Fire OS / Android TV app (Kotlin, Media3). `TitlesActivity` (pick a show), `PlayerActivity` (playback + cards), `Questions.kt` (when to show a card), `Api.kt` |
| `cloud/` | Lambda code (`handler.py`, `questions.py`) and `deploy.sh` (creates/updates S3, IAM role, both Lambdas, the function URL) |
| `tools/` | `register_video.py` (upload a video with metadata), `make_questions.py` (run the generator locally), `eval_questions.py` (compare generation settings) |
| `demo/` | How the demo video was made. `build2.py` builds the current video (emulator footage, the real CloudWatch log of a run, the frames Nova saw; narration in `narration2.json`, Amazon Polly). `review/` records how it was reviewed against the rules and judging criteria. `build.py` made the first version |
| `docs/` | Design notes and evaluation records (Japanese), evaluation contact sheets |
| `submission/` | Devpost text, product feedback, friction log, feature requests |

## Run it yourself
### Requirements
- An AWS account with access to Amazon Bedrock **Nova Pro** in `us-east-1`, Amazon Rekognition, S3 and Lambda
- Python 3.12+, ffmpeg, AWS CLI v2 (profile `default`)
- JDK 17 and the Android SDK (platform 35); an Android TV emulator or a Fire TV device

### 1. Cloud
```bash
python3 -m venv tools/.venv && tools/.venv/bin/pip install boto3
# edit ACCOUNT / BUCKET at the top of cloud/deploy.sh and BUCKET in tools/register_video.py for your account
cloud/deploy.sh            # prints the API URL
tools/.venv/bin/python tools/register_video.py caminandes3 path/to/caminandes3.mp4 \
  --title "Caminandes 3: Llamigos" --story-end 135 \
  --characters "llama: brown, long neck, big eyes; penguin: small, black and white"
```
Questions appear in `s3://<bucket>/questions/caminandes3.json` after 1–2 minutes (Lambda logs: `/aws/lambda/askalong-on-upload`).

### 2. Fire TV app
Set `API_URL` in `app/build.gradle.kts` to the URL printed by `deploy.sh`, then:
```bash
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.shokiku.askalong/.TitlesActivity
```
Remote: **OK** pause & ask / resume · **Back** skip the card · **◀ ▶** −/+10 s. Media keys (and "Alexa, pause" on Fire TV) go through MediaSession.

## Measured accuracy
We checked generated questions frame by frame against the scenes on two open films. Depending on the version and run, **5 to 9 of every 10 questions matched the scene** (details: `docs/design.md`, `docs/eval_round*`). Mismatches come from the model misreading frames; the one-button skip keeps the parent in control.

## Credits
- Big Buck Bunny — © Blender Foundation | peach.blender.org — CC BY 3.0
- Caminandes 3: Llamigos — © Blender Foundation | caminandes.com — CC BY
- Videos are not included in this repository; download them from the Blender Foundation.

## License
MIT — see [LICENSE](LICENSE).
