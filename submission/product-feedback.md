# Product Feedback — Ask-Along

## Which developer tools, APIs and SDKs did you use, and for what?
| Tool / API / SDK | What we used it for |
|---|---|
| Fire OS (Android) + Fire TV developer docs | Target platform; remote-control input, 10-foot UI guidelines, Media Session voice playback controls |
| Android TV emulator (API 31, arm64) | Running and recording the app (the FAQ allows the Android TV emulator) |
| AndroidX Media3 (ExoPlayer, MediaSession, UI) | Video playback, D-pad control, Alexa playback commands through Media Session |
| Amazon S3 | Storing videos (private), shot lists and question files; presigned URLs for streaming |
| AWS Lambda (Python 3.12, arm64) + function URL | Generating questions when a video is uploaded; a small API for the TV app (titles, questions, skip feedback) |
| Amazon Rekognition Video — segment detection (SHOT) | Splitting each video into shots so a question card is shown only while its scene is on screen |
| Amazon Bedrock — Amazon Nova Pro (and Nova 2 Lite in experiments) | Describing frames and writing scene-grounded questions for the parent |
| Amazon Polly (neural) | Narration for the demo video |
| AWS CLI / boto3 | Deployment script and tools |

## What worked well?
- **Bedrock Converse API**: the same request shape for every model made it easy to compare Nova Pro and Nova 2 Lite on a fixed evaluation set. Sending JPEG frames as bytes needed no S3 staging.
- **Rekognition segment detection**: frame-accurate shot boundaries, and it caught fast camera moves that ffmpeg's scene detector missed. Cheap ($0.05/min) and simple to poll from Lambda.
- **Media3 + MediaSession**: one session gives remote keys, media keys and (on device) Alexa playback commands with almost no code. `adb shell input keyevent KEYCODE_MEDIA_PLAY/PAUSE` let us test the same path on the emulator.
- **Fire TV docs** on Media Session voice commands were clear about what works without any catalog integration.
- **Lambda function URLs**: a tiny HTTPS API without API Gateway.

## What needs work?
- **Nova video input**: when we sent a whole 10-minute video, Nova Pro / Nova 2 Lite reported its length as 334.9 seconds (actual 596 s) and timestamps drifted, so we could not trust model-provided times. The Nova 2 user guide also says videos over 16 minutes are sampled to 960 frames while its table lists 1 FPS up to 45 minutes; the two statements conflict.
- **Model availability in Bedrock**: Nova Premier returned ResourceNotFound and Claude models required an extra use-case form for our account. The console and `list-foundation-models` listed them as ACTIVE, so we only found out at call time.
- **Lambda function URL permissions**: since October 2025, auth type NONE also needs `lambda:InvokeFunction` with `lambda:InvokedViaFunctionUrl`. We got a plain 403 with no hint; the AWS CLI version we had did not support `--invoked-via-function-url`, so we used boto3.
- **Emulator for Fire OS 8**: Fire OS 8 is based on Android 11 (API 30), but on Apple Silicon the first arm64 Android TV system image is API 31.
- **Hackathon wording**: the rules say the demo must run on "an actual Fire TV device or the Fire TV/Vega simulator", while the FAQ says the Android TV emulator is fine. A single sentence in both places would remove the doubt.

## How was your onboarding experience (zero to hello world)?
Fast for the app: an Android TV project with Media3 played video in the emulator on the first day. The cloud side took longer only because of the function-URL permission change above. Getting from "a model writes questions" to "questions that match the screen" took most of the effort.

## Would you build with these devices and services again?
**Yes.** Fire TV's Media Session path gives voice and remote control for free, and Rekognition + Bedrock let a single developer build a video-understanding pipeline in days. We would like clearer model-availability signals in Bedrock and more reliable timestamps from Nova video input.
