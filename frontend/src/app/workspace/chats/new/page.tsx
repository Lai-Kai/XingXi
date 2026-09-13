import { redirect } from "next/navigation";

import { legacyModeRedirectHref } from "@/core/threads/xingxi-entry";

import ChatPage from "../[thread_id]/page";

export default async function NewChatPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const legacyRedirect = legacyModeRedirectHref(await searchParams);
  if (legacyRedirect) redirect(legacyRedirect);
  return <ChatPage />;
}
