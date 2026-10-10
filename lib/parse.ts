import type { FieldKey } from "./fields";

// Heuristic extraction from raw OCR text. Results are suggestions: staff check every field.

export type Extracted = Partial<Record<FieldKey, string>>;

const AR_RE = /[؀-ۿ]/;
const DATE_RE = /(\d{1,2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{4})/;

function toLines(text: string) {
  return text
    .split(/\r?\n/)
    .map((l) => l.replace(/[|_~«»"“”]+/g, " ").replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function latinOnly(s: string) {
  return s.replace(/[؀-ۿ]+/g, " ").replace(/\s+/g, " ").trim();
}

function fmtDate(m: RegExpExecArray | null) {
  return m ? `${m[1].padStart(2, "0")}/${m[2].padStart(2, "0")}/${m[3]}` : "";
}

/** Value following a label on the same line, or the next line if the label stands alone. */
function afterLabel(lines: string[], re: RegExp): string {
  for (let i = 0; i < lines.length; i++) {
    const m = re.exec(lines[i]);
    if (!m) continue;
    const rest = latinOnly(lines[i].slice(m.index + m[0].length)).replace(/^[\s:.\-/]+/, "").trim();
    if (rest.length >= 2) return rest;
    const next = lines[i + 1] ? latinOnly(lines[i + 1]).replace(/^[\s:.\-/]+/, "") : "";
    if (next.length >= 2) return next;
  }
  return "";
}

function dateNearLabel(lines: string[], re: RegExp): string {
  for (let i = 0; i < lines.length; i++) {
    if (!re.test(lines[i])) continue;
    const d = DATE_RE.exec(lines[i]) ?? (lines[i + 1] ? DATE_RE.exec(lines[i + 1]) : null);
    if (d) return fmtDate(d);
  }
  return "";
}

const LATIN_STOP = /\b(ROYAUME|MAROC|KINGDOM|MOROCCO|CARTE|NATIONALE?|IDENTIT[EÉ]|VALABLE|JUSQU|N[EÉ]E?|LE|DIRECTION|SURETE|SÛRETÉ)\b/;
const AR_STOP = /(المملكة|المغربية|البطاقة|الوطنية|للتعريف|مزداد|بتاريخ|صالحة|إلى|الى|غاية)/;

export function parseCinRecto(text: string): Extracted {
  const lines = toLines(text);
  const out: Extracted = {};

  const cin = /\b([A-Z]{1,2})\s?(\d{5,7})\b/.exec(text.toUpperCase());
  if (cin) out.cinNumero = cin[1] + cin[2];

  const birthLabel = /n[ée]e?\s*le|naissance/i;
  out.dateNaissance = dateNearLabel(lines, birthLabel);
  out.dateExpiration = dateNearLabel(lines, /valable|jusqu|expir/i);
  if (!out.dateNaissance || !out.dateExpiration) {
    const all: string[] = [];
    const g = new RegExp(DATE_RE.source, "g");
    for (let m; (m = g.exec(text)); ) all.push(fmtDate(m));
    const byYear = [...new Set(all)].sort((a, b) => +a.slice(6) - +b.slice(6));
    if (byYear.length >= 2) {
      out.dateNaissance ||= byYear[0];
      out.dateExpiration ||= byYear[byYear.length - 1];
    }
  }

  // Birthplace: "à CASABLANCA" on or just after the birth-date line.
  const bi = lines.findIndex((l) => birthLabel.test(l));
  const scan = bi >= 0 ? lines.slice(bi, bi + 3) : lines;
  for (const l of scan) {
    const m = /(?:^|\s)[àa]\s+([A-ZÀ-Ÿ][A-ZÀ-Ÿ' \-]{2,})/.exec(latinOnly(l));
    if (m) { out.lieuNaissance = m[1].trim(); break; }
  }

  // Latin names: uppercase-only lines that are not headers or labels. Order assumed prénom, then nom.
  const latinNames: string[] = [];
  for (const l of lines) {
    if (/\d/.test(l) || birthLabel.test(l) || /^[àa]\s/i.test(l)) continue;
    const words = latinOnly(l).split(" ").filter((w) => /^[A-ZÀ-Ÿ'\-]{2,}$/.test(w));
    const name = words.join(" ");
    if (name.length >= 3 && !LATIN_STOP.test(name)) latinNames.push(name);
  }
  if (latinNames[0]) out.prenom = latinNames[0];
  if (latinNames[1]) out.nom = latinNames[1];

  const arNames: string[] = [];
  for (const l of lines) {
    if (!AR_RE.test(l) || /\d/.test(l) || AR_STOP.test(l)) continue;
    const name = l.replace(/[^ء-ي\s]/g, " ").replace(/\s+/g, " ").trim();
    if (name.replace(/\s/g, "").length >= 3 && !/^ب\s/.test(name)) arNames.push(name);
  }
  if (arNames[0]) out.prenomAr = arNames[0];
  if (arNames[1]) out.nomAr = arNames[1];

  return out;
}

export function parseCinVerso(text: string): Extracted {
  const adresse = afterLabel(toLines(text), /adresse/i);
  return adresse ? { adresse } : {};
}

// ---- MRZ (TD1, 3 lines of 30 chars) ----

function checkDigit(s: string) {
  const w = [7, 3, 1];
  let sum = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    const v = c === "<" ? 0 : /\d/.test(c) ? +c : c.charCodeAt(0) - 55;
    sum += v * w[i % 3];
  }
  return String(sum % 10);
}

function mrzDate(yymmdd: string, isBirth: boolean) {
  const yy = +yymmdd.slice(0, 2);
  const nowYY = new Date().getFullYear() % 100;
  const century = isBirth ? (yy > nowYY ? 1900 : 2000) : 2000;
  return `${yymmdd.slice(4, 6)}/${yymmdd.slice(2, 4)}/${century + yy}`;
}

/** Only fields whose check digit is valid (dates) or whose shape is unambiguous (names) are returned. */
export function parseMrz(text: string): Extracted {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.replace(/\s/g, "").toUpperCase())
    .filter((l) => l.length >= 15 && l.includes("<"));
  const out: Extracted = {};
  for (const raw of lines) {
    if (/^I[A-Z<]MAR/.test(raw)) continue; // line 1: document number
    const d = /(\d{6})(\d)[MF<](\d{6})(\d)/.exec(raw.replace(/O/g, "0"));
    if (d) {
      if (checkDigit(d[1]) === d[2]) out.dateNaissance = mrzDate(d[1], true);
      if (checkDigit(d[3]) === d[4]) out.dateExpiration = mrzDate(d[3], false);
      continue;
    }
    const n = /^([A-Z]+(?:<[A-Z]+)*)<<([A-Z]+(?:<[A-Z]+)*)/.exec(raw.replace(/0/g, "O"));
    if (n && !out.nom) {
      out.nom = n[1].replace(/</g, " ");
      out.prenom = n[2].replace(/</g, " ");
    }
  }
  return out;
}

// ---- Carte grise ----

export function parseCgRecto(text: string): Extracted {
  const lines = toLines(text);
  const out: Extracted = {};
  const plate = /(\d{1,6})\s*[-|/ ]\s*([ء-ي]|[A-Z])\s*[-|/ ]\s*(\d{1,2})\b/;
  const labelled = lines.find((l) => /immatricul/i.test(l));
  const m = (labelled && plate.exec(labelled)) || plate.exec(text) || /\bWW\s*-?\s*\d{3,6}\b/.exec(text);
  if (m) out.immatriculation = m[3] ? `${m[1]}-${m[2]}-${m[3]}` : m[0].replace(/\s/g, "");
  out.proprietaire = afterLabel(lines, /propri[ée]taire|nom\s+ou\s+raison\s+sociale|nom\s+et\s+pr[ée]nom/i);
  out.adresseProprietaire = afterLabel(lines, /adresse/i);
  return out;
}

function findVin(lines: string[]): string {
  const fix = (s: string) => s.replace(/O/g, "0").replace(/[IL](?=\d)/g, "1").replace(/Q/g, "0");
  const candidates: string[] = [];
  for (const l of lines) {
    const toks = l.toUpperCase().split(/[^A-Z0-9]+/).filter(Boolean);
    for (let i = 0; i < toks.length; i++) {
      let joined = "";
      for (let j = i; j < Math.min(i + 3, toks.length); j++) {
        joined += toks[j];
        if (joined.length === 17 && (joined.match(/\d/g) ?? []).length >= 4 && /[A-Z]/.test(joined))
          candidates.push(fix(joined));
        if (joined.length >= 17) break;
      }
    }
  }
  return candidates[0] ?? "";
}

/** VIN from the whitelist-only pass, where label letters may be glued in front of it. */
function findVinWhitelisted(text: string): string {
  for (const run of text.toUpperCase().match(/[A-HJ-NPR-Z0-9]{17,}/g) ?? []) {
    const vin = run.slice(-17);
    if ((vin.match(/\d/g) ?? []).length >= 4 && /[A-Z]/.test(vin)) return vin;
  }
  return "";
}

export function parseCgVerso(text: string, vinPass = ""): Extracted {
  const lines = toLines(text);
  const out: Extracted = {};
  const vi = lines.findIndex((l) => /ch[aâ]ss?is|\bVIN\b|s[ée]rie/i.test(l));
  out.vin = (vi >= 0 && findVin(lines.slice(vi, vi + 2))) || findVinWhitelisted(vinPass) || findVin(lines);
  out.marque = afterLabel(lines, /marque/i);
  out.type = afterLabel(lines, /\btype\b(?!\s*(de\s+)?carburant)/i);
  out.genre = afterLabel(lines, /genre/i);

  const fuelRaw = afterLabel(lines, /carburant|[ée]nergie/i);
  const fuels: [RegExp, string][] = [
    [/diesel|gasoil|gazoil/i, "Diesel"],
    [/essence/i, "Essence"],
    [/hybride/i, "Hybride"],
    [/[ée]lectrique/i, "Électrique"],
  ];
  const fuel = fuels.find(([re]) => re.test(fuelRaw)) ?? fuels.find(([re]) => re.test(text));
  out.carburant = fuel ? fuel[1] : fuelRaw;

  const pi = lines.findIndex((l) => /puissance/i.test(l));
  const pfNum =
    (pi >= 0 && (/puissance[^\d]*(\d{1,2})\b/i.exec(lines[pi]) ?? /^\D{0,3}(\d{1,2})\b/.exec(lines[pi + 1] ?? ""))) ||
    /\b(\d{1,2})\s*CV\b/i.exec(text);
  if (pfNum) out.puissanceFiscale = pfNum[1];

  out.dateMiseEnCirculation =
    dateNearLabel(lines, /circulation|1[èe]re?\s+mise|\bM\.?\s?C\b/i) || fmtDate(DATE_RE.exec(text));
  return out;
}
