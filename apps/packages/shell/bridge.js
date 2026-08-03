/**
 * Minimal MCP Apps host bridge (postMessage JSON-RPC, SEP-1865).
 * No network, no CDN.
 *
 * Lifecycle: ui/initialize -> ui/notifications/initialized -> host sends
 * ui/notifications/tool-input then ui/notifications/tool-result. The host is
 * forbidden from sending anything before `initialized`, so the notification is
 * mandatory, not optional.
 */
(function (global) {
  var PROTOCOL_VERSION = "2026-01-26";
  var DEFAULT_TIMEOUT_MS = 15000;
  var TOOL_CALL_TIMEOUT_MS = 60000;
  var NO_RESULT_AFTER_MS = 20000;

  function ZiksakaBridge(appName) {
    this.appName = appName;
    this._id = 1;
    this._pending = new Map();
    this._onResult = null;
    this._onError = null;
    this._onInput = null;
    this._onHostContext = null;
    this._gotResult = false;
    this._noResultTimer = null;
    this._sizeTimer = null;
    this._lastSize = "";
    this.hostContext = {};
    this.hostCapabilities = {};
    this.toolInput = null;
    this.autoDiagnostics = true;
    var self = this;
    window.addEventListener("message", function (ev) {
      self._onMessage(ev);
    });
  }

  ZiksakaBridge.prototype.connect = function () {
    var self = this;
    return this._request("ui/initialize", {
      protocolVersion: PROTOCOL_VERSION,
      appInfo: { name: this.appName, version: "1.0.0" },
      appCapabilities: {
        availableDisplayModes: ["inline", "fullscreen"],
      },
    }).then(function (result) {
      self.hostContext = (result && result.hostContext) || {};
      self.hostCapabilities = (result && result.capabilities) || {};
      self._applyHostStyles();
      // The host will not send tool-input/tool-result until it sees this.
      self._notify("ui/notifications/initialized", {});
      self._watchSize();
      self._armNoResultDiagnostic();
      return result;
    });
  };

  ZiksakaBridge.prototype.onToolResult = function (fn) {
    this._onResult = fn;
  };

  ZiksakaBridge.prototype.onToolError = function (fn) {
    this._onError = fn;
  };

  ZiksakaBridge.prototype.onToolInput = function (fn) {
    this._onInput = fn;
    if (this.toolInput) fn(this.toolInput);
  };

  ZiksakaBridge.prototype.onHostContextChanged = function (fn) {
    this._onHostContext = fn;
  };

  ZiksakaBridge.prototype.callServerTool = function (name, args) {
    return this._request(
      "tools/call",
      { name: name, arguments: args || {} },
      TOOL_CALL_TIMEOUT_MS
    );
  };

  ZiksakaBridge.prototype.readResource = function (uri) {
    return this._request("resources/read", { uri: uri });
  };

  ZiksakaBridge.prototype.sendFollowup = function (text) {
    return this._request("ui/message", {
      role: "user",
      content: { type: "text", text: String(text) },
    });
  };

  ZiksakaBridge.prototype.updateModelContext = function (structuredContent) {
    return this._request("ui/update-model-context", {
      structuredContent: structuredContent || {},
    });
  };

  ZiksakaBridge.prototype.openLink = function (url) {
    return this._request("ui/open-link", { url: url });
  };

  ZiksakaBridge.prototype.requestFullscreen = function () {
    var modes = this.hostContext.availableDisplayModes;
    if (modes && modes.indexOf("fullscreen") === -1) {
      return Promise.resolve({ mode: this.hostContext.displayMode || "inline" });
    }
    return this._request("ui/request-display-mode", { mode: "fullscreen" }).catch(
      function () {
        return null;
      }
    );
  };

  ZiksakaBridge.prototype.log = function (level, data) {
    this._notify("notifications/message", {
      level: level || "info",
      logger: this.appName,
      data: data,
    });
  };

  /** Report body size so the host can size the iframe. */
  ZiksakaBridge.prototype.reportSize = function () {
    var body = document.body;
    if (!body) return;
    var height = Math.ceil(
      Math.max(
        body.scrollHeight,
        body.offsetHeight,
        document.documentElement ? document.documentElement.scrollHeight : 0
      )
    );
    var width = Math.ceil(body.scrollWidth || body.offsetWidth || 0);
    if (!height) return;
    var key = width + "x" + height;
    if (key === this._lastSize) return;
    this._lastSize = key;
    this._notify("ui/notifications/size-changed", {
      width: width,
      height: height,
    });
  };

  ZiksakaBridge.prototype._watchSize = function () {
    var self = this;
    var schedule = function () {
      if (self._sizeTimer) return;
      self._sizeTimer = setTimeout(function () {
        self._sizeTimer = null;
        self.reportSize();
      }, 50);
    };
    schedule();
    if (global.ResizeObserver && document.body) {
      try {
        new ResizeObserver(schedule).observe(document.body);
      } catch (e) {
        /* ignore */
      }
    }
    window.addEventListener("load", schedule);
  };

  /** Apply host-provided theme variables for visual cohesion. */
  ZiksakaBridge.prototype._applyHostStyles = function () {
    var styles = this.hostContext.styles || {};
    var vars = styles.variables || {};
    var rootEl = document.documentElement;
    Object.keys(vars).forEach(function (key) {
      var value = vars[key];
      if (typeof value === "string" && value) rootEl.style.setProperty(key, value);
    });
    if (this.hostContext.theme) {
      rootEl.style.colorScheme = this.hostContext.theme;
      rootEl.setAttribute("data-theme", this.hostContext.theme);
    }
  };

  /**
   * A blank surface is the worst failure mode: if the host never delivers a
   * result, say so instead of leaving the skeleton up forever.
   */
  ZiksakaBridge.prototype._armNoResultDiagnostic = function () {
    var self = this;
    this._noResultTimer = setTimeout(function () {
      if (self._gotResult) return;
      var err = new Error(
        "No tool result received from the host after " +
          Math.round(NO_RESULT_AFTER_MS / 1000) +
          "s."
      );
      if (self._onError) {
        self._onError(err);
      } else if (self.autoDiagnostics) {
        self._renderDiagnostic(err.message);
      }
    }, NO_RESULT_AFTER_MS);
  };

  ZiksakaBridge.prototype._renderDiagnostic = function (message) {
    var root = document.getElementById("root");
    if (!root) return;
    root.innerHTML =
      '<div class="error"><strong>' +
      this.appName +
      "</strong><br/>" +
      String(message).replace(/[<>&]/g, "") +
      "</div>";
    this.reportSize();
  };

  ZiksakaBridge.prototype._request = function (method, params, timeoutMs) {
    var id = this._id++;
    var self = this;
    return new Promise(function (resolve, reject) {
      self._pending.set(id, { resolve: resolve, reject: reject });
      self._post({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
      setTimeout(function () {
        if (self._pending.has(id)) {
          self._pending.delete(id);
          reject(new Error("timeout waiting for host: " + method));
        }
      }, timeoutMs || DEFAULT_TIMEOUT_MS);
    });
  };

  ZiksakaBridge.prototype._notify = function (method, params) {
    this._post({ jsonrpc: "2.0", method: method, params: params || {} });
  };

  ZiksakaBridge.prototype._respond = function (id, result) {
    this._post({ jsonrpc: "2.0", id: id, result: result || {} });
  };

  ZiksakaBridge.prototype._post = function (msg) {
    (window.parent || window).postMessage(msg, "*");
  };

  ZiksakaBridge.prototype._onMessage = function (ev) {
    var data = ev.data;
    if (!data || data.jsonrpc !== "2.0") return;

    // Response to one of our requests.
    if (data.method === undefined && data.id != null) {
      var p = this._pending.get(data.id);
      if (!p) return;
      this._pending.delete(data.id);
      if (data.error) p.reject(new Error(data.error.message || "host error"));
      else p.resolve(data.result);
      return;
    }

    // Request from the host: it blocks until we answer.
    if (data.id != null && data.method) {
      if (data.method === "ping" || data.method === "ui/resource-teardown") {
        this._respond(data.id, {});
      } else {
        this._post({
          jsonrpc: "2.0",
          id: data.id,
          error: { code: -32601, message: "Method not found: " + data.method },
        });
      }
      return;
    }

    switch (data.method) {
      case "ui/notifications/tool-input":
      case "ui/notifications/tool-input-partial":
        this.toolInput = (data.params && data.params.arguments) || {};
        if (this._onInput) this._onInput(this.toolInput);
        break;
      case "ui/notifications/tool-result":
        this._gotResult = true;
        clearTimeout(this._noResultTimer);
        if (this._onResult) this._onResult(data.params, data.params);
        this.reportSize();
        break;
      case "ui/notifications/tool-cancelled":
        this._gotResult = true;
        clearTimeout(this._noResultTimer);
        var reason = (data.params && data.params.reason) || "Tool call cancelled.";
        if (this._onError) this._onError(new Error(reason));
        else if (this.autoDiagnostics) this._renderDiagnostic(reason);
        break;
      case "ui/notifications/host-context-changed":
        this.hostContext = Object.assign({}, this.hostContext, data.params || {});
        this._applyHostStyles();
        if (this._onHostContext) this._onHostContext(this.hostContext);
        break;
      default:
        break;
    }
  };

  /** Extract structured payload from a CallToolResult. */
  ZiksakaBridge.structured = function (result) {
    if (!result) return null;
    if (result.structuredContent) return result.structuredContent;
    if (result.metadata) return result.metadata;
    if (result.content && result.content[0] && result.content[0].text) {
      try {
        return JSON.parse(result.content[0].text);
      } catch (e) {
        return { text: result.content[0].text };
      }
    }
    return result;
  };

  global.ZiksakaBridge = ZiksakaBridge;
})(window);
