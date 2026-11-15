import assert from "node:assert/strict";
import { test } from "node:test";
import { AUTO_SETTINGS, processClip } from "./process-clip.ts";

for (const { status, waited, body, failure } of [
  { status: 504, waited: 0, body: '{"error":"Ghost API is still processing; the proxy stopped waiting."}', failure: { kind: "proxy-timeout" } },
  { status: 504, waited: 600_000, body: '{"error":"Gateway timeout"}', failure: { kind: "proxy-timeout" } },
  { status: 504, waited: 0, body: "<html>Gateway timeout</html>", failure: { kind: "proxy-timeout" } },
  { status: 502, waited: 0, body: '{"error":"Service unavailable"}', failure: { kind: "offline", message: "Service unavailable" } },
  { status: 502, waited: 30_000, body: '{"error":"Service unavailable"}', failure: { kind: "proxy-timeout" } },
]) {
  test(`HTTP ${status} after ${waited} ms with ${body.startsWith("<") ? "HTML" : "JSON"} uses ${failure.kind}`, async (t) => {
    const originalXHR = globalThis.XMLHttpRequest;
    t.after(() => {
      if (originalXHR === undefined) delete globalThis.XMLHttpRequest;
      else globalThis.XMLHttpRequest = originalXHR;
    });
    let nowCalls = 0;
    t.mock.method(performance, "now", () => nowCalls++ === 0 ? 0 : waited);
    globalThis.XMLHttpRequest = class {
      upload = {};
      status = status;
      responseText = body;
      open(method, url) {
        assert.equal(method, "POST");
        assert.equal(url, "/api/process");
      }
      setRequestHeader(name, value) {
        assert.equal(name, "Accept");
        assert.equal(value, "application/json");
      }
      send(form) {
        assert.equal(form.get("file").name, "swing.mov");
        this.upload.onload();
        this.onload();
      }
    };
    const job = processClip(new File(["synthetic clip"], "swing.mov"), AUTO_SETTINGS, {
      progress() {}, uploaded() {},
    });
    assert.deepEqual(await job.result, { ok: false, failure });
  });
}
