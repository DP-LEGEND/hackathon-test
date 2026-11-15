import assert from "node:assert/strict";
import { test } from "node:test";
import { AUTO_SETTINGS, checkOffset, checkSensorCsv, processClip } from "./process-clip.ts";

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

/** Stands in for XMLHttpRequest: records the request and answers with `status` and `body`. */
function fakeXHR(t, status, body) {
  const originalXHR = globalThis.XMLHttpRequest;
  t.after(() => {
    if (originalXHR === undefined) delete globalThis.XMLHttpRequest;
    else globalThis.XMLHttpRequest = originalXHR;
  });
  const seen = {};
  globalThis.XMLHttpRequest = class {
    upload = {};
    status = status;
    responseText = body;
    open(method, url) { Object.assign(seen, { method, url }); }
    setRequestHeader() {}
    send(form) {
      seen.form = form;
      this.upload.onload();
      this.onload();
    }
  };
  return seen;
}

const on = { progress() {}, uploaded() {} };
const clip = (name) => new File(["synthetic clip"], name);

test("without extras the upload is the single /process request, unchanged", async (t) => {
  const seen = fakeXHR(t, 201, '{"swingId":"live-1"}');
  const job = processClip(clip("swing.mov"), { hand: "R", stroke: "auto", slowdown: "4" }, on);
  assert.deepEqual(await job.result, { ok: true, swingId: "live-1", warnings: [] });
  assert.equal(seen.url, "/api/process");
  assert.deepEqual([...seen.form.keys()], ["file", "hand", "slowdown"]);
  assert.equal(seen.form.get("slowdown"), "4");
});

test("a second angle sends every file to /process/multi and returns the warnings", async (t) => {
  const seen = fakeXHR(t, 201, '{"swingId":"live-2","warnings":["Clips synced from audio.", "", 3]}');
  const extras = { secondClip: clip("side.mov"), sensorCsv: new File(["t,roll\n0,1"], "wrist.csv"), offset: " -0.25 " };
  const job = processClip(clip("swing.mov"), { ...AUTO_SETTINGS, slowdown: "8" }, on, extras);
  assert.deepEqual(await job.result, { ok: true, swingId: "live-2", warnings: ["Clips synced from audio."] });
  assert.equal(seen.method, "POST");
  assert.equal(seen.url, "/api/process/multi");
  assert.deepEqual([...seen.form.keys()], ["video_a", "video_b", "sensor_csv", "slowdown_a", "slowdown_b", "offset_b_s"]);
  assert.equal(seen.form.get("video_a").name, "swing.mov");
  assert.equal(seen.form.get("video_b").name, "side.mov");
  assert.equal(seen.form.get("sensor_csv").name, "wrist.csv");
  assert.equal(seen.form.get("slowdown_b"), "8");
  assert.equal(seen.form.get("offset_b_s"), "-0.25");
});

test("a sensor CSV alone goes to /process/multi without video_b, slowdown_b or offset_b_s", async (t) => {
  const seen = fakeXHR(t, 201, '{"swingId":"live-3"}');
  const extras = { secondClip: null, sensorCsv: new File(["t,roll\n0,1"], "wrist.csv"), offset: "1.5" };
  await processClip(clip("swing.mov"), AUTO_SETTINGS, on, extras).result;
  assert.equal(seen.url, "/api/process/multi");
  assert.deepEqual([...seen.form.keys()], ["video_a", "sensor_csv"]);
});

test("a 404 from /process/multi says the route is missing, not the upload API", async (t) => {
  fakeXHR(t, 404, '{"detail":"Not Found"}');
  const extras = { secondClip: clip("side.mov"), sensorCsv: null, offset: "" };
  assert.deepEqual(await processClip(clip("swing.mov"), AUTO_SETTINGS, on, extras).result, {
    ok: false,
    failure: { kind: "no-multi-route" },
  });
});

test("offsets and sensor files are checked before sending", () => {
  for (const ok of ["", "  ", "0", "0.5", "-1.2", "+2", ".25"]) assert.equal(checkOffset(ok), null, ok);
  for (const bad of ["abc", "1,5", "1.2.3", "-", "Infinity", "1e3"]) assert.notEqual(checkOffset(bad), null, bad);
  assert.equal(checkSensorCsv(new File(["t\n0"], "wrist.CSV")), null);
  assert.match(checkSensorCsv(new File(["x"], "wrist.txt")), /isn’t a CSV file/);
  assert.match(checkSensorCsv(new File([], "wrist.csv")), /is empty/);
});
