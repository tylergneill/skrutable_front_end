// Cross-tab settings sync.
//
// Each open page keeps its own copy of the "extra" settings (see extra_option_names
// in flask_app.py) and sends that copy to the server whenever it saves. Without sync,
// a tab opened earlier would keep using, and saving back, values that another tab has
// since changed (e.g. settings page in one tab, workbench in another).
//
// BroadcastChannel is a browser feature: every same-site tab in the same browser that
// opens a channel with the same name receives the messages the others post to it.
// It never touches the server. The sender does not receive its own messages.
//
// Messages are plain objects keyed by session variable name,
// with booleans for checkboxes and strings for selects, e.g.
//   { preserve_anunasika: true, splitter_model: "dharmamitra_2024_sept" }

var SettingsSync = (function() {
	var channel = null;
	try {
		if (typeof BroadcastChannel !== "undefined") {
			channel = new BroadcastChannel("skrutable-settings");
		}
	} catch (e) {
		// unavailable (very old browser or restricted context): pages just don't sync
	}
	return {
		// tell the other open tabs that these settings now have these values
		announce: function(settings) {
			if (channel) channel.postMessage(settings);
		},
		// run handler(settings) whenever another tab announces a change
		onChange: function(handler) {
			if (channel) channel.onmessage = function(event) { handler(event.data || {}); };
		},
	};
})();
