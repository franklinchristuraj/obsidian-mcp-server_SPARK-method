/**
 * Minimal MCP Apps host bridge (postMessage JSON-RPC).
 * Compatible enough for Claude hosts; no network, no CDN.
 */
(function (global) {
  function ZiksakaBridge(appName) {
    this.appName = appName;
    this._id = 1;
    this._pending = new Map();
    this._onResult = null;
    this._onError = null;
    this.hostContext = {};
    var self = this;
    window.addEventListener("message", function (ev) {
      self._onMessage(ev);
    });
  }

  ZiksakaBridge.prototype.connect = function () {
    var self = this;
    return this._request("ui/initialize", {
      appInfo: { name: this.appName, version: "1.0.0" },
      appCapabilities: {
        availableDisplayModes: ["inline", "fullscreen"],
      },
    }).then(function (result) {
      self.hostContext = (result && result.hostContext) || {};
      return result;
    });
  };

  ZiksakaBridge.prototype.onToolResult = function (fn) {
    this._onResult = fn;
  };

  ZiksakaBridge.prototype.onToolError = function (fn) {
    this._onError = fn;
  };

  ZiksakaBridge.prototype.callServerTool = function (name, args) {
    return this._request("tools/call", {
      name: name,
      arguments: args || {},
    });
  };

  ZiksakaBridge.prototype.sendFollowup = function (message) {
    return this._request("ui/message", { role: "user", content: message }).catch(
      function () {
        return self._request("ui/open-link", { url: "#" }).catch(function () {
          return null;
        });
      }
    );
  };

  ZiksakaBridge.prototype.requestFullscreen = function () {
    return this._request("ui/request-display-mode", { mode: "fullscreen" }).catch(
      function () {
        return null;
      }
    );
  };

  ZiksakaBridge.prototype._request = function (method, params) {
    var id = this._id++;
    var self = this;
    return new Promise(function (resolve, reject) {
      self._pending.set(id, { resolve: resolve, reject: reject });
      var msg = { jsonrpc: "2.0", id: id, method: method, params: params || {} };
      (window.parent || window).postMessage(msg, "*");
      setTimeout(function () {
        if (self._pending.has(id)) {
          self._pending.delete(id);
          reject(new Error("timeout waiting for host: " + method));
        }
      }, 15000);
    });
  };

  ZiksakaBridge.prototype._onMessage = function (ev) {
    var data = ev.data;
    if (!data || data.jsonrpc !== "2.0") return;
    if (data.id != null && this._pending.has(data.id)) {
      var p = this._pending.get(data.id);
      this._pending.delete(data.id);
      if (data.error) p.reject(new Error(data.error.message || "host error"));
      else p.resolve(data.result);
      return;
    }
    if (data.method === "ui/notifications/tool-result" || data.method === "tool-result") {
      var result = (data.params && (data.params.structuredContent || data.params.result)) || data.params;
      if (this._onResult) this._onResult(result, data.params);
    }
    if (data.method === "ui/notifications/tool-input" && data.params) {
      // Host may stream input; ignore for now
    }
  };

  /** Extract structured payload from a tools/call result. */
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
