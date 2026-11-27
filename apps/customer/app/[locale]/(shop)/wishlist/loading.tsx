import { ListRouteSkeleton } from "../_components/route-skeletons";

export default function Loading() {
  return <ListRouteSkeleton testId="wishlist-loading" filters={false} cards={4} />;
}
