import assert from "node:assert/strict";
import { test } from "node:test";
import { AUTO_SETTINGS, checkOffset, checkSensorFile, checkUploadTotal, processClip } from "./process-clip.ts";

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
  const extras = { secondClip: clip("side.mov"), sensorFile: new File(["t,roll\n0,1"], "wrist.csv"), offset: " -0.25 " };
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
  const extras = { secondClip: null, sensorFile: new File(["t,roll\n0,1"], "wrist.csv"), offset: "1.5" };
  await processClip(clip("swing.mov"), AUTO_SETTINGS, on, extras).result;
  assert.equal(seen.url, "/api/process/multi");
  assert.deepEqual([...seen.form.keys()], ["video_a", "sensor_csv"]);
});

test("a Sensor Logger .zip goes in the same sensor_csv field, under its own name", async (t) => {
  const seen = fakeXHR(t, 201, '{"swingId":"live-4"}');
  const zip = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], "Sensor Logger 2026-11-15.zip", { type: "application/zip" });
  const extras = { secondClip: null, sensorFile: zip, offset: "" };
  await processClip(clip("swing.mov"), AUTO_SETTINGS, on, extras).result;
  assert.equal(seen.url, "/api/process/multi");
  assert.deepEqual([...seen.form.keys()], ["video_a", "sensor_csv"]);
  assert.equal(seen.form.get("sensor_csv").name, "Sensor Logger 2026-11-15.zip");
  assert.equal(seen.form.get("sensor_csv").size, 4);
});

test("a 404 from /process/multi says the route is missing, not the upload API", async (t) => {
  fakeXHR(t, 404, '{"detail":"Not Found"}');
  const extras = { secondClip: clip("side.mov"), sensorFile: null, offset: "" };
  assert.deepEqual(await processClip(clip("swing.mov"), AUTO_SETTINGS, on, extras).result, {
    ok: false,
    failure: { kind: "no-multi-route" },
  });
});

test("offsets and sensor files are checked before sending", () => {
  for (const ok of ["", "  ", "0", "0.5", "-1.2", "+2", ".25"]) assert.equal(checkOffset(ok), null, ok);
  for (const bad of ["abc", "1,5", "1.2.3", "-", "Infinity", "1e3"]) assert.notEqual(checkOffset(bad), null, bad);
  assert.equal(checkSensorFile(new File(["t\n0"], "wrist.CSV")), null);
  assert.equal(checkSensorFile(new File(["PK"], "export.ZIP")), null);
  assert.match(checkSensorFile(new File(["x"], "wrist.txt")), /isn’t a ZIP or CSV file/);
  assert.match(checkSensorFile(new File([], "wrist.csv")), /is empty/);
  assert.match(checkSensorFile(new File([], "export.zip")), /is empty/);
});

const MB = 1024 * 1024;

test("a .csv or a .zip may be up to 10 MB, like the service", () => {
  // checkSensorFile reads only the name and size, so plain objects stand in for big files.
  for (const name of ["wrist.csv", "export.zip"]) {
    assert.equal(checkSensorFile({ name, size: 10 * MB }), null, name);
    assert.equal(
      checkSensorFile({ name, size: 10 * MB + 1 }),
      "Sensor export too large: 10.0 MB. The limit is 10 MB.",
      name,
    );
    assert.match(checkSensorFile({ name, size: 30 * MB }), /^Sensor export too large: 30\.0 MB\. The limit is 10 MB\.$/, name);
  }
});

test("everything chosen together may be at most 250 MB", () => {
  const none = { secondClip: null, sensorFile: null };
  // The main clip alone never trips it: checkClip already caps a clip at 250 MB.
  assert.equal(checkUploadTotal({ size: 250 * MB }, none), null);
  assert.equal(checkUploadTotal({ size: 200 * MB }, { secondClip: { size: 40 * MB }, sensorFile: { size: 10 * MB } }), null);
  assert.equal(
    checkUploadTotal({ size: 200 * MB }, { secondClip: { size: 40 * MB }, sensorFile: { size: 10 * MB + 1 } }),
    "Your files add up to 250 MB. One upload can be at most 250 MB in total, so trim a video to just the swing or remove an optional file.",
  );
  assert.match(
    checkUploadTotal({ size: 200 * MB }, { secondClip: { size: 120 * MB }, sensorFile: null }),
    /^Your files add up to 320 MB\. One upload can be at most 250 MB in total/,
  );
  assert.match(checkUploadTotal({ size: 245 * MB }, { secondClip: null, sensorFile: { size: 6 * MB } }), /add up to 251 MB/);
});
