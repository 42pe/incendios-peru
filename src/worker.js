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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

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
