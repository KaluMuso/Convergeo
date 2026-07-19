import {
  listSitemapChunkUrls,
  SITEMAP_XML_HEADERS,
  toSitemapIndexXml,
} from "../../lib/seo/sitemap-build";

/** ISR: chunk list depends on catalogue size; refresh hourly like entity fetches. */
export const revalidate = 3600;

/**
 * Root sitemap index at `/sitemap.xml`.
 *
 * Required because Next.js metadata `generateSitemaps()` only emits
 * `/sitemap/{id}.xml` chunks and leaves `/sitemap.xml` as 404.
 */
export async function GET(): Promise<Response> {
  const chunkUrls = await listSitemapChunkUrls();
  return new Response(toSitemapIndexXml(chunkUrls), {
    status: 200,
    headers: SITEMAP_XML_HEADERS,
  });
}
