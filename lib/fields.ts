export type TabId = "cinRecto" | "cinVerso" | "cgRecto" | "cgVerso";

export type FieldKey =
  | "cinNumero"
  | "nom"
  | "prenom"
  | "nomAr"
  | "prenomAr"
  | "dateNaissance"
  | "lieuNaissance"
  | "dateExpiration"
  | "adresse"
  | "immatriculation"
  | "proprietaire"
  | "adresseProprietaire"
  | "vin"
  | "marque"
  | "type"
  | "genre"
  | "carburant"
  | "puissanceFiscale"
  | "dateMiseEnCirculation";

export type Check = "cin" | "vin" | "date" | "number";

export interface FieldDef {
  key: FieldKey;
  label: string;
  rtl?: boolean;
  check?: Check;
  upper?: boolean;
}

export const TABS: { id: TabId; label: string; fields: FieldDef[] }[] = [
  {
    id: "cinRecto",
    label: "CIN recto",
    fields: [
      { key: "cinNumero", label: "N° CIN", check: "cin", upper: true },
      { key: "nom", label: "Nom" },
      { key: "prenom", label: "Prénom" },
      { key: "nomAr", label: "Nom en arabe", rtl: true },
      { key: "prenomAr", label: "Prénom en arabe", rtl: true },
      { key: "dateNaissance", label: "Date de naissance", check: "date" },
      { key: "lieuNaissance", label: "Lieu de naissance" },
      { key: "dateExpiration", label: "Date d'expiration", check: "date" },
    ],
  },
  {
    id: "cinVerso",
    label: "CIN verso",
    fields: [{ key: "adresse", label: "Adresse" }],
  },
  {
    id: "cgRecto",
    label: "Carte grise recto",
    fields: [
      { key: "immatriculation", label: "N° immatriculation" },
      { key: "proprietaire", label: "Propriétaire" },
      { key: "adresseProprietaire", label: "Adresse du propriétaire" },
    ],
  },
  {
    id: "cgVerso",
    label: "Carte grise verso",
    fields: [
      { key: "vin", label: "N° châssis (VIN)", check: "vin", upper: true },
      { key: "marque", label: "Marque" },
      { key: "type", label: "Type" },
      { key: "genre", label: "Genre" },
      { key: "carburant", label: "Carburant" },
      { key: "puissanceFiscale", label: "Puissance fiscale", check: "number" },
      { key: "dateMiseEnCirculation", label: "Date de 1ère mise en circulation", check: "date" },
    ],
  },
];

export const ALL_FIELDS: FieldDef[] = TABS.flatMap((t) => t.fields);

/** Returns an error message, or null when the value is empty or valid. */
export function validate(check: Check | undefined, value: string): string | null {
  const v = value.trim();
  if (!check || !v) return null;
  switch (check) {
    case "cin":
      return /^[A-Z]{1,2}\d+$/.test(v) ? null : "1 ou 2 lettres puis des chiffres (ex. AB123456)";
    case "vin":
      if (v.length !== 17) return `17 caractères attendus (${v.length} actuellement)`;
      return /^[A-HJ-NPR-Z0-9]{17}$/.test(v) ? null : "Lettres I, O, Q interdites ; lettres et chiffres uniquement";
    case "date": {
      const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(v);
      if (!m || +m[1] < 1 || +m[1] > 31 || +m[2] < 1 || +m[2] > 12) return "Format JJ/MM/AAAA";
      return null;
    }
    case "number":
      return /^\d+$/.test(v) ? null : "Nombre attendu (ex. 6)";
  }
}
