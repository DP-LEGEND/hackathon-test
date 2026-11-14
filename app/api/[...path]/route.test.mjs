import assert from "node:assert/strict";
import { createServer } from "node:http";
import { afterEach, test } from "node:test";
import { GET, POST, maxDuration } from "./route.ts";

const originalFetch = globalThis.fetch;
const originalUrl = process.env.GHOST_API_URL;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalUrl === undefined) delete process.env.GHOST_API_URL;
  else process.env.GHOST_API_URL = originalUrl;
});

const context = (path) => ({ params: Promise.resolve({ path }) });

test("GET forwards the query to the default API without credentials", async () => {
  delete process.env.GHOST_API_URL;
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "http://localhost:8000/swings?side=backhand");
    assert.equal(init?.cache, "no-store");
    assert.equal(new Headers(init?.headers).get("cookie"), null);
    return Response.json({ swings: [] });
  };
  const result = await GET(new Request("http://localhost:3000/api/swings?side=backhand", {
    headers: { cookie: "session=private" },
  }), context(["swings"]));
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { swings: [] });
});

test("POST preserves JSON body, upstream status and configured base path", async () => {
  process.env.GHOST_API_URL = "http://localhost:9000/service/";
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "http://localhost:9000/service/compare/sample");
    assert.equal(init?.method, "POST");
    assert.equal(init?.duplex, "half");
    assert.deepEqual(await new Response(init?.body).json(), {
      fix: "bend_elbow", amount: 12,
    });
    return Response.json({ detail: "Invalid fix" }, { status: 422 });
  };
  const response = await POST(new Request("http://localhost:3000/api/compare/sample", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fix: "bend_elbow", amount: 12 }),
  }), context(["compare", "sample"]));
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: "Invalid fix" });
});

test("unavailable upstream gives a clear 502 without leaking exception details", async () => {
  globalThis.fetch = async () => { throw new Error("private upstream configuration"); };
  const response = await GET(new Request("http://localhost:3000/api/swings"), context(["swings"]));
  assert.equal(response.status, 502);
  assert.match((await response.json()).error, /Ghost API is unavailable/);
});

test("path traversal cannot escape the configured upstream base", async () => {
  globalThis.fetch = async () => { throw new Error("must not fetch"); };
  const response = await GET(new Request("http://localhost:3000/api/swings"), context(["..", "private"]));
  assert.equal(response.status, 400);
});

const contentType = "multipart/form-data; boundary=ghost-test-boundary";
const multipart = Buffer.concat([
  Buffer.from('--ghost-test-boundary\r\nContent-Disposition: form-data; name="hand"\r\n\r\nR\r\n'),
  Buffer.from('--ghost-test-boundary\r\nContent-Disposition: form-data; name="file"; filename="demo.mp4"\r\nContent-Type: video/mp4\r\n\r\n'),
  Buffer.from([0, 255, 1, 128, 13, 10, 42]),
  Buffer.from('\r\n--ghost-test-boundary--\r\n'),
]);

async function pythonEndpoint(t, handler) {
  // A local HTTP endpoint stands in for FastAPI; use real fetch/Node streaming.
  const server = createServer(handler);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  process.env.GHOST_API_URL = `http://127.0.0.1:${server.address().port}`;
  t.after(() => new Promise((resolve) => {
    server.closeAllConnections();
    server.close(resolve);
  }));
}

test("multipart reaches Python unchanged before the client finishes uploading", async (t) => {
  const firstChunk = Promise.withResolvers();
  const finishUpload = Promise.withResolvers();
  const seen = {};
  await pythonEndpoint(t, (request, response) => {
    seen.url = request.url;
    seen.headers = request.headers;
    const chunks = [];
    request.on("data", (chunk) => {
      chunks.push(chunk);
      firstChunk.resolve();
    });
    request.on("end", () => {
      seen.body = Buffer.concat(chunks);
      response.writeHead(201, { "Content-Type": "application/json" });
      response.end('{"swingId":"uploaded-swing"}');
    });
  });
  let started = false;
  const body = new ReadableStream({
    async pull(controller) {
      if (!started) {
        started = true;
        controller.enqueue(multipart.subarray(0, 100));
      } else {
        await finishUpload.promise;
        controller.enqueue(multipart.subarray(100));
        controller.close();
      }
    },
  });
  const request = new Request("http://localhost:3000/api/process", {
    method: "POST", body, duplex: "half",
    headers: { "Content-Type": contentType, "Content-Length": String(multipart.length) },
  });
  for (const method of ["arrayBuffer", "formData", "json", "text", "blob"]) {
    request[method] = () => { throw new Error("The proxy must not buffer/parse uploads"); };
  }
  const forwarding = POST(request, context(["process"]));
  const timer = setTimeout(() => firstChunk.reject(new Error("Proxy buffered the upload")), 5_000);
  try {
    await firstChunk.promise;
  } finally {
    clearTimeout(timer);
    finishUpload.resolve();
  }
  const response = await forwarding;
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { swingId: "uploaded-swing" });
  assert.equal(seen.url, "/process");
  assert.equal(seen.headers["content-type"], contentType);
  assert.equal(seen.headers["content-length"], String(multipart.length));
  assert.deepEqual(seen.body, multipart);
});

for (const status of [400, 413, 422, 429]) {
  test(`Python ${status} JSON is preserved even when it rejects before upload completion`, async (t) => {
    const errorBody = `{ "detail": "Python rejected the clip", "status": ${status} }\n`;
    await pythonEndpoint(t, (_request, response) => {
      response.writeHead(status, { "Content-Type": "application/json", "Retry-After": "7" });
      response.end(errorBody);
    });
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 5_000);
    try {
      // Deliberately omit the closing boundary and keep the upload open.
      const body = new ReadableStream({ start(controller) { controller.enqueue(multipart.subarray(0, 100)); } });
      const response = await POST(new Request("http://localhost:3000/api/process", {
        method: "POST", headers: { "Content-Type": contentType }, body, duplex: "half", signal: abort.signal,
      }), context(["process"]));
      assert.equal(response.status, status);
      assert.equal(response.headers.get("content-type"), "application/json");
      assert.equal(response.headers.get("retry-after"), "7");
      assert.equal(await response.text(), errorBody);
    } finally {
      clearTimeout(timer);
      abort.abort();
    }
  });
}

test("declared uploads over 250 MiB are rejected without consuming or forwarding the body", async () => {
  globalThis.fetch = () => assert.fail("Oversized upload must not be forwarded");
  let reads = 0;
  const body = new ReadableStream({ pull() { reads++; } }, { highWaterMark: 0 });
  const response = await POST(new Request("http://localhost:3000/api/process", {
    method: "POST", headers: { "Content-Type": contentType, "Content-Length": String(250 * 1024 * 1024 + 1) },
    body, duplex: "half",
  }), context(["process"]));
  assert.equal(response.status, 413);
  assert.equal(reads, 0);
});

for (const overflow of [false, true]) {
  test(`unknown-length upload ${overflow ? "over" : "at"} 250 MiB is ${overflow ? "rejected" : "accepted"} while streaming`, async () => {
    const chunk = new Uint8Array(1024 * 1024);
    let remaining = 250;
    let forwarded = 0;
    const body = new ReadableStream({
      pull(controller) {
        if (remaining-- > 0) controller.enqueue(chunk);
        else {
          if (overflow) controller.enqueue(new Uint8Array(1));
          controller.close();
        }
      },
    });
    globalThis.fetch = async (_url, init) => {
      const reader = init.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        forwarded += value.byteLength;
      }
      return Response.json({ swingId: "large-swing" }, { status: 201 });
    };
    const response = await POST(new Request("http://localhost:3000/api/process", {
      method: "POST", headers: { "Content-Type": contentType }, body, duplex: "half",
    }), context(["process"]));
    assert.equal(response.status, overflow ? 413 : 201);
    assert.equal(forwarded, 250 * 1024 * 1024);
  });
}

test("processing gets a 600-second timeout and propagates client cancellation", async (t) => {
  const abort = new AbortController();
  const timeout = new AbortController();
  let timeoutMilliseconds;
  let forwardedSignal;
  t.mock.method(AbortSignal, "timeout", (milliseconds) => {
    timeoutMilliseconds = milliseconds;
    return timeout.signal;
  });
  globalThis.fetch = async (_url, init) => {
    forwardedSignal = init.signal;
    abort.abort();
    throw init.signal.reason;
  };
  const response = await POST(new Request("http://localhost:3000/api/process", {
    method: "POST", body: multipart, headers: { "Content-Type": contentType }, signal: abort.signal,
  }), context(["process"]));
  assert.equal(timeoutMilliseconds, 10 * 60_000);
  assert.equal(forwardedSignal.aborted, true);
  assert.equal(maxDuration, 600);
  assert.equal(response.status, 502);
});

for (const path of [["swings"], ["coach", "sample"], ["compare", "sample"], ["processing"]]) {
  test(`${path.join("/")} keeps a 30-second upstream timeout`, async (t) => {
    const timeout = new AbortController();
    let timeoutMilliseconds;
    let forwardedSignal;
    t.mock.method(AbortSignal, "timeout", (milliseconds) => {
      timeoutMilliseconds = milliseconds;
      return timeout.signal;
    });
    globalThis.fetch = async (_url, init) => {
      forwardedSignal = init.signal;
      timeout.abort();
      throw init.signal.reason;
    };
    const response = await GET(new Request(`http://localhost:3000/api/${path.join("/")}`), context(path));
    assert.equal(timeoutMilliseconds, 30_000);
    assert.equal(forwardedSignal.aborted, true);
    assert.equal(response.status, 502);
  });
}
