"use client";

import type { Worker } from "tesseract.js";

const MAX_SIDE = 2400;
const MRZ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<";
const VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";

type Langs = "fra+ara" | "fra";
const workers: Partial<Record<Langs, Promise<Worker>>> = {};
let onProgress: ((p: number) => void) | null = null;
let queue: Promise<unknown> = Promise.resolve();

// "fra+ara" reads the cards; a Latin-only "fra" worker handles the MRZ and VIN passes,
// because mixing in the Arabic model garbles long alphanumeric strings.
function getWorker(langs: Langs) {
  if (!workers[langs]) {
    const p = import("tesseract.js").then(({ createWorker }) =>
      createWorker(langs.split("+"), 1, {
        logger: (m) => {
          if (m.status === "recognizing text") onProgress?.(m.progress);
        },
      }),
    );
    p.catch(() => delete workers[langs]);
    workers[langs] = p;
  }
  return workers[langs]!;
}

/** Grayscale + contrast stretch, downscaled for speed. Runs entirely in the browser. */
async function preprocess(file: File): Promise<HTMLCanvasElement> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.round(img.naturalWidth * scale);
    const h = Math.round(img.naturalHeight * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    ctx.drawImage(img, 0, 0, w, h);

    const data = ctx.getImageData(0, 0, w, h);
    const px = data.data;
    const gray = new Uint8ClampedArray(w * h);
    const hist = new Uint32Array(256);
    for (let i = 0, j = 0; i < px.length; i += 4, j++) {
      const g = (px[i] * 299 + px[i + 1] * 587 + px[i + 2] * 114) / 1000;
      gray[j] = g;
      hist[gray[j]]++;
    }
    // Stretch between 2nd and 98th percentile, then boost contrast around the middle.
    const total = w * h;
    let lo = 0, hi = 255, acc = 0;
    for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= total * 0.02) { lo = v; break; } }
    acc = 0;
    for (let v = 255; v >= 0; v--) { acc += hist[v]; if (acc >= total * 0.02) { hi = v; break; } }
    const range = Math.max(1, hi - lo);
    const CONTRAST = 1.4;
    for (let i = 0, j = 0; i < px.length; i += 4, j++) {
      let v = ((gray[j] - lo) * 255) / range;
      v = (v - 128) * CONTRAST + 128;
      px[i] = px[i + 1] = px[i + 2] = v;
    }
    ctx.putImageData(data, 0, 0);
    return canvas;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export interface OcrOutput {
  text: string;
  /** Second pass restricted to the MRZ or VIN character set. */
  extra?: string;
}

/** OCR one photo. Jobs are serialized so only one runs at a time. */
export function runOcr(file: File, pass: "mrz" | "vin" | null, progress: (p: number) => void): Promise<OcrOutput> {
  const job = queue.then(async () => {
    onProgress = progress;
    try {
      const canvas = await preprocess(file);
      const main = await getWorker("fra+ara");
      await main.setParameters({ tessedit_pageseg_mode: "3" as never });
      const { data } = await main.recognize(canvas);
      const out: OcrOutput = { text: data.text };
      if (pass) {
        const latin = await getWorker("fra");
        await latin.setParameters({
          tessedit_pageseg_mode: "6" as never,
          tessedit_char_whitelist: pass === "mrz" ? MRZ_CHARS : VIN_CHARS,
        });
        // The MRZ sits at the bottom of the card: only read the lower part.
        const top = pass === "mrz" ? Math.round(canvas.height * 0.5) : 0;
        const res = await latin.recognize(canvas, {
          rectangle: { left: 0, top, width: canvas.width, height: canvas.height - top },
        });
        out.extra = res.data.text;
      }
      return out;
    } finally {
      onProgress = null;
    }
  });
  queue = job.catch(() => undefined);
  return job;
}
