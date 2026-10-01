import type { Metadata } from "next";

export type BrandAssetSurface = "any" | "browser" | "dark" | "light";

interface BrandAsset {
  naturalHeight: number;
  naturalWidth: number;
  role: "browser-icon" | "compact-mark" | "wordmark";
  src: `/${string}`;
  surface: BrandAssetSurface;
}

function defineBrandAsset<const T extends BrandAsset>(asset: T): Readonly<T> {
  return Object.freeze(asset);
}

export const BRAND_ASSETS = Object.freeze({
  onDark: defineBrandAsset({
    naturalHeight: 50,
    naturalWidth: 228,
    role: "wordmark",
    src: "/images/logos/wordmark-on-dark.png",
    surface: "dark",
  }),
  onLight: defineBrandAsset({
    naturalHeight: 50,
    naturalWidth: 228,
    role: "wordmark",
    src: "/images/logos/wordmark-on-light.png",
    surface: "light",
  }),
  icon: defineBrandAsset({
    naturalHeight: 64,
    naturalWidth: 64,
    role: "compact-mark",
    src: "/images/logos/compact-mark.png",
    surface: "any",
  }),
  dimensionalAlternate: defineBrandAsset({
    naturalHeight: 50,
    naturalWidth: 228,
    role: "wordmark",
    src: "/images/logos/wordmark-dimensional.png",
    surface: "light",
  }),
  favicon: defineBrandAsset({
    naturalHeight: 16,
    naturalWidth: 16,
    role: "browser-icon",
    src: "/images/logos/favicon.ico",
    surface: "browser",
  }),
  favicon16: defineBrandAsset({
    naturalHeight: 16,
    naturalWidth: 16,
    role: "browser-icon",
    src: "/images/logos/favicon-16.ico",
    surface: "browser",
  }),
  favicon32: defineBrandAsset({
    naturalHeight: 32,
    naturalWidth: 32,
    role: "browser-icon",
    src: "/images/logos/favicon-32.ico",
    surface: "browser",
  }),
  appleTouchIcon: defineBrandAsset({
    naturalHeight: 180,
    naturalWidth: 180,
    role: "browser-icon",
    src: "/images/logos/apple-touch-icon.png",
    surface: "browser",
  }),
});

export const BRAND_LOGO_VARIANTS = ["onDark", "onLight", "icon"] as const;

export type BrandLogoVariant = (typeof BRAND_LOGO_VARIANTS)[number];

export function getBrandIconMetadata(): NonNullable<Metadata["icons"]> {
  return {
    apple: [
      {
        sizes: "180x180",
        type: "image/png",
        url: BRAND_ASSETS.appleTouchIcon.src,
      },
    ],
    icon: [
      {
        sizes: "16x16",
        type: "image/x-icon",
        url: BRAND_ASSETS.favicon16.src,
      },
      {
        sizes: "32x32",
        type: "image/x-icon",
        url: BRAND_ASSETS.favicon32.src,
      },
    ],
    shortcut: [
      {
        sizes: "16x16",
        type: "image/x-icon",
        url: BRAND_ASSETS.favicon.src,
      },
    ],
  };
}
