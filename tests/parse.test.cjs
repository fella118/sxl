const assert = require("node:assert/strict");
const path = require("node:path");
const dir = process.env.CSCAN_TEST_OUTPUT;
const {
  parseCinRecto,
  parseMrz,
  parseCgRecto,
  parseCgVerso,
  cleanName,
} = require(path.join(dir, "parse.js"));
const { validate } = require(path.join(dir, "fields.js"));
// Synthetic fixtures only: never commit identity documents or OCR transcripts.
const front = parseCinRecto(
  "ROYAUME DU MAROC\nAMINE\nEL IDRISSI\nNé le 04.03.2000\nàKENITRA\nValable jusqu’au 12.03.2031\nAB123456",
);
assert.equal(front.nom, undefined);
assert.equal(front.prenom, undefined);
assert.equal(front.lieuNaissance, "KENITRA");
assert.equal(cleanName("àKENITRA"), "");
assert.equal(cleanName("AMINE"), "AMINE");
assert.equal(cleanName("بتاريخ", true), "");
const mrz = parseMrz(
  "IDMAR1234567890<<<<<<<<<<<<<<<\n0403243M3103120MAR<<<<<<<<<<<<8\nEL<IDRISSI<<AMINE<<<<<<<<<<<<<<",
);
assert.equal(mrz.nom, "EL IDRISSI");
assert.equal(mrz.prenom, "AMINE");
assert.equal(mrz.dateNaissance, "24/03/2004");
assert.equal(mrz.dateExpiration, "12/03/2031");
assert.equal(
  parseMrz("0403249M3103129MAR<<<<<<<<<<<<8").dateNaissance,
  undefined,
);
assert.equal(validate("date", "31/02/2026"), "Date inexistante");
assert.equal(validate("date", "29/02/2024"), null);
assert.equal(
  parseCgRecto("Première mise en circulation 02/03/2020").dateMiseEnCirculation,
  "02/03/2020",
);
assert.equal(
  parseCgVerso(
    "Marque NISSAN\nType\nGenre FOURGON\nPuissance fiscale 6\nN° du chassis VSKTBAM20Z0123456",
  ).type,
  "",
);
assert.equal(parseCgVerso("", "LABELVSKTBAM20Z0123456").vin, "");
assert.equal(
  parseCgVerso("N° du chassis VSKTBAM20Z0123456").vin,
  "VSKTBAM20Z0123456",
);
assert.equal(parseCgVerso("N° du chassis VSKTBAM2OZ0123456").vin, "");
console.log("Parser regression checks passed.");
