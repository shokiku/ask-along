# デモ動画の見直し 2: 満たすべき条件・差・改善案(2026-10-07)

## 受賞作の調査(調査役、2026-10-07。7本を3秒ごとの画像で分類。音声は聞いていない)
- Devpost 公式 "Video-making best practices"(2026-05-27 更新): ナレーション付きの画面収録を推奨。"explain what your app does ... in the first few seconds"。"Make sure it's a demo! Leave the lengthy introduction to your text description"。"Snazzy marketing videos ... don't help others understand"。
- Devpost ブログ "6 Tips": 約3分、冒頭でエレベーターピッチ、参加者の声として "no slide shows/decks"。
- Amazon 主催の受賞作: 総合上位4本は製品画面 61〜83%、うち3本は36秒以内に製品が動く。部門賞等3本は 19〜39%。最長の静止は Sai 約27秒、Oracus 約30秒(3分より後)、Drone 約39秒。総合1位 BackstageCommercials は説明を製品画面に重ね、静止スライドがほぼ無い。
- Fire TV の受賞作は無い(今回の発表は 2026-12-03 予定)。

## 満たすべき条件(審査基準・規約・調査から)
| # | 条件 | 根拠 |
|---|---|---|
| C1 | 3分未満。見どころは全部3分以内 | 規約 |
| C2 | 最初の5秒以内に、Fire TV の画面で製品が動き、何をするアプリかを一言で言う | Devpost 公式 "first few seconds" |
| C3 | 製品(Fire TV シミュレータの画面、またはクラウドが実際に動く画面)が全体の 60%以上 | 規約(functioning)、受賞上位の傾向 |
| C4 | 静止した画面が5秒を超えて続かない | Devpost "no slide shows"、受賞上位 |
| C5 | Tech Implementation: クラウドの処理(S3→Lambda→Rekognition→Nova)が実際に動いた証拠を映像で見せる | 審査基準 |
| C6 | Design: リモコン操作(OK で一時停止・再開、Back でスキップ、場面が変わるとカードが消える)を全部、実際の画面で見せる | 審査基準 "interaction model intuitive for the target device" |
| C7 | Potential Impact: 誰の何の困りごとかを、根拠の数字つきで短く(15秒以内) | 審査基準 "credible, specific case" |
| C8 | Quality of Idea: 「見ている場面に合わせて AI が質問を作る」ことが一目で分かる(Nova が見たフレームと、できた質問を並べて見せる) | 審査基準(creative 例 "AI-enhanced viewing") |
| C9 | 正直さ: 正確さの数字(5〜9/10)、エミュレータであること、Alexa は実機での話であることを偽らない | 自分たちの方針 |
| C10 | 第三者の素材は CC BY の映画のみ、出典表示、音楽なし | 規約・FAQ |

## 今の動画との差
| # | 今 | 判定 |
|---|---|---|
| C1 | 117秒 | 満たす |
| C2 | 製品が初めて映るのは 33.8秒目 | ✗ |
| C3 | 製品 29% | ✗ |
| C4 | 静止 23.6秒・27.9秒・16.9秒ほか、合計約78秒 | ✗ |
| C5 | 仕組みは静止した図だけ。実際に動いた証拠の映像なし | ✗ |
| C6 | OK・再開・Back・場面切替で消える、は映っている | 満たす |
| C7 | 課題 23.6秒(静止) | △ 長い |
| C8 | 質問がどう作られるかの実例が映像に無い | ✗ |
| C9 | 満たす | 満たす |
| C10 | 満たす | 満たす |

## 改善案(新しい構成、目標 約2分15秒)
| 時間 | 場面 | 映すもの(静止させない) | ナレーション(要旨) |
|---|---|---|---|
| 0:00–0:08 | 掴み | シミュレータで Big Buck Bunny 再生中、質問カードが出る → OK で一時停止 | 「Ask-Along は、見ている場面について子どもに聞く質問を、親にそっと出す Fire TV アプリ」 |
| 0:08–0:20 | 課題 | 再生画面を背景に、数字(74%、81家族の研究)を順に重ねる | 親の多くは一緒に見ている。止めて質問すると子どもの理解が伸びる。でも何を聞けばいいか分からない |
| 0:20–1:05 | デモ | 作品を選ぶ → カード → OK 一時停止 → OK 再開 → 場面が変わるとカードが消える → Back でスキップ → 別の作品・別の質問タイプ | 操作の説明(今の文面を流用) |
| 1:05–1:45 | 仕組み(実物) | 動画を S3 に上げる → Lambda のログが流れる → Rekognition のショット → Nova が見た5枚のフレームと説明文 → できた質問 → アプリに出る。図は動画の隅に小さく、今どこかを光らせる | 今の文面を短く |
| 1:45–2:05 | 正直な結果 | 評価用に並べたフレームと質問の画像を、合っている例・外れた例の順にパン | 5〜9/10、外れはスキップで親が外せる |
| 2:05–2:15 | 次の一手と締め | 再生画面に戻り、ロゴとリンク | Amazon Kids+ の「質問トラック」 |
| 末尾 | クレジット | 文字が流れる | なし |

必要な作業: エミュレータでの再収録(デモ・掴み)、クラウドが動く様子の画面収録(新しい動画1本を登録して Lambda を実際に動かす。費用は Rekognition・Nova・Lambda で少額)、ナレーションの書き直しと Polly、組み立て(build.py を場面ごとの重ね合わせに対応させる)。

## 出典の確認(2026-10-07)
- 74%: Common Sense Census 2025 報告書 PDF(https://www.commonsensemedia.org/sites/default/files/research/report/2025-common-sense-census-web-2.pdf)p.27「Most parents report co-watching their child's TV shows (74%) or YouTube videos (62%) at least some of the time」。方法の節「probability-based online survey of 1,578 parents of children age 8 or younger, conducted from August 5 to August 29, 2024」。curl で取得し pdftotext で確認。
- ログの原文(CloudWatch、2026-10-03 15:36:38–15:39:14 UTC): 65.3–69.2s は「絵の数と説明の数が合わない」で説明が4件(絵は5枚)。347.5–355.3s は5枚のうち2枚の説明が空 = 全部の絵に共通する登場人物がいない。
