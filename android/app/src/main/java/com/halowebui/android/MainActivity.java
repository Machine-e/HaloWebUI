package com.halowebui.android;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Space;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.SSLException;

public final class MainActivity extends Activity {
	private static final String PREFS_NAME = "halo_webui_android";
	private static final String KEY_BASE_URL = "base_url";
	private static final String KEY_ACCOUNT = "account";
	private static final String KEY_PASSWORD = "password";
	private static final String KEY_AUTO_LOGIN = "auto_login";
	private static final String KEY_TOKEN = "token";

	private static final int REQUEST_TIMEOUT_MS = 12000;

	private SharedPreferences preferences;
	private final Handler mainHandler = new Handler(Looper.getMainLooper());
	private final ExecutorService executor = Executors.newSingleThreadExecutor();

	private EditText urlInput;
	private EditText accountInput;
	private EditText passwordInput;
	private CheckBox autoLoginInput;
	private TextView statusText;
	private Button loginButton;
	private WebView webView;
	private ProgressBar webProgress;

	private boolean darkMode;
	private int pageStartColor;
	private int pageEndColor;
	private int surfaceColor;
	private int inputColor;
	private int textColor;
	private int mutedTextColor;
	private int borderColor;
	private int buttonColor;
	private int buttonTextColor;
	private int accentColor;

	private String currentBaseUrl;
	private String pendingToken;
	private boolean tokenInjected;

	@Override
	protected void onCreate(Bundle savedInstanceState) {
		super.onCreate(savedInstanceState);
		preferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
		setupPalette();
		setupWindow();
		CookieManager.getInstance().setAcceptCookie(true);

		showLoginScreen(null);

		if (shouldAutoLogin()) {
			mainHandler.postDelayed(() -> beginLogin(true), 250);
		}
	}

	@Override
	protected void onDestroy() {
		if (webView != null) {
			webView.stopLoading();
			webView.destroy();
			webView = null;
		}
		executor.shutdownNow();
		super.onDestroy();
	}

	@Override
	public void onBackPressed() {
		if (webView != null && webView.canGoBack()) {
			webView.goBack();
			return;
		}
		super.onBackPressed();
	}

	private void setupPalette() {
		darkMode = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
			== Configuration.UI_MODE_NIGHT_YES;
		if (darkMode) {
			pageStartColor = Color.rgb(10, 10, 15);
			pageEndColor = Color.rgb(17, 24, 39);
			surfaceColor = Color.rgb(17, 24, 39);
			inputColor = Color.rgb(31, 41, 55);
			textColor = Color.rgb(243, 244, 246);
			mutedTextColor = Color.rgb(156, 163, 175);
			borderColor = Color.rgb(55, 65, 81);
			buttonColor = Color.rgb(243, 244, 246);
			buttonTextColor = Color.rgb(17, 24, 39);
		} else {
			pageStartColor = Color.rgb(249, 250, 251);
			pageEndColor = Color.rgb(239, 246, 255);
			surfaceColor = Color.rgb(255, 255, 255);
			inputColor = Color.rgb(243, 244, 246);
			textColor = Color.rgb(17, 24, 39);
			mutedTextColor = Color.rgb(107, 114, 128);
			borderColor = Color.rgb(229, 231, 235);
			buttonColor = Color.rgb(31, 41, 55);
			buttonTextColor = Color.WHITE;
		}
		accentColor = Color.rgb(37, 99, 235);
	}

	private void setupWindow() {
		Window window = getWindow();
		window.setStatusBarColor(pageStartColor);
		window.setNavigationBarColor(pageStartColor);
		if (!darkMode) {
			window.getDecorView().setSystemUiVisibility(
				View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
			);
		}
	}

	private boolean shouldAutoLogin() {
		return preferences.getBoolean(KEY_AUTO_LOGIN, false)
			&& !preferences.getString(KEY_BASE_URL, "").trim().isEmpty()
			&& !preferences.getString(KEY_ACCOUNT, "").trim().isEmpty()
			&& !preferences.getString(KEY_PASSWORD, "").isEmpty();
	}

	private void showLoginScreen(String message) {
		destroyWebView();

		FrameLayout root = new FrameLayout(this);
		root.setBackground(new GradientDrawable(
			GradientDrawable.Orientation.TL_BR,
			new int[] { pageStartColor, pageEndColor }
		));

		ScrollView scrollView = new ScrollView(this);
		scrollView.setFillViewport(true);
		root.addView(scrollView, new FrameLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			ViewGroup.LayoutParams.MATCH_PARENT
		));

		LinearLayout outer = new LinearLayout(this);
		outer.setOrientation(LinearLayout.VERTICAL);
		outer.setGravity(Gravity.CENTER);
		outer.setPadding(dp(24), dp(24), dp(24), dp(24));
		scrollView.addView(outer, new ScrollView.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			ViewGroup.LayoutParams.MATCH_PARENT
		));

		LinearLayout form = new LinearLayout(this);
		form.setOrientation(LinearLayout.VERTICAL);
		form.setGravity(Gravity.CENTER_HORIZONTAL);
		form.setPadding(dp(24), dp(28), dp(24), dp(28));
		form.setBackground(rounded(surfaceColor, dp(20), borderColor, 1));
		LinearLayout.LayoutParams formParams = new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			ViewGroup.LayoutParams.WRAP_CONTENT
		);
		formParams.width = Math.min(getResources().getDisplayMetrics().widthPixels - dp(48), dp(440));
		outer.addView(form, formParams);

		TextView logo = new TextView(this);
		logo.setText("H");
		logo.setGravity(Gravity.CENTER);
		logo.setTextColor(Color.WHITE);
		logo.setTypeface(Typeface.DEFAULT_BOLD);
		logo.setTextSize(24);
		logo.setBackground(rounded(accentColor, dp(18), Color.TRANSPARENT, 0));
		form.addView(logo, new LinearLayout.LayoutParams(dp(56), dp(56)));

		TextView title = new TextView(this);
		title.setText(getString(R.string.login_title));
		title.setTextColor(textColor);
		title.setTextSize(24);
		title.setTypeface(Typeface.DEFAULT_BOLD);
		title.setGravity(Gravity.CENTER);
		LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			ViewGroup.LayoutParams.WRAP_CONTENT
		);
		titleParams.setMargins(0, dp(18), 0, dp(4));
		form.addView(title, titleParams);

		TextView subtitle = new TextView(this);
		subtitle.setText(getString(R.string.login_subtitle));
		subtitle.setTextColor(mutedTextColor);
		subtitle.setTextSize(13);
		subtitle.setGravity(Gravity.CENTER);
		subtitle.setLineSpacing(dp(2), 1.0f);
		form.addView(subtitle, fullWidthParams());

		addSpace(form, 22);

		form.addView(label(getString(R.string.server_url_label)), fullWidthParams());
		urlInput = input(getString(R.string.server_url_hint), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
		urlInput.setText(preferences.getString(KEY_BASE_URL, ""));
		form.addView(urlInput, inputParams());

		form.addView(label(getString(R.string.account_label)), fullWidthParams());
		accountInput = input(getString(R.string.account_hint), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
		accountInput.setText(preferences.getString(KEY_ACCOUNT, ""));
		form.addView(accountInput, inputParams());

		form.addView(label(getString(R.string.password_label)), fullWidthParams());
		passwordInput = input(getString(R.string.password_hint), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
		if (preferences.getBoolean(KEY_AUTO_LOGIN, false)) {
			passwordInput.setText(preferences.getString(KEY_PASSWORD, ""));
		}
		form.addView(passwordInput, inputParams());

		autoLoginInput = new CheckBox(this);
		autoLoginInput.setText(getString(R.string.auto_login_label));
		autoLoginInput.setTextColor(textColor);
		autoLoginInput.setTextSize(14);
		autoLoginInput.setChecked(preferences.getBoolean(KEY_AUTO_LOGIN, false));
		LinearLayout.LayoutParams autoParams = fullWidthParams();
		autoParams.setMargins(0, dp(6), 0, dp(8));
		form.addView(autoLoginInput, autoParams);

		statusText = new TextView(this);
		statusText.setTextColor(message == null ? mutedTextColor : accentColor);
		statusText.setTextSize(13);
		statusText.setGravity(Gravity.CENTER);
		statusText.setMinHeight(dp(24));
		statusText.setText(message == null ? getString(R.string.login_status_idle) : message);
		form.addView(statusText, fullWidthParams());

		loginButton = new Button(this);
		loginButton.setAllCaps(false);
		loginButton.setText(getString(R.string.login_button));
		loginButton.setTextColor(buttonTextColor);
		loginButton.setTextSize(15);
		loginButton.setTypeface(Typeface.DEFAULT_BOLD);
		loginButton.setBackground(rounded(buttonColor, dp(999), Color.TRANSPARENT, 0));
		loginButton.setOnClickListener(view -> beginLogin(false));
		LinearLayout.LayoutParams buttonParams = fullWidthParams();
		buttonParams.height = dp(48);
		buttonParams.setMargins(0, dp(12), 0, 0);
		form.addView(loginButton, buttonParams);

		setContentView(root);
	}

	private TextView label(String text) {
		TextView view = new TextView(this);
		view.setText(text);
		view.setTextColor(textColor);
		view.setTextSize(14);
		view.setTypeface(Typeface.DEFAULT_BOLD);
		view.setGravity(Gravity.START);
		return view;
	}

	private EditText input(String hint, int inputType) {
		EditText editText = new EditText(this);
		editText.setSingleLine(true);
		editText.setHint(hint);
		editText.setHintTextColor(mutedTextColor);
		editText.setTextColor(textColor);
		editText.setTextSize(14);
		editText.setInputType(inputType);
		editText.setPadding(dp(14), 0, dp(14), 0);
		editText.setBackground(rounded(inputColor, dp(12), borderColor, 1));
		return editText;
	}

	private LinearLayout.LayoutParams inputParams() {
		LinearLayout.LayoutParams params = fullWidthParams();
		params.height = dp(46);
		params.setMargins(0, dp(7), 0, dp(14));
		return params;
	}

	private LinearLayout.LayoutParams fullWidthParams() {
		return new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			ViewGroup.LayoutParams.WRAP_CONTENT
		);
	}

	private void addSpace(LinearLayout parent, int dpHeight) {
		Space space = new Space(this);
		parent.addView(space, new LinearLayout.LayoutParams(1, dp(dpHeight)));
	}

	private void beginLogin(boolean fromAutoLogin) {
		if (urlInput == null || accountInput == null || passwordInput == null) {
			return;
		}

		final String baseUrl;
		try {
			baseUrl = normalizeBaseUrl(urlInput.getText().toString());
		} catch (IllegalArgumentException error) {
			setLoginStatus(error.getMessage(), true);
			return;
		}

		final String account = accountInput.getText().toString().trim();
		final String password = passwordInput.getText().toString();

		if (account.isEmpty()) {
			setLoginStatus(getString(R.string.account_required), true);
			return;
		}
		if (password.isEmpty()) {
			setLoginStatus(getString(R.string.password_required), true);
			return;
		}

		hideKeyboard();
		setLoginBusy(true, fromAutoLogin ? getString(R.string.auto_login_running) : getString(R.string.login_running));

		executor.execute(() -> {
			LoginResult result = signIn(baseUrl, account, password);
			mainHandler.post(() -> handleLoginResult(result, baseUrl, account, password, fromAutoLogin));
		});
	}

	private void handleLoginResult(
		LoginResult result,
		String baseUrl,
		String account,
		String password,
		boolean fromAutoLogin
	) {
		if (result.success) {
			boolean autoLogin = fromAutoLogin || autoLoginInput.isChecked();
			saveLoginSettings(baseUrl, account, password, autoLogin, result.token);
			openWebApp(baseUrl, result.token);
			return;
		}

		String message = fromAutoLogin
			? getString(result.networkError ? R.string.auto_login_network_failed : R.string.auto_login_failed, result.message)
			: result.message;

		if (fromAutoLogin) {
			showLoginScreen(message);
		} else {
			setLoginBusy(false, message);
		}
	}

	private LoginResult signIn(String baseUrl, String account, String password) {
		HttpURLConnection connection = null;
		try {
			URL url = new URL(baseUrl + "/api/v1/auths/signin");
			JSONObject body = new JSONObject()
				.put("email", account)
				.put("password", password);
			byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);

			connection = (HttpURLConnection) url.openConnection();
			connection.setRequestMethod("POST");
			connection.setConnectTimeout(REQUEST_TIMEOUT_MS);
			connection.setReadTimeout(REQUEST_TIMEOUT_MS);
			connection.setDoOutput(true);
			connection.setRequestProperty("Accept", "application/json");
			connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
			connection.setRequestProperty("Content-Length", String.valueOf(payload.length));

			try (OutputStream outputStream = connection.getOutputStream()) {
				outputStream.write(payload);
			}

			int status = connection.getResponseCode();
			String raw = readResponse(status >= 200 && status < 300
				? connection.getInputStream()
				: connection.getErrorStream());

			if (status >= 200 && status < 300) {
				JSONObject response = new JSONObject(raw);
				String token = response.optString("token", response.optString("access_token", ""));
				if (token.isEmpty()) {
					return LoginResult.error(getString(R.string.login_missing_token), false);
				}
				return LoginResult.success(token);
			}

			return LoginResult.error(parseErrorMessage(raw, status), false);
		} catch (UnknownHostException | ConnectException | SocketTimeoutException | SSLException error) {
			return LoginResult.error(getString(R.string.network_error, error.getLocalizedMessage()), true);
		} catch (IOException error) {
			return LoginResult.error(getString(R.string.network_error, error.getLocalizedMessage()), true);
		} catch (JSONException error) {
			return LoginResult.error(getString(R.string.login_parse_error), false);
		} finally {
			if (connection != null) {
				connection.disconnect();
			}
		}
	}

	private String readResponse(InputStream inputStream) throws IOException {
		if (inputStream == null) {
			return "";
		}
		try (InputStream input = inputStream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
			byte[] buffer = new byte[4096];
			int read;
			while ((read = input.read(buffer)) != -1) {
				output.write(buffer, 0, read);
			}
			return output.toString(StandardCharsets.UTF_8.name());
		}
	}

	private String parseErrorMessage(String raw, int status) {
		if (raw == null || raw.trim().isEmpty()) {
			return getString(R.string.http_error, status);
		}
		try {
			JSONObject response = new JSONObject(raw);
			Object detail = response.opt("detail");
			if (detail instanceof String) {
				return (String) detail;
			}
			if (detail instanceof JSONObject || detail instanceof JSONArray) {
				return detail.toString();
			}
			String message = response.optString("message", "");
			if (!message.isEmpty()) {
				return message;
			}
		} catch (JSONException ignored) {
			// Fall through to the raw server text.
		}
		return raw.length() > 220 ? raw.substring(0, 220) : raw;
	}

	private void saveLoginSettings(String baseUrl, String account, String password, boolean autoLogin, String token) {
		SharedPreferences.Editor editor = preferences.edit()
			.putString(KEY_BASE_URL, baseUrl)
			.putString(KEY_ACCOUNT, account)
			.putBoolean(KEY_AUTO_LOGIN, autoLogin);

		if (autoLogin) {
			editor.putString(KEY_PASSWORD, password);
			editor.putString(KEY_TOKEN, token);
		} else {
			editor.remove(KEY_PASSWORD);
			editor.remove(KEY_TOKEN);
		}
		editor.apply();
	}

	private void openWebApp(String baseUrl, String token) {
		destroyWebView();
		currentBaseUrl = baseUrl;
		pendingToken = token;
		tokenInjected = false;

		LinearLayout root = new LinearLayout(this);
		root.setOrientation(LinearLayout.VERTICAL);
		root.setBackgroundColor(pageStartColor);

		LinearLayout toolbar = new LinearLayout(this);
		toolbar.setGravity(Gravity.CENTER_VERTICAL);
		toolbar.setPadding(dp(14), 0, dp(10), 0);
		toolbar.setBackgroundColor(surfaceColor);
		root.addView(toolbar, new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			dp(56)
		));

		LinearLayout titleBox = new LinearLayout(this);
		titleBox.setOrientation(LinearLayout.VERTICAL);
		titleBox.setGravity(Gravity.CENTER_VERTICAL);
		toolbar.addView(titleBox, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1));

		TextView title = new TextView(this);
		title.setText(getString(R.string.app_name));
		title.setTextColor(textColor);
		title.setTextSize(16);
		title.setTypeface(Typeface.DEFAULT_BOLD);
		titleBox.addView(title);

		TextView urlText = new TextView(this);
		urlText.setText(baseUrl);
		urlText.setTextColor(mutedTextColor);
		urlText.setTextSize(11);
		urlText.setSingleLine(true);
		titleBox.addView(urlText);

		Button changeButton = new Button(this);
		changeButton.setAllCaps(false);
		changeButton.setText(getString(R.string.change_server_button));
		changeButton.setTextColor(textColor);
		changeButton.setTextSize(13);
		changeButton.setBackground(rounded(inputColor, dp(999), borderColor, 1));
		changeButton.setOnClickListener(view -> showLoginScreen(getString(R.string.change_server_hint)));
		toolbar.addView(changeButton, new LinearLayout.LayoutParams(dp(76), dp(38)));

		webProgress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
		webProgress.setMax(100);
		root.addView(webProgress, new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			dp(2)
		));

		webView = new WebView(this);
		configureWebView(webView);
		root.addView(webView, new LinearLayout.LayoutParams(
			ViewGroup.LayoutParams.MATCH_PARENT,
			0,
			1
		));

		setContentView(root);
		webView.loadUrl(baseUrl);
	}

	private void configureWebView(WebView view) {
		WebSettings settings = view.getSettings();
		settings.setJavaScriptEnabled(true);
		settings.setDomStorageEnabled(true);
		settings.setDatabaseEnabled(true);
		settings.setLoadWithOverviewMode(true);
		settings.setUseWideViewPort(true);
		settings.setBuiltInZoomControls(false);
		settings.setDisplayZoomControls(false);
		settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

		CookieManager cookieManager = CookieManager.getInstance();
		cookieManager.setAcceptCookie(true);
		cookieManager.setAcceptThirdPartyCookies(view, true);

		view.setWebChromeClient(new WebChromeClient() {
			@Override
			public void onProgressChanged(WebView view, int progress) {
				if (webProgress != null) {
					webProgress.setProgress(progress);
					webProgress.setVisibility(progress >= 100 ? View.GONE : View.VISIBLE);
				}
			}
		});

		view.setWebViewClient(new WebViewClient() {
			@Override
			public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
				Uri uri = request.getUrl();
				String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
				if ("http".equals(scheme) || "https".equals(scheme)) {
					return false;
				}
				openExternalUrl(uri);
				return true;
			}

			@Override
			public void onPageFinished(WebView view, String url) {
				injectTokenIfNeeded(view, url);
			}

			@Override
			public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
				if (request.isForMainFrame()) {
					showLoginScreen(getString(R.string.webview_network_failed, error.getDescription()));
				}
			}

			@Override
			public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
				if (request.isForMainFrame() && errorResponse.getStatusCode() >= 500) {
					showLoginScreen(getString(R.string.webview_http_failed, errorResponse.getStatusCode()));
				}
			}
		});
	}

	private void injectTokenIfNeeded(WebView view, String pageUrl) {
		if (tokenInjected || pendingToken == null || pendingToken.isEmpty() || !sameOrigin(pageUrl, currentBaseUrl)) {
			return;
		}

		tokenInjected = true;
		String script = "(function(){"
			+ "localStorage.setItem('token'," + JSONObject.quote(pendingToken) + ");"
			+ "window.location.replace(" + JSONObject.quote(currentBaseUrl) + ");"
			+ "})();";
		view.evaluateJavascript(script, null);
	}

	private boolean sameOrigin(String pageUrl, String baseUrl) {
		if (pageUrl == null || baseUrl == null) {
			return false;
		}
		Uri page = Uri.parse(pageUrl);
		Uri base = Uri.parse(baseUrl);
		return safeEquals(page.getScheme(), base.getScheme())
			&& safeEquals(page.getHost(), base.getHost())
			&& normalizedPort(page) == normalizedPort(base);
	}

	private boolean safeEquals(String left, String right) {
		return left == null ? right == null : left.equalsIgnoreCase(right);
	}

	private int normalizedPort(Uri uri) {
		int port = uri.getPort();
		if (port >= 0) {
			return port;
		}
		String scheme = uri.getScheme();
		if ("https".equalsIgnoreCase(scheme)) {
			return 443;
		}
		return 80;
	}

	private void openExternalUrl(Uri uri) {
		try {
			startActivity(new Intent(Intent.ACTION_VIEW, uri));
		} catch (ActivityNotFoundException ignored) {
			// Nothing to open this URL scheme with.
		}
	}

	private void destroyWebView() {
		if (webView == null) {
			return;
		}
		webView.stopLoading();
		webView.setWebChromeClient(null);
		webView.setWebViewClient(null);
		webView.destroy();
		webView = null;
		webProgress = null;
	}

	private void setLoginBusy(boolean busy, String message) {
		urlInput.setEnabled(!busy);
		accountInput.setEnabled(!busy);
		passwordInput.setEnabled(!busy);
		autoLoginInput.setEnabled(!busy);
		loginButton.setEnabled(!busy);
		loginButton.setText(busy ? getString(R.string.login_button_busy) : getString(R.string.login_button));
		setLoginStatus(message, false);
	}

	private void setLoginStatus(String message, boolean error) {
		if (statusText == null) {
			return;
		}
		statusText.setText(message);
		statusText.setTextColor(error ? Color.rgb(220, 38, 38) : mutedTextColor);
	}

	private String normalizeBaseUrl(String rawValue) {
		String value = rawValue == null ? "" : rawValue.trim();
		if (value.isEmpty()) {
			throw new IllegalArgumentException(getString(R.string.server_url_required));
		}
		if (!value.toLowerCase(Locale.ROOT).startsWith("http://")
			&& !value.toLowerCase(Locale.ROOT).startsWith("https://")) {
			value = "http://" + value;
		}
		Uri uri = Uri.parse(value);
		String scheme = uri.getScheme();
		if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) {
			throw new IllegalArgumentException(getString(R.string.server_url_invalid));
		}
		if (uri.getHost() == null || uri.getHost().trim().isEmpty()) {
			throw new IllegalArgumentException(getString(R.string.server_url_invalid));
		}
		while (value.endsWith("/") && value.length() > scheme.length() + 3) {
			value = value.substring(0, value.length() - 1);
		}
		return value;
	}

	private GradientDrawable rounded(int color, int radius, int strokeColor, int strokeWidthDp) {
		GradientDrawable drawable = new GradientDrawable();
		drawable.setColor(color);
		drawable.setCornerRadius(radius);
		if (strokeWidthDp > 0) {
			drawable.setStroke(dp(strokeWidthDp), strokeColor);
		}
		return drawable;
	}

	private int dp(int value) {
		return Math.round(value * getResources().getDisplayMetrics().density);
	}

	private void hideKeyboard() {
		View currentFocus = getCurrentFocus();
		if (currentFocus == null) {
			return;
		}
		InputMethodManager inputMethodManager =
			(InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
		if (inputMethodManager != null) {
			inputMethodManager.hideSoftInputFromWindow(currentFocus.getWindowToken(), 0);
		}
	}

	private static final class LoginResult {
		final boolean success;
		final String token;
		final String message;
		final boolean networkError;

		private LoginResult(boolean success, String token, String message, boolean networkError) {
			this.success = success;
			this.token = token;
			this.message = message;
			this.networkError = networkError;
		}

		static LoginResult success(String token) {
			return new LoginResult(true, token, "", false);
		}

		static LoginResult error(String message, boolean networkError) {
			return new LoginResult(false, "", message, networkError);
		}
	}
}
