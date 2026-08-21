const SAMPLE_URL = "../../Samples/synthetic-trip.json";

// The adopted JSON remains read-only. Every interaction in this stage lives
// only in this in-memory object and is discarded when the page is closed.
const draftState = {
  preparation: new Map(),
  rioPacking: new Map(),
  placeSelections: new Map(),
  instructions: new Map(),
  openInstructionFields: new Set(),
};

const targetKey = (type, id) => `${type}:${id}`;

function instructionField(type, id, label, collapsible = false) {
  const key = targetKey(type, id);
  const value = draftState.instructions.get(key) ?? "";
  const expanded = !collapsible || draftState.openInstructionFields.has(key);
  if (collapsible) {
    return `<div class="instruction-control ${expanded ? "expanded" : ""}">
      <button type="button" class="instruction-toggle" data-instruction-toggle="${escapeHtml(key)}" aria-expanded="${expanded ? "true" : "false"}">${value.trim() ? "変更メモ（入力済み）" : expanded ? "変更メモを閉じる" : "変更メモ"}<small>一時・未送信</small></button>
      ${expanded ? `<label class="instruction-field"><span class="visually-hidden">AIへの指示メモ</span><textarea rows="2" data-instruction-key="${escapeHtml(key)}" placeholder="${escapeHtml(label)}">${escapeHtml(value)}</textarea></label>` : ""}
    </div>`;
  }
  return `<label class="instruction-field">
    <span>AIへの指示メモ <small>一時・未送信</small></span>
    <textarea rows="2" data-instruction-key="${escapeHtml(key)}" placeholder="${escapeHtml(label)}">${escapeHtml(value)}</textarea>
  </label>`;
}

const dateFormatter = new Intl.DateTimeFormat("ja-JP", {
  month: "long",
  day: "numeric",
  weekday: "short",
});
const fullDateFormatter = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "long",
  day: "numeric",
});
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

const formatDate = (value, full = false) => {
  const date = new Date(`${value}T00:00:00+09:00`);
  return (full ? fullDateFormatter : dateFormatter).format(date);
};

const formatDateRange = ({ start, end }) =>
  `${formatDate(start, true)} — ${formatDate(end)}`;

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
  if (time.mode === "undecided") return "時間未定";
  if (time.mode === "range") return `${time.start}〜${time.end}`;
  if (time.end) return `${time.start}〜${time.end}`;
  return time.start;
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
  return `
    <section class="home-hero">
      <p class="eyebrow">YOUR TRAVEL CALENDAR</p>
      <h1>次の旅を、ひと目で。</h1>
      <p>採用済みの旅行プランを、見やすく確認するための読み取り専用画面です。</p>
    </section>
    <section aria-labelledby="upcoming-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">UPCOMING</p>
          <h2 id="upcoming-title">これからの旅</h2>
        </div>
        <span class="count-badge">1 trip</span>
      </div>
      <article class="trip-card">
        <div class="trip-card-art" aria-hidden="true">
          <span class="sun"></span><span class="island island-one"></span><span class="island island-two"></span>
          <span class="art-caption">SETOUCHI<br>2027</span>
        </div>
        <div class="trip-card-body">
          <p class="trip-date">${escapeHtml(formatDateRange(trip.dateRange))}</p>
          <h3>${escapeHtml(trip.title)}</h3>
          <p>${escapeHtml(trip.summary)}</p>
          <div class="trip-meta">
            <span>${trip.days.length}日間</span>
            <span>${trip.places.length}スポット</span>
            <span>合成サンプル</span>
          </div>
          <a class="primary-link" href="./trip.html?id=${encodeURIComponent(trip.id)}">旅行詳細を見る <span aria-hidden="true">→</span></a>
        </div>
      </article>
    </section>`;
}

function itineraryEntry(entry, placesById) {
  if (entry.kind === "transport") {
    const from = placesById.get(entry.fromPlaceId);
    const to = placesById.get(entry.toPlaceId);
    return `<article class="timeline-entry transport-entry">
      <div class="time-column"><strong>${escapeHtml(formatTime(entry.time))}</strong><span>${entry.time.durationMinutes}分</span></div>
      <div class="timeline-dot" aria-hidden="true">↗</div>
      <div class="entry-card">
        <div class="entry-kicker">移動 · ${escapeHtml(transportLabels[entry.mode] ?? entry.mode)}</div>
        <h4>${escapeHtml(from.name)} → ${escapeHtml(to.name)}</h4>
        <p>${escapeHtml(from.address)} から ${escapeHtml(to.address)}</p>
        ${instructionField("transport", entry.id, "例：この移動を一本遅い便に変更して", true)}
      </div>
    </article>`;
  }

  const selection = entry.placeSelection;
  const adopted = new Set(selection.selection);
  const selected = draftState.placeSelections.get(entry.id) ?? adopted;
  const candidates = selection.candidatePlaceIds.map((id) => placesById.get(id));
  const belowMinimum = selection.minSelections !== null && selected.size < selection.minSelections;
  const limitText = selectionLabel(selection).replace("を予定", "を選択");
  return `<article class="timeline-entry schedule-entry">
    <div class="time-column"><strong>${escapeHtml(formatTime(entry.time))}</strong><span>${entry.time.durationMinutes}分</span></div>
    <div class="timeline-dot" aria-hidden="true">●</div>
    <div class="entry-card">
      <div class="entry-kicker">行動 · <span class="time-mode ${entry.time.mode}">${modeLabels[entry.time.mode]}</span></div>
      <h4>${escapeHtml(entry.action)}</h4>
      <div class="candidate-summary"><span>場所候補 ${candidates.length}件 · ${escapeHtml(limitText)}</span><strong class="selection-count ${belowMinimum ? "invalid" : ""}">${selected.size}件選択中</strong></div>
      <div class="candidate-list">${candidates.map((place) => {
        const checked = selected.has(place.id);
        const atMaximum = selection.maxSelections !== null && selected.size >= selection.maxSelections;
        return `<label class="candidate-row selectable ${checked ? "selected" : ""}"><input type="checkbox" data-place-selection="${escapeHtml(entry.id)}" data-place-id="${escapeHtml(place.id)}" ${checked ? "checked" : ""} ${!checked && atMaximum ? "disabled" : ""}><span class="choice-mark" aria-hidden="true">${checked ? "✓" : ""}</span><span class="candidate-copy"><strong>${escapeHtml(place.name)}</strong><span>${escapeHtml(place.address)}</span></span>${placeRating(place)}</label>`;
      }).join("")}</div>
      <p class="selection-guidance ${belowMinimum ? "error" : ""}">${belowMinimum ? `あと${selection.minSelections - selected.size}件選択してください` : selection.maxSelections !== null && selected.size >= selection.maxSelections ? "選択できる上限です" : "候補の選択はAIへの指示として一時保存されます"}</p>
      ${instructionField("scheduleItem", entry.id, "例：この予定を午後に移して", true)}
    </div>
  </article>`;
}

function renderItinerary(trip, placesById) {
  return `<div class="tab-panel" id="panel-itinerary" role="tabpanel" aria-labelledby="tab-itinerary">
    ${trip.days.map((day, index) => {
      const transports = trip.transports.filter((item) => day.transportIds.includes(item.id));
      const entries = [
        ...day.scheduleItems.map((item) => ({ ...item, kind: "schedule" })),
        ...transports.map((item) => ({ ...item, kind: "transport" })),
      ].sort((a, b) => a.order - b.order);
      return `<section class="day-section">
        <div class="day-heading"><span>DAY ${index + 1}</span><div><h3>${escapeHtml(formatDate(day.date))}</h3><p>${escapeHtml(day.title)}</p>${instructionField("day", day.id, "例：この日は移動を少なめにして", true)}</div></div>
        <div class="timeline">${entries.map((entry) => itineraryEntry(entry, placesById)).join("")}</div>
      </section>`;
    }).join("")}
  </div>`;
}

function renderMap(trip) {
  const points = trip.places.filter((place) => place.location);
  const latitudes = points.map((place) => place.location.latitude);
  const longitudes = points.map((place) => place.location.longitude);
  const minLat = Math.min(...latitudes), maxLat = Math.max(...latitudes);
  const minLng = Math.min(...longitudes), maxLng = Math.max(...longitudes);
  const mapped = points.map((place, index) => {
    const x = 8 + ((place.location.longitude - minLng) / (maxLng - minLng || 1)) * 84;
    const y = 90 - ((place.location.latitude - minLat) / (maxLat - minLat || 1)) * 78;
    return `<button class="map-pin ${place.category}" style="left:${x}%;top:${y}%" aria-label="${escapeHtml(place.name)}" data-place-index="${index}"><span>${index + 1}</span></button>`;
  }).join("");
  return `<div class="tab-panel" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden>
    <div class="map-layout">
      <div class="map-card">
        <div class="map-watermark">SETONAIKAI</div>
        <svg class="map-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M8 75 C30 35 50 52 66 20 S88 16 93 10"/></svg>
        ${mapped}
        <div class="map-note">外部地図APIを使わない位置確認図</div>
      </div>
      <ol class="place-index">${points.map((place, index) => `<li><span>${index + 1}</span><div><strong>${escapeHtml(place.name)}</strong><small>${escapeHtml(place.address)}</small></div>${placeRating(place)}</li>`).join("")}</ol>
    </div>
  </div>`;
}

const preparationChecklist = (items) => `<ul class="check-list">${items.map((item) => {
  const completed = draftState.preparation.get(item.id) ?? item.completed;
  const changed = draftState.preparation.has(item.id) && completed !== item.completed;
  return `<li class="${completed ? "completed" : ""} ${changed ? "draft-changed" : ""}"><label><input type="checkbox" data-preparation-id="${escapeHtml(item.id)}" ${completed ? "checked" : ""}><span class="check-icon" aria-hidden="true">${completed ? "✓" : "○"}</span><span>${escapeHtml(item.label)}</span>${changed ? "<em>変更予定</em>" : ""}</label></li>`;
}).join("")}</ul>`;

const rioChecklist = (items, extraClass = "") => `<ul class="check-list ${extraClass}">${items.map((item) => {
  const value = draftState.rioPacking.get(item.id) ?? (item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending");
  const original = item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending";
  return `<li class="${value === "completed" ? "completed" : ""} ${value === "notNeeded" ? "not-needed" : ""} ${value !== original ? "draft-changed" : ""}"><span>${escapeHtml(item.label)}</span><select data-rio-packing-id="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.label)}の一時状態"><option value="pending" ${value === "pending" ? "selected" : ""}>未完了</option><option value="completed" ${value === "completed" ? "selected" : ""}>完了</option><option value="notNeeded" ${value === "notNeeded" ? "selected" : ""}>不要</option></select>${value !== original ? "<em>変更予定</em>" : ""}</li>`;
}).join("")}</ul>`;

function renderPreparation(trip, placesById) {
  const transportsById = new Map(trip.transports.map((transport) => [transport.id, transport]));
  const requiredRio = trip.rioPlan.packingItems.filter((item) => !item.notNeeded).sort((a, b) => a.order - b.order);
  const unnecessaryRio = trip.rioPlan.packingItems.filter((item) => item.notNeeded).sort((a, b) => a.order - b.order);
  const total = trip.bookings.reduce((sum, booking) => sum + booking.amount, 0);
  const totals = Object.entries(categoryLabels).map(([category, label]) => {
    const value = trip.bookings.filter((booking) => booking.category === category).reduce((sum, booking) => sum + booking.amount, 0);
    return `<div><span>${label}</span><strong>${moneyFormatter.format(value)}</strong></div>`;
  }).join("");
  return `<div class="tab-panel" id="panel-preparation" role="tabpanel" aria-labelledby="tab-preparation" hidden>
    <div class="preparation-grid">
      <section class="prep-card wife-card">
        <div class="card-heading"><div><p class="eyebrow">PREPARATION</p><h3>妻の準備</h3></div><span class="deadline">期限 ${escapeHtml(formatDate(trip.preparation.packingDueDate))}</span></div>
        <p class="draft-help">チェック操作は一時状態です。採用済みJSONは変更しません。</p>
        <h4>パッキング</h4>${preparationChecklist([...trip.preparation.items].sort((a, b) => a.order - b.order))}
        <h4>特別準備</h4>${preparationChecklist([...trip.preparation.specialPreparations].sort((a, b) => a.order - b.order))}
        ${instructionField("preparation", trip.preparation.id, "例：雨具を追加して")}
      </section>
      <section class="prep-card rio-card">
        <div class="card-heading"><div><p class="eyebrow">RIO PLAN</p><h3>Rioの予定</h3></div><span class="decision-alert">早期決定</span></div>
        <div class="decision-box"><span>同伴 / 預ける</span><strong>未定</strong><small>決定期限 ${escapeHtml(formatDate(trip.rioPlan.careDecisionDueDate))}</small></div>
        <p class="care-detail">${escapeHtml(trip.rioPlan.careDetails)}</p>
        <p class="draft-help">完了・不要の変更はAIへの未送信指示として扱います。</p>
        <h4>標準持参品</h4>${rioChecklist(requiredRio)}
        <h4 class="subdued-heading">今回は不要</h4>${rioChecklist(unnecessaryRio, "unnecessary")}
        ${instructionField("rioPlan", trip.rioPlan.id, "例：預け先候補も調べて")}
      </section>
      <section class="prep-card booking-card">
        <div class="card-heading"><div><p class="eyebrow">BOOKING</p><h3>予約と費用</h3></div><strong class="total">${moneyFormatter.format(total)}</strong></div>
        <div class="cost-grid">${totals}</div>
        <div class="booking-list">${trip.bookings.map((booking) => {
          const target = placesById.get(booking.placeId);
          const transport = transportsById.get(booking.transportId);
          const transportName = transport ? `${transportLabels[transport.mode] ?? transport.mode} ${placesById.get(transport.fromPlaceId).name} → ${placesById.get(transport.toPlaceId).name}` : null;
          return `<article><div><span>${categoryLabels[booking.category]}</span><strong>${escapeHtml(target?.name ?? transportName ?? "予約")}</strong><small class="official-note"><b>正式な予約メモ</b>${escapeHtml(booking.notes)}</small>${instructionField("booking", booking.id, "例：キャンセル条件を確認して")}</div><div><strong>${moneyFormatter.format(booking.amount)}</strong><em class="status ${booking.status}">${booking.status === "booked" ? "予約済み" : "確認待ち"}</em></div></article>`;
        }).join("")}</div>
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
  if (type === "preparation") return "妻の準備：パッキング・特別準備";
  if (type === "rioPlan") return "Rioの予定：同行・預け先と持参品";
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
  const preparationItems = [...trip.preparation.items, ...trip.preparation.specialPreparations];

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
  const materials = updateMaterials(trip, placesById);
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="notes-workspace">
      <div class="notes-heading"><div><p class="eyebrow">AI UPDATE MATERIAL</p><h3>AIへ渡す変更内容</h3><p>一時状態を、次版の完全JSONを再生成するための更新材料として確認できます。</p></div><span class="unsent-badge">未送信</span></div>
      ${instructionField("trip", trip.id, "例：全体をゆったりした旅程にして")}
      <div class="material-heading">
        <div><h4>変更内容の確認</h4><p><strong data-update-count>${materials.length}</strong>件の変更があります。</p></div>
        <button type="button" class="copy-materials" data-copy-update ${materials.length ? "" : "disabled"}>クリップボードへコピー</button>
      </div>
      <p class="copy-status" data-copy-status role="status">${materials.length ? "内容を確認してからコピーしてください。" : "AIへ渡す変更はまだありません。"}</p>
      <div class="material-summary">
        ${materials.length ? `<ol>${materials.map((material) => `<li><div class="material-title"><strong>${escapeHtml(material.name)}</strong><span>${escapeHtml(material.type)}</span></div><dl><div><dt>安定ID</dt><dd>${escapeHtml(material.id)}</dd></div><div><dt>変更内容</dt><dd>${escapeHtml(material.change)}</dd></div></dl></li>`).join("")}</ol>` : "<div class=\"material-empty\"><strong>変更内容はありません</strong><span>準備のチェック、Rio持参品、場所候補、またはAI指示メモを変更すると、ここに表示されます。</span></div>"}
      </div>
      <div class="boundary-note"><strong>更新材料について</strong><span>採用済み完全JSON、Bookingの正式な予約メモ、内部差分ではありません。コピーしても一時状態は消えず、外部AIへの送信・完全JSON生成・採用も行いません。</span></div>
    </section>
  </div>`;
}

function renderTrip(trip) {
  document.title = `${trip.title} | Calendar`;
  const placesById = new Map(trip.places.map((place) => [place.id, place]));
  return `<a class="back-link" href="./index.html">← 旅の一覧へ</a>
    <section class="trip-hero">
      <div><p class="eyebrow">SYNTHETIC TRIP · ${trip.id}</p><h1>${escapeHtml(trip.title)}</h1><p>${escapeHtml(formatDateRange(trip.dateRange))}</p></div>
      <div class="trip-stat"><strong>${trip.days.length}</strong><span>DAYS</span></div>
    </section>
    <aside class="draft-status" aria-live="polite"><div><strong>変更指示を編集中</strong><span>ブラウザ内だけの一時状態・AIへ未送信</span></div><div><b data-draft-count>${draftCount()}</b><span>件の変更</span><button type="button" data-reset-draft ${draftCount() ? "" : "disabled"}>すべて取り消す</button></div></aside>
    <nav class="tabs" aria-label="旅行詳細">
      <button id="tab-itinerary" class="tab active" role="tab" aria-selected="true" aria-controls="panel-itinerary" data-tab="itinerary">旅程</button>
      <button id="tab-map" class="tab" role="tab" aria-selected="false" aria-controls="panel-map" data-tab="map">地図</button>
      <button id="tab-preparation" class="tab" role="tab" aria-selected="false" aria-controls="panel-preparation" data-tab="preparation">準備</button>
      <button id="tab-notes" class="tab" role="tab" aria-selected="false" aria-controls="panel-notes" data-tab="notes">メモ</button>
    </nav>
    ${renderItinerary(trip, placesById)}
    ${renderMap(trip)}
    ${renderPreparation(trip, placesById)}
    ${renderNotes(trip, placesById)}`;
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
    if (event.target.closest("[data-reset-draft]")) {
      draftState.preparation.clear();
      draftState.rioPacking.clear();
      draftState.placeSelections.clear();
      draftState.instructions.clear();
      draftState.openInstructionFields.clear();
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
    const instructionToggle = event.target.closest("[data-instruction-toggle]");
    if (instructionToggle) {
      const key = instructionToggle.dataset.instructionToggle;
      if (draftState.openInstructionFields.has(key)) draftState.openInstructionFields.delete(key);
      else draftState.openInstructionFields.add(key);
      rerender();
      if (draftState.openInstructionFields.has(key)) app.querySelector(`[data-instruction-key="${CSS.escape(key)}"]`)?.focus();
    }
  });

  app.addEventListener("input", (event) => {
    const key = event.target.dataset.instructionKey;
    if (!key) return;
    if (event.target.value.trim()) draftState.instructions.set(key, event.target.value);
    else draftState.instructions.delete(key);
    app.querySelector("[data-draft-count]").textContent = draftCount();
    app.querySelector("[data-reset-draft]").disabled = draftCount() === 0;
    const updateCount = app.querySelector("[data-update-count]");
    const copyButton = app.querySelector("[data-copy-update]");
    if (updateCount) updateCount.textContent = updateMaterials(trip, new Map(trip.places.map((place) => [place.id, place]))).length;
    if (copyButton) copyButton.disabled = draftCount() === 0;
  });

  app.addEventListener("change", (event) => {
    if (event.target.dataset.instructionKey) {
      rerender();
      return;
    }
    const preparationId = event.target.dataset.preparationId;
    if (preparationId) {
      const item = [...trip.preparation.items, ...trip.preparation.specialPreparations].find((candidate) => candidate.id === preparationId);
      if (event.target.checked === item.completed) draftState.preparation.delete(preparationId);
      else draftState.preparation.set(preparationId, event.target.checked);
      rerender();
      return;
    }
    const rioId = event.target.dataset.rioPackingId;
    if (rioId) {
      const item = trip.rioPlan.packingItems.find((candidate) => candidate.id === rioId);
      const original = item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending";
      if (event.target.value === original) draftState.rioPacking.delete(rioId);
      else draftState.rioPacking.set(rioId, event.target.value);
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
