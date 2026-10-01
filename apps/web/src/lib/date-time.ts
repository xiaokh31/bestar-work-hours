const DEFAULT_OPERATIONAL_TIME_ZONE = "America/Edmonton";

export const OPERATIONAL_TIME_ZONE = resolveOperationalTimeZone(
  process.env.NEXT_PUBLIC_OPERATIONAL_TIME_ZONE,
);
export const OPERATIONAL_TIME_ZONE_LABEL = OPERATIONAL_TIME_ZONE;
export const OPERATIONAL_TIME_ZONE_DESCRIPTION = `${OPERATIONAL_TIME_ZONE} (dynamic DST)`;

interface OperationalDateTimeFormatterCache {
  constructionCount: () => number;
  get: () => Intl.DateTimeFormat;
}

type DateTimeFormatterFactory = (
  locale: string,
  options: Intl.DateTimeFormatOptions,
) => Intl.DateTimeFormat;

const operationalDateTimeFormatterCache =
  createOperationalDateTimeFormatterCache();
const localizedOperationalDateTimeFormatters = new Map<
  string,
  Intl.DateTimeFormat
>();

export function formatOperationalDateTime(value: string | Date): string {
  const date = parseDate(value);

  if (!date) {
    return String(value);
  }

  const parts = operationalDateTimeFormatterCache.get().formatToParts(date);
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );

  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second} ${values.timeZoneName}`;
}

export function formatLocalizedOperationalDateTime(
  value: string | Date,
  locale: "en" | "zh-CN",
): string {
  const date = parseDate(value);
  if (!date) return String(value);

  let formatter = localizedOperationalDateTimeFormatters.get(locale);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale === "en" ? "en-CA" : locale, {
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
      minute: "2-digit",
      month: "short",
      timeZone: OPERATIONAL_TIME_ZONE,
      timeZoneName: "short",
      year: "numeric",
    });
    localizedOperationalDateTimeFormatters.set(locale, formatter);
  }
  return formatter.format(date);
}

export function operationalMonthValue(value: string | Date): string {
  const date = parseDate(value);
  if (!date) {
    throw new Error("Invalid operational date");
  }
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      month: "2-digit",
      timeZone: OPERATIONAL_TIME_ZONE,
      year: "numeric",
    })
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}`;
}

export function createOperationalDateTimeFormatterCache(
  factory: DateTimeFormatterFactory = (locale, options) =>
    new Intl.DateTimeFormat(locale, options),
  timeZone = OPERATIONAL_TIME_ZONE,
): OperationalDateTimeFormatterCache {
  let formatter: Intl.DateTimeFormat | null = null;
  let constructionCount = 0;

  return {
    constructionCount: () => constructionCount,
    get() {
      if (!formatter) {
        formatter = factory("en-CA", {
          day: "2-digit",
          hour: "2-digit",
          hourCycle: "h23",
          minute: "2-digit",
          month: "2-digit",
          second: "2-digit",
          timeZone,
          timeZoneName: "short",
          year: "numeric",
        });
        constructionCount += 1;
      }

      return formatter;
    },
  };
}

export function resolveOperationalTimeZone(
  configured: string | undefined,
): string {
  if (configured && isValidTimeZone(configured)) {
    return configured;
  }

  return DEFAULT_OPERATIONAL_TIME_ZONE;
}

function isValidTimeZone(timeZone: string): boolean {
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date(0));
    return true;
  } catch {
    return false;
  }
}

function parseDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
}
