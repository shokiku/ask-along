package com.shokiku.askalong

import org.json.JSONObject

/** 場面ごとの「子への質問」。クラウドの Lambda(cloud/questions.py)が Nova で作ったもの。 */
data class Question(
    /** カードを出す時刻 */
    val timeMs: Long,
    /** カードを消す時刻(その場面が終わる時刻。場面が変わったら質問と画面が食い違うため) */
    val untilMs: Long,
    val type: String,
    val text: String,
)

/** クラウドが返す {"questions": [...]} を読む。見直しで外された質問(review が "rejected")は使わない。 */
fun parseQuestions(json: String): List<Question> {
    val array = JSONObject(json).getJSONArray("questions")
    return (0 until array.length())
        .map { array.getJSONObject(it) }
        .filter { it.optString("review") != "rejected" }
        .map {
            Question(timeMs = it.getLong("t_ms"), untilMs = it.getLong("until_ms"),
                type = it.getString("type"), text = it.getString("question"))
        }
        .sortedBy { it.timeMs }
}

/**
 * 再生位置から、いま出すべき質問を決める。
 * - 再生位置が質問の時刻を過ぎたら、その質問を1回だけ出す。
 * - 巻き戻したら、戻った位置より後の質問はもう一度出せるようにする。
 */
class QuestionSchedule(private val questions: List<Question>) {
    private var lastPositionMs = 0L
    private val shown = mutableSetOf<Question>()

    /** 新しく出す質問があれば返す。無ければ null。 */
    fun onPosition(positionMs: Long): Question? {
        if (positionMs < lastPositionMs) {
            shown.removeAll { it.timeMs > positionMs }
        }
        lastPositionMs = positionMs
        // 早送りで飛ばした質問は出さず、直近の1件だけを候補にする
        val due = questions.lastOrNull { it.timeMs <= positionMs && it !in shown } ?: return null
        questions.filter { it.timeMs <= due.timeMs }.forEach { shown.add(it) }
        // その場面がもう終わっていたら(シークで飛んできた)出さない
        return due.takeIf { positionMs < it.untilMs }
    }
}
