import { start } from "./index.js";

start().catch((err) => {
  console.error(err);
  process.exit(1);
});
