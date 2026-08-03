/**
 * Simulates an MCP Apps host against a bundle's inlined bridge and asserts the
 * SEP-1865 lifecycle. Run: node tests/shell/bridge_harness.mjs apps/dist/smoke.html
 *
 * The bug this guards against: the view must send ui/notifications/initialized,
 * because hosts must not send tool-input/tool-result before receiving it.
 */
import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";
import { basename } from "node:path";

const target = process.argv[2];
if (!target) {
  console.error("usage: bridge_harness.mjs <bundle.html>");
  process.exit(2);
}

const html = readFileSync(target, "utf8");
const bridgeSrc = html.match(
  /<!-- shell:bridge:start -->\s*<script>([\s\S]*?)<\/script>/
);
if (!bridgeSrc) {
  console.error(`${basename(target)}: no bridge block found`);
  process.exit(1);
}

const sent = [];
const listeners = [];
const styleProps = {};

function makeEl() {
  return {
    innerHTML: "",
    scrollHeight: 420,
    offsetHeight: 420,
    scrollWidth: 600,
    offsetWidth: 600,
    style: { setProperty: (k, v) => (styleProps[k] = v) },
    setAttribute() {},
  };
}

const body = makeEl();
const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  Promise,
  Object,
  Error,
  Math,
  JSON,
  String,
  Map,
  document: {
    body,
    documentElement: makeEl(),
    getElementById: () => makeEl(),
  },
};
sandbox.window = sandbox;
sandbox.global = sandbox;
sandbox.window.parent = {
  postMessage: (msg) => sent.push(msg),
};
sandbox.window.addEventListener = (type, fn) => {
  if (type === "message") listeners.push(fn);
};
createContext(sandbox);
runInContext(bridgeSrc[1], sandbox);

function hostSend(msg) {
  listeners.forEach((fn) => fn({ data: msg, source: sandbox.window.parent }));
}
const byMethod = (m) => sent.filter((x) => x.method === m);

const failures = [];
function check(label, cond) {
  if (!cond) failures.push(label);
}

const bridge = new sandbox.ZiksakaBridge("harness");
let resultPayload = null;
bridge.onToolResult((params) => {
  resultPayload = sandbox.ZiksakaBridge.structured(params);
});

const connected = bridge.connect();

const init = sent.find((m) => m.method === "ui/initialize");
check("view sends ui/initialize", !!init);
check("ui/initialize declares appCapabilities", !!init?.params?.appCapabilities);
check(
  "view sends no notification before initialize resolves",
  byMethod("ui/notifications/initialized").length === 0
);

hostSend({
  jsonrpc: "2.0",
  id: init.id,
  result: {
    hostContext: { theme: "dark", styles: { variables: { "--x": "#fff" } } },
    capabilities: { serverTools: {} },
  },
});

await connected;
await new Promise((r) => setTimeout(r, 120));

check(
  "view sends ui/notifications/initialized after handshake",
  byMethod("ui/notifications/initialized").length === 1
);
check("view reports size", byMethod("ui/notifications/size-changed").length >= 1);
const size = byMethod("ui/notifications/size-changed")[0];
check("size payload has height", size?.params?.height > 0);
check("host theme variables applied", styleProps["--x"] === "#fff");

hostSend({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-input",
  params: { arguments: { scope: "work" } },
});
hostSend({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: {
    content: [{ type: "text", text: '{"ok":true}' }],
    structuredContent: { ok: true, message: "hi" },
  },
});

check("tool result delivered to app", resultPayload?.ok === true);
check("tool input captured", bridge.toolInput?.scope === "work");

hostSend({ jsonrpc: "2.0", id: 99, method: "ui/resource-teardown", params: {} });
const teardown = sent.find((m) => m.id === 99 && m.result);
check("view answers ui/resource-teardown", !!teardown);

hostSend({ jsonrpc: "2.0", id: 100, method: "ping", params: {} });
check("view answers ping", !!sent.find((m) => m.id === 100 && m.result));

if (failures.length) {
  console.error(`FAIL ${basename(target)}`);
  failures.forEach((f) => console.error("  - " + f));
  process.exit(1);
}
console.log(`ok ${basename(target)} (${sent.length} messages sent)`);
process.exit(0);
