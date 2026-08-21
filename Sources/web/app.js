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
};

const targetKey = (type, id) => `${type}:${id}`;

function aiTargetButton(type, id, name, label = "AIへ変更を指示") {
  return `<button type="button" class="row-action" data-ai-target-type="${escapeHtml(type)}" data-ai-target-id="${escapeHtml(id)}" data-ai-target-name="${escapeHtml(name)}" aria-label="${escapeHtml(`${name}：${label}`)}">…</button>`;
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
    const transportName = `${from.name} → ${to.name}`;
    return `<article class="timeline-entry transport-entry">
      <div class="time-column"><strong>${escapeHtml(formatTime(entry.time))}</strong><span>所要${entry.time.durationMinutes}分</span></div>
      <div class="timeline-dot" aria-hidden="true">↗</div>
      <div class="entry-card">
        <div class="entry-top"><div class="entry-kicker">移動 · ${escapeHtml(transportLabels[entry.mode] ?? entry.mode)}</div>${aiTargetButton("transport", entry.id, transportName)}</div>
        <h4>${escapeHtml(transportName)}</h4>
        <p>${escapeHtml(from.address)} から ${escapeHtml(to.address)}</p>
      </div>
    </article>`;
  }

  const selection = entry.placeSelection;
  const adopted = new Set(selection.selection);
  const selected = draftState.placeSelections.get(entry.id) ?? adopted;
  const candidates = selection.candidatePlaceIds.map((id) => placesById.get(id));
  return `<article class="timeline-entry schedule-entry">
    <div class="time-column"><strong>${escapeHtml(formatTime(entry.time))}</strong><span>所要${entry.time.durationMinutes}分</span></div>
    <div class="timeline-dot" aria-hidden="true">●</div>
    <div class="entry-card">
      <div class="entry-top"><div class="entry-kicker">行動 · <span class="time-mode ${entry.time.mode}">${modeLabels[entry.time.mode]}</span></div>${aiTargetButton("scheduleItem", entry.id, entry.action)}</div>
      <h4>${escapeHtml(entry.action)}</h4>
      <div class="candidate-list">${candidates.map((place) => {
        const checked = selected.has(place.id);
        const atMaximum = selection.maxSelections !== null && selected.size >= selection.maxSelections;
        return `<label class="candidate-row selectable ${checked ? "selected" : ""}"><input type="checkbox" data-place-selection="${escapeHtml(entry.id)}" data-place-id="${escapeHtml(place.id)}" ${checked ? "checked" : ""} ${!checked && atMaximum ? "disabled" : ""}><span class="choice-mark" aria-hidden="true">${checked ? "✓" : ""}</span><span class="candidate-copy"><strong>${escapeHtml(place.name)}</strong><span>${escapeHtml(place.address)}</span></span>${placeRating(place)}</label>`;
      }).join("")}</div>
    </div>
  </article>`;
}

function renderItinerary(trip, placesById) {
  return `<div class="tab-panel" id="panel-itinerary" role="tabpanel" aria-labelledby="tab-itinerary">
    <div class="itinerary-grid">${trip.days.map((day, index) => {
      const transports = trip.transports.filter((item) => day.transportIds.includes(item.id));
      const entries = [
        ...day.scheduleItems.map((item) => ({ ...item, kind: "schedule" })),
        ...transports.map((item) => ({ ...item, kind: "transport" })),
      ].sort((a, b) => a.order - b.order);
      return `<section class="day-section">
        <div class="day-heading"><span>DAY ${index + 1}</span><div><h3>${escapeHtml(formatDate(day.date))}</h3><p>${escapeHtml(day.title)}</p></div>${aiTargetButton("day", day.id, `${formatDate(day.date)} ${day.title}`)}</div>
        <div class="timeline">${entries.map((entry) => itineraryEntry(entry, placesById)).join("")}</div>
      </section>`;
    }).join("")}</div>
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

const preparationChecklist = (items) => `<ul class="check-list task-list">${items.map((item) => {
  const completed = draftState.preparation.get(item.id) ?? item.completed;
  return `<li class="${completed ? "completed" : "pending"}"><label><input type="checkbox" data-preparation-id="${escapeHtml(item.id)}" ${completed ? "checked" : ""}><span class="check-icon" aria-hidden="true">${completed ? "✓" : "○"}</span><span class="task-copy"><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(formatDate(item.dueDate))}期限</small></span></label>${aiTargetButton("preparation", item.id, item.label)}</li>`;
}).join("")}</ul>`;

const rioChecklist = (items) => `<ul class="check-list rio-list">${items.map((item) => {
  const value = draftState.rioPacking.get(item.id) ?? (item.notNeeded ? "notNeeded" : item.completed ? "completed" : "pending");
  return `<li class="${value === "completed" ? "completed" : "pending"} ${value === "notNeeded" ? "not-needed" : ""}"><label><input type="checkbox" data-rio-packing-id="${escapeHtml(item.id)}" ${value === "completed" ? "checked" : ""}><span class="check-icon" aria-hidden="true">${value === "completed" ? "✓" : "○"}</span><span>${escapeHtml(item.label)}${value === "notNeeded" ? "（持参しない）" : ""}</span></label>${aiTargetButton("rioPlan", item.id, item.label)}</li>`;
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
        <div class="card-heading"><div><p class="eyebrow">PREPARATION</p><h3>妻の準備</h3></div>${aiTargetButton("preparation", trip.preparation.id, "妻の準備")}</div>
        ${preparationChecklist([...trip.preparation.tasks].sort((a, b) => a.order - b.order))}
      </section>
      <section class="prep-card rio-card">
        <div class="card-heading"><div><p class="eyebrow">RIO PLAN</p><h3>Rioの予定</h3></div>${aiTargetButton("rioPlan", trip.rioPlan.id, "Rioの予定")}</div>
        <div class="decision-box"><span>同伴 / 預ける</span><strong>未定</strong><small>決定期限 ${escapeHtml(formatDate(trip.rioPlan.careDecisionDueDate))}</small></div>
        <p class="care-detail">${escapeHtml(trip.rioPlan.careDetails)}</p>
        ${rioChecklist(rioItems)}
      </section>
      <section class="prep-card booking-card">
        <div class="card-heading"><div><p class="eyebrow">BOOKING</p><h3>予約</h3></div></div>
        <div class="booking-table" role="table" aria-label="予約一覧">${trip.bookings.map((booking) => {
          const target = placesById.get(booking.placeId);
          const transport = transportsById.get(booking.transportId);
          const transportName = transport ? `${transportLabels[transport.mode] ?? transport.mode} ${placesById.get(transport.fromPlaceId).name} → ${placesById.get(transport.toPlaceId).name}` : null;
          const bookingName = target?.name ?? transportName ?? "予約";
          return `<div class="booking-row" role="row"><div role="cell"><span>${categoryLabels[booking.category]}</span><strong>${escapeHtml(bookingName)}</strong></div><small class="official-note" role="cell">${escapeHtml(booking.notes)}</small><em class="status ${booking.status}" role="cell">${booking.status === "booked" ? "予約済み" : "確認待ち"}</em>${aiTargetButton("booking", booking.id, bookingName)}</div>`;
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
  const materials = updateMaterials(trip, placesById);
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="notes-workspace">
      <div class="notes-heading"><div><p class="eyebrow">AI UPDATE MATERIAL</p><h3>AIへ渡す変更内容</h3><p>一時状態を、次版の完全JSONを再生成するための更新材料として確認できます。</p></div><span class="unsent-badge">未送信</span></div>
      <div class="material-heading">
        <div><h4>変更内容の確認</h4><p><strong data-update-count>${materials.length}</strong>件の変更があります。</p></div>
        <div class="material-actions"><button type="button" class="quiet-button" data-reset-draft ${materials.length ? "" : "disabled"}>すべて取り消す</button><button type="button" class="copy-materials" data-copy-update ${materials.length ? "" : "disabled"}>クリップボードへコピー</button></div>
      </div>
      <p class="copy-status" data-copy-status role="status">${materials.length ? "内容を確認してからコピーしてください。" : "AIへ渡す変更はまだありません。"}</p>
      <div class="material-summary">
        ${materials.length ? `<ol>${materials.map((material) => `<li><div class="material-title"><strong>${escapeHtml(material.name)}</strong><span>${escapeHtml(material.type)}</span></div><dl><div><dt>安定ID</dt><dd>${escapeHtml(material.id)}</dd></div><div><dt>変更内容</dt><dd>${escapeHtml(material.change)}</dd></div></dl></li>`).join("")}</ol>` : "<div class=\"material-empty\"><strong>変更内容はありません</strong><span>準備のチェック、Rio持参品、場所候補、またはAI指示メモを変更すると、ここに表示されます。</span></div>"}
      </div>
      <div class="boundary-note"><strong>更新材料について</strong><span>採用済み完全JSON、Bookingの正式な予約メモ、内部差分ではありません。コピーしても一時状態は消えず、外部AIへの送信・完全JSON生成・採用も行いません。</span></div>
    </section>
  </div>`;
}

function renderAiPanel(trip) {
  if (!draftState.aiPanelOpen) return "";
  const target = draftState.aiTarget ?? { type: "trip", id: trip.id, name: trip.title };
  const key = targetKey(target.type, target.id);
  const value = draftState.instructions.get(key) ?? "";
  return `<section class="ai-panel" role="dialog" aria-modal="false" aria-labelledby="ai-panel-title">
    <div class="ai-panel-heading"><div><span>対象: ${escapeHtml(target.name)}</span><h3 id="ai-panel-title">AIへ指示</h3></div><button type="button" data-close-ai aria-label="AI指示パネルを閉じる">×</button></div>
    <p>この項目について、どのように変更しますか？</p>
    <label class="ai-panel-input"><span class="visually-hidden">AIへの指示</span><textarea rows="3" data-instruction-key="${escapeHtml(key)}" placeholder="変更したい内容を入力">${escapeHtml(value)}</textarea></label>
    <small>一時状態・AIへ未送信</small>
  </section>`;
}

function renderTrip(trip) {
  document.title = `${trip.title} | Calendar`;
  const placesById = new Map(trip.places.map((place) => [place.id, place]));
  return `<a class="back-link" href="./index.html">← 旅の一覧へ</a>
    <section class="trip-hero">
      <div><p class="eyebrow">SYNTHETIC TRIP · ${trip.id}</p><h1>${escapeHtml(trip.title)}</h1><p>${escapeHtml(formatDateRange(trip.dateRange))}</p></div>
      <div class="trip-stat"><strong>${trip.days.length}</strong><span>DAYS</span></div>
    </section>
    <nav class="tabs bottom-nav" aria-label="旅行詳細">
      <button id="tab-itinerary" class="tab active" role="tab" aria-selected="true" aria-controls="panel-itinerary" data-tab="itinerary">旅程</button>
      <button id="tab-map" class="tab" role="tab" aria-selected="false" aria-controls="panel-map" data-tab="map">地図</button>
      <button id="tab-preparation" class="tab" role="tab" aria-selected="false" aria-controls="panel-preparation" data-tab="preparation">準備</button>
      <button id="tab-notes" class="tab" role="tab" aria-selected="false" aria-controls="panel-notes" data-tab="notes">AI <span class="draft-count" data-draft-count>${draftCount()}</span></button>
      <button type="button" class="ai-primary" data-open-ai-all>AIへ指示</button>
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
