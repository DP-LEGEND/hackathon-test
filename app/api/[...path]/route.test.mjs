import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { GET, POST } from "./route.ts";

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
    assert.deepEqual(JSON.parse(new TextDecoder().decode(init?.body)), {
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
