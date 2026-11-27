"use client";

import { createApiClient } from "@vergeo/config";

import { getBrowserAccessToken } from "../../../../../lib/access-token";
import { downscaleImageFile, uploadSignedImage } from "../../../../../lib/admin-image-upload";
import { getApiBaseUrl } from "../../../../../lib/api-base-url";

import type { TaxonomyNode, TaxonomyStatus, Umbrella } from "./taxonomy-model";

export const taxonomyApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

const BASE = "/admin/catalog/taxonomy";

export function listNodes(umbrella: Umbrella, q: string): Promise<TaxonomyNode[]> {
  const query = new URLSearchParams({ umbrella });
  if (q.trim()) query.set("q", q.trim());
  return taxonomyApi.request<TaxonomyNode[]>(`${BASE}?${query.toString()}`, {
    cache: "no-store",
  });
}

export type NodeInput = {
  name?: string;
  slug?: string;
  parent_id?: string | null;
  show_in_customer?: boolean;
  show_in_vendor?: boolean;
  icon?: string | null;
  image_public_id?: string | null;
  image_alt?: string | null;
  status?: TaxonomyStatus;
};

export function createNode(umbrella: Umbrella, input: NodeInput): Promise<TaxonomyNode> {
  return taxonomyApi.request<TaxonomyNode>(BASE, {
    method: "POST",
    body: JSON.stringify({ umbrella, ...input }),
  });
}

export function updateNode(
  umbrella: Umbrella,
  id: string,
  input: Omit<NodeInput, "slug" | "parent_id">,
): Promise<TaxonomyNode> {
  return taxonomyApi.request<TaxonomyNode>(`${BASE}/${umbrella}/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function setStatus(
  umbrella: Umbrella,
  id: string,
  status: TaxonomyStatus,
  reason?: string,
): Promise<TaxonomyNode> {
  return taxonomyApi.request<TaxonomyNode>(`${BASE}/${umbrella}/${encodeURIComponent(id)}/status`, {
    method: "POST",
    body: JSON.stringify({ status, reason: reason || undefined }),
  });
}

export function moveNode(
  umbrella: Umbrella,
  id: string,
  parentId: string | null,
): Promise<TaxonomyNode> {
  return taxonomyApi.request<TaxonomyNode>(`${BASE}/${umbrella}/${encodeURIComponent(id)}/move`, {
    method: "POST",
    body: JSON.stringify({ parent_id: parentId }),
  });
}

export function reorderNodes(
  umbrella: Umbrella,
  parentId: string | null,
  orderedIds: string[],
): Promise<TaxonomyNode[]> {
  return taxonomyApi.request<TaxonomyNode[]>(`${BASE}/${umbrella}/reorder`, {
    method: "POST",
    body: JSON.stringify({ parent_id: parentId, ordered_ids: orderedIds }),
  });
}

export function deleteNode(umbrella: Umbrella, id: string): Promise<TaxonomyNode> {
  return taxonomyApi.request<TaxonomyNode>(`${BASE}/${umbrella}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

type SignedSlot = {
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
};

/** Sign (admin-scoped `taxonomy/<umbrella>` folder) and upload; resolves the Cloudinary id. */
export async function uploadNodeImage(umbrella: Umbrella, file: File): Promise<string> {
  const resized = await downscaleImageFile(file, 800);
  const signed = await taxonomyApi.request<SignedSlot>(`${BASE}/image/sign`, {
    method: "POST",
    body: JSON.stringify({ umbrella, file_size_bytes: resized.size }),
  });
  const uploaded = await uploadSignedImage(resized, signed);
  return uploaded.public_id;
}
