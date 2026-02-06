import { start } from "./doc/index.js";

// Ensure the server runs on stdio
process.env.MCP_STDIO = "1";

start().catch((err) => {
  console.error(err);
  process.exit(1);
});
