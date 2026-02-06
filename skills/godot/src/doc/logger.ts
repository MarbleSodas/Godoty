export type LogLevel = "silent" | "error" | "warn" | "info" | "debug";

export interface Logger {
  debug(msg: string, meta?: Record<string, unknown>): void;
  info(msg: string, meta?: Record<string, unknown>): void;
  warn(msg: string, meta?: Record<string, unknown>): void;
  error(msg: string, meta?: Record<string, unknown>): void;
  level: LogLevel;
}

const levels: LogLevel[] = ["silent", "error", "warn", "info", "debug"];

export function createLogger(level: LogLevel = "info"): Logger {
  const idx = Math.max(0, levels.indexOf(level));
  const enabled = (name: LogLevel) => idx >= levels.indexOf(name);
  return {
    debug(msg, meta) {
      if (enabled("debug")) console.debug(format("debug", msg, meta));
    },
    info(msg, meta) {
      if (enabled("info")) console.info(format("info", msg, meta));
    },
    warn(msg, meta) {
      if (enabled("warn")) console.warn(format("warn", msg, meta));
    },
    error(msg, meta) {
      if (enabled("error")) console.error(format("error", msg, meta));
    },
    level,
  };
}

function format(level: string, msg: string, meta?: Record<string, unknown>) {
  const base = `[${level}] ${msg}`;
  return meta && Object.keys(meta).length ? `${base} ${JSON.stringify(meta)}` : base;
}
