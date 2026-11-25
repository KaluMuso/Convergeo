import { redirect } from "next/navigation";

type PageProps = { params: Promise<{ locale: string }> };

export default async function PeopleIndexPage({ params }: PageProps) {
  const { locale } = await params;
  redirect(`/${locale}/account/people/contacts`);
}
