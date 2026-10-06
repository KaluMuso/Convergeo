import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

/** Bind the server-rendered list to the identity authenticated for its API request. */
export async function getAccountListSession(locale: string) {
  const supabase = createServerClient(await cookies());
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login?next=/${locale}/account`);

  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token || session.user.id !== user.id) {
    redirect(`/${locale}/login?next=/${locale}/account`);
  }

  return { accountId: user.id, accessToken: session.access_token };
}
