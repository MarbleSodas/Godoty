import { chmod, rm, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { platform, arch, tmpdir } from "node:os";
import { exec } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";

const execAsync = promisify(exec);

const VERSION = "v1.1.53";
const REPO = "anomalyco/opencode";
const BASE_URL = `https://github.com/${REPO}/releases/download/${VERSION}/`;
const BINARIES_DIR = join(process.cwd(), "src-tauri", "bin");

interface Target {
  triple: string;
  ext: string;
  assetName: string;
  binaryNameInArchive: string;
}

const getTarget = (): Target => {
  const os = platform();
  const cpu = arch();

  if (os === "win32" && cpu === "x64") {
    return { 
      triple: "x86_64-pc-windows-msvc", 
      ext: ".exe",
      assetName: "opencode-windows-x64.zip",
      binaryNameInArchive: "opencode.exe"
    };
  }
  if (os === "linux" && cpu === "x64") {
    return { 
      triple: "x86_64-unknown-linux-gnu", 
      ext: "",
      assetName: "opencode-linux-x64.tar.gz",
      binaryNameInArchive: "opencode"
    };
  }
  if (os === "darwin") {
    if (cpu === "x64") {
      return { 
        triple: "x86_64-apple-darwin", 
        ext: "",
        assetName: "opencode-darwin-x64.zip",
        binaryNameInArchive: "opencode"
      };
    }
    if (cpu === "arm64") {
      return { 
        triple: "aarch64-apple-darwin", 
        ext: "",
        assetName: "opencode-darwin-arm64.zip",
        binaryNameInArchive: "opencode"
      };
    }
  }

  throw new Error(`Unsupported platform/architecture: ${os}/${cpu}`);
};

const setup = async () => {
  const { triple, ext, assetName, binaryNameInArchive } = getTarget();
  const targetBinaryName = `opencode-cli-${triple}${ext}`;
  const url = `${BASE_URL}${assetName}`;
  const outputPath = join(BINARIES_DIR, targetBinaryName);
  
  // Create temp directory for extraction
  const tempDir = join(tmpdir(), `opencode-setup-${Date.now()}`);
  await mkdir(tempDir, { recursive: true });
  const downloadPath = join(tempDir, assetName);

  console.log(`Downloading OpenCode ${VERSION} for ${triple}...`);
  console.log(`URL: ${url}`);
  
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to download binary: ${response.statusText} (${response.status})`);
    }

    const buffer = await response.arrayBuffer();
    await Bun.write(downloadPath, buffer);

    console.log("Extracting...");
    
    if (assetName.endsWith(".zip")) {
      if (platform() === "win32") {
        await execAsync(`powershell -Command "Expand-Archive -Path '${downloadPath}' -DestinationPath '${tempDir}' -Force"`);
      } else {
        await execAsync(`unzip -o '${downloadPath}' -d '${tempDir}'`);
      }
    } else if (assetName.endsWith(".tar.gz")) {
      await execAsync(`tar -xf '${downloadPath}' -C '${tempDir}'`);
    }

    // Find the binary in the extracted files
    // Use 'find' or recursive search because it might be nested
    // For simplicity, we assume it's in the top level or we search for it.
    // But since we can't easily do recursive search in node without dependencies or verbose code,
    // we'll assume it's at root or top level folder.
    // Windows zip usually has 'opencode-windows-x64/opencode.exe' or just 'opencode.exe'
    
    // We'll search for the binary file
    let foundPath = join(tempDir, binaryNameInArchive);
    if (!existsSync(foundPath)) {
        // Try one level deep (e.g. opencode-windows-x64/opencode.exe)
        // Since we don't know the folder name exactly, we read dir
        const { readdir } = require("node:fs/promises");
        const files = await readdir(tempDir);
        for (const file of files) {
            const nested = join(tempDir, file, binaryNameInArchive);
            if (existsSync(nested)) {
                foundPath = nested;
                break;
            }
        }
    }

    if (!existsSync(foundPath)) {
         throw new Error(`Could not find ${binaryNameInArchive} in extracted files`);
    }

    console.log(`Moving binary to ${outputPath}...`);
    await Bun.write(outputPath, Bun.file(foundPath));

    if (platform() !== "win32") {
      console.log("Setting executable permissions...");
      await chmod(outputPath, 0o755);
    }

    console.log("Sidecar setup complete!");

  } catch (error) {
    throw error;
  } finally {
    // Cleanup
    try {
        await rm(tempDir, { recursive: true, force: true });
    } catch (e) {
        console.warn("Failed to cleanup temp dir:", e);
    }
  }
};

setup().catch((err) => {
  console.error("Error setting up sidecar:", err);
  process.exit(1);
});
