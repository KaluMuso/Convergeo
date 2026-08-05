"use client";

import { useEffect, useRef } from "react";

import {
  reportClientError,
  type ClientErrorApplication,
  type ClientErrorBoundary,
  type ClientErrorPayload,
  type ReportClientErrorOptions,
} from "./report-client-error";

export function useReportClientError(
  error: Error & { digest?: string },
  payload: Omit<ClientErrorPayload, "message" | "digest" | "stack" | "url" | "userAgent">,
  options: ReportClientErrorOptions = {},
): void {
  const reportedRef = useRef<string | null>(null);

  useEffect(() => {
    const fingerprint = `${payload.boundary}:${payload.application}:${error.digest ?? error.message}`;
    if (reportedRef.current === fingerprint) {
      return;
    }
    reportedRef.current = fingerprint;

    void reportClientError(
      error,
      {
        ...payload,
        message: error.message,
        digest: error.digest,
        stack: error.stack,
      },
      options,
    );
  }, [error, options.apiBaseUrl, options.locale, payload.application, payload.boundary]);
}

export type {
  ClientErrorApplication,
  ClientErrorBoundary,
  ClientErrorPayload,
  ReportClientErrorOptions,
};
