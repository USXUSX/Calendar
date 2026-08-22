const SAMPLE_URL = "../../Samples/synthetic-trip.json";

// The adopted JSON remains read-only. Every interaction in this stage lives
// only in this in-memory object and is discarded when the page is closed.
const draftState = {
  preparation: new Map(),
  rioPacking: new Map(),
  placeSelections: new Map(),
  instructions: new Map(),
  aiPanelOpen: false,
  aiTarget: null,
  collapsedDays: new Set(),
  collapsedMapDays: new Set(),
  itineraryDay: "all",
  itineraryCategory: "all",
  mapDay: "all",
  mapCategory: "all",
  pendingTripComment: "",
  editingCommentKey: null,
};

const targetKey = (type, id) => `${type}:${id}`;

const shortDateFormatter = new Intl.DateTimeFormat("ja-JP", { month: "numeric", day: "numeric" });
const weekdayFormatter = new Intl.DateTimeFormat("ja-JP", { weekday: "short" });
const currentDateFormatter = new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "numeric", day: "numeric", weekday: "short" });
const moneyFormatter = new Intl.NumberFormat("ja-JP", {
  style: "currency",
  currency: "JPY",
  maximumFractionDigits: 0,
});

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const localDate = (value) => new Date(`${value}T00:00:00+09:00`);
const formatDate = (value) => {
  return shortDateFormatter.format(localDate(value));
};

const formatDateRange = ({ start, end }) => {
  const first = localDate(start);
  return `${first.getFullYear()}/${first.getMonth() + 1}/${first.getDate()}〜${formatDate(end)}`;
};

const formatShortDateRange = ({ start, end }) => `${formatDate(start)}〜${formatDate(end)}`;

const formatClock = (value) => value ? value.replace(/^0/, "") : "";
const formatCurrentDate = (date = new Date()) => currentDateFormatter.format(date).replace(/\(([^)]+)\)$/, "（$1）");
const formatIsoLocalDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

const transportLabels = {
  ferry: "フェリー",
  walk: "徒歩",
  train: "電車",
  bus: "バス",
  car: "車",
  flight: "飛行機",
};

const categoryLabels = {
  accommodation: "宿泊費",
  transport: "交通費",
  activity: "観光・チケット",
  other: "その他",
};

function placeRating(place) {
  if (!place.rating) return "";
  return `<span class="rating">${escapeHtml(place.rating.source)} ${place.rating.value.toFixed(2)}</span>`;
}

function renderHome(trips) {
  document.title = "Calendar | 旅の一覧";
  const today = formatIsoLocalDate();
  const upcoming = [...trips].filter((trip) => trip.dateRange.end >= today).sort((a, b) => a.dateRange.start.localeCompare(b.dateRange.start));
  const past = [...trips].filter((trip) => trip.dateRange.end < today).sort((a, b) => b.dateRange.end.localeCompare(a.dateRange.end));
  const referenceTrip = upcoming[0] ?? past[0];
  if (!referenceTrip) throw new Error("採用済みの旅行がありません。Calendar_Localを確認してください。");
  const start = localDate(referenceTrip.dateRange.start);
  const year = start.getFullYear();
  const month = start.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let index = 0; index < firstDay.getDay(); index += 1) cells.push(`<div class="calendar-cell muted" aria-hidden="true"></div>`);
  for (let day = 1; day <= lastDay; day += 1) {
    const date = new Date(year, month, day);
    const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const tripsOnDate = trips.filter((trip) => iso >= trip.dateRange.start && iso <= trip.dateRange.end);
    const startingTrips = tripsOnDate.filter((trip) => iso === trip.dateRange.start);
    cells.push(`<div class="calendar-cell ${tripsOnDate.length ? "trip-span" : ""}"><span>${day}</span>${startingTrips.map((trip) => `<a href="./trip.html?id=${encodeURIComponent(trip.id)}">${escapeHtml(trip.title)}</a>`).join("")}</div>`);
  }
  const tripLink = (trip) => `<a class="trip-line" href="./trip.html?id=${encodeURIComponent(trip.id)}"><strong>${escapeHtml(trip.title)}</strong><span>${escapeHtml(formatShortDateRange(trip.dateRange))}</span></a>`;
  return `
    <header class="home-header"><h1>カレンダー</h1><time datetime="${formatIsoLocalDate()}">${formatCurrentDate()}</time></header>
    <section class="calendar-panel" aria-labelledby="calendar-title">
      <div class="month-heading"><button type="button" aria-label="前月">‹</button><h2 id="calendar-title">${year}年${month + 1}月</h2><button type="button" aria-label="翌月">›</button></div>
      <div class="calendar-weekdays">${["日", "月", "火", "水", "木", "金", "土"].map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="month-grid">${cells.join("")}</div>
    </section>
    <div class="home-columns">
      <section><h2>今後1週間の予定</h2><p class="empty-line">予定はありません</p></section>
      <section><h2>旅行予定</h2>${upcoming.map(tripLink).join("") || `<p class="empty-line">予定はありません</p>`}<button class="past-trips" type="button" aria-expanded="false" ${past.length ? "" : "disabled"}>過去の旅行</button><div class="past-trip-list" hidden>${past.map(tripLink).join("")}</div></section>
    </div>`;
}

function setupHomeInteractions(app) {
  app.addEventListener("click", (event) => {
    const button = event.target.closest(".past-trips");
    if (!button || button.disabled) return;
    const list = app.querySelector(".past-trip-list");
    list.hidden = !list.hidden;
    button.setAttribute("aria-expanded", String(!list.hidden));
  });
}

const legacyCategory = (value) => {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("食") || text.includes("meal") || text.includes("restaurant")) return "food";
  if (text.includes("宿") || text.includes("hotel") || text.includes("accommodation")) return "accommodation";
  if (text.includes("移") || text.includes("transport")) return "transport";
  return "sightseeing";
};

function legacyTime(value) {
  const clocks = String(value ?? "").match(/\d{1,2}:\d{2}/g) ?? [];
  if (!clocks.length) return { mode: "undecided" };
  return { mode: clocks.length > 1 ? "range" : "fixed", start: clocks[0], ...(clocks[1] ? { end: clocks[1] } : {}) };
}

function normalizeTrip(source) {
  if (source?.id && source?.dateRange && Array.isArray(source.days)) return source;
  const metadata = source?.trip;
  if (!metadata?.id) throw new Error("旅行JSONにtrip.idがありません。");
  const mapPoints = Array.isArray(source.mapPoints) ? source.mapPoints : [];
  const places = mapPoints.map((point) => ({
    id: point.id,
    name: point.name,
    summary: point.candidate ? "候補" : "",
    category: legacyCategory(point.category) === "food" ? "restaurant" : legacyCategory(point.category) === "accommodation" ? "hotel" : "attraction",
    location: Number.isFinite(point.latitude) && Number.isFinite(point.longitude) ? { latitude: point.latitude, longitude: point.longitude } : null,
    rating: null,
  }));
  const placeIds = new Set(places.map((place) => place.id));
  const itinerary = Array.isArray(source.itinerary) ? source.itinerary : [];
  itinerary.forEach((item) => {
    const id = item.mapPointId || `${item.id}-place`;
    if (!placeIds.has(id)) {
      places.push({ id, name: item.title || "場所未定", summary: item.summary || "", category: "attraction", location: null, rating: null });
      placeIds.add(id);
    }
  });
  const days = (Array.isArray(source.days) ? source.days : []).map((day, dayIndex) => {
    const dayItems = itinerary.filter((item) => item.date === day.date);
    return {
      id: `day-${day.date}`,
      date: day.date,
      title: day.label || `第${day.dayNumber || dayIndex + 1}日`,
      routeSummary: day.overview || (Array.isArray(day.areas) ? day.areas.join(" → ") : ""),
      scheduleItems: dayItems.map((item, index) => {
        const placeId = item.mapPointId || `${item.id}-place`;
        return {
          id: item.id,
          dayId: `day-${day.date}`,
          order: Number(item.displayOrder) || (index + 1) * 10,
          action: item.title || "予定",
          summary: item.summary || (Array.isArray(item.details) ? item.details[0] : ""),
          details: Array.isArray(item.details) ? item.details : [],
          category: legacyCategory(item.category || item.type),
          time: legacyTime(item.time),
          placeSelection: { candidatePlaceIds: [placeId], selection: item.selectionStatus === "未定" || item.status === "候補" ? [] : [placeId], minSelections: 1, maxSelections: 1 },
        };
      }),
      transportIds: [],
    };
  });
  const preparation = (Array.isArray(source.preparation) ? source.preparation : []).map((item, index) => ({
    id: item.id,
    label: item.label,
    dueDate: item.dueDate || metadata.startDate,
    completed: Boolean(item.defaultCompleted),
    order: index + 1,
  }));
  const rioSource = source.rioPlan && typeof source.rioPlan === "object" ? source.rioPlan : {};
  const rioItems = Array.isArray(rioSource.items) ? rioSource.items : [];
  const rioPacking = rioItems.map((item, index) => typeof item === "string"
    ? { id: `rio-${index + 1}`, label: item, completed: false, notNeeded: false, order: index + 1 }
    : { id: item.id || `rio-${index + 1}`, label: item.label || item.name || "持参品", completed: Boolean(item.completed), notNeeded: Boolean(item.notNeeded), order: index + 1 });
  const bookingCategory = (value) => String(value ?? "").includes("宿") ? "accommodation" : String(value ?? "").includes("交通") ? "transport" : String(value ?? "").includes("観光") ? "activity" : "other";
  return {
    id: metadata.id,
    title: metadata.name,
    dateRange: { start: metadata.startDate, end: metadata.endDate },
    days,
    places,
    transports: [],
    preparation: { id: `${metadata.id}-preparation`, tasks: preparation },
    rioPlan: { id: `${metadata.id}-rio`, applicable: rioPacking.length > 0, careMode: rioSource.mode === "預ける" ? "leave" : "accompany", packingItems: rioPacking },
    bookings: (Array.isArray(source.bookings) ? source.bookings : []).map((booking) => ({
      id: booking.id,
      category: bookingCategory(booking.type),
      status: booking.status === "確定" ? "booked" : "pending",
      targetDate: booking.dueDate || metadata.startDate,
      amount: Number(booking.amount) || 0,
      currency: booking.currency || "JPY",
      notes: booking.note || "",
    })),
  };
}

const filterLabels = { all: "全て", transport: "移動", sightseeing: "観光", food: "食事", accommodation: "宿泊" };
const filterStateKeys = ["itineraryDay", "itineraryCategory", "mapDay", "mapCategory"];
const placeCategory = (place) => place?.category === "restaurant" ? "food" : place?.category === "hotel" ? "accommodation" : "sightseeing";
const entryCategory = (entry, placesById) => entry.kind === "transport" ? "transport" : (entry.category || placeCategory(placesById.get(entry.placeSelection.selection[0])));
const daySwitcher = (scope, active, days) => `<nav class="day-switcher ${scope === "map" ? "map-days" : ""}" aria-label="${scope === "map" ? "地図" : "旅程"}の日付">${[["all", "全日程"], ...days.map((day) => [day.id, formatDate(day.date)])].map(([key, label]) => `<button type="button" data-${scope}-day="${escapeHtml(key)}" class="${active === key ? "active" : ""}">${escapeHtml(label)}</button>`).join("")}</nav>`;
const categoryFilter = (scope, active) => `<nav class="category-filter" aria-label="分類">${Object.entries(filterLabels).map(([key, label]) => `<button type="button" data-${scope}-category="${key}" class="${active === key ? "active" : ""}">${label}</button>`).join("")}</nav>`;
const formatDateWithWeekday = (value) => `${formatDate(value)}（${weekdayFormatter.format(localDate(value))}）`;

function timeBlock(time) {
  if (time.end) return `<time>${formatClock(time.start)}</time><span>⋮</span><time>${formatClock(time.end)}</time>`;
  return `<time>${time.mode === "undecided" ? "未定" : formatClock(time.start)}</time>${time.durationMinutes ? `<small>${time.durationMinutes}分</small>` : ""}`;
}

function itineraryEntry(entry, placesById) {
  if (entry.kind === "transport") {
    const from = placesById.get(entry.fromPlaceId);
    const to = placesById.get(entry.toPlaceId);
    const transportName = `${from.name} → ${to.name}`;
    return `<article class="itinerary-row transport-row">
      <div class="entry-time">${timeBlock(entry.time)}</div>
      <div class="entry-classification"><span aria-hidden="true">↗</span><small>${escapeHtml(transportLabels[entry.mode] ?? entry.mode)}</small></div>
      <div class="row-main"><strong>${escapeHtml(transportName)}</strong><p>${entry.time.durationMinutes}分</p></div>
    </article>`;
  }

  const selection = entry.placeSelection;
  const adopted = new Set(selection.selection);
  const selected = draftState.placeSelections.get(entry.id) ?? adopted;
  const candidates = selection.candidatePlaceIds.map((id) => placesById.get(id));
  const category = entryCategory(entry, placesById);
  const confirmedPlace = candidates.length === 1 && selected.has(candidates[0].id) ? candidates[0] : null;
  const title = confirmedPlace ? `${confirmedPlace.name}で${entry.action.replace(/^(港で)?/, "")}` : entry.action;
  return `<article class="itinerary-row schedule-row">
    <div class="entry-time">${timeBlock(entry.time)}</div>
    <div class="entry-classification"><span aria-hidden="true">${category === "food" ? "●" : category === "accommodation" ? "◆" : "▲"}</span><small>${filterLabels[category]}</small></div>
    <div class="row-main"><strong>${escapeHtml(title)}</strong>${entry.summary ? `<p>${escapeHtml(entry.summary)}</p>` : ""}${confirmedPlace ? "" : `<div class="candidate-inline">${candidates.map((place) => {
        const checked = selected.has(place.id);
        const atMaximum = selection.maxSelections !== null && selected.size >= selection.maxSelections;
        return `<label class="candidate-chip ${checked ? "selected" : ""}"><input type="checkbox" data-place-selection="${escapeHtml(entry.id)}" data-place-id="${escapeHtml(place.id)}" ${checked ? "checked" : ""} ${!checked && atMaximum ? "disabled" : ""}><span class="candidate-check" aria-hidden="true">${checked ? "✓" : ""}</span><span class="candidate-copy"><strong>${escapeHtml(place.name)}</strong>${place.summary ? `<small>${escapeHtml(place.summary)}</small>` : ""}</span>${placeRating(place)}</label>`;
      }).join("")}</div>`}${entry.details?.length ? `<p class="entry-detail">${escapeHtml(entry.details[0])}</p>` : ""}</div>
  </article>`;
}

function renderItinerary(trip, placesById) {
  return `<div class="tab-panel" id="panel-itinerary" role="tabpanel" aria-labelledby="tab-itinerary">
    <div class="top-controls">${daySwitcher("itinerary", draftState.itineraryDay, trip.days)}${categoryFilter("itinerary", draftState.itineraryCategory)}</div>
    <div class="all-days">${trip.days.map((day, dayIndex) => {
      if (draftState.itineraryDay !== "all" && draftState.itineraryDay !== day.id) return "";
      const transports = trip.transports.filter((item) => day.transportIds.includes(item.id));
      const entries = [...day.scheduleItems.map((item) => ({ ...item, kind: "schedule" })), ...transports.map((item) => ({ ...item, kind: "transport" }))].sort((a, b) => a.order - b.order);
      const visibleEntries = entries.filter((entry) => draftState.itineraryCategory === "all" || entryCategory(entry, placesById) === draftState.itineraryCategory);
      const collapsed = draftState.collapsedDays.has(day.id);
      return `<section class="day-section" id="${escapeHtml(day.id)}" style="--day-color: var(--day-${dayIndex % 5 + 1})">
        <div class="day-heading"><button type="button" class="day-toggle" data-toggle-day="${escapeHtml(day.id)}" aria-expanded="${!collapsed}"><span class="day-label"><strong class="day-number">第${dayIndex + 1}日</strong> <span class="day-date">${escapeHtml(formatDate(day.date))}（${weekdayFormatter.format(localDate(day.date))}）</span></span><span class="day-copy"><strong>${escapeHtml(day.title)}</strong><small>${escapeHtml(day.routeSummary || "")}</small></span><b aria-hidden="true">${collapsed ? "⌄" : "⌃"}</b></button></div>
        <div class="itinerary-list" ${collapsed ? "hidden" : ""}>${visibleEntries.map((entry) => itineraryEntry(entry, placesById)).join("")}</div>
      </section>`;
    }).join("")}</div>
  </div>`;
}

function renderMap(trip) {
  const placesById = new Map(trip.places.map((place) => [place.id, place]));
  const dayEntries = trip.days.flatMap((day, dayIndex) => [...day.scheduleItems.flatMap((item) => item.placeSelection.candidatePlaceIds.map((placeId) => ({ placeId, day, dayIndex, time: item.time, category: item.category || placeCategory(placesById.get(placeId)) }))), ...trip.transports.filter((item) => day.transportIds.includes(item.id)).flatMap((item) => [item.fromPlaceId, item.toPlaceId].map((placeId) => ({ placeId, day, dayIndex, time: item.time, category: "transport" }))) ]);
  const seen = new Set();
  const entries = dayEntries.filter((entry) => {
    const key = `${entry.day.id}:${entry.placeId}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return (draftState.mapDay === "all" || entry.day.id === draftState.mapDay) && (draftState.mapCategory === "all" || entry.category === draftState.mapCategory);
  });
  const points = entries.map((entry) => ({ ...placesById.get(entry.placeId), map: entry })).filter((place) => place.location);
  const latitudes = points.map((place) => place.location.latitude);
  const longitudes = points.map((place) => place.location.longitude);
  const minLat = Math.min(...latitudes), maxLat = Math.max(...latitudes);
  const minLng = Math.min(...longitudes), maxLng = Math.max(...longitudes);
  const mapped = points.map((place, index) => {
    const x = 8 + ((place.location.longitude - minLng) / (maxLng - minLng || 1)) * 84;
    const y = 90 - ((place.location.latitude - minLat) / (maxLat - minLat || 1)) * 78;
    const dayPoints = points.slice(0, index + 1).filter((candidate) => candidate.map.day.id === place.map.day.id);
    return `<button class="map-pin ${place.category}" style="left:${x}%;top:${y}%;--pin-color:var(--day-${place.map.dayIndex % 5 + 1})" aria-label="${escapeHtml(place.name)}" data-place-index="${index}"><span>${dayPoints.length}</span></button>`;
  }).join("");
  return `<div class="tab-panel" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden>
    <div class="top-controls">${daySwitcher("map", draftState.mapDay, trip.days)}${categoryFilter("map", draftState.mapCategory)}</div>
    <div class="map-layout">
      <div class="map-card">
        <div class="map-watermark">SETONAIKAI</div>
        <svg class="map-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M8 75 C30 35 50 52 66 20 S88 16 93 10"/></svg>
        ${mapped}
        <div class="map-note">外部地図APIを使わない位置確認図</div>
      </div>
      <div class="map-place-list">${trip.days.map((day, dayIndex) => { const dayPoints = points.filter((place) => place.map.day.id === day.id); if (!dayPoints.length) return ""; const collapsed = draftState.collapsedMapDays.has(day.id); return `<section style="--day-color:var(--day-${dayIndex % 5 + 1})"><button type="button" class="map-day-heading" data-toggle-map-day="${escapeHtml(day.id)}" aria-expanded="${!collapsed}"><span class="day-label"><strong class="day-number">第${dayIndex + 1}日</strong> <span class="day-date">${formatDate(day.date)}（${weekdayFormatter.format(localDate(day.date))}）</span></span><span class="day-copy"><strong>${escapeHtml(day.title)}</strong><small>${escapeHtml(day.routeSummary || "")}</small></span><b aria-hidden="true">${collapsed ? "⌄" : "⌃"}</b></button><ol class="place-index" ${collapsed ? "hidden" : ""}>${dayPoints.map((place, index) => `<li><span>${index + 1}</span><time>${escapeHtml(formatClock(place.map.time.start) || "未定")}</time><i>●</i><strong>${escapeHtml(place.name)}</strong><small>${filterLabels[place.map.category]}</small></li>`).join("")}</ol></section>`; }).join("")}</div>
    </div>
  </div>`;
}

const preparationChecklist = (items) => `<ul class="check-list task-list">${items.map((item) => {
  const completed = draftState.preparation.get(item.id) ?? item.completed;
  return `<li class="${completed ? "completed" : "pending"}"><label><input type="checkbox" data-preparation-id="${escapeHtml(item.id)}" ${completed ? "checked" : ""}><span class="check-icon" aria-hidden="true">${completed ? "✓" : ""}</span><time>${escapeHtml(formatDateWithWeekday(item.dueDate))}</time><span class="task-copy"><strong>${escapeHtml(item.label)}</strong></span></label></li>`;
}).join("")}</ul>`;

const rioChecklist = (items) => `<ul class="check-list rio-list">${items.map((item) => {
  const value = draftState.rioPacking.get(item.id) ?? (item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending");
  return `<li class="${value === "completed" ? "completed" : "pending"} ${value === "notNeeded" ? "not-needed" : ""}"><label><input type="checkbox" data-rio-packing-id="${escapeHtml(item.id)}" ${value === "completed" ? "checked" : ""}><span class="check-icon" aria-hidden="true">${value === "completed" ? "✓" : ""}</span><span>${escapeHtml(item.label)}${value === "notNeeded" ? "（持参しない）" : ""}</span></label></li>`;
}).join("")}</ul>`;

function renderPreparation(trip, placesById) {
  const transportsById = new Map(trip.transports.map((transport) => [transport.id, transport]));
  const rioItems = [...trip.rioPlan.packingItems].sort((a, b) => a.order - b.order);
  return `<div class="tab-panel" id="panel-preparation" role="tabpanel" aria-labelledby="tab-preparation" hidden>
    <div class="preparation-grid">
      <section class="prep-card wife-card">
        <div class="card-heading"><h3>準備すること</h3></div>
        ${preparationChecklist([...trip.preparation.tasks].sort((a, b) => a.order - b.order))}
      </section>
      ${trip.rioPlan.applicable === false ? "" : `<section class="prep-card rio-card">
        <div class="card-heading"><h3>リオ　${trip.rioPlan.careMode === "leave" ? "預ける" : "同行"}</h3></div>
        ${rioChecklist(rioItems)}
      </section>`}
      <section class="prep-card booking-card">
        <div class="card-heading"><h3>予約・手配</h3></div>
        <div class="booking-table" role="table" aria-label="予約一覧">${trip.bookings.map((booking) => {
          const target = placesById.get(booking.placeId);
          const transport = transportsById.get(booking.transportId);
          const transportName = transport ? `${transportLabels[transport.mode] ?? transport.mode} ${placesById.get(transport.fromPlaceId).name} → ${placesById.get(transport.toPlaceId).name}` : null;
          const bookingName = target?.name ?? transportName ?? "予約";
          const reserved = booking.status === "booked";
          const importantNote = reserved ? "" : booking.notes;
          return `<div class="booking-row" role="row"><span class="booking-check" aria-label="${reserved ? "予約済み" : "未予約"}">${reserved ? "✓" : ""}</span><time>${escapeHtml(formatDateWithWeekday(booking.targetDate))}</time><span class="booking-category">${categoryLabels[booking.category]}</span><div class="booking-content" role="cell"><strong>${escapeHtml(bookingName)}</strong>${importantNote ? `<small class="official-note">${escapeHtml(importantNote)}</small>` : ""}</div><b class="booking-amount">${moneyFormatter.format(booking.amount)}</b></div>`;
        }).join("")}</div>
      </section>
    </div>
  </div>`;
}

function draftCount() {
  const notes = [...draftState.instructions.values()].filter((value) => value.trim()).length;
  return draftState.preparation.size + draftState.rioPacking.size + draftState.placeSelections.size + notes;
}

function commentCount() {
  return [...draftState.instructions.values()].filter((value) => value.trim()).length;
}

function instructionTargetLabel(trip, key, placesById) {
  const [type, id] = key.split(":");
  if (type === "trip") return "旅行全体";
  if (type === "day") {
    const day = trip.days.find((item) => item.id === id);
    return day ? `日程：${formatDate(day.date)} ${day.title}` : "日程";
  }
  if (type === "scheduleItem") {
    const item = trip.days.flatMap((day) => day.scheduleItems).find((candidate) => candidate.id === id);
    return item ? `旅程 › ${item.action}` : "旅程";
  }
  if (type === "transport") {
    const transport = trip.transports.find((item) => item.id === id);
    if (transport) return `旅程 › ${placesById.get(transport.fromPlaceId)?.name ?? "出発地"} → ${placesById.get(transport.toPlaceId)?.name ?? "到着地"}`;
    return "旅程 › 移動";
  }
  if (type === "booking") {
    const booking = trip.bookings.find((item) => item.id === id);
    const transport = trip.transports.find((item) => item.id === booking?.transportId);
    const transportName = transport ? `${placesById.get(transport.fromPlaceId)?.name ?? "出発地"} → ${placesById.get(transport.toPlaceId)?.name ?? "到着地"}` : null;
    return `準備 › ${placesById.get(booking?.placeId)?.name ?? transportName ?? "予約項目"}`;
  }
  if (type === "preparation") {
    const task = trip.preparation.tasks.find((item) => item.id === id);
    return task ? `準備 › ${task.label}` : "準備";
  }
  if (type === "rioPlan") {
    const item = trip.rioPlan.packingItems.find((candidate) => candidate.id === id);
    return item ? `準備 › リオ › ${item.label}` : "準備 › リオ";
  }
  return "関連項目";
}

const updateTargetTypes = {
  trip: "Trip",
  day: "Day",
  scheduleItem: "ScheduleItem",
  transport: "Transport",
  preparation: "Preparation",
  rioPlan: "RioPlan",
  booking: "Booking",
};

function updateMaterials(trip, placesById) {
  const materials = [];
  const preparationItems = trip.preparation.tasks;

  draftState.preparation.forEach((completed, id) => {
    const item = preparationItems.find((candidate) => candidate.id === id);
    materials.push({
      type: "Preparation item",
      id,
      name: item?.label ?? "準備項目",
      change: `完了状態を「${completed ? "完了" : "未完了"}」に変更する`,
    });
  });

  draftState.rioPacking.forEach((value, id) => {
    const item = trip.rioPlan.packingItems.find((candidate) => candidate.id === id);
    const stateLabels = { pending: "未完了", completed: "完了", notNeeded: "不要" };
    materials.push({
      type: "RioPlan packing item",
      id,
      name: item?.label ?? "Rio持参品",
      change: `持参品の状態を「${stateLabels[value]}」に変更する`,
    });
  });

  draftState.placeSelections.forEach((selected, id) => {
    const item = trip.days.flatMap((day) => day.scheduleItems).find((candidate) => candidate.id === id);
    const placeNames = [...selected].map((placeId) => placesById.get(placeId)?.name ?? placeId);
    materials.push({
      type: "PlaceSelection",
      id,
      name: item?.action ?? "場所候補のある予定",
      change: placeNames.length ? `場所候補として「${placeNames.join("、")}」を選ぶ` : "場所候補を選択なしにする",
    });
  });

  draftState.instructions.forEach((value, key) => {
    if (!value.trim()) return;
    const [type, id] = key.split(":");
    materials.push({
      type: updateTargetTypes[type] ?? type,
      id,
      name: instructionTargetLabel(trip, key, placesById),
      change: `AIへの指示：${value.trim()}`,
    });
  });

  return materials;
}

function updateMaterialText(trip, materials) {
  const lines = [
    "Calendar AI更新材料",
    `対象旅行: ${trip.title}`,
    `Trip ID: ${trip.id}`,
    `変更件数: ${materials.length}件`,
    "",
    "以下は、採用済み完全JSONから次版の完全JSONを再生成するための更新材料です。差分パッチや次版JSONではありません。",
    "",
  ];
  materials.forEach((material, index) => {
    lines.push(`${index + 1}. ${material.name}`);
    lines.push(`   対象種別: ${material.type}`);
    lines.push(`   安定ID: ${material.id}`);
    lines.push(`   変更内容: ${material.change}`);
    lines.push("");
  });
  return lines.join("\n").trimEnd();
}

function renderNotes(trip, placesById) {
  const commentTargets = [
    { type: "trip", id: trip.id },
    ...trip.days.flatMap((day) => [
      ...day.scheduleItems.map((item) => ({ type: "scheduleItem", id: item.id })),
      ...trip.transports.filter((item) => day.transportIds.includes(item.id)).map((item) => ({ type: "transport", id: item.id })),
    ]),
    ...trip.preparation.tasks.map((item) => ({ type: "preparation", id: item.id })),
    ...trip.rioPlan.packingItems.map((item) => ({ type: "rioPlan", id: item.id })),
    ...trip.bookings.map((item) => ({ type: "booking", id: item.id })),
  ];
  const comments = [...draftState.instructions.entries()].filter(([, value]) => value.trim()).map(([key, value]) => {
    const editing = draftState.editingCommentKey === key;
    const body = editing
      ? `<textarea data-instruction-key="${escapeHtml(key)}" aria-label="コメントを編集" autofocus>${escapeHtml(value)}</textarea>`
      : `<button type="button" class="comment-text" data-edit-comment="${escapeHtml(key)}">${escapeHtml(value)}</button>`;
    return `<article><span>${escapeHtml(instructionTargetLabel(trip, key, placesById))}</span><div class="comment-body">${body}<button type="button" class="cancel-comment" data-cancel-comment="${escapeHtml(key)}">取消</button></div></article>`;
  }).join("");
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="comments-workspace">
      <div class="comments-heading"><h2>コメント</h2><div class="comment-actions"><label><span class="visually-hidden">コメント対象</span><select data-comment-target>${commentTargets.map((target) => { const key = targetKey(target.type, target.id); return `<option value="${escapeHtml(key)}">${escapeHtml(instructionTargetLabel(trip, key, placesById))}</option>`; }).join("")}</select></label><button type="button" data-open-comment-target>コメントを追加</button><button type="button" data-copy-update ${draftCount() ? "" : "disabled"}>AI更新材料をコピー</button></div></div>
      <p class="copy-status" data-copy-status role="status"></p>
      <div class="comment-list">${comments || `<p class="empty-line">未処理のコメントはありません</p>`}</div>
      <div class="trip-comment"><label><span>旅行全体へのコメントを追加</span><textarea data-new-trip-comment placeholder="コメントを入力">${escapeHtml(draftState.pendingTripComment)}</textarea></label><button type="button" data-add-trip-comment ${draftState.pendingTripComment.trim() ? "" : "disabled"}>追加</button></div>
    </section>
  </div>`;
}

function renderAiPanel(trip) {
  if (!draftState.aiPanelOpen) return "";
  const target = draftState.aiTarget ?? { type: "trip", id: trip.id, name: trip.title };
  const key = targetKey(target.type, target.id);
  const value = draftState.instructions.get(key) ?? "";
  return `<section class="ai-panel" role="dialog" aria-modal="false" aria-labelledby="ai-panel-title">
    <div class="ai-panel-heading"><div><span>${escapeHtml(target.name)}</span><h3 id="ai-panel-title">コメント</h3></div><button type="button" data-close-ai aria-label="コメント入力を閉じる">×</button></div>
    <label class="ai-panel-input"><span class="visually-hidden">コメント</span><textarea rows="3" data-instruction-key="${escapeHtml(key)}" placeholder="コメントを入力">${escapeHtml(value)}</textarea></label>
  </section>`;
}

function renderTrip(trip) {
  document.title = `${trip.title} | Calendar`;
  const placesById = new Map(trip.places.map((place) => [place.id, place]));
  return `<section class="trip-summary"><h1>${escapeHtml(trip.title)}<span>（${escapeHtml(formatDateRange(trip.dateRange))}）</span></h1></section>
    <nav class="tabs bottom-nav" aria-label="旅行詳細">
      <a class="tab" href="./index.html">カレンダー</a>
      <button id="tab-itinerary" class="tab active" role="tab" aria-selected="true" aria-controls="panel-itinerary" data-tab="itinerary">旅程</button>
      <button id="tab-map" class="tab" role="tab" aria-selected="false" aria-controls="panel-map" data-tab="map">地図</button>
      <button id="tab-preparation" class="tab" role="tab" aria-selected="false" aria-controls="panel-preparation" data-tab="preparation">準備</button>
      <button id="tab-notes" class="tab" role="tab" aria-selected="false" aria-controls="panel-notes" data-tab="notes">コメント${commentCount() ? ` <span class="draft-count" data-comment-count>${commentCount()}</span>` : ""}</button>
    </nav>
    ${renderItinerary(trip, placesById)}
    ${renderMap(trip)}
    ${renderPreparation(trip, placesById)}
    ${renderNotes(trip, placesById)}
    ${renderAiPanel(trip)}`;
}

function activateTab(name, updateHistory = true) {
  const tabs = [...document.querySelectorAll("[data-tab]")];
  tabs.forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    document.querySelector(`#panel-${tab.dataset.tab}`).hidden = !active;
  });
  if (updateHistory) history.replaceState(null, "", `#${name}`);
}

function selectedSetsEqual(left, right) {
  return left.size === right.size && [...left].every((value) => right.has(value));
}

function updateFilterState(target) {
  const selector = filterStateKeys.map((key) => `[data-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}]`).join(", ");
  const control = target.closest(selector);
  if (!control) return false;
  const stateKey = filterStateKeys.find((key) => control.dataset[key] !== undefined);
  draftState[stateKey] = control.dataset[stateKey];
  if (stateKey === "itineraryDay" && draftState.itineraryDay !== "all") draftState.collapsedDays.delete(draftState.itineraryDay);
  return true;
}

function setupTripInteractions(app, trip) {
  const rerender = () => {
    const activeTab = location.hash.slice(1) || "itinerary";
    app.innerHTML = renderTrip(trip);
    activateTab(activeTab, false);
  };

  app.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      history.replaceState(null, "", `#${tab.dataset.tab}`);
      if (tab.dataset.tab === "notes") rerender();
      else activateTab(tab.dataset.tab, false);
    }
    if (updateFilterState(event.target)) {
      rerender();
      return;
    }
    const dayToggle = event.target.closest("[data-toggle-day]");
    if (dayToggle) {
      const id = dayToggle.dataset.toggleDay;
      if (draftState.collapsedDays.has(id)) draftState.collapsedDays.delete(id);
      else draftState.collapsedDays.add(id);
      rerender();
    }
    const mapDayToggle = event.target.closest("[data-toggle-map-day]");
    if (mapDayToggle) {
      const id = mapDayToggle.dataset.toggleMapDay;
      if (draftState.collapsedMapDays.has(id)) draftState.collapsedMapDays.delete(id);
      else draftState.collapsedMapDays.add(id);
      rerender();
    }
    const cancelledComment = event.target.closest("[data-cancel-comment]");
    if (cancelledComment) {
      draftState.instructions.delete(cancelledComment.dataset.cancelComment);
      if (draftState.editingCommentKey === cancelledComment.dataset.cancelComment) draftState.editingCommentKey = null;
      rerender();
    }
    const editableComment = event.target.closest("[data-edit-comment]");
    if (editableComment) {
      draftState.editingCommentKey = editableComment.dataset.editComment;
      rerender();
      app.querySelector(`[data-instruction-key="${CSS.escape(draftState.editingCommentKey)}"]`)?.focus();
    }
    if (event.target.closest("[data-add-trip-comment]")) {
      const value = draftState.pendingTripComment.trim();
      if (value) draftState.instructions.set(targetKey("trip", trip.id), value);
      draftState.pendingTripComment = "";
      rerender();
    }
    const copyButton = event.target.closest("[data-copy-update]");
    if (copyButton && !copyButton.disabled) {
      const placesById = new Map(trip.places.map((place) => [place.id, place]));
      const materials = updateMaterials(trip, placesById);
      navigator.clipboard.writeText(updateMaterialText(trip, materials)).then(() => {
        const status = app.querySelector("[data-copy-status]");
        if (status) status.textContent = `${materials.length}件の変更内容をコピーしました。一時状態は保持されています。`;
      }).catch(() => {
        const status = app.querySelector("[data-copy-status]");
        if (status) status.textContent = "コピーできませんでした。ブラウザのクリップボード許可を確認してください。";
      });
    }
    if (event.target.closest("[data-open-comment-target]")) {
      const selected = app.querySelector("[data-comment-target]")?.value;
      if (selected) {
        const [type, id] = selected.split(":");
        const placesById = new Map(trip.places.map((place) => [place.id, place]));
        draftState.aiTarget = { type, id, name: instructionTargetLabel(trip, selected, placesById) };
        draftState.aiPanelOpen = true;
        rerender();
        app.querySelector("[data-instruction-key]")?.focus();
      }
    }
    if (event.target.closest("[data-close-ai]")) {
      draftState.aiPanelOpen = false;
      rerender();
    }
  });

  app.addEventListener("input", (event) => {
    if (event.target.dataset.newTripComment !== undefined) {
      draftState.pendingTripComment = event.target.value;
      const addButton = app.querySelector("[data-add-trip-comment]");
      if (addButton) addButton.disabled = !event.target.value.trim();
      return;
    }
    const key = event.target.dataset.instructionKey;
    if (!key) return;
    if (event.target.value.trim()) draftState.instructions.set(key, event.target.value);
    else draftState.instructions.delete(key);
    app.querySelectorAll("[data-comment-count]").forEach((item) => { item.textContent = commentCount(); });
    const copyButton = app.querySelector("[data-copy-update]");
    if (copyButton) copyButton.disabled = draftCount() === 0;
  });

  app.addEventListener("change", (event) => {
    if (event.target.dataset.instructionKey) return;
    const preparationId = event.target.dataset.preparationId;
    if (preparationId) {
      const item = trip.preparation.tasks.find((candidate) => candidate.id === preparationId);
      if (event.target.checked === item.completed) draftState.preparation.delete(preparationId);
      else draftState.preparation.set(preparationId, event.target.checked);
      rerender();
      return;
    }
    const rioId = event.target.dataset.rioPackingId;
    if (rioId) {
      const item = trip.rioPlan.packingItems.find((candidate) => candidate.id === rioId);
      const original = item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending";
      const next = event.target.checked ? "completed" : (item.notNeeded ? "notNeeded" : "pending");
      if (next === original) draftState.rioPacking.delete(rioId);
      else draftState.rioPacking.set(rioId, next);
      rerender();
      return;
    }
    const scheduleId = event.target.dataset.placeSelection;
    if (scheduleId) {
      const item = trip.days.flatMap((day) => day.scheduleItems).find((candidate) => candidate.id === scheduleId);
      const original = new Set(item.placeSelection.selection);
      const selected = new Set(draftState.placeSelections.get(scheduleId) ?? original);
      if (event.target.checked) selected.add(event.target.dataset.placeId);
      else selected.delete(event.target.dataset.placeId);
      if (selectedSetsEqual(selected, original)) draftState.placeSelections.delete(scheduleId);
      else draftState.placeSelections.set(scheduleId, selected);
      rerender();
    }
  });

  const requested = location.hash.slice(1);
  const available = [...document.querySelectorAll("[data-tab]")].some((tab) => tab.dataset.tab === requested);
  activateTab(available ? requested : "itinerary", false);
}

async function responseJson(response, context) {
  if (!response.ok) {
    let message = `${context}: HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.error) message = body.error;
    } catch (_) {
      // Public static hosts commonly return an HTML 404 for the local-only API.
    }
    throw new Error(message);
  }
  return response.json();
}

async function loadData(page) {
  const indexResponse = await fetch("/api/trips", { cache: "no-store" });
  if (indexResponse.status === 404) {
    const sampleResponse = await fetch(SAMPLE_URL, { cache: "no-store" });
    const sample = await responseJson(sampleResponse, "合成JSONを読み込めませんでした");
    return page === "trip" ? normalizeTrip(sample) : [tripSummary(sample)];
  }
  const trips = await responseJson(indexResponse, "旅行一覧を読み込めませんでした");
  if (!Array.isArray(trips) || trips.length === 0) throw new Error("採用済みの旅行がありません。Calendar_Localを確認してください。");
  if (page === "home") return trips;
  const tripId = new URLSearchParams(location.search).get("id");
  if (!tripId) throw new Error("URLにTrip IDがありません。");
  if (!trips.some((trip) => trip.id === tripId)) throw new Error(`旅行が見つかりません: ${tripId}`);
  const currentResponse = await fetch(`/api/trips/${encodeURIComponent(tripId)}/current`, { cache: "no-store" });
  return normalizeTrip(await responseJson(currentResponse, "旅行JSONを読み込めませんでした"));
}

function tripSummary(source) {
  const trip = normalizeTrip(source);
  return { id: trip.id, title: trip.title, dateRange: trip.dateRange };
}

async function start() {
  const app = document.querySelector("#app");
  try {
    const page = document.body.dataset.page;
    const data = await loadData(page);
    app.innerHTML = page === "trip" ? renderTrip(data) : renderHome(data);
    if (page === "trip") setupTripInteractions(app, data);
    else setupHomeInteractions(app);
  } catch (error) {
    app.innerHTML = `<section class="error-state"><h1>旅行情報を表示できませんでした</h1><p>${escapeHtml(error.message)}</p><p>ローカル利用時は <code>python3 scripts/serve_calendar.py</code> で起動してください。</p></section>`;
  }
}

start();
