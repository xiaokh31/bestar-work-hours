/* eslint-disable @next/next/no-img-element */
import {
  BRAND_ASSETS,
  type BrandLogoVariant,
} from "../../lib/brand-assets";
import type { Locale, MessageKey } from "../../lib/i18n/catalog";
import { createTranslator } from "../../lib/i18n/translator";

type BrandLogoAccessibility =
  | {
      accessibility: "decorative";
      accessibleName?: never;
    }
  | {
      accessibility: "meaningful";
      accessibleName: MessageKey;
      locale: Locale;
    };

export type BrandLogoProps = BrandLogoAccessibility & {
  preload?: boolean;
  responsiveCompact?: boolean;
  variant: BrandLogoVariant;
};

export function BrandLogo(props: BrandLogoProps) {
  const asset = BRAND_ASSETS[props.variant];
  const className = [
    props.variant === "onDark" ? "brand-logo-transparent-on-dark" : null,
    props.responsiveCompact ? "shell-brand-logo-responsive" : null,
    props.responsiveCompact ? null : "brand-logo-fluid",
    props.responsiveCompact
      ? null
      : props.variant === "icon"
        ? "brand-logo-icon"
        : "brand-logo-wordmark",
  ]
    .filter(Boolean)
    .join(" ") || undefined;
  const alt =
    props.accessibility === "meaningful"
      ? createTranslator(props.locale).t(props.accessibleName)
      : "";

  const image = (
    <img
      alt={alt}
      className={className}
      data-brand-logo={props.variant}
      height={asset.naturalHeight}
      fetchPriority={props.preload ? "high" : undefined}
      sizes={
        props.responsiveCompact
          ? `(max-width: 359px) ${BRAND_ASSETS.icon.naturalWidth}px, ${asset.naturalWidth}px`
          : `${asset.naturalWidth}px`
      }
      src={asset.src}
      width={asset.naturalWidth}
    />
  );

  if (!props.responsiveCompact) {
    return image;
  }

  return (
    <picture data-brand-logo-responsive="true">
      <source
        height={BRAND_ASSETS.icon.naturalHeight}
        media="(max-width: 359px)"
        srcSet={BRAND_ASSETS.icon.src}
        width={BRAND_ASSETS.icon.naturalWidth}
      />
      {image}
    </picture>
  );
}
