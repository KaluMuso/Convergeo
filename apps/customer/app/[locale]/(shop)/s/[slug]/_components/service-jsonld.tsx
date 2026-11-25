import { JsonLdScript } from "@vergeo/ui/src/seo/json-ld";

import { buildServiceJsonLd, type ServiceJsonLdInput } from "../_lib/service-jsonld";

export function ServiceJsonLd({ service }: { service: ServiceJsonLdInput }) {
  return <JsonLdScript data={buildServiceJsonLd(service)} />;
}

export type { ServiceJsonLdInput };
