type ProxyContext = { params: Promise<{ path: string[] }> };

export const maxDuration = 300;
const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;

function uploadTooLarge(): Response {
  return Response.json({ detail: "Video exceeds the 250 MB upload limit" }, { status: 413 });
}

async function forward(request: Request, context: ProxyContext): Promise<Response> {
  const { path } = await context.params;
  if (path.some((part) => !part || part === "." || part === ".." || /[\\/]/.test(part))) {
    return Response.json({ error: "Invalid API path" }, { status: 400 });
  }

  const isUpload = request.method === "POST" && path[0] === "process"
    && (path.length === 1 || (path.length === 2 && path[1] === "multi"));
  if (isUpload) {
    const length = request.headers.get("content-length");
    if (length !== null) {
      if (!/^\d+$/.test(length)) {
        return Response.json({ detail: "Invalid Content-Length" }, { status: 400 });
      }
      if (Number(length) > MAX_UPLOAD_BYTES) return uploadTooLarge();
    }
  }

  let exceededLimit = false;
  let timeoutSignal: AbortSignal | undefined;
  let upstreamSignal: AbortSignal | undefined;
  try {
    const base = new URL(process.env.GHOST_API_URL || "http://localhost:8000");
    if (!["http:", "https:"].includes(base.protocol)) {
      throw new Error("Invalid API URL");
    }
    base.pathname = `${base.pathname.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}`;
    base.search = new URL(request.url).search;
    const headers = new Headers();
    for (const name of ["content-type", "content-length", "accept"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    let body = request.method === "GET" || request.method === "HEAD" ? null : request.body;
    if (isUpload && body) {
      let bytes = 0;
      // Count bytes with backpressure, preserving the multipart boundary and
      // payload verbatim. Also bound uploads without a Content-Length header.
      body = body.pipeThrough(new TransformStream<Uint8Array<ArrayBuffer>, Uint8Array<ArrayBuffer>>({
        transform(chunk, controller) {
          bytes += chunk.byteLength;
          if (bytes > MAX_UPLOAD_BYTES) {
            exceededLimit = true;
            controller.error(new Error("Upload limit exceeded"));
          } else {
            controller.enqueue(chunk);
          }
        },
      }));
    }
    timeoutSignal = AbortSignal.timeout(path[0] === "process" ? 10 * 60_000 : 30_000);
    upstreamSignal = AbortSignal.any([request.signal, timeoutSignal]);
    const init: RequestInit & { duplex: "half" } = {
      method: request.method,
      headers,
      body,
      duplex: "half",
      cache: "no-store",
      redirect: "manual",
      signal: upstreamSignal,
    };
    const upstream = await fetch(base, init);
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "allow", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    if (exceededLimit) return uploadTooLarge();
    // The combined signal retains the first abort reason even if both fire.
    if (timeoutSignal?.aborted && upstreamSignal?.reason === timeoutSignal.reason) {
      return Response.json({ error: "Ghost API is still processing; the proxy stopped waiting." }, { status: 504 });
    }
    if (request.signal.aborted) {
      return Response.json({ error: "Request cancelled." }, { status: 499 });
    }
    return Response.json(
      { error: "Ghost API is unavailable. Start the FastAPI service and retry." },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const HEAD = forward;
export const OPTIONS = forward;
