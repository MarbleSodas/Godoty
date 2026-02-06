export function formatSearchUri(q?: string, kind?: string): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  const qs = params.toString();
  return `godot://search${qs ? `?${qs}` : ""}`;
}
