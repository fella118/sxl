export type Point = { x: number; y: number };
export async function loadPhoto(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return image;
  } finally {
    URL.revokeObjectURL(url);
  }
}
export async function canvasFile(canvas: HTMLCanvasElement): Promise<File> {
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("Image illisible"))),
      "image/jpeg",
      0.95,
    ),
  );
  return new File([blob], "document.jpg", { type: "image/jpeg" });
}
// Solve the projective mapping from the unit rectangle to the selected quadrilateral.
function homography(points: Point[]) {
  const matrix: number[][] = [];
  [
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ].forEach(([u, v], i) => {
    const { x, y } = points[i];
    matrix.push(
      [u, v, 1, 0, 0, 0, -u * x, -v * x, x],
      [0, 0, 0, u, v, 1, -u * y, -v * y, y],
    );
  });
  for (let col = 0; col < 8; col++) {
    let pivot = col;
    for (let row = col + 1; row < 8; row++)
      if (Math.abs(matrix[row][col]) > Math.abs(matrix[pivot][col]))
        pivot = row;
    [matrix[col], matrix[pivot]] = [matrix[pivot], matrix[col]];
    const div = matrix[col][col];
    if (Math.abs(div) < 1e-9)
      throw new Error("Écartez les quatre coins du document.");
    for (let j = col; j < 9; j++) matrix[col][j] /= div;
    for (let row = 0; row < 8; row++)
      if (row !== col) {
        const scale = matrix[row][col];
        for (let j = col; j < 9; j++) matrix[row][j] -= scale * matrix[col][j];
      }
  }
  return matrix.map((row) => row[8]);
}
export function rectify(
  source: HTMLCanvasElement,
  corners: Point[],
): HTMLCanvasElement {
  // Require a convex clockwise polygon of usable area; reject crossed corner handles.
  let area = 0;
  for (let i = 0; i < 4; i++) {
    const a = corners[i],
      b = corners[(i + 1) % 4],
      c = corners[(i + 2) % 4];
    if ((b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x) <= 0.001)
      throw new Error("Placez les coins dans l’ordre autour de la carte.");
    area += a.x * b.y - b.x * a.y;
  }
  if (area < 0.06) throw new Error("La carte est trop petite dans la photo.");
  const h = homography(
    corners.map((p) => ({
      x: p.x * (source.width - 1),
      y: p.y * (source.height - 1),
    })),
  );
  const result = document.createElement("canvas");
  result.width = 1800;
  result.height = 1135;
  const pixels = source
    .getContext("2d")!
    .getImageData(0, 0, source.width, source.height).data;
  const ctx = result.getContext("2d")!;
  const out = ctx.createImageData(result.width, result.height);
  for (let y = 0; y < result.height; y++)
    for (let x = 0; x < result.width; x++) {
      const u = x / (result.width - 1),
        v = y / (result.height - 1),
        d = h[6] * u + h[7] * v + 1;
      const sx = Math.max(
        0,
        Math.min(source.width - 1, (h[0] * u + h[1] * v + h[2]) / d),
      );
      const sy = Math.max(
        0,
        Math.min(source.height - 1, (h[3] * u + h[4] * v + h[5]) / d),
      );
      const x0 = Math.floor(sx),
        y0 = Math.floor(sy),
        x1 = Math.min(x0 + 1, source.width - 1),
        y1 = Math.min(y0 + 1, source.height - 1),
        dx = sx - x0,
        dy = sy - y0;
      const index = (y * result.width + x) * 4;
      for (let c = 0; c < 3; c++)
        out.data[index + c] =
          pixels[(y0 * source.width + x0) * 4 + c] * (1 - dx) * (1 - dy) +
          pixels[(y0 * source.width + x1) * 4 + c] * dx * (1 - dy) +
          pixels[(y1 * source.width + x0) * 4 + c] * (1 - dx) * dy +
          pixels[(y1 * source.width + x1) * 4 + c] * dx * dy;
      out.data[index + 3] = 255;
    }
  ctx.putImageData(out, 0, 0);
  return result;
}
