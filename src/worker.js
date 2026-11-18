// Minimal Worker in front of the static ./public assets.
//
// Why this exists: the basemap is a .pmtiles archive, which the pmtiles client
// reads with HTTP Range requests ("give me just bytes 0-16383"). Cloudflare's
// static-assets serving ignores Range and always returns the whole file with
// status 200, so the pmtiles client aborts ("Check that your storage backend
// supports HTTP Byte Serving") and the map never renders.
//
// This Worker intercepts requests for .pmtiles and serves real 206 Partial
// Content responses. Everything else is handed straight to the assets binding,
// which keeps the SPA fallback and normal caching behaviour intact.

const PMTILES_RE = /\.pmtiles$/;

// PostHog reverse proxy: /rx/* is forwarded to PostHog's US ingestion host so
// ad blockers that block posthog.com don't drop events. The SDK itself is
// loaded from jsdelivr with SRI, so static assets are never proxied.
const PROXY_PREFIX = "/rx/";
const POSTHOG_HOST = "us.i.posthog.com";

async function proxyPostHog(request, url) {
  const target = new URL(request.url);
  target.protocol = "https:";
  target.hostname = POSTHOG_HOST;
  target.port = "";
  target.pathname = url.pathname.slice(PROXY_PREFIX.length - 1);
  const headers = new Headers(request.headers);
  headers.delete("cookie");
  // Cookieless mode hashes the visitor's IP server-side: pass the real one,
  // or every visitor would look like the Worker.
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) headers.set("X-Forwarded-For", ip);
  return fetch(new Request(target.toString(), {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
  }));
}

// Data refresh trigger: GitHub's own cron for refresh-data.yml asks for every
// 30 min but in practice fires every 2–7 h (scheduled workflows are delayed
// under load). Cloudflare cron triggers are punctual, so this Worker kicks the
// workflow via workflow_dispatch instead. GH_DISPATCH_TOKEN is a fine-grained
// PAT scoped to this repo with "Actions: read and write" (wrangler secret).
const REFRESH_DISPATCH_URL =
  "https://api.github.com/repos/42pe/incendios-peru/actions/workflows/refresh-data.yml/dispatches";

async function dispatchRefresh(env) {
  if (!env.GH_DISPATCH_TOKEN) {
    console.error("GH_DISPATCH_TOKEN not set; skipping refresh dispatch");
    return;
  }
  const resp = await fetch(REFRESH_DISPATCH_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "incendios-peru-worker", // GitHub rejects requests without one
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (resp.status !== 204) {
    // Throwing marks the cron invocation as failed in the Cloudflare dashboard.
    throw new Error(`workflow_dispatch failed: ${resp.status} ${await resp.text()}`);
  }
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(dispatchRefresh(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith(PROXY_PREFIX)) {
      return proxyPostHog(request, url);
    }

    if (!PMTILES_RE.test(url.pathname)) {
      return env.ASSETS.fetch(request);
    }

    const rangeHeader = request.headers.get("Range");

    // Fetch the full asset once. Forward the Range in case Cloudflare ever
    // starts honouring it on assets — then we stream the 206 through for free.
    const assetResp = await env.ASSETS.fetch(
      new Request(url.toString(), { headers: rangeHeader ? { Range: rangeHeader } : {} })
    );

    if (assetResp.status === 206) {
      return assetResp; // backend already did byte serving
    }

    const baseHeaders = {
      "Content-Type": "application/octet-stream",
      "Accept-Ranges": "bytes",
      "Cache-Control": "public, max-age=86400, immutable",
    };

    const buf = await assetResp.arrayBuffer();
    const total = buf.byteLength;

    if (!rangeHeader) {
      return new Response(buf, {
        status: 200,
        headers: { ...baseHeaders, "Content-Length": String(total) },
      });
    }

    // Parse a single "bytes=start-end" range (what pmtiles emits).
    const match = /^bytes=(\d*)-(\d*)$/.exec(rangeHeader.trim());
    if (!match || (match[1] === "" && match[2] === "")) {
      return new Response(buf, {
        status: 200,
        headers: { ...baseHeaders, "Content-Length": String(total) },
      });
    }

    let start;
    let end;
    if (match[1] === "") {
      // suffix range: bytes=-N  -> last N bytes
      const suffix = parseInt(match[2], 10);
      start = Math.max(total - suffix, 0);
      end = total - 1;
    } else {
      start = parseInt(match[1], 10);
      end = match[2] === "" ? total - 1 : Math.min(parseInt(match[2], 10), total - 1);
    }

    if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= total) {
      return new Response("Range Not Satisfiable", {
        status: 416,
        headers: { ...baseHeaders, "Content-Range": `bytes */${total}` },
      });
    }

    const slice = buf.slice(start, end + 1);
    return new Response(slice, {
      status: 206,
      headers: {
        ...baseHeaders,
        "Content-Range": `bytes ${start}-${end}/${total}`,
        "Content-Length": String(slice.byteLength),
      },
    });
  },
};
