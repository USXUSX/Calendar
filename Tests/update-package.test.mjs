import assert from "node:assert/strict";
import { createUpdatePackage } from "../Sources/web/update-package.mjs";

const original = {
  schemaVersion: "calendar-trip-v1",
  trip: { id: "legacy-trip", name: "合成旅行" },
  meals: [{ id: "meal-1", candidates: [{ id: "restaurant-1", name: "合成食堂" }] }],
  intercityRoutes: [{ date: "2030-01-01", mode: "車", places: ["A", "B"] }],
};
const displayTrip = {
  id: "legacy-trip",
  title: "合成旅行",
  days: [],
  transports: [{ id: "intercity-1-1" }],
  places: [],
};
const text = createUpdatePackage(original, displayTrip, [
  { type: "Meal", id: "meal-1", name: "昼食", change: "候補を変更する" },
  { type: "Transport", id: "intercity-1-1", name: "A → B", change: "出発時刻を調整する" },
]);

assert.match(text, /Calendar AI更新依頼パッケージ/);
assert.match(text, /差分や部分JSONではなく次版の完全JSON/);
assert.match(text, /schemaVersionと基本構造を維持/);
assert.match(text, /安定ID: meal-1/);
assert.match(text, /派生表示上の参照: intercity-1-1/);
assert.match(text, /元JSON上のIDではありません/);
const jsonText = text.split("採用済みcurrent.json（完全JSON・表示用正規化前）\n")[1];
assert.deepEqual(JSON.parse(jsonText), original);
assert.match(jsonText, /"schemaVersion": "calendar-trip-v1"/);
assert.match(jsonText, /"meals"/);
assert.match(jsonText, /"intercityRoutes"/);
assert.doesNotMatch(jsonText, /"transports"/);

console.log("AI update package checks passed.");
