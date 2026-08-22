import assert from "node:assert/strict";
import { candidateProbe } from "../Sources/web/candidate-probe.mjs";

const response = (status, body = null) => ({
  ok: status >= 200 && status < 300,
  status,
  async json() {
    if (body === null) throw new Error("not JSON");
    return body;
  },
});

assert.deepEqual(await candidateProbe(response(200)), { available: true, error: null });
assert.deepEqual(await candidateProbe(response(404)), { available: false, error: null });

const invalid = await candidateProbe(response(500, { error: "cannot read valid JSON for trip synthetic-trip" }));
assert.equal(invalid.available, false);
assert.match(invalid.error, /候補版を確認できません/);
assert.match(invalid.error, /candidate\.jsonを確認してください/);

const mismatch = await candidateProbe(response(500, { error: "trip folder and JSON id do not match for synthetic-trip" }));
assert.equal(mismatch.available, false);
assert.match(mismatch.error, /JSON id do not match/);

console.log("Candidate availability probe checks passed.");
