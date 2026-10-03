# Ask-Along 設計書(2026-10-03)

## 目的
小さな子と一緒に動画を見ている親に、場面に合った「子への質問」を画面の隅に出す。答えさせるのは親。
根拠: Strouse ら 2013(Developmental Psychology)。3歳児81組で、親が止めて質問した組が、物語の理解と語彙で「止めて話しかけるだけ」「何もしない」組を上回った。

## 動き(最小の版)
1. アプリを開くと作品を選ぶ画面になる。選ぶと、その作品の質問をクラウドから読んで再生が始まる。
2. 質問の時刻になると、画面の右上にカードが出る(質問文と「OK で止めて聞く」の案内だけ。見出しは付けない)。
3. 親がリモコンの決定(OK)を押すと一時停止し、カードが大きくなる(「答えを待っています」)。もう一度 OK を押すと再生に戻る。
4. 押さなければ、カードは12秒で消えて、再生はそのまま続く。止めるかどうかは親が決める(研究では、止めて質問した組に効果があった)。
5. 再生と一時停止は、MediaSession を通しても届く(Fire TV では "Alexa, pause" が届く。エミュレータでは adb のメディアキーで試す)。

## クラウドの構成(2026-10-03 に作った。作り直しは cloud/deploy.sh)
- アカウント 166690002196、us-east-1。S3 バケット askalong-166690002196-use1(公開しない)。
- 動画を videos/<id>.mp4 に上げる(メタデータ story-end=本編の終わりの秒数、title=題名)と、Lambda askalong-on-upload が質問を作り、questions/<id>.json に置く。
  Big Buck Bunny(約10分)は26秒で10件、Caminandes 3(2分30秒)は22秒で4件(CloudWatch Logs で確認)。
- テレビのアプリは関数 URL(askalong-api)を呼ぶ。?action=titles で作品の一覧と動画の署名つき URL(6時間)、?action=questions&id=X で質問。認証なし・読み取りだけ。
- 質問が読めなかったときは、質問なしで再生する(2026-10-03 ユーザーの了承)。

## 質問の作り方(旧: 前もって、Mac で1回だけ。今はクラウドで同じ処理 cloud/questions.py を動かす)
- `tools/make_questions.py`: ffmpeg で動画を縮小する(音なし、Nova の 25MB の上限に収める)。Bedrock の Converse API で Nova 2 Lite に動画を渡し、場面ごとの質問を JSON で受け取る。
- 質問の型は、読み聞かせの研究の CROWD(Completion・Recall・Open-ended・Wh-・Distancing)に合わせる。3歳児向けの短い英語にする。
- 出力: `app/src/main/assets/questions.json`。
  ```json
  [{"t_ms": 61000, "type": "open", "question": "How is the bunny feeling right now?", "why": "..."}]
  ```
- Nova は音を聞かない。Big Buck Bunny にはセリフが無いので、この弱点は効かない。
- 人が見直してから使う(質問の質がばらつくため)。

## 構成
- Kotlin、Android Views。動画は Media3 ExoPlayer と PlayerView、MediaSession は Media3 で扱う。
- minSdk 25(Fire OS 6 以上)、targetSdk/compileSdk 35。
- 動画ファイルはアプリに同梱しない。クラウドの署名つき URL から流す。
- manifest: `android.software.leanback` は required=false。`android.hardware.touchscreen` も required=false。LEANBACK_LAUNCHER を付ける。Fire TV の Alexa 用の権限 `com.amazon.permission.media.session.voicecommandcontrol` を付ける。

## デモ
- Android TV エミュレータ(API 31、arm64)。Fire OS 8 は API 30 が元なので、minSdk を下げて対応している。
- エミュレータの録画で撮る(Android の文書では音も入る)。

## 未検証
- Nova 2 Lite が、場面に合った質問を正しい時刻で返すか。
- エミュレータで、adb のメディアキーが自分のアプリの MediaSession に届くか。

## 検証の記録: 質問の質(2026-10-03)
何を: Nova が作った質問が、カードを出す瞬間の画面と合っているか。
どうやって: 各質問の時刻の前後のフレームを ffmpeg で切り出し、私(Claude)が目で見て判定した。判定は私の主観で、映画は Big Buck Bunny の1本だけ。

| 版 | 作り方 | 画面と合っていた | 誤り |
|---|---|---|---|
| v1 | 動画を45秒ずつ Nova Pro に渡す | 3/11 | 8(穴のウサギを「クマ」、質問になっていない文など) |
| v2 | カットの直前の静止画3枚を Nova Pro に渡す | 8/10(うち3件は平凡) | 2 |
| v3 | v2 +「平凡な質問を禁止」などの指示 | 6/10 | 4(前の場面の「花を嗅ぐ」を書き続けた) |
| v4 | v3 + あらすじは recall の型のときだけ渡す | 9/10 | 0(1件は、止めた瞬間に鳥がもう飛び去っていたので直した) |

- 採用: v4。`app/src/main/assets/questions.json` に、直す前の Nova の文(nova_question)と見直しの結果(review)を残した。
- 注意: 同じ作り方でも回によって 6〜9 件と揺れた。1本の映画・1回ずつの結果で、ほかの映画で通用するかは確かめていない。
- 結論: 「AI が下書きし、人が短時間で見直す」形なら成り立つ(v4 では10件中1件の手直し)。人の見直しを外せる精度ではない。
- 費用: v1〜v4 と試行の合計で約 $0.4(トークン数 × 単価で概算)。
- 未検証の欄の「Nova 2 Lite が場面に合った質問を正しい時刻で返すか」は、上の表で答えが出た(時刻はこちらで決め、Nova Pro を使う)。

## 検証の記録: エミュレータでの動作(2026-10-03)
何を・どうやって: Android TV エミュレータ(API 31、arm64、画面なしで起動)にアプリを入れ、adb のキー入力で操作し、画面を adb screencap で撮って確かめた。
- 作品の一覧がクラウドから読めて、テレビの画面に出た(2本、どちらも「Questions ready」)。
- Caminandes 3 を再生し、質問の時刻にカードが出た。OK で一時停止し、案内が「答えを待っています」に変わった(MediaSession の状態が 2=停止)。もう一度 OK で再生に戻った(状態 3)。
- メディアキー(adb shell input keyevent KEYCODE_MEDIA_PLAY / PAUSE)で再生と停止が切り替わった。Fire TV で Alexa の再生操作が通るのと同じ MediaSession の経路。`cmd media_session dispatch` は API 31 では "packageName may not be empty" で使えなかった。
- 見つけた不具合と直したこと:
  1. カードを場面の終わりの直前に出して12秒出し続けたため、次の場面に変わっても質問が残り、画面と食い違った(「ペンギン」の質問のときにリャマ)。→ カードは場面が映っている間だけ出し、場面が終わったら消すようにした(until_ms)。直した後、場面が汽車に変わるとカードが消えることを確認。
  2. ffmpeg の場面判定が、カメラを素早く振る切り替わりを見落とし、Nova が別の場面の絵で質問を作った。→ 場面の検出を Rekognition(SHOT)に替え、さらに Nova に「3枚が同じ場面か」を答えさせ、違えば別の区間を使うようにした。
- 終わったあとエミュレータと adb を止め、プロセスが残っていないことを pgrep で確認。

## 費用(2026-10-03 までの概算、単価 × 量)
- Rekognition の場面検出: Caminandes 3(2.5分)×4回 + Big Buck Bunny(10分)×1回 ≒ $1.0
- Bedrock(Nova 2 Lite・Nova Pro): 試行の合計 ≒ $0.6
- Lambda・S3: 数セント

## 検証の記録: 質問の精度を上げる試み(2026-10-03)
何を・どうやって: 同じ場面の区間(Big Buck Bunny 8か所、Caminandes 3 6か所)について作り方を変えて質問を作り、
区間の絵を並べた画像(docs/eval_round1〜3/sheet_*.png)と見比べて、私(Claude)が判定した。主観の判定。

| 回 | 作り方 | 出した数 | 合っていた | 弱い | 誤り |
|---|---|---|---|---|---|
| 1 | Nova Pro(絵3枚) | 13 | 7 | 6 | 0 |
| 1 | Nova Pro + 登場人物の名前 | 13 | 7 | 3 | 3 |
| 1 | Nova 2 Lite + 名前 | 14 | 10 | 3 | 1 |
| 2 | Nova Pro + 名前 + 2段階(絵ごとに書かせ、共通のものだけで質問) | 11 | 9 | 0 | 2 |
| 3 | Nova Pro + 名前 + 2段階 + 絵5枚 + 映っていない名前の確認 | 6 | 4 | 2 | 0 |
| 本番 | 3 と同じ作り方を Lambda で(近い区間を4つまで試す) | 10 | 5 | 3 | 2 |

- 本番の誤り2件: 「なぜ跳んでいるの?」(跳んでいない)、「鳥を見る前に何をした?」(鳥がいない)。Nova の絵の説明そのものが誤っていた。
- 判定役に別のモデル(Claude)を使う予定だったが、アカウントで Anthropic の利用申請が要り、使えなかった。Nova Premier も使えなかった。
- 結論: Nova だけでは、合っている割合は 7〜8 割で頭打ち。誤りは「絵の説明の誤り」から来ており、作り方の工夫では減り切らない。
