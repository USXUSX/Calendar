const collectOriginalIds = (value, ids = new Set()) => {
  if (Array.isArray(value)) {
    value.forEach((item) => collectOriginalIds(item, ids));
  } else if (value && typeof value === "object") {
    if (typeof value.id === "string") ids.add(value.id);
    Object.values(value).forEach((item) => collectOriginalIds(item, ids));
  }
  return ids;
};

export function createUpdatePackage(originalJson, trip, materials) {
  const originalIds = collectOriginalIds(originalJson);
  const lines = [
    "Calendar AI更新依頼パッケージ",
    `対象旅行: ${trip.title}`,
    `Trip ID: ${trip.id}`,
    "",
    "Chatへの更新指示",
    "採用済み完全JSONと更新材料を基に、差分や部分JSONではなく次版の完全JSONを生成してください。",
    "既存JSON上のIDは、同じ対象について維持してください。",
    "通常更新では、採用済みJSONのschemaVersionと基本構造を維持し、表示用の正規化形式へ勝手に変換しないでください。",
    "",
    `更新材料（${materials.length}件）`,
  ];
  materials.forEach((material, index) => {
    lines.push(`${index + 1}. ${material.name}`);
    lines.push(`   対象種別: ${material.type}`);
    if (originalIds.has(material.id)) lines.push(`   安定ID: ${material.id}`);
    else lines.push(`   派生表示上の参照: ${material.id}（元JSON上のIDではありません。名称・日付・経路で対象を特定してください）`);
    lines.push(`   変更内容: ${material.change}`);
  });
  lines.push("", "採用済みcurrent.json（完全JSON・表示用正規化前）", JSON.stringify(originalJson, null, 2));
  return lines.join("\n");
}
