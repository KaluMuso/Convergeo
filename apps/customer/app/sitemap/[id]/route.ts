import {
  buildSitemapChunk,
  listSitemapChunkIds,
  parseSitemapChunkSegment,
  SITEMAP_XML_HEADERS,
  toUrlsetXml,
} from "../../../lib/seo/sitemap-build";

/** ISR: entity slug lists revalidate hourly via fetch cache tags in sources. */
export const revalidate = 3600;

type RouteParams = { params: Promise<{ id: string }> };

/** Pre-render the same chunk set the legacy metadata route emitted. */
export async function generateStaticParams(): Promise<Array<{ id: string }>> {
  const ids = await listSitemapChunkIds();
  return ids.map((id) => ({ id: `${id}.xml` }));
}

/**
 * Chunked sitemap urlset at `/sitemap/{id}.xml` (also accepts `/sitemap/{id}`).
 */
export async function GET(_request: Request, context: RouteParams): Promise<Response> {
  const { id: rawId } = await context.params;
  const id = parseSitemapChunkSegment(rawId);
  if (id === null) {
    return new Response("Not Found", { status: 404 });
  }

  const entries = await buildSitemapChunk(id);
  if (entries === null) {
    return new Response("Not Found", { status: 404 });
  }

  return new Response(toUrlsetXml(entries), {
    status: 200,
    headers: SITEMAP_XML_HEADERS,
  });
}
