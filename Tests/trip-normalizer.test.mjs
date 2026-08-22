import assert from "node:assert/strict";
import { normalizeTrip } from "../Sources/web/trip-normalizer.mjs";

const legacyTrip = {
  schemaVersion: "calendar-trip-v1",
  trip: {
    id: "synthetic-legacy-trip",
    name: "合成旧形式旅行",
    startDate: "2030-04-10",
    endDate: "2030-04-11",
  },
  days: [
    { date: "2030-04-10", dayNumber: 1, label: "港と食事", areas: ["港", "温泉"] },
    { date: "2030-04-11", dayNumber: 2, label: "帰宅", areas: ["温泉", "駅"] },
  ],
  itinerary: [
    {
      id: "visit-port",
      date: "2030-04-10",
      time: "09:30",
      title: "港を見学",
      category: "観光",
      status: "確定",
      transport: "レンタカーで30分",
      mapPointId: "port",
    },
  ],
  mapPoints: [
    { id: "port", date: "2030-04-10", name: "合成港", category: "観光", latitude: 35.0, longitude: 135.0 },
    { id: "restaurant-map", date: "2030-04-10", name: "候補食堂", category: "食事", latitude: 35.1, longitude: 135.1 },
  ],
  meals: [
    {
      id: "lunch",
      date: "2030-04-10",
      timing: "昼",
      title: "昼食",
      description: "海鮮を比較する",
      status: "候補",
      candidates: [
        { id: "restaurant-a", name: "候補食堂", mapPointId: "restaurant-map", summary: "海鮮", rating: 3.5, ratingUpdatedAt: "2030-03-01" },
        { id: "restaurant-b", name: "第二食堂", summary: "定食" },
      ],
    },
  ],
  intercityRoutes: [
    { date: "2030-04-10", mode: "車", places: ["合成港", "合成温泉"] },
    { date: "2030-04-11", mode: "電車", places: ["合成温泉", "合成駅"] },
  ],
  preparation: [],
  bookings: [
    { id: "hotel-booking", label: "合成ホテル", status: "確定", amount: null },
    { id: "flight-booking", label: "航空券", status: "未定", amount: 0 },
    { id: "unknown-booking", label: "連絡事項", status: "未定", amount: null },
  ],
};

const normalized = normalizeTrip(legacyTrip);
const firstDay = normalized.days[0];
const secondDay = normalized.days[1];
const meal = firstDay.scheduleItems.find((item) => item.id === "lunch");
const itinerary = firstDay.scheduleItems.find((item) => item.id === "visit-port");

assert.deepEqual(meal.placeSelection.candidatePlaceIds, ["restaurant-a", "restaurant-b"]);
assert.equal(meal.category, "food");
assert.equal(normalized.places.find((place) => place.id === "restaurant-a").legacyMapPointId, "restaurant-map");
assert.deepEqual(normalized.places.find((place) => place.id === "restaurant-a").location, { latitude: 35.1, longitude: 135.1 });
assert.equal(normalized.places.find((place) => place.id === "restaurant-a").rating.value, 3.5);

assert.equal(itinerary.legacyTransport, "レンタカーで30分");
assert.match(itinerary.summary, /レンタカーで30分/);
assert.equal(normalized.transports.length, 2);
assert.deepEqual(firstDay.transportIds, ["intercity-1-1"]);
assert.deepEqual(secondDay.transportIds, ["intercity-2-1"]);
assert.equal(normalized.transports[0].mode, "car");
assert.equal(normalized.transports[1].mode, "train");
assert.equal(normalized.places.find((place) => place.id === normalized.transports[0].toPlaceId).name, "合成温泉");

const hotelBooking = normalized.bookings.find((booking) => booking.id === "hotel-booking");
const flightBooking = normalized.bookings.find((booking) => booking.id === "flight-booking");
const unknownBooking = normalized.bookings.find((booking) => booking.id === "unknown-booking");
assert.equal(hotelBooking.label, "合成ホテル");
assert.equal(hotelBooking.amount, null);
assert.equal(hotelBooking.category, "accommodation");
assert.equal(flightBooking.amount, 0);
assert.equal(flightBooking.category, "transport");
assert.equal(unknownBooking.category, "other");

console.log("Legacy trip normalization checks passed.");
