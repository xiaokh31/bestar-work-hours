import type { Locale, MessageKey } from '@/lib/i18n/catalog';
import { createTranslator } from '@/lib/i18n/translator';

const REVIEW_MESSAGE_KEYS: Record<string, MessageKey> = {
  FILENAME_REVIEW_AMBIGUOUS_ENCODING:
    'i18n.filenameReview.ambiguousEncoding',
  FILENAME_REVIEW_EMPTY: 'i18n.filenameReview.empty',
  FILENAME_REVIEW_INVALID_UTF8_TRANSPORT:
    'i18n.filenameReview.invalidUtf8',
  FILENAME_REVIEW_TOO_LONG: 'i18n.filenameReview.tooLong',
  FILENAME_REVIEW_UNSAFE_CHARACTERS:
    'i18n.filenameReview.unsafeCharacters',
};

export function FilenameReviewNotice({
  code,
  locale,
}: {
  code: string | null | undefined;
  locale: Locale;
}) {
  if (!code) return null;
  const { t } = createTranslator(locale);
  const messageKey =
    REVIEW_MESSAGE_KEYS[code] ?? 'i18n.filenameReview.unknown';
  return (
    <p
      className="mt-1 max-w-full break-words text-xs font-medium text-amber-800"
      data-filename-review-code={code}
    >
      {t('Filename needs review')}: {t(messageKey)}
    </p>
  );
}
