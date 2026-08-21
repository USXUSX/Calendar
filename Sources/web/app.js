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
  itineraryCategory: "all",
  mapDay: "all",
  mapCategory: "all",
  pendingTripComment: "",
};

const targetKey = (type, id) => `${type}:${id}`;

function aiTargetButton(type, id, name, label = "AIへ変更を指示") {
  return `<button type="button" class="row-action" data-ai-target-type="${escapeHtml(type)}" data-ai-target-id="${escapeHtml(id)}" data-ai-target-name="${escapeHtml(name)}" aria-label="${escapeHtml(`${name}：${label}`)}">…</button>`;
}

const shortDateFormatter = new Intl.DateTimeFormat("ja-JP", { month: "numeric", day: "numeric" });
const weekdayFormatter = new Intl.DateTimeFormat("ja-JP", { weekday: "short" });
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

const formatClock = (value) => value ? value.replace(/^0/, "") : "";

const modeLabels = {
  fixed: "時刻確定",
  range: "時間帯",
  undecided: "時間未定",
};

const transportLabels = {
  ferry: "フェリー",
  walk: "徒歩",
  train: "鉄道",
  bus: "バス",
};

const categoryLabels = {
  accommodation: "宿泊費",
  transport: "交通費",
  activity: "観光・チケット",
  other: "その他",
};

function formatTime(time) {
  if (time.mode === "undecided") return "未定";
  if (time.end) return `${formatClock(time.start)}〜${formatClock(time.end)}`;
  return formatClock(time.start);
}

function selectionLabel(selection) {
  const { minSelections: min, maxSelections: max } = selection;
  if (min === null && max === null) return "選択数は未定";
  if (min === max) return `${min}箇所を予定`;
  if (max === null) return `${min}箇所以上を予定`;
  return `${min}〜${max}箇所を予定`;
}

function placeRating(place) {
  if (!place.rating) return "";
  return `<span class="rating">${escapeHtml(place.rating.source)} ${place.rating.value.toFixed(2)}</span>`;
}

function renderHome(trip) {
  document.title = "Calendar | 旅の一覧";
  const start = localDate(trip.dateRange.start);
  const year = start.getFullYear();
  const month = start.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let index = 0; index < firstDay.getDay(); index += 1) cells.push(`<div class="calendar-cell muted" aria-hidden="true"></div>`);
  for (let day = 1; day <= lastDay; day += 1) {
    const date = new Date(year, month, day);
    const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const inTrip = iso >= trip.dateRange.start && iso <= trip.dateRange.end;
    const startsTrip = iso === trip.dateRange.start;
    cells.push(`<div class="calendar-cell ${inTrip ? "trip-span" : ""}"><span>${day}</span>${startsTrip ? `<a href="./trip.html?id=${encodeURIComponent(trip.id)}">${escapeHtml(trip.title)}</a>` : ""}</div>`);
  }
  return `
    <header class="home-header"><h1>カレンダー</h1><time>2026/8/21（金）</time></header>
    <section class="calendar-panel" aria-labelledby="calendar-title">
      <div class="month-heading"><button type="button" aria-label="前月">‹</button><h2 id="calendar-title">${year}年${month + 1}月</h2><button type="button" aria-label="翌月">›</button></div>
      <div class="calendar-weekdays">${["日", "月", "火", "水", "木", "金", "土"].map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="month-grid">${cells.join("")}</div>
    </section>
    <div class="home-columns">
      <section><h2>今後1週間の予定</h2><p class="empty-line">予定はありません</p></section>
      <section><h2>旅行予定</h2><a class="trip-line" href="./trip.html?id=${encodeURIComponent(trip.id)}"><strong>${escapeHtml(trip.title)}</strong><span>${escapeHtml(formatDateRange(trip.dateRange))}</span></a><button class="past-trips" type="button">過去の旅行</button></section>
    </div>`;
}

const filterLabels = { all: "全て", transport: "移動", sightseeing: "観光", food: "食事", accommodation: "宿泊" };
const placeCategory = (place) => place?.category === "restaurant" ? "food" : place?.category === "hotel" ? "accommodation" : "sightseeing";
const entryCategory = (entry, placesById) => entry.kind === "transport" ? "transport" : (entry.category || placeCategory(placesById.get(entry.placeSelection.selection[0])));
const categoryFilter = (scope, active) => `<nav class="category-filter" aria-label="分類">${Object.entries(filterLabels).map(([key, label]) => `<button type="button" data-${scope}-category="${key}" class="${active === key ? "active" : ""}">${label}</button>`).join("")}</nav>`;

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
      <div class="entry-classification"><span aria-hidden="true">↗</span><small>移動</small></div>
      <div class="row-main"><strong>${escapeHtml(transportName)}</strong><p>${escapeHtml(transportLabels[entry.mode] ?? entry.mode)}　${entry.time.durationMinutes}分</p></div>
      ${aiTargetButton("transport", entry.id, transportName)}
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
        return `<label class="candidate-chip ${checked ? "selected" : ""}"><input type="checkbox" data-place-selection="${escapeHtml(entry.id)}" data-place-id="${escapeHtml(place.id)}" ${checked ? "checked" : ""} ${!checked && atMaximum ? "disabled" : ""}><span>${escapeHtml(place.name)}</span>${placeRating(place)}</label>`;
      }).join("")}</div>`}${entry.details?.length ? `<p class="entry-detail">${escapeHtml(entry.details[0])}</p>` : ""}</div>
    ${aiTargetButton("scheduleItem", entry.id, entry.action)}
  </article>`;
}

function renderItinerary(trip, placesById) {
  return `<div class="tab-panel" id="panel-itinerary" role="tabpanel" aria-labelledby="tab-itinerary">
    <nav class="day-switcher" aria-label="日付へ移動"><button type="button" data-day-anchor="all">全日程</button>${trip.days.map((day) => `<button type="button" data-day-anchor="${escapeHtml(day.id)}">${escapeHtml(formatDate(day.date))}</button>`).join("")}</nav>
    ${categoryFilter("itinerary", draftState.itineraryCategory)}
    <div class="all-days">${trip.days.map((day, dayIndex) => {
      const transports = trip.transports.filter((item) => day.transportIds.includes(item.id));
      const entries = [...day.scheduleItems.map((item) => ({ ...item, kind: "schedule" })), ...transports.map((item) => ({ ...item, kind: "transport" }))].sort((a, b) => a.order - b.order);
      const visibleEntries = entries.filter((entry) => draftState.itineraryCategory === "all" || entryCategory(entry, placesById) === draftState.itineraryCategory);
      const collapsed = draftState.collapsedDays.has(day.id);
      return `<section class="day-section" id="${escapeHtml(day.id)}" style="--day-color: var(--day-${dayIndex % 5 + 1})">
        <div class="day-heading"><button type="button" class="day-toggle" data-toggle-day="${escapeHtml(day.id)}" aria-expanded="${!collapsed}"><span>第${dayIndex + 1}日 ${escapeHtml(formatDate(day.date))}（${weekdayFormatter.format(localDate(day.date))}）</span><span class="day-copy"><strong>${escapeHtml(day.title)}</strong><small>${escapeHtml(day.routeSummary || "")}</small></span><b aria-hidden="true">${collapsed ? "⌄" : "⌃"}</b></button>${aiTargetButton("day", day.id, `${formatDate(day.date)} ${day.title}`)}</div>
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
    <nav class="day-switcher map-days" aria-label="地図の日付">${[["all", "全日程"], ...trip.days.map((day) => [day.id, formatDate(day.date)])].map(([key, label]) => `<button type="button" data-map-day="${escapeHtml(key)}" class="${draftState.mapDay === key ? "active" : ""}">${escapeHtml(label)}</button>`).join("")}</nav>
    ${categoryFilter("map", draftState.mapCategory)}
    <div class="map-layout">
      <div class="map-card">
        <div class="map-watermark">SETONAIKAI</div>
        <svg class="map-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M8 75 C30 35 50 52 66 20 S88 16 93 10"/></svg>
        ${mapped}
        <div class="map-note">外部地図APIを使わない位置確認図</div>
      </div>
      <div class="map-place-list">${trip.days.map((day, dayIndex) => { const dayPoints = points.filter((place) => place.map.day.id === day.id); if (!dayPoints.length) return ""; return `<section style="--day-color:var(--day-${dayIndex % 5 + 1})"><div class="map-day-heading"><strong>第${dayIndex + 1}日 ${formatDate(day.date)}（${weekdayFormatter.format(localDate(day.date))}）</strong><span><b>${escapeHtml(day.title)}</b><small>${escapeHtml(day.routeSummary || "")}</small></span></div><ol class="place-index">${dayPoints.map((place, index) => `<li><span>${index + 1}</span><time>${escapeHtml(formatClock(place.map.time.start) || "未定")}</time><i>●</i><strong>${escapeHtml(place.name)}</strong><small>${filterLabels[place.map.category]}</small></li>`).join("")}</ol></section>`; }).join("")}</div>
    </div>
  </div>`;
}

const preparationChecklist = (items) => `<ul class="check-list task-list">${items.map((item) => {
  const completed = draftState.preparation.get(item.id) ?? item.completed;
  return `<li class="${completed ? "completed" : "pending"}"><label><input type="checkbox" data-preparation-id="${escapeHtml(item.id)}" ${completed ? "checked" : ""}><span class="check-icon" aria-hidden="true">${completed ? "✓" : "○"}</span><time>${escapeHtml(formatDate(item.dueDate))}</time><span class="task-copy"><strong>${escapeHtml(item.label)}</strong></span></label></li>`;
}).join("")}</ul>`;

const rioChecklist = (items) => `<ul class="check-list rio-list">${items.map((item) => {
  const value = draftState.rioPacking.get(item.id) ?? (item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending");
  return `<li class="${value === "completed" ? "completed" : "pending"} ${value === "notNeeded" ? "not-needed" : ""}"><label><input type="checkbox" data-rio-packing-id="${escapeHtml(item.id)}" ${value === "completed" ? "checked" : ""}><span class="check-icon" aria-hidden="true">${value === "completed" ? "✓" : "○"}</span><span>${escapeHtml(item.label)}${value === "notNeeded" ? "（持参しない）" : ""}</span></label></li>`;
}).join("")}</ul>`;

function renderPreparation(trip, placesById) {
  const transportsById = new Map(trip.transports.map((transport) => [transport.id, transport]));
  const rioItems = [...trip.rioPlan.packingItems].sort((a, b) => a.order - b.order);
  const total = trip.bookings.reduce((sum, booking) => sum + booking.amount, 0);
  const totals = Object.entries(categoryLabels).map(([category, label]) => {
    const value = trip.bookings.filter((booking) => booking.category === category).reduce((sum, booking) => sum + booking.amount, 0);
    return `<div><span>${label}</span><strong>${moneyFormatter.format(value)}</strong></div>`;
  }).join("");
  return `<div class="tab-panel" id="panel-preparation" role="tabpanel" aria-labelledby="tab-preparation" hidden>
    <div class="preparation-grid">
      <section class="prep-card wife-card">
        <div class="card-heading"><h3>準備すること</h3>${aiTargetButton("preparation", trip.preparation.id, "準備すること")}</div>
        ${preparationChecklist([...trip.preparation.tasks].sort((a, b) => a.order - b.order))}
      </section>
      ${trip.rioPlan.applicable === false ? "" : `<section class="prep-card rio-card">
        <div class="card-heading"><h3>リオ　${trip.rioPlan.careMode === "leave" ? "預ける" : "同行"}</h3>${aiTargetButton("rioPlan", trip.rioPlan.id, "リオ")}</div>
        ${rioChecklist(rioItems)}
      </section>`}
      <section class="prep-card booking-card">
        <div class="card-heading"><h3>予約・手配</h3></div>
        <div class="booking-table" role="table" aria-label="予約一覧">${trip.bookings.map((booking) => {
          const target = placesById.get(booking.placeId);
          const transport = transportsById.get(booking.transportId);
          const transportName = transport ? `${transportLabels[transport.mode] ?? transport.mode} ${placesById.get(transport.fromPlaceId).name} → ${placesById.get(transport.toPlaceId).name}` : null;
          const bookingName = target?.name ?? transportName ?? "予約";
          return `<div class="booking-row" role="row"><span class="booking-check" aria-label="${booking.reserved ? "予約済み" : "未予約"}">${booking.reserved ? "✓" : "○"}</span><time>${escapeHtml(formatDate(booking.targetDate))}</time><span>${categoryLabels[booking.category]}</span><div role="cell"><strong>${escapeHtml(bookingName)}</strong><small class="official-note">${escapeHtml(booking.notes)}</small></div><b>${moneyFormatter.format(booking.amount)}</b>${aiTargetButton("booking", booking.id, bookingName)}</div>`;
        }).join("")}</div>
        <div class="cost-summary"><div><span>費用合計</span><strong>${moneyFormatter.format(total)}</strong></div><div class="cost-breakdown">${totals}</div></div>
      </section>
    </div>
  </div>`;
}

function draftCount() {
  const notes = [...draftState.instructions.values()].filter((value) => value.trim()).length;
  return draftState.preparation.size + draftState.rioPacking.size + draftState.placeSelections.size + notes;
}

function instructionTargetLabel(trip, key, placesById) {
  const [type, id] = key.split(":");
  if (type === "trip") return `旅行全体：${trip.title}`;
  if (type === "day") {
    const day = trip.days.find((item) => item.id === id);
    return day ? `日程：${formatDate(day.date)} ${day.title}` : "日程";
  }
  if (type === "scheduleItem") {
    const item = trip.days.flatMap((day) => day.scheduleItems).find((candidate) => candidate.id === id);
    return item ? `予定：${item.action}` : "予定";
  }
  if (type === "transport") {
    const transport = trip.transports.find((item) => item.id === id);
    if (transport) return `移動：${placesById.get(transport.fromPlaceId)?.name ?? "出発地"} → ${placesById.get(transport.toPlaceId)?.name ?? "到着地"}`;
    return "移動";
  }
  if (type === "booking") {
    const booking = trip.bookings.find((item) => item.id === id);
    const transport = trip.transports.find((item) => item.id === booking?.transportId);
    const transportName = transport ? `${placesById.get(transport.fromPlaceId)?.name ?? "出発地"} → ${placesById.get(transport.toPlaceId)?.name ?? "到着地"}` : null;
    return `予約：${placesById.get(booking?.placeId)?.name ?? transportName ?? "予約項目"}`;
  }
  if (type === "preparation") {
    const task = trip.preparation.tasks.find((item) => item.id === id);
    return task ? `準備：${task.label}` : "妻の準備";
  }
  if (type === "rioPlan") {
    const item = trip.rioPlan.packingItems.find((candidate) => candidate.id === id);
    return item ? `Rio持参品：${item.label}` : "Rioの予定";
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
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="comments-workspace">
      <h2>コメント</h2>
      <p class="copy-status" data-copy-status role="status"></p>
      <div class="comment-list">${[...draftState.instructions.entries()].filter(([, value]) => value.trim()).map(([key, value]) => `<article><span>${escapeHtml(instructionTargetLabel(trip, key, placesById))}</span><div class="comment-body"><textarea data-instruction-key="${escapeHtml(key)}" aria-label="コメントを編集">${escapeHtml(value)}</textarea><button type="button" data-cancel-comment="${escapeHtml(key)}">取消</button></div></article>`).join("") || `<p class="empty-line">未処理のコメントはありません</p>`}</div>
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
  return `<section class="trip-summary"><h1>${escapeHtml(trip.title)}</h1><p>${escapeHtml(formatDateRange(trip.dateRange))}</p></section>
    <nav class="tabs bottom-nav" aria-label="旅行詳細">
      <a class="tab" href="./index.html">カレンダー</a>
      <button id="tab-itinerary" class="tab active" role="tab" aria-selected="true" aria-controls="panel-itinerary" data-tab="itinerary">旅程</button>
      <button id="tab-map" class="tab" role="tab" aria-selected="false" aria-controls="panel-map" data-tab="map">地図</button>
      <button id="tab-preparation" class="tab" role="tab" aria-selected="false" aria-controls="panel-preparation" data-tab="preparation">準備</button>
      <button id="tab-notes" class="tab" role="tab" aria-selected="false" aria-controls="panel-notes" data-tab="notes">コメント <span class="draft-count" data-draft-count>${draftCount()}</span></button>
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
    const dayAnchor = event.target.closest("[data-day-anchor]");
    if (dayAnchor) {
      const target = dayAnchor.dataset.dayAnchor === "all" ? app.querySelector(".all-days") : app.querySelector(`#${CSS.escape(dayAnchor.dataset.dayAnchor)}`);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    const dayToggle = event.target.closest("[data-toggle-day]");
    if (dayToggle) {
      const id = dayToggle.dataset.toggleDay;
      if (draftState.collapsedDays.has(id)) draftState.collapsedDays.delete(id);
      else draftState.collapsedDays.add(id);
      rerender();
    }
    const itineraryCategory = event.target.closest("[data-itinerary-category]");
    if (itineraryCategory) {
      draftState.itineraryCategory = itineraryCategory.dataset.itineraryCategory;
      rerender();
    }
    const mapDay = event.target.closest("[data-map-day]");
    if (mapDay) {
      draftState.mapDay = mapDay.dataset.mapDay;
      rerender();
    }
    const mapCategory = event.target.closest("[data-map-category]");
    if (mapCategory) {
      draftState.mapCategory = mapCategory.dataset.mapCategory;
      rerender();
    }
    const cancelledComment = event.target.closest("[data-cancel-comment]");
    if (cancelledComment) {
      draftState.instructions.delete(cancelledComment.dataset.cancelComment);
      rerender();
    }
    if (event.target.closest("[data-add-trip-comment]")) {
      const value = draftState.pendingTripComment.trim();
      if (value) draftState.instructions.set(targetKey("trip", trip.id), value);
      draftState.pendingTripComment = "";
      rerender();
    }
    if (event.target.closest("[data-reset-draft]")) {
      draftState.preparation.clear();
      draftState.rioPacking.clear();
      draftState.placeSelections.clear();
      draftState.instructions.clear();
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
    const aiTarget = event.target.closest("[data-ai-target-type]");
    if (aiTarget) {
      draftState.aiTarget = {
        type: aiTarget.dataset.aiTargetType,
        id: aiTarget.dataset.aiTargetId,
        name: aiTarget.dataset.aiTargetName,
      };
      draftState.aiPanelOpen = true;
      rerender();
      app.querySelector("[data-instruction-key]")?.focus();
    }
    if (event.target.closest("[data-open-ai-all]")) {
      draftState.aiTarget = null;
      draftState.aiPanelOpen = true;
      rerender();
      app.querySelector("[data-instruction-key]")?.focus();
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
    app.querySelectorAll("[data-draft-count]").forEach((item) => { item.textContent = draftCount(); });
    app.querySelectorAll("[data-reset-draft]").forEach((item) => { item.disabled = draftCount() === 0; });
    const updateCount = app.querySelector("[data-update-count]");
    const copyButton = app.querySelector("[data-copy-update]");
    if (updateCount) updateCount.textContent = updateMaterials(trip, new Map(trip.places.map((place) => [place.id, place]))).length;
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

async function start() {
  const app = document.querySelector("#app");
  try {
    const response = await fetch(SAMPLE_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const trip = await response.json();
    app.innerHTML = document.body.dataset.page === "trip" ? renderTrip(trip) : renderHome(trip);
    if (document.body.dataset.page === "trip") setupTripInteractions(app, trip);
  } catch (error) {
    app.innerHTML = `<section class="error-state"><h1>旅行情報を表示できませんでした</h1><p>${escapeHtml(error.message)}</p><p>リポジトリ直下をローカルHTTPサーバーで配信してください。</p></section>`;
  }
}

start();
