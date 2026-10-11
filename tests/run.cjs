const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const out = mkdtempSync(path.join(tmpdir(), "cscan-test-"));
try {
  execFileSync(
    process.execPath,
    [
      require.resolve("typescript/bin/tsc"),
      "lib/parse.ts",
      "lib/fields.ts",
      "--outDir",
      out,
      "--module",
      "commonjs",
      "--target",
      "es2020",
      "--skipLibCheck",
    ],
    { stdio: "inherit" },
  );
  execFileSync(process.execPath, ["tests/parse.test.cjs"], {
    stdio: "inherit",
    env: { ...process.env, CSCAN_TEST_OUTPUT: out },
  });
} finally {
  rmSync(out, { recursive: true, force: true });
}
