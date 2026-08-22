const legacyCategory = (value) => {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("食") || text.includes("meal") || text.includes("restaurant")) return "food";
  if (text.includes("宿") || text.includes("hotel") || text.includes("accommodation")) return "accommodation";
  if (text.includes("移") || text.includes("transport")) return "transport";
  return "sightseeing";
};

const legacyTime = (value) => {
  const clocks = String(value ?? "").match(/\d{1,2}:\d{2}/g) ?? [];
  if (!clocks.length) return { mode: "undecided" };
  return { mode: clocks.length > 1 ? "range" : "fixed", start: clocks[0], ...(clocks[1] ? { end: clocks[1] } : {}) };
};

const transportMode = (value) => {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("徒歩") || text.includes("walk")) return "walk";
  if (text.includes("鉄道") || text.includes("電車") || text.includes("新幹線") || text.includes("train")) return "train";
  if (text.includes("バス") || text.includes("bus")) return "bus";
  if (text.includes("飛行機") || text.includes("航空") || text.includes("flight")) return "flight";
  if (text.includes("フェリー") || text.includes("船") || text.includes("ferry")) return "ferry";
  return "car";
};

const combineSummary = (...values) => values.filter(Boolean).join(" / ");

export function normalizeTrip(source) {
  if (source?.id && source?.dateRange && Array.isArray(source.days)) return source;
  const metadata = source?.trip;
  if (!metadata?.id) throw new Error("旅行JSONにtrip.idがありません。");
  const mapPoints = Array.isArray(source.mapPoints) ? source.mapPoints : [];
  const mapPointsById = new Map(mapPoints.map((point) => [point.id, point]));
  const places = mapPoints.map((point) => ({
    id: point.id,
    name: point.name,
    summary: point.candidate ? "候補" : "",
    category: legacyCategory(point.category) === "food" ? "restaurant" : legacyCategory(point.category) === "accommodation" ? "hotel" : "attraction",
    location: Number.isFinite(point.latitude) && Number.isFinite(point.longitude) ? { latitude: point.latitude, longitude: point.longitude } : null,
    rating: null,
  }));
  const placeIds = new Set(places.map((place) => place.id));
  const addPlace = (place) => {
    if (placeIds.has(place.id)) return;
    places.push(place);
    placeIds.add(place.id);
  };

  const itinerary = Array.isArray(source.itinerary) ? source.itinerary : [];
  itinerary.forEach((item) => {
    const id = item.mapPointId || `${item.id}-place`;
    addPlace({ id, name: item.title || "場所未定", summary: item.summary || "", category: "attraction", location: null, rating: null });
  });

  const meals = Array.isArray(source.meals) ? source.meals : [];
  meals.forEach((meal) => {
    const candidates = Array.isArray(meal.candidates) ? meal.candidates : [];
    if (!candidates.length) {
      addPlace({ id: `${meal.id}-place`, name: meal.title || `${meal.timing || ""}食`, summary: meal.description || "", category: "restaurant", location: null, rating: null });
    }
    candidates.forEach((candidate) => {
      const point = mapPointsById.get(candidate.mapPointId);
      addPlace({
        id: candidate.id,
        name: candidate.name,
        summary: candidate.summary || "",
        category: "restaurant",
        location: point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude) ? { latitude: point.latitude, longitude: point.longitude } : null,
        rating: Number.isFinite(candidate.rating) ? { source: "食べログ", value: candidate.rating, checkedAt: candidate.ratingUpdatedAt || candidate.ratingCheckedAt || null } : null,
        legacyMapPointId: candidate.mapPointId || null,
      });
    });
  });

  const rawRoutes = Array.isArray(source.intercityRoutes) ? source.intercityRoutes : [];
  const transports = [];
  const transportIdsByDate = new Map();
  rawRoutes.forEach((route, routeIndex) => {
    const names = Array.isArray(route.places) ? route.places : [];
    names.forEach((name, placeIndex) => {
      const matchingPoint = mapPoints.find((point) => point.name === name);
      const id = matchingPoint?.id || `route-${routeIndex + 1}-place-${placeIndex + 1}`;
      addPlace({ id, name, summary: "", category: "other", location: matchingPoint && Number.isFinite(matchingPoint.latitude) && Number.isFinite(matchingPoint.longitude) ? { latitude: matchingPoint.latitude, longitude: matchingPoint.longitude } : null, rating: null });
    });
    for (let segment = 0; segment < names.length - 1; segment += 1) {
      const fromPoint = mapPoints.find((point) => point.name === names[segment]);
      const toPoint = mapPoints.find((point) => point.name === names[segment + 1]);
      const id = `intercity-${routeIndex + 1}-${segment + 1}`;
      transports.push({
        id,
        dayId: `day-${route.date}`,
        order: 500 + routeIndex * 100 + segment,
        mode: transportMode(route.mode),
        fromPlaceId: fromPoint?.id || `route-${routeIndex + 1}-place-${segment + 1}`,
        toPlaceId: toPoint?.id || `route-${routeIndex + 1}-place-${segment + 2}`,
        time: { mode: "undecided" },
        legacyMode: route.mode || "",
      });
      const ids = transportIdsByDate.get(route.date) ?? [];
      ids.push(id);
      transportIdsByDate.set(route.date, ids);
    }
  });

  const days = (Array.isArray(source.days) ? source.days : []).map((day, dayIndex) => {
    const dayItems = itinerary.filter((item) => item.date === day.date);
    const dayMeals = meals.filter((meal) => meal.date === day.date);
    const scheduleItems = dayItems.map((item, index) => {
      const placeId = item.mapPointId || `${item.id}-place`;
      const transportSummary = item.transport ? `移動: ${item.transport}` : "";
      return {
        id: item.id,
        dayId: `day-${day.date}`,
        order: Number(item.displayOrder) || (index + 1) * 10,
        action: item.title || "予定",
        summary: combineSummary(item.summary, transportSummary) || (Array.isArray(item.details) ? item.details[0] : ""),
        details: [...(Array.isArray(item.details) ? item.details : []), ...(transportSummary ? [transportSummary] : [])],
        category: legacyCategory(item.category || item.type),
        time: legacyTime(item.time),
        legacyTransport: item.transport || null,
        placeSelection: { candidatePlaceIds: [placeId], selection: item.selectionStatus === "未定" || item.status === "候補" ? [] : [placeId], minSelections: 1, maxSelections: 1 },
      };
    });
    dayMeals.forEach((meal, mealIndex) => {
      const candidates = Array.isArray(meal.candidates) ? meal.candidates : [];
      const candidateIds = candidates.length ? candidates.map((candidate) => candidate.id) : [`${meal.id}-place`];
      const selected = candidateIds.length === 1 && meal.selectionStatus !== "未定" && meal.status !== "候補" && meal.status !== "未定" ? candidateIds : [];
      scheduleItems.push({
        id: meal.id,
        dayId: `day-${day.date}`,
        order: 700 + mealIndex * 10,
        action: meal.title || `${meal.timing || ""}食`,
        summary: combineSummary(meal.area, meal.description),
        details: meal.description ? [meal.description] : [],
        category: "food",
        time: legacyTime(meal.time),
        placeSelection: { candidatePlaceIds: candidateIds, selection: selected, minSelections: 1, maxSelections: 1 },
      });
    });
    return {
      id: `day-${day.date}`,
      date: day.date,
      title: day.label || `第${day.dayNumber || dayIndex + 1}日`,
      routeSummary: day.overview || (Array.isArray(day.areas) ? day.areas.join(" → ") : ""),
      scheduleItems,
      transportIds: transportIdsByDate.get(day.date) ?? [],
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
  const bookingCategory = (type, label) => {
    const text = `${type ?? ""} ${label ?? ""}`.toLowerCase();
    if (/宿|ホテル|旅館|accommodation|hotel/.test(text)) return "accommodation";
    if (/交通|航空|飛行|フェリー|船|鉄道|電車|新幹線|バス|レンタカー|transport|flight|train/.test(text)) return "transport";
    if (/観光|入場|体験|ツアー|チケット|activity|tour|ticket/.test(text)) return "activity";
    return "other";
  };
  return {
    id: metadata.id,
    title: metadata.name,
    dateRange: { start: metadata.startDate, end: metadata.endDate },
    days,
    places,
    transports,
    preparation: { id: `${metadata.id}-preparation`, tasks: preparation },
    rioPlan: { id: `${metadata.id}-rio`, applicable: rioPacking.length > 0, careMode: rioSource.mode === "預ける" ? "leave" : "accompany", packingItems: rioPacking },
    bookings: (Array.isArray(source.bookings) ? source.bookings : []).map((booking) => ({
      id: booking.id,
      label: booking.label || "予約",
      category: bookingCategory(booking.type, booking.label),
      status: booking.status === "確定" ? "booked" : "pending",
      targetDate: booking.dueDate || metadata.startDate,
      amount: booking.amount === null || booking.amount === undefined || booking.amount === "" || !Number.isFinite(Number(booking.amount)) ? null : Number(booking.amount),
      currency: booking.currency || "JPY",
      notes: booking.note || "",
    })),
  };
}
