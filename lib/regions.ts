import type { FieldKey, TabId } from "./fields";
export type Region = {
  key: FieldKey;
  box: [number, number, number, number];
  lang: "fra" | "ara";
  kind?: "name" | "vin";
};
// Coordinates apply to the aligned card, never the uncropped camera frame.
export const REGIONS: Record<TabId, Region[]> = {
  cinRecto: [
    { key: "prenom", box: [0.37, 0.2, 0.36, 0.1], lang: "fra", kind: "name" },
    { key: "nom", box: [0.37, 0.32, 0.36, 0.09], lang: "fra", kind: "name" },
    {
      key: "prenomAr",
      box: [0.73, 0.17, 0.27, 0.11],
      lang: "ara",
      kind: "name",
    },
    { key: "nomAr", box: [0.73, 0.28, 0.27, 0.12], lang: "ara", kind: "name" },
  ],
  cinVerso: [],
  cgRecto: [],
  cgVerso: [
    { key: "marque", box: [0.27, 0.035, 0.25, 0.075], lang: "fra" },
    { key: "type", box: [0.27, 0.095, 0.25, 0.075], lang: "fra" },
    { key: "genre", box: [0.15, 0.15, 0.42, 0.075], lang: "fra" },
    { key: "carburant", box: [0.27, 0.26, 0.25, 0.075], lang: "fra" },
    { key: "vin", box: [0.2, 0.33, 0.32, 0.06], lang: "fra", kind: "vin" },
    { key: "puissanceFiscale", box: [0.31, 0.425, 0.1, 0.07], lang: "fra" },
  ],
};
