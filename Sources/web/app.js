const SAMPLE_URL = "../../Samples/synthetic-trip.json";

// The adopted JSON remains read-only. Every interaction in this stage lives
// only in this in-memory object and is discarded when the page is closed.
const draftState = {
  preparation: new Map(),
  rioPacking: new Map(),
  placeSelections: new Map(),
  instructions: new Map(),
};

const targetKey = (type, id) => `${type}:${id}`;

function instructionField(type, id, label) {
  const key = targetKey(type, id);
  return `<label class="instruction-field">
    <span>AIへの指示メモ <small>一時・未送信</small></span>
    <textarea rows="2" data-instruction-key="${escapeHtml(key)}" placeholder="${escapeHtml(label)}">${escapeHtml(draftState.instructions.get(key) ?? "")}</textarea>
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
        ${instructionField("transport", entry.id, "例：この移動を一本遅い便に変更して")}
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
      ${instructionField("scheduleItem", entry.id, "例：この予定を午後に移して")}
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
        <div class="day-heading"><span>DAY ${index + 1}</span><div><h3>${escapeHtml(formatDate(day.date))}</h3><p>${escapeHtml(day.title)}</p>${instructionField("day", day.id, "例：この日は移動を少なめにして")}</div></div>
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

function renderNotes(trip) {
  const labels = {
    trip: "旅行全体",
    day: "日程",
    scheduleItem: "予定",
    transport: "移動",
    preparation: "妻の準備",
    rioPlan: "Rioの予定",
    booking: "予約",
  };
  const notes = [...draftState.instructions.entries()].filter(([, value]) => value.trim());
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="notes-workspace">
      <div class="notes-heading"><div><p class="eyebrow">AI INSTRUCTIONS</p><h3>AIへの指示メモ</h3><p>対象ごとのメモを一時的にまとめます。まだAIへ送信されていません。</p></div><span class="unsent-badge">未送信</span></div>
      ${instructionField("trip", trip.id, "例：全体をゆったりした旅程にして")}
      <div class="instruction-summary">
        <h4>入力済みメモ</h4>
        ${notes.length ? `<ul>${notes.map(([key, value]) => `<li><span>${escapeHtml(labels[key.split(":")[0]] ?? "関連項目")}</span><p>${escapeHtml(value)}</p></li>`).join("")}</ul>` : "<p>各画面で入力したメモがここに表示されます。</p>"}
      </div>
      <div class="boundary-note"><strong>一時状態について</strong><span>採用済みJSONや予約の正式メモは変更しません。AI送信・完全JSON生成・採用はこの段階では行いません。</span></div>
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
    ${renderNotes(trip)}`;
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
  });

  app.addEventListener("input", (event) => {
    const key = event.target.dataset.instructionKey;
    if (!key) return;
    if (event.target.value.trim()) draftState.instructions.set(key, event.target.value);
    else draftState.instructions.delete(key);
    app.querySelector("[data-draft-count]").textContent = draftCount();
    app.querySelector("[data-reset-draft]").disabled = draftCount() === 0;
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
