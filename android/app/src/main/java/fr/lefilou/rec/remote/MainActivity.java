package fr.lefilou.rec.remote;

import android.app.Activity;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final String SETUP = "file:///android_asset/index.html";
    private WebView web;
    private boolean onSetup = true;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // L'écran reste allumé : sinon le téléphone perd la connexion avec le PC.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                onSetup = url.startsWith("file:///android_asset");
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    view.loadUrl(SETUP + "?error=1");
                }
            }
        });
        web.loadUrl(SETUP);
    }

    @Override
    public void onBackPressed() {
        if (!onSetup) {
            web.loadUrl(SETUP + "?edit=1");   // retour à l'écran « adresse du PC »
        } else {
            super.onBackPressed();
        }
    }
}
