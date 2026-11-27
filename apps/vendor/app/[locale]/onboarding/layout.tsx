import { routeMessagesLayout } from "../_components/route-messages";

// KYC document state is per-vendor and must never be prerendered.
export const dynamic = "force-dynamic";

export default routeMessagesLayout("onboarding");
