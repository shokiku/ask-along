package com.shokiku.askalong

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaSession
import androidx.media3.ui.PlayerView
import java.util.concurrent.Executors

/**
 * 動画を再生し、質問の時刻になったら画面の右上に「子への質問」のカードを出す。
 * 質問の一覧は、再生を始めるときにクラウドからその作品の分を読む。
 * 読めなかったとき(まだ作られていない・通信できない)は、質問なしで再生する(2026-10-03 ユーザーの了承済み)。
 *
 * リモコン:
 * - カードが出ているときの OK: 一時停止して「答えを待っています」の表示にする。もう一度 OK で再生に戻る。
 * - カードが無いときの OK / 再生キー: 再生と一時停止を切り替える。
 * - カードが出ているときの戻る: その質問を飛ばす(合わない質問だったとき)。飛ばしたことはクラウドに知らせる。
 * - 左右: 10秒戻る・進む。
 * 再生操作は MediaSession にもつないでいるので、Fire TV では "Alexa, pause" なども届く。
 */
class PlayerActivity : AppCompatActivity() {

    private lateinit var player: ExoPlayer
    private lateinit var session: MediaSession
    private var schedule = QuestionSchedule(emptyList())
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var titleId: String

    private lateinit var card: LinearLayout
    private lateinit var cardQuestion: TextView
    private lateinit var cardHint: TextView

    private val handler = Handler(Looper.getMainLooper())
    private var cardState = CardState.HIDDEN
    private var offered: Question? = null

    private enum class CardState { HIDDEN, OFFERED, ASKING }

    private val tick = object : Runnable {
        override fun run() {
            onTick()
            handler.postDelayed(this, TICK_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_player)

        card = findViewById(R.id.card)
        cardQuestion = findViewById(R.id.card_question)
        cardHint = findViewById(R.id.card_hint)

        player = ExoPlayer.Builder(this).build()
        // 「答えを待っています」の間に、Alexa やリモコンの再生キーで再生が始まったらカードを閉じる
        player.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                if (isPlaying && cardState == CardState.ASKING) hideCard()
            }

            // 再生できないときに黒い画面のままにしない(Big Buck Bunny の 640x359 の動画がエミュレータで読めなかった)
            override fun onPlayerError(error: PlaybackException) {
                hideCard()
                findViewById<TextView>(R.id.error).apply {
                    text = getString(R.string.playback_error, error.errorCodeName)
                    visibility = View.VISIBLE
                }
            }
        })
        findViewById<PlayerView>(R.id.player_view).player = player
        session = MediaSession.Builder(this, player).build()

        titleId = intent.getStringExtra(EXTRA_TITLE_ID)!!
        player.setMediaItem(MediaItem.fromUri(intent.getStringExtra(EXTRA_VIDEO_URL)!!))
        player.prepare()

        // 質問を読み終えてから再生を始める(冒頭の質問を取りこぼさないため)
        io.execute {
            val result = runCatching { Api.questions(titleId) }
            runOnUiThread {
                result.onSuccess { schedule = QuestionSchedule(it) }
                    .onFailure { Toast.makeText(this, R.string.questions_unavailable, Toast.LENGTH_LONG).show() }
                player.playWhenReady = true
            }
        }
    }

    override fun onStart() {
        super.onStart()
        handler.post(tick)
    }

    override fun onStop() {
        handler.removeCallbacks(tick)
        player.pause()
        super.onStop()
    }

    override fun onDestroy() {
        io.shutdownNow()
        session.release()
        player.release()
        super.onDestroy()
    }

    private fun onTick() {
        if (cardState == CardState.ASKING) return
        schedule.onPosition(player.currentPosition)?.let { offer(it) }
        // 場面が変わったら(またはシークで場面の外に出たら)カードを消す
        val current = offered
        if (cardState == CardState.OFFERED && current != null &&
            player.currentPosition !in current.timeMs until current.untilMs) hideCard()
    }

    private fun offer(question: Question) {
        // 動作確認・デモ撮影の合図(adb logcat -s AskAlong で見る)
        Log.i(LOG_TAG, "card shown t_ms=${question.timeMs}")
        cardQuestion.text = question.text
        cardHint.setText(R.string.card_hint)
        card.visibility = View.VISIBLE
        cardState = CardState.OFFERED
        offered = question
    }

    private fun startAsking() {
        player.pause()
        cardHint.setText(R.string.asking_hint)
        cardState = CardState.ASKING
    }

    private fun hideCard() {
        card.visibility = View.GONE
        cardState = CardState.HIDDEN
        offered = null
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action != KeyEvent.ACTION_DOWN) return super.dispatchKeyEvent(event)
        return when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                when (cardState) {
                    CardState.OFFERED -> startAsking()
                    CardState.ASKING -> { hideCard(); player.play() }
                    CardState.HIDDEN -> togglePlay()
                }
                true
            }
            KeyEvent.KEYCODE_BACK -> {
                if (cardState == CardState.HIDDEN) return super.dispatchKeyEvent(event)
                skipQuestion()
                true
            }
            KeyEvent.KEYCODE_DPAD_LEFT -> { seekBy(-SEEK_MS); true }
            KeyEvent.KEYCODE_DPAD_RIGHT -> { seekBy(SEEK_MS); true }
            else -> super.dispatchKeyEvent(event)
        }
    }

    private fun skipQuestion() {
        val question = offered ?: return
        val wasAsking = cardState == CardState.ASKING
        hideCard()
        if (wasAsking) player.play()
        // 知らせられなくても視聴は続ける(飛ばした記録が1回減るだけ)
        io.execute { runCatching { Api.skip(titleId, question) } }
    }

    private fun togglePlay() {
        if (player.playbackState == Player.STATE_ENDED) player.seekTo(0)
        if (player.isPlaying) player.pause() else player.play()
    }

    private fun seekBy(deltaMs: Long) {
        if (cardState == CardState.ASKING) { hideCard(); player.play() }
        player.seekTo((player.currentPosition + deltaMs).coerceAtLeast(0))
    }

    companion object {
        const val EXTRA_TITLE_ID = "title_id"
        private const val LOG_TAG = "AskAlong"
        const val EXTRA_VIDEO_URL = "video_url"
        private const val TICK_MS = 250L
        private const val SEEK_MS = 10_000L
    }
}
