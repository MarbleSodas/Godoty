import path from "node:path";

export function withinDir(baseDir: string, targetPath: string): boolean {
  const base = path.resolve(baseDir);
  const target = path.resolve(targetPath);
  return target === base || target.startsWith(base + path.sep);
}

export function assertWithinDir(baseDir: string, targetPath: string, what: string = "path"): void {
  if (!withinDir(baseDir, targetPath)) {
    throw new Error(`Access denied: ${what} outside base directory`);
  }
}

export function allowIndexPath(indexPath: string, allowedPath: string): boolean {
  const resolved = path.resolve(indexPath);
  const allowed = path.resolve(allowedPath || "./.cache/godot-index.json");
  const allowedDir = path.dirname(allowed);
  return withinDir(allowedDir, resolved);
}
