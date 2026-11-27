import { ListRouteSkeleton } from "../_components/route-skeletons";

export default function Loading() {
  return <ListRouteSkeleton testId="compare-loading" filters={false} cards={3} />;
}
