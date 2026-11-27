import { ListRouteSkeleton } from "../_components/route-skeletons";

export default function Loading() {
  return <ListRouteSkeleton testId="deals-loading" filters={false} />;
}
