import { cookies } from "next/headers";
import { LOCALE_COOKIE_NAME, type Locale } from "./catalog";
import { normalizeLocale } from "./translator";

export async function getServerLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  return normalizeLocale(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}
