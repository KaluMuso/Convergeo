import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

export type ApiUnavailableLabels = {
  title: string;
  body: string;
  retry: string;
};

type ApiUnavailablePanelProps = {
  retryHref: string;
  labels: ApiUnavailableLabels;
  testId?: string;
};

export function ApiUnavailablePanel({
  retryHref,
  labels,
  testId = "api-unavailable",
}: ApiUnavailablePanelProps) {
  return (
    <div className="mx-auto w-full max-w-3xl py-10" data-testid={testId}>
      <EmptyState
        title={labels.title}
        body={labels.body}
        action={
          <LinkButton
            href={retryHref}
            variant="primary"
            className="rounded-lg text-sm"
            LinkComponent={Link}
          >
            {labels.retry}
          </LinkButton>
        }
      />
    </div>
  );
}
