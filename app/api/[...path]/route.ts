type ProxyContext = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: ProxyContext): Promise<Response> {
  const { path } = await context.params;
  if (path.some((part) => !part || part === "." || part === ".." || /[\\/]/.test(part))) {
    return Response.json({ error: "Invalid API path" }, { status: 400 });
  }

  try {
    const base = new URL(process.env.GHOST_API_URL || "http://localhost:8000");
    if (!["http:", "https:"].includes(base.protocol)) {
      throw new Error("Invalid API URL");
    }
    base.pathname = `${base.pathname.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}`;
    base.search = new URL(request.url).search;
    const headers = new Headers();
    for (const name of ["content-type", "accept"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const upstream = await fetch(base, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]),
    });
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "allow", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
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
