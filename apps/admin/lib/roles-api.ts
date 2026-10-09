"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

export const rolesApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type AdminPermissions = {
  permissions: string[];
  can_manage_roles: boolean;
  unrestricted: boolean;
};

export type AdminRole = { key: string; name: string; permissions: string[] };
export type AdminRoleAssignment = { user_id: string; role: string };

export function loadAdminPermissions(): Promise<AdminPermissions> {
  return rolesApi.request<AdminPermissions>("/admin/me/permissions");
}
