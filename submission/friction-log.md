# Friction Log — Ask-Along

Each entry: task attempted · steps taken · expected vs. actual · severity · workaround · actionable suggestion.

## 1. Lambda function URL returns 403 with auth type NONE
- **Task**: Expose a public read-only API for the Fire TV app with a Lambda function URL.
- **Steps**: `aws lambda create-function-url-config --auth-type NONE`; `aws lambda add-permission --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE`; `curl` the URL.
- **Expected**: HTTP 200 (this was enough before).
- **Actual**: `403 Forbidden` (`AccessDeniedException`) with a link to the docs and no detail. The docs note that since October 2025 new function URLs also need `lambda:InvokeFunction`.
- **Severity**: High (blocks the whole app; easy to misdiagnose as IAM or network).
- **Workaround**: Added a second statement `lambda:InvokeFunction` for `*` with condition `lambda:InvokedViaFunctionUrl = true`. Our AWS CLI had no `--invoked-via-function-url` flag, so we used boto3 `add_permission(InvokedViaFunctionUrl=True)`.
- **Suggestion**: Make the 403 body name the missing action, and have `create-function-url-config --auth-type NONE` offer to add both statements.

## 2. Nova video input reports the wrong duration and drifting timestamps
- **Task**: Ask Amazon Nova to find moments in a 10-minute film and return timestamps.
- **Steps**: Converse API with the video as bytes (re-encoded under 25 MB); asked "How long is this video?" and for events with timestamps.
- **Expected**: About 596 seconds and timestamps within a few seconds.
- **Actual**: "334.9 seconds"; event times were compressed accordingly. With 45-second clips, token counts suggested about 0.5 frames per second rather than 1 FPS.
- **Severity**: High for any timeline feature.
- **Workaround**: We stopped relying on model timestamps. We pick the times ourselves (Rekognition shots), extract frames with ffmpeg, and send still images.
- **Suggestion**: Return the sampled frame timestamps (or the effective FPS) in the response metadata, and fix the conflict in the Nova 2 user guide (">16 min → 960 frames" vs. the table showing 1 FPS up to 45 minutes).

## 3. ffmpeg scene detection misses fast camera moves; Rekognition does not
- **Task**: Split a cartoon into shots so a question card shows only while its scene is on screen.
- **Steps**: ffmpeg `select='gt(scene,0.3)'` (also tried 0.2, 0.15, 0.1) on Caminandes 3.
- **Expected**: A boundary where the camera whip-pans from the llama to the penguin (~47 s).
- **Actual**: No boundary at any threshold; the generated question asked about the penguin while the llama was on screen.
- **Severity**: Medium.
- **Workaround**: Rekognition `StartSegmentDetection` (SHOT) split it into 44.0–47.3 s and 47.5–49.8 s.
- **Suggestion**: A short sample in the Rekognition docs showing "segment detection → per-shot frame sampling for a multimodal model" would help others combine Rekognition with Bedrock.

## 4. Bedrock models listed as ACTIVE but not callable
- **Task**: Compare question quality across models and use a different model as an automatic judge.
- **Steps**: `aws bedrock list-foundation-models` / `list-inference-profiles` showed Nova Premier and several Claude models; called them via Converse.
- **Expected**: Either success or an access error before we build around them.
- **Actual**: Nova Premier → `ResourceNotFoundException`; Claude Sonnet 4.6 → "Model use case details have not been submitted for this account" (a text-only test call had succeeded earlier).
- **Severity**: Medium (lost the automatic judge; we judged by hand).
- **Workaround**: Compared Nova Pro and Nova 2 Lite only; manual frame-by-frame evaluation.
- **Suggestion**: Add an "invocable by this account: yes/no + reason" field to `list-foundation-models`.

## 5. `cmd media_session dispatch` fails on the API 31 Android TV emulator
- **Task**: Test the Media Session path that Alexa uses ("Alexa, pause") without a device.
- **Steps**: `adb shell cmd media_session dispatch play`.
- **Expected**: The app's session receives PLAY.
- **Actual**: `java.lang.IllegalArgumentException: packageName may not be empty`.
- **Severity**: Low.
- **Workaround**: `adb shell input keyevent KEYCODE_MEDIA_PLAY` / `KEYCODE_MEDIA_PAUSE`; confirmed state changes with `dumpsys media_session`.
- **Suggestion**: In the Fire TV Media Session doc, add the exact adb commands for testing voice transport controls on the emulator.

## 6. No arm64 Android TV image for API 30 (Fire OS 8 base)
- **Task**: Test on an emulator that matches Fire OS 8 (Android 11 / API 30) on an Apple Silicon Mac.
- **Steps**: `sdkmanager --list | grep android-tv`.
- **Expected**: `system-images;android-30;android-tv;arm64-v8a`.
- **Actual**: API 30 exists only for x86; arm64 starts at API 31.
- **Severity**: Low.
- **Workaround**: API 31 arm64 image, app built with minSdk 25.
- **Suggestion**: A Fire OS 8 emulator profile (or guidance on the closest image for Apple Silicon) in the Fire TV docs.

## 7. Rules and FAQ disagree on the demo environment
- **Task**: Decide where to record the demo without a Fire TV device.
- **Steps**: Read the Official Rules and the FAQ.
- **Expected**: One consistent answer.
- **Actual**: Rules: "an actual Fire TV device or the Fire TV/Vega simulator". FAQ: "an emulator (Android TV Emulator or the Fire TV/Vega simulator) is fine".
- **Severity**: Medium (uncertainty about eligibility).
- **Workaround**: Followed the FAQ and stated it in the submission.
- **Suggestion**: Update the rules text to match the FAQ.
