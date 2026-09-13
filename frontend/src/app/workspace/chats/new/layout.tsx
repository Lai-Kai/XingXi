import { ChatProviders } from "../[thread_id]/providers";

export default function NewChatLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <ChatProviders>{children}</ChatProviders>;
}
