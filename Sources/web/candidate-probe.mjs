export async function candidateProbe(response) {
  if (response.ok) return { available: true, error: null };
  if (response.status === 404) return { available: false, error: null };
  let message = `候補版を確認できません（HTTP ${response.status}）。candidate.jsonを確認してください。`;
  try {
    const body = await response.json();
    if (body?.error) message = `候補版を確認できません（${body.error}）。candidate.jsonを確認してください。`;
  } catch (_) {
    // Keep the status-based local diagnostic when the body is not JSON.
  }
  return { available: false, error: message };
}
