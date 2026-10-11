"use client";
import { useEffect, useRef, useState } from "react";
import { canvasFile, loadPhoto, rectify, type Point } from "@/lib/image";

export default function Capture({
  hasPhoto,
  onFile,
}: {
  hasPhoto: boolean;
  onFile: (file: File) => void;
}) {
  const native = useRef<HTMLInputElement>(null),
    upload = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null),
    stream = useRef<MediaStream | null>(null);
  const requestId = useRef(0);
  const [camera, setCamera] = useState(false),
    [ready, setReady] = useState(false),
    [error, setError] = useState("");
  const [draft, setDraft] = useState<File | null>(null);
  const stop = () => {
    requestId.current++;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    setCamera(false);
    setReady(false);
  };
  useEffect(
    () => () => {
      requestId.current++;
      stream.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );
  useEffect(() => {
    if (!camera) return;
    const hide = () => {
      if (document.hidden) stop();
    };
    document.addEventListener("visibilitychange", hide);
    return () => document.removeEventListener("visibilitychange", hide);
  }, [camera]);
  const open = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      native.current?.click();
      return;
    }
    const id = ++requestId.current;
    setCamera(true);
    setReady(false);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 2560 },
          height: { ideal: 1440 },
        },
      });
      if (id !== requestId.current) {
        media.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = media;
      if (video.current) {
        video.current.srcObject = media;
        await video.current.play();
      }
    } catch {
      if (id === requestId.current) {
        stop();
        setError(
          "Caméra indisponible ou accès refusé. Autorisez la caméra, utilisez « Appareil photo du téléphone » ou importez une image.",
        );
      }
    }
  };
  const take = async () => {
    const v = video.current;
    if (!v?.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    try {
      const file = await canvasFile(c);
      stop();
      setDraft(file);
    } catch {
      setError("Capture impossible. Réessayez.");
    }
  };
  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      setError("");
      setDraft(file);
    }
  };
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={open}
          className="min-h-12 rounded-lg bg-blue-600 px-3 text-sm font-medium text-white"
        >
          {hasPhoto ? "Reprendre la photo" : "Prendre une photo"}
        </button>
        <button
          onClick={() => upload.current?.click()}
          className="min-h-12 rounded-lg border border-slate-300 bg-white px-3 text-sm"
        >
          Importer une photo
        </button>
        <input
          ref={native}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={pick}
        />
        <input
          ref={upload}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={pick}
        />
      </div>
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
        >
          {error}{" "}
          <button className="underline" onClick={() => native.current?.click()}>
            Appareil photo du téléphone
          </button>
        </p>
      )}
      {camera && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Prendre une photo"
          className="fixed inset-0 z-30 flex flex-col justify-center gap-4 overflow-auto bg-slate-950 p-4 text-white"
        >
          <p>Placez la carte entière dans l’image, à plat et sans reflet.</p>
          <video
            ref={video}
            autoPlay
            playsInline
            muted
            onLoadedMetadata={() => setReady(true)}
            className="max-h-[65vh] w-full rounded-xl object-contain"
          />
          {!ready && (
            <p>Ouverture de la caméra… Autorisez l’accès si demandé.</p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              disabled={!ready}
              onClick={take}
              className="min-h-12 rounded-lg bg-blue-600 px-5 disabled:opacity-40"
            >
              Prendre la photo
            </button>
            <button onClick={stop} className="min-h-12 px-4">
              Annuler
            </button>
            <button
              className="min-h-12 underline"
              onClick={() => {
                stop();
                native.current?.click();
              }}
            >
              Appareil photo du téléphone
            </button>
          </div>
        </div>
      )}
      {draft && (
        <AlignPhoto
          file={draft}
          onCancel={() => setDraft(null)}
          onReady={(file) => {
            setDraft(null);
            onFile(file);
          }}
        />
      )}
    </>
  );
}
const full: Point[] = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];
function AlignPhoto({
  file,
  onCancel,
  onReady,
}: {
  file: File;
  onCancel: () => void;
  onReady: (file: File) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null),
    container = useRef<HTMLDivElement>(null);
  const [corners, setCorners] = useState<Point[]>(full),
    [rotation, setRotation] = useState(0),
    [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setLoaded(false);
    loadPhoto(file)
      .then((img) => {
        if (!alive || !canvas.current) return;
        const c = canvas.current,
          scale = Math.min(1, 2600 / Math.max(img.width, img.height)),
          w = Math.round(img.width * scale),
          h = Math.round(img.height * scale);
        c.width = rotation % 180 ? h : w;
        c.height = rotation % 180 ? w : h;
        const ctx = c.getContext("2d")!;
        ctx.translate(c.width / 2, c.height / 2);
        ctx.rotate((rotation * Math.PI) / 180);
        ctx.drawImage(img, -w / 2, -h / 2, w, h);
        setLoaded(true);
        setCorners(full);
      })
      .catch(() => setError("Image illisible. Essayez une photo JPEG ou PNG."));
    return () => {
      alive = false;
    };
  }, [file, rotation]);
  const move = (i: number, e: React.PointerEvent<HTMLButtonElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const b = container.current!.getBoundingClientRect();
    const point = {
      x: Math.max(0, Math.min(1, (e.clientX - b.left) / b.width)),
      y: Math.max(0, Math.min(1, (e.clientY - b.top) / b.height)),
    };
    setCorners((p) => p.map((old, j) => (j === i ? point : old)));
  };
  const analyze = async () => {
    setBusy(true);
    setError("");
    try {
      const result = rectify(canvas.current!, corners);
      onReady(await canvasFile(result));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Recadrage impossible.");
      setBusy(false);
    }
  };
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Aligner la carte"
      className="fixed inset-0 z-30 overflow-auto bg-slate-950 p-6 text-white"
    >
      <div className="mx-auto max-w-2xl space-y-5">
        <h2 className="text-lg font-semibold">
          Alignez les quatre coins de la carte
        </h2>
        <p className="text-sm">
          Glissez les points sur les coins. Le texte doit être à l’endroit.
          L’analyse démarre après validation.
        </p>
        <div ref={container} className="relative">
          <canvas ref={canvas} className="block w-full" />
          {loaded && (
            <>
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
              >
                <polygon
                  points={corners
                    .map((p) => `${p.x * 100},${p.y * 100}`)
                    .join(" ")}
                  fill="rgba(37,99,235,.08)"
                  stroke="#60a5fa"
                  strokeWidth=".5"
                />
              </svg>
              {corners.map((p, i) => (
                <button
                  key={i}
                  aria-label={`Coin ${i + 1}`}
                  style={{
                    left: `${p.x * 100}%`,
                    top: `${p.y * 100}%`,
                    touchAction: "none",
                  }}
                  className="absolute flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white bg-blue-600 text-sm"
                  onPointerDown={(e) =>
                    e.currentTarget.setPointerCapture(e.pointerId)
                  }
                  onPointerMove={(e) => move(i, e)}
                  onKeyDown={(e) => {
                    const delta = e.shiftKey ? 0.05 : 0.01;
                    const d: Record<string, Point> = {
                      ArrowLeft: { x: -delta, y: 0 },
                      ArrowRight: { x: delta, y: 0 },
                      ArrowUp: { x: 0, y: -delta },
                      ArrowDown: { x: 0, y: delta },
                    };
                    if (d[e.key]) {
                      e.preventDefault();
                      setCorners((ps) =>
                        ps.map((p, j) =>
                          j === i
                            ? {
                                x: Math.max(0, Math.min(1, p.x + d[e.key].x)),
                                y: Math.max(0, Math.min(1, p.y + d[e.key].y)),
                              }
                            : p,
                        ),
                      );
                    }
                  }}
                >
                  {i + 1}
                </button>
              ))}
            </>
          )}
        </div>
        {error && (
          <p role="alert" className="text-amber-300">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <button
            disabled={!loaded || busy}
            onClick={analyze}
            className="min-h-12 rounded-lg bg-blue-600 px-5 disabled:opacity-40"
          >
            {busy ? "Préparation…" : "Valider et analyser"}
          </button>
          <button
            disabled={busy}
            onClick={() => setRotation((r) => (r + 90) % 360)}
            className="min-h-12 px-3"
          >
            Tourner ↻
          </button>
          <button disabled={busy} onClick={onCancel} className="min-h-12 px-3">
            Annuler
          </button>
        </div>
      </div>
    </div>
  );
}
