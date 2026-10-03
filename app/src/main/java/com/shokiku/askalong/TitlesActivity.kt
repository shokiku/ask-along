package com.shokiku.askalong

import android.content.Intent
import android.os.Bundle
import android.util.TypedValue
import android.view.KeyEvent
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors

/** 作品を選ぶ画面。一覧はクラウドから読む。選んだら PlayerActivity で再生する。 */
class TitlesActivity : AppCompatActivity() {

    private val io = Executors.newSingleThreadExecutor()
    private lateinit var status: TextView
    private lateinit var list: LinearLayout
    private var loadFailed = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_titles)
        status = findViewById(R.id.titles_status)
        list = findViewById(R.id.titles_list)
    }

    override fun onResume() {
        super.onResume()
        load() // 署名つき URL は6時間で切れるので、戻ってくるたびに読み直す
    }

    override fun onDestroy() {
        io.shutdownNow()
        super.onDestroy()
    }

    private fun load() {
        status.setText(R.string.titles_loading)
        io.execute {
            val result = runCatching { Api.titles() }
            runOnUiThread { result.fold(::show, ::showError) }
        }
    }

    private fun show(titles: List<Title>) {
        loadFailed = false
        list.removeAllViews()
        if (titles.isEmpty()) {
            status.setText(R.string.titles_empty)
            return
        }
        status.text = ""
        titles.forEach { title -> list.addView(titleButton(title)) }
        list.getChildAt(0).requestFocus()
    }

    private fun showError(error: Throwable) {
        loadFailed = true
        list.removeAllViews()
        status.text = getString(R.string.titles_error) + "\n(" + error.message + ")"
    }

    private fun titleButton(title: Title) = Button(this).apply {
        val ready = getString(if (title.questionsReady) R.string.questions_ready else R.string.questions_preparing)
        text = "${title.name}   ·   $ready"
        isAllCaps = false
        setTextColor(0xFFF3F1EC.toInt())
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f)
        setBackgroundResource(R.drawable.title_bg)
        setPadding(dp(28), dp(18), dp(28), dp(18))
        layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(14) }
        setOnClickListener {
            startActivity(Intent(this@TitlesActivity, PlayerActivity::class.java)
                .putExtra(PlayerActivity.EXTRA_TITLE_ID, title.id)
                .putExtra(PlayerActivity.EXTRA_VIDEO_URL, title.videoUrl))
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        val ok = keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER
        if (ok && loadFailed) {
            load()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
