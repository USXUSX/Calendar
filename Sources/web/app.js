const SAMPLE_URL = "../../Samples/synthetic-trip.json";

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
      </div>
    </article>`;
  }

  const candidates = entry.placeSelection.candidatePlaceIds.map((id) => placesById.get(id));
  return `<article class="timeline-entry schedule-entry">
    <div class="time-column"><strong>${escapeHtml(formatTime(entry.time))}</strong><span>${entry.time.durationMinutes}分</span></div>
    <div class="timeline-dot" aria-hidden="true">●</div>
    <div class="entry-card">
      <div class="entry-kicker">行動 · <span class="time-mode ${entry.time.mode}">${modeLabels[entry.time.mode]}</span></div>
      <h4>${escapeHtml(entry.action)}</h4>
      <div class="candidate-summary">場所候補 ${candidates.length}件 · ${escapeHtml(selectionLabel(entry.placeSelection))}</div>
      <div class="candidate-list">${candidates.map((place) => `<div class="candidate-row"><div><strong>${escapeHtml(place.name)}</strong><span>${escapeHtml(place.address)}</span></div>${placeRating(place)}</div>`).join("")}</div>
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
        <div class="day-heading"><span>DAY ${index + 1}</span><div><h3>${escapeHtml(formatDate(day.date))}</h3><p>${escapeHtml(day.title)}</p></div></div>
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

const checklist = (items, extraClass = "") => `<ul class="check-list ${extraClass}">${items.map((item) => `<li class="${item.completed ? "completed" : ""} ${item.notNeeded ? "not-needed" : ""}"><span class="check-icon" aria-hidden="true">${item.completed ? "✓" : item.notNeeded ? "−" : "○"}</span><span>${escapeHtml(item.label)}</span>${item.notNeeded ? "<em>不要</em>" : ""}</li>`).join("")}</ul>`;

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
        <h4>パッキング</h4>${checklist(trip.preparation.items.sort((a, b) => a.order - b.order))}
        <h4>特別準備</h4>${checklist(trip.preparation.specialPreparations.sort((a, b) => a.order - b.order))}
      </section>
      <section class="prep-card rio-card">
        <div class="card-heading"><div><p class="eyebrow">RIO PLAN</p><h3>Rioの予定</h3></div><span class="decision-alert">早期決定</span></div>
        <div class="decision-box"><span>同伴 / 預ける</span><strong>未定</strong><small>決定期限 ${escapeHtml(formatDate(trip.rioPlan.careDecisionDueDate))}</small></div>
        <p class="care-detail">${escapeHtml(trip.rioPlan.careDetails)}</p>
        <h4>標準持参品</h4>${checklist(requiredRio)}
        <h4 class="subdued-heading">今回は不要</h4>${checklist(unnecessaryRio, "unnecessary")}
      </section>
      <section class="prep-card booking-card">
        <div class="card-heading"><div><p class="eyebrow">BOOKING</p><h3>予約と費用</h3></div><strong class="total">${moneyFormatter.format(total)}</strong></div>
        <div class="cost-grid">${totals}</div>
        <div class="booking-list">${trip.bookings.map((booking) => {
          const target = placesById.get(booking.placeId);
          const transport = transportsById.get(booking.transportId);
          const transportName = transport ? `${transportLabels[transport.mode] ?? transport.mode} ${placesById.get(transport.fromPlaceId).name} → ${placesById.get(transport.toPlaceId).name}` : null;
          return `<article><div><span>${categoryLabels[booking.category]}</span><strong>${escapeHtml(target?.name ?? transportName ?? "予約")}</strong><small>${escapeHtml(booking.notes)}</small></div><div><strong>${moneyFormatter.format(booking.amount)}</strong><em class="status ${booking.status}">${booking.status === "booked" ? "予約済み" : "確認待ち"}</em></div></article>`;
        }).join("")}</div>
      </section>
    </div>
  </div>`;
}

function renderNotes() {
  return `<div class="tab-panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="notes-empty">
      <div class="notes-icon" aria-hidden="true">✦</div>
      <p class="eyebrow">AI INSTRUCTIONS</p>
      <h3>AIへの指示メモはまだありません</h3>
      <p>この第1段階は読み取り専用です。メモは採用済みJSONには含めず、将来の画面操作中だけ一時状態として扱います。</p>
      <div class="boundary-note"><strong>この画面で行わないこと</strong><span>JSONの直接更新・ChangeSet表示・AIへの送信</span></div>
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
    <nav class="tabs" aria-label="旅行詳細">
      <button id="tab-itinerary" class="tab active" role="tab" aria-selected="true" aria-controls="panel-itinerary" data-tab="itinerary">旅程</button>
      <button id="tab-map" class="tab" role="tab" aria-selected="false" aria-controls="panel-map" data-tab="map">地図</button>
      <button id="tab-preparation" class="tab" role="tab" aria-selected="false" aria-controls="panel-preparation" data-tab="preparation">準備</button>
      <button id="tab-notes" class="tab" role="tab" aria-selected="false" aria-controls="panel-notes" data-tab="notes">メモ</button>
    </nav>
    ${renderItinerary(trip, placesById)}
    ${renderMap(trip)}
    ${renderPreparation(trip, placesById)}
    ${renderNotes()}`;
}

function setupTabs() {
  const tabs = [...document.querySelectorAll("[data-tab]")];
  const activate = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      document.querySelector(`#panel-${tab.dataset.tab}`).hidden = !active;
    });
    history.replaceState(null, "", `#${name}`);
  };
  tabs.forEach((tab) => tab.addEventListener("click", () => activate(tab.dataset.tab)));
  const requested = location.hash.slice(1);
  if (tabs.some((tab) => tab.dataset.tab === requested)) activate(requested);
}

async function start() {
  const app = document.querySelector("#app");
  try {
    const response = await fetch(SAMPLE_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const trip = await response.json();
    app.innerHTML = document.body.dataset.page === "trip" ? renderTrip(trip) : renderHome(trip);
    if (document.body.dataset.page === "trip") setupTabs();
  } catch (error) {
    app.innerHTML = `<section class="error-state"><h1>旅行情報を表示できませんでした</h1><p>${escapeHtml(error.message)}</p><p>リポジトリ直下をローカルHTTPサーバーで配信してください。</p></section>`;
  }
}

start();
