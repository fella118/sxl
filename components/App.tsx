"use client";

import { useRef, useState } from "react";
import {
  ALL_FIELDS,
  TABS,
  validate,
  type FieldDef,
  type FieldKey,
  type TabId,
} from "@/lib/fields";
import { runOcr } from "@/lib/ocr";
import Capture from "./Capture";
import {
  cleanName,
  parseCgRecto,
  parseCgVerso,
  parseCinRecto,
  parseCinVerso,
  parseMrz,
  type Extracted,
} from "@/lib/parse";

type Photo = { url: string; id: number };
type Ocr = { status: "idle" | "running" | "done" | "error"; progress: number };

const TAB_IDS = TABS.map((t) => t.id);
const MRZ_KEYS: FieldKey[] = [
  "nom",
  "prenom",
  "dateNaissance",
  "dateExpiration",
];

const perTab = <T,>(v: T) =>
  Object.fromEntries(TAB_IDS.map((id) => [id, v])) as Record<TabId, T>;
const perField = <T,>(v: T) =>
  Object.fromEntries(ALL_FIELDS.map((f) => [f.key, v])) as Record<FieldKey, T>;

const PARSERS: Record<TabId, (text: string, extra?: string) => Extracted> = {
  cinRecto: parseCinRecto,
  cinVerso: parseCinVerso,
  cgRecto: parseCgRecto,
  cgVerso: parseCgVerso,
};

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

export default function App() {
  const [active, setActive] = useState<TabId>("cinRecto");
  const [photos, setPhotos] = useState<Record<TabId, Photo | null>>(
    perTab(null),
  );
  const [ocr, setOcr] = useState<Record<TabId, Ocr>>(
    perTab({ status: "idle", progress: 0 }),
  );
  const [values, setValues] = useState<Record<FieldKey, string>>(perField(""));
  const [copied, setCopied] = useState<Record<FieldKey, boolean>>(
    perField(false),
  );
  const [mrz, setMrz] = useState<Extracted | null>(null);
  const mrzRef = useRef<Extracted | null>(null);
  // Latest photo id per tab: OCR results for a replaced photo are dropped.
  const photoIds = useRef<Record<TabId, number>>(perTab(0));
  const counter = useRef(0);
  const edited = useRef<Record<FieldKey, boolean>>(perField(false));
  const [review, setReview] = useState<Record<FieldKey, boolean>>(
    perField(false),
  );

  const setMrzBoth = (m: Extracted | null) => {
    mrzRef.current = m;
    setMrz(m);
  };

  // Refresh machine suggestions, never values edited by staff.
  const fillEmpty = (data: Extracted) => {
    setCopied((c) => ({
      ...c,
      ...Object.fromEntries(
        Object.keys(data)
          .filter((k) => !edited.current[k as FieldKey])
          .map((k) => [k, false]),
      ),
    }));
    setValues((v) => {
      const next = { ...v };
      for (const [k, val] of Object.entries(data) as [FieldKey, string][]) {
        if (val && !edited.current[k]) next[k] = val;
      }
      return next;
    });
  };

  const handleFile = async (tab: TabId, file: File) => {
    const id = ++counter.current;
    photoIds.current[tab] = id;
    const tabFields = TABS.find((t) => t.id === tab)!.fields;

    setPhotos((p) => {
      if (p[tab]) URL.revokeObjectURL(p[tab]!.url);
      return { ...p, [tab]: { url: URL.createObjectURL(file), id } };
    });
    // Retakes refresh OCR suggestions but preserve staff edits.
    setValues((v) => ({
      ...v,
      ...Object.fromEntries(
        tabFields.filter((f) => !edited.current[f.key]).map((f) => [f.key, ""]),
      ),
    }));
    setCopied((c) => ({
      ...c,
      ...Object.fromEntries(tabFields.map((f) => [f.key, false])),
    }));
    if (tab === "cinVerso") setMrzBoth(null);
    setOcr((o) => ({ ...o, [tab]: { status: "running", progress: 0 } }));

    try {
      const res = await runOcr(file, tab, (p) => {
        if (photoIds.current[tab] === id)
          setOcr((o) => ({ ...o, [tab]: { status: "running", progress: p } }));
      });
      if (photoIds.current[tab] !== id) return;

      const data = PARSERS[tab](res.text, res.extra);
      if (tab === "cgVerso") {
        for (const key of [
          "marque",
          "type",
          "genre",
          "carburant",
          "puissanceFiscale",
        ] as const) {
          const region = res.regions[key];
          const value = region?.text.replace(/\s+/g, " ").trim() ?? "";
          const check = TABS.find((t) => t.id === tab)!.fields.find(
            (f) => f.key === key,
          )?.check;
          data[key] =
            region &&
            region.confidence >= 60 &&
            value &&
            !validate(check, value)
              ? value
              : "";
        }
      }
      for (const key of ["nom", "prenom", "nomAr", "prenomAr"] as const) {
        const region = res.regions[key];
        if (region && region.confidence >= 45) {
          const name = cleanName(region.text, key.endsWith("Ar"));
          if (name) data[key] = name;
        }
      }
      setReview((r) => ({
        ...r,
        ...Object.fromEntries(tabFields.map((f) => [f.key, true])),
      }));
      if (tab === "cinVerso") {
        const m = { ...parseMrz(res.text), ...parseMrz(res.extra ?? "") };
        const found = Object.keys(m).length > 0 ? m : null;
        setMrzBoth(found);
        if (found) fillEmpty(found);
      }
      if (tab === "cinRecto" && mrzRef.current) {
        // Prefer the structured MRZ, while fillEmpty preserves all manual corrections.
        for (const k of MRZ_KEYS)
          if (mrzRef.current[k]) data[k] = mrzRef.current[k];
      }
      fillEmpty(data);
      setOcr((o) => ({ ...o, [tab]: { status: "done", progress: 1 } }));
    } catch {
      if (photoIds.current[tab] === id)
        setOcr((o) => ({ ...o, [tab]: { status: "error", progress: 0 } }));
    }
  };

  const changeValue = (f: FieldDef, raw: string) => {
    edited.current[f.key] = true;
    setReview((r) => ({ ...r, [f.key]: false }));
    const val = f.upper ? raw.toUpperCase().replace(/\s/g, "") : raw;
    setValues((v) => ({ ...v, [f.key]: val }));
    setCopied((c) => ({ ...c, [f.key]: false }));
  };

  const copyField = async (key: FieldKey) => {
    const text = values[key].trim();
    if (text && (await copyText(text)))
      setCopied((c) => ({ ...c, [key]: true }));
  };

  const nextClient = () => {
    const hasData =
      TAB_IDS.some((t) => photos[t]) || ALL_FIELDS.some((f) => values[f.key]);
    if (
      hasData &&
      !window.confirm("Effacer toutes les photos et tous les champs ?")
    )
      return;
    for (const t of TAB_IDS) {
      photoIds.current[t] = ++counter.current;
      if (photos[t]) URL.revokeObjectURL(photos[t]!.url);
    }
    setPhotos(perTab(null));
    setOcr(perTab({ status: "idle", progress: 0 }));
    setValues(perField(""));
    edited.current = perField(false);
    setReview(perField(false));
    setCopied(perField(false));
    setMrzBoth(null);
    setActive("cinRecto");
    window.scrollTo(0, 0);
  };

  const dot = (tab: TabId) => {
    if (!photos[tab]) return "bg-slate-300";
    const fields = TABS.find((t) => t.id === tab)!.fields;
    return fields.every((f) => copied[f.key])
      ? "bg-green-500"
      : "bg-orange-400";
  };

  const tab = TABS.find((t) => t.id === active)!;
  const photo = photos[active];
  const state = ocr[active];

  return (
    <div className="mx-auto min-h-dvh max-w-2xl pb-16">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 px-4 py-2">
          <h1 className="text-base font-semibold">C scan</h1>
          <button
            onClick={nextClient}
            className="min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white active:bg-slate-700"
          >
            Client suivant
          </button>
        </div>
        <nav className="grid grid-cols-4 border-t border-slate-100">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              className={`flex min-h-14 flex-col items-center justify-center gap-1 px-1 text-xs leading-tight ${
                t.id === active
                  ? "border-b-2 border-slate-900 font-semibold"
                  : "border-b-2 border-transparent text-slate-500"
              }`}
            >
              <span
                className={`h-2.5 w-2.5 rounded-full ${dot(t.id)}`}
                aria-hidden
              />
              <span className="text-center">{t.label}</span>
            </button>
          ))}
        </nav>
      </header>

      <main className="space-y-4 px-4 pt-4">
        <Capture
          key={active}
          hasPhoto={!!photo}
          onFile={(file) => handleFile(active, file)}
        />

        {photo && <PhotoViewer key={photo.id} url={photo.url} />}

        {state.status === "running" && (
          <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
            Analyse en cours… {Math.round(state.progress * 100)} %
          </p>
        )}
        {state.status === "error" && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            Échec de l&apos;analyse. Saisissez les champs à la main ou reprenez
            la photo.
          </p>
        )}
        {active === "cinVerso" && state.status === "done" && (
          <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
            {mrz
              ? "Zone MRZ lue : suggestions reportées dans CIN recto. Vérifiez les noms sur la carte."
              : "Aucune zone MRZ lisible sur cette photo."}
          </p>
        )}

        {state.status === "done" && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Vérifiez les suggestions sur la photo. Les champs illisibles restent
            à compléter.{" "}
            {active === "cinRecto" &&
              "Scannez aussi le verso pour lire les noms dans la zone MRZ."}
          </p>
        )}
        <p className="text-xs text-slate-500">
          Analyse sur cet appareil. Les photos ne sont pas envoyées à un service
          OCR.
        </p>
        <div className="space-y-4">
          {tab.fields.map((f) => (
            <FieldRow
              key={f.key}
              field={f}
              value={values[f.key]}
              copied={copied[f.key]}
              needsReview={review[f.key]}
              mrzValue={
                active === "cinRecto" && MRZ_KEYS.includes(f.key)
                  ? mrz?.[f.key]
                  : undefined
              }
              onChange={(v) => changeValue(f, v)}
              onCopy={() => copyField(f.key)}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function PhotoViewer({ url }: { url: string }) {
  const [zoom, setZoom] = useState(1);
  return (
    <div>
      <div className="max-h-[70vh] overflow-auto rounded-lg border border-slate-200 bg-slate-900">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt="Photo du document"
          style={{ width: `${zoom * 100}%` }}
          className="block max-w-none"
        />
      </div>
      <div className="mt-2 flex items-center justify-end gap-2">
        <span className="mr-auto text-xs text-slate-500">
          Zoom {Math.round(zoom * 100)} %
        </span>
        {[
          { label: "−", onClick: () => setZoom((z) => Math.max(1, z - 0.5)) },
          { label: "100 %", onClick: () => setZoom(1) },
          { label: "+", onClick: () => setZoom((z) => Math.min(5, z + 0.5)) },
        ].map((b) => (
          <button
            key={b.label}
            onClick={b.onClick}
            className="min-h-11 min-w-11 rounded-lg border border-slate-300 bg-white px-3 text-base font-medium active:bg-slate-100"
          >
            {b.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function FieldRow({
  field,
  value,
  copied,
  mrzValue,
  needsReview,
  onChange,
  onCopy,
}: {
  field: FieldDef;
  value: string;
  copied: boolean;
  mrzValue?: string;
  needsReview: boolean;
  onChange: (v: string) => void;
  onCopy: () => void;
}) {
  const error = validate(field.check, value);
  const id = `f-${field.key}`;
  const mrzMatches =
    mrzValue && mrzValue.trim().toUpperCase() === value.trim().toUpperCase();
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1 block text-sm font-medium text-slate-700"
      >
        {field.label}
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          dir={field.rtl ? "rtl" : "ltr"}
          lang={field.rtl ? "ar" : "fr"}
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          className={`min-h-12 w-full min-w-0 rounded-lg border bg-white px-3 text-base outline-none focus:ring-2 ${
            error
              ? "border-red-500 focus:ring-red-200"
              : needsReview
                ? "border-amber-400 focus:ring-amber-200"
                : "border-slate-300 focus:ring-blue-200"
          }`}
        />
        <button
          onClick={onCopy}
          disabled={!value.trim()}
          aria-label={`Copier ${field.label}`}
          className={`min-h-12 min-w-24 shrink-0 rounded-lg px-3 text-sm font-semibold disabled:opacity-40 ${
            copied
              ? "bg-green-600 text-white"
              : "bg-slate-900 text-white active:bg-slate-700"
          }`}
        >
          {copied ? "✓ Copié" : "Copier"}
        </button>
      </div>
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      {mrzValue && mrzMatches && (
        <p className="mt-1 text-sm text-green-700">
          Correspond à la lecture MRZ — à vérifier
        </p>
      )}
      {mrzValue && !mrzMatches && (
        <div className="mt-1 flex items-center gap-2 text-sm text-amber-800">
          <span>
            MRZ : <strong>{mrzValue}</strong>
          </span>
          <button
            onClick={() => onChange(mrzValue)}
            className="min-h-11 rounded-lg border border-amber-400 bg-amber-50 px-3 font-medium active:bg-amber-100"
          >
            Utiliser
          </button>
        </div>
      )}
    </div>
  );
}
