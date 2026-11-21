package com.utkarsh.sanitrack;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.PermissionRequest;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebChromeClient;
import com.getcapacitor.BridgeWebViewClient;

public class MainActivity extends BridgeActivity {
    private static final int PERMISSION_REQ_CODE = 101;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 1. Request native Android Camera & Audio permissions if not yet granted
        String[] permissions = new String[]{
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO
        };
        boolean needsPermission = false;
        for (String perm : permissions) {
            if (ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED) {
                needsPermission = true;
                break;
            }
        }
        if (needsPermission) {
            ActivityCompat.requestPermissions(this, permissions, PERMISSION_REQ_CODE);
        }

        // 2. Configure WebView WebChromeClient to grant getUserMedia (camera/video) requests while preserving Capacitor file chooser
        if (this.bridge != null && this.bridge.getWebView() != null) {
            this.bridge.getWebView().setWebChromeClient(new BridgeWebChromeClient(this.bridge) {
                @Override
                public void onPermissionRequest(final PermissionRequest request) {
                    runOnUiThread(() -> {
                        request.grant(request.getResources());
                    });
                }
            });

            // 3. Handle Telegram (t.me / tg:), WhatsApp, and external links via native intents
            this.bridge.getWebView().setWebViewClient(new BridgeWebViewClient(this.bridge) {
                @Override
                public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                    String url = request.getUrl().toString();
                    if (isExternalUrl(url)) {
                        return launchExternalIntent(url) || super.shouldOverrideUrlLoading(view, request);
                    }
                    return super.shouldOverrideUrlLoading(view, request);
                }

                @Override
                public boolean shouldOverrideUrlLoading(WebView view, String url) {
                    if (url != null && isExternalUrl(url)) {
                        return launchExternalIntent(url) || super.shouldOverrideUrlLoading(view, url);
                    }
                    return super.shouldOverrideUrlLoading(view, url);
                }

                private boolean isExternalUrl(String url) {
                    return url != null && (
                        url.startsWith("https://t.me/") || 
                        url.startsWith("tg://") || 
                        url.startsWith("tel:") || 
                        url.startsWith("mailto:") || 
                        url.startsWith("whatsapp://") || 
                        url.startsWith("https://wa.me/")
                    );
                }

                private boolean launchExternalIntent(String url) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(intent);
                        return true;
                    } catch (Exception e) {
                        return false;
                    }
                }
            });
        }
    }
}
