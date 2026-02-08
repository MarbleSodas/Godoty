import { join } from "node:path";
import { platform, arch } from "node:os";
import { createOpencodeServer } from "../packages/sdk/src/server";

const getTarget = () => {
  const os = platform();
  const cpu = arch();

  if (os === "win32" && cpu === "x64") {
    return { triple: "x86_64-pc-windows-msvc", ext: ".exe" };
  }
  if (os === "linux" && cpu === "x64") {
    return { triple: "x86_64-unknown-linux-gnu", ext: "" };
  }
  if (os === "darwin") {
    if (cpu === "x64") return { triple: "x86_64-apple-darwin", ext: "" };
    if (cpu === "arm64") return { triple: "aarch64-apple-darwin", ext: "" };
  }
  
  throw new Error(`Unsupported platform/architecture: ${os}/${cpu}`);
};

const main = async () => {
  const { triple, ext } = getTarget();
  const binaryName = `opencode-cli-${triple}${ext}`;
  const binaryPath = join(process.cwd(), "src-tauri", "bin", binaryName);
  
  // Isolate dev server configuration
  process.env.XDG_CONFIG_HOME = join(process.cwd(), "src-tauri", "target", "dev-config");
  process.env.OPENCODE_CONFIG_DIR = process.env.XDG_CONFIG_HOME;
  // Ensure the directory exists
  await import("node:fs/promises").then(fs => fs.mkdir(process.env.XDG_CONFIG_HOME!, { recursive: true }));

  console.log(`Starting OpenCode server from: ${binaryPath}`);

  const server = await createOpencodeServer({
    command: binaryPath,
    port: 4096,
    config: {
      logLevel: "INFO"
    }
  });

  console.log(`Server started at ${server.url}`);

  process.on("SIGINT", () => {
    server.close();
    process.exit(0);
  });
};

main().catch(console.error);
