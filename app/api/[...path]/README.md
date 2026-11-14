# Ghost API proxy

`POST /api/process` forwards a multipart upload to Python's `POST /process`.
`GHOST_API_URL` is a server-side setting (default `http://localhost:8000`).
Send `FormData` normally; let the browser set its multipart Content-Type boundary.
The proxy streams the original bytes and forwards Content-Type and Content-Length
when supplied. It does not parse, re-encode, or buffer the complete upload.

The limit matches Python: 250 × 1024 × 1024 bytes for the complete request,
including multipart overhead. Declared oversized requests receive 413 before
reading the body. Unknown-length uploads are counted incrementally with
backpressure and stopped at the same limit. The upstream request has a 120-second
timeout covering upload and processing; client cancellation propagates upstream.
The route also declares `maxDuration = 120` for hosting platforms.

Upstream status codes and response bytes are preserved, including 400, 413, 422
and 429 JSON errors. Content-Type and Retry-After are passed through. Connection
failures/timeouts return the existing sanitized 502 JSON error. Other API methods
and JSON requests use the same streaming forwarding path.

## Deployment constraint

The 250 MiB limit is supported by the route on a local/self-hosted Node server
whose ingress permits it. It does **not** override a hosting provider's request
limit. [Vercel Functions documents a 4.5 MB request-body cap](https://vercel.com/docs/functions/limitations#request-body-size),
so large video uploads on Vercel need a direct-to-Python/storage upload path.
Changing the route timeout or Next.js body settings cannot remove that cap.

## Regression tests

From this directory, with the project's Node version:

```sh
node --test route.test.mjs
```

The test endpoint stands in for Python using a local HTTP server. Tests verify a
small binary multipart file and form field arrive byte-for-byte before the client
finishes uploading, preserved early error responses, the 250 MiB boundary without
allocating a whole video, and timeout/client cancellation settings. No video files
are committed.
