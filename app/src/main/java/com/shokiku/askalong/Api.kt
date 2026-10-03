package com.shokiku.askalong

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** 作品。動画はクラウドの署名つき URL(6時間有効)で再生する。 */
data class Title(
    val id: String,
    val name: String,
    val videoUrl: String,
    val questionsReady: Boolean,
)

/**
 * クラウド(cloud/handler.py の api)を呼ぶ。メインスレッドからは呼ばないこと。
 * 失敗したら例外を投げる(呼ぶ側で扱いを決める)。
 */
object Api {
    private const val TIMEOUT_MS = 10_000

    fun titles(): List<Title> {
        val array = JSONObject(get("action=titles")).getJSONArray("titles")
        return (0 until array.length()).map { array.getJSONObject(it) }.map {
            Title(
                id = it.getString("id"),
                name = it.getString("title"),
                videoUrl = it.getString("video_url"),
                questionsReady = it.getBoolean("questions_ready"),
            )
        }
    }

    fun questions(titleId: String): List<Question> =
        parseQuestions(get("action=questions&id=" + URLEncoder.encode(titleId, "UTF-8")))

    /** 親が質問を飛ばしたことを知らせる。何度も飛ばされた質問は、クラウドが出さなくする。 */
    fun skip(titleId: String, question: Question) {
        post(JSONObject().put("action", "skip").put("id", titleId).put("t_ms", question.timeMs).toString())
    }

    private fun post(json: String) {
        val connection = URL(BuildConfig.API_URL).openConnection() as HttpURLConnection
        connection.connectTimeout = TIMEOUT_MS
        connection.readTimeout = TIMEOUT_MS
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        try {
            connection.outputStream.use { it.write(json.toByteArray()) }
            val code = connection.responseCode
            if (code != HttpURLConnection.HTTP_OK) throw ApiException(code)
        } finally {
            connection.disconnect()
        }
    }

    private fun get(query: String): String {
        val connection = URL(BuildConfig.API_URL + "?" + query).openConnection() as HttpURLConnection
        connection.connectTimeout = TIMEOUT_MS
        connection.readTimeout = TIMEOUT_MS
        try {
            val code = connection.responseCode
            if (code != HttpURLConnection.HTTP_OK) throw ApiException(code)
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}

class ApiException(val statusCode: Int) : Exception("API returned HTTP $statusCode")
