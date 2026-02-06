#!/usr/bin/env node
/**
 * Godot MCP Server
 *
 * This MCP server provides tools for interacting with the Godot game engine.
 * It enables AI assistants to launch the Godot editor, run Godot projects,
 * capture debug output, and control project execution.
 */

import { fileURLToPath } from 'url';
import { join, dirname, normalize, basename } from 'path';
import { existsSync, readdirSync } from 'fs';
import { spawn, exec } from 'child_process';
import { promisify } from 'util';
import { z } from 'zod';
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

// Check if debug mode is enabled
const DEBUG_MODE: boolean = process.env.DEBUG === 'true';
const GODOT_DEBUG_MODE: boolean = true; // Always use GODOT DEBUG MODE

const execAsync = promisify(exec);

// Derive __filename and __dirname in ESM
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Interface representing a running Godot process
 */
interface GodotProcess {
  process: any;
  output: string[];
  errors: string[];
}

/**
 * Interface for operation parameters
 */
interface OperationParams {
  [key: string]: any;
}

/**
 * Handler class for Godot operations
 */
export class GodotHandler {
  private activeProcess: GodotProcess | null = null;
  private godotPath: string | null = null;
  private operationsScriptPath: string;
  private viewportCaptureScriptPath: string;
  private validatedPaths: Map<string, boolean> = new Map();
  private strictPathValidation: boolean = false;

  /**
   * Parameter name mappings between snake_case and camelCase
   * This allows the server to accept both formats
   */
  private parameterMappings: Record<string, string> = {
    'project_path': 'projectPath',
    'scene_path': 'scenePath',
    'root_node_type': 'rootNodeType',
    'parent_node_path': 'parentNodePath',
    'node_type': 'nodeType',
    'node_name': 'nodeName',
    'texture_path': 'texturePath',
    'node_path': 'nodePath',
    'output_path': 'outputPath',
    'mesh_item_names': 'meshItemNames',
    'new_path': 'newPath',
    'file_path': 'filePath',
    'directory': 'directory',
    'recursive': 'recursive',
    'scene': 'scene',
  };

  /**
   * Reverse mapping from camelCase to snake_case
   * Generated from parameterMappings for quick lookups
   */
  private reverseParameterMappings: Record<string, string> = {};

  constructor() {
    // Initialize reverse parameter mappings
    for (const [snakeCase, camelCase] of Object.entries(this.parameterMappings)) {
      this.reverseParameterMappings[camelCase] = snakeCase;
    }

    // Set the path to the operations script
    // Note: In dist/server.js, __dirname is dist/. Scripts are in dist/scripts/
    this.operationsScriptPath = join(__dirname, 'scripts', 'godot_operations.gd');
    if (DEBUG_MODE) console.error(`[DEBUG] Operations script path: ${this.operationsScriptPath}`);

    this.viewportCaptureScriptPath = join(__dirname, 'scripts', 'viewport_capture.gd');
    if (DEBUG_MODE) console.error(`[DEBUG] Viewport capture script path: ${this.viewportCaptureScriptPath}`);
    
    // Check environment variable for Godot path
    if (process.env.GODOT_PATH) {
      this.godotPath = normalize(process.env.GODOT_PATH);
    }
  }

  /**
   * Log debug messages if debug mode is enabled
   * Using stderr instead of stdout to avoid interfering with JSON-RPC communication
   */
  private logDebug(message: string): void {
    if (DEBUG_MODE) {
      console.error(`[DEBUG] ${message}`);
    }
  }

  /**
   * Validate a path to prevent path traversal attacks
   */
  private validatePath(path: string): boolean {
    // Basic validation to prevent path traversal
    if (!path || path.includes('..')) {
      return false;
    }

    // Add more validation as needed
    return true;
  }

  /**
   * Validate if a Godot path is valid and executable
   */
  private async isValidGodotPath(path: string): Promise<boolean> {
    // Check cache first
    if (this.validatedPaths.has(path)) {
      return this.validatedPaths.get(path)!;
    }

    try {
      this.logDebug(`Validating Godot path: ${path}`);

      // Check if the file exists (skip for 'godot' which might be in PATH)
      if (path !== 'godot' && !existsSync(path)) {
        this.logDebug(`Path does not exist: ${path}`);
        this.validatedPaths.set(path, false);
        return false;
      }

      // Try to execute Godot with --version flag
      const command = path === 'godot' ? 'godot --version' : `"${path}" --version`;
      await execAsync(command);

      this.logDebug(`Valid Godot path: ${path}`);
      this.validatedPaths.set(path, true);
      return true;
    } catch (error) {
      this.logDebug(`Invalid Godot path: ${path}, error: ${error}`);
      this.validatedPaths.set(path, false);
      return false;
    }
  }

  /**
   * Detect the Godot executable path based on the operating system
   */
  public async detectGodotPath() {
    // If godotPath is already set and valid, use it
    if (this.godotPath && await this.isValidGodotPath(this.godotPath)) {
      this.logDebug(`Using existing Godot path: ${this.godotPath}`);
      return;
    }

    // Check environment variable next
    if (process.env.GODOT_PATH) {
      const normalizedPath = normalize(process.env.GODOT_PATH);
      this.logDebug(`Checking GODOT_PATH environment variable: ${normalizedPath}`);
      if (await this.isValidGodotPath(normalizedPath)) {
        this.godotPath = normalizedPath;
        this.logDebug(`Using Godot path from environment: ${this.godotPath}`);
        return;
      } else {
        this.logDebug(`GODOT_PATH environment variable is invalid`);
      }
    }

    // Auto-detect based on platform
    const osPlatform = process.platform;
    this.logDebug(`Auto-detecting Godot path for platform: ${osPlatform}`);

    const possiblePaths: string[] = [
      'godot', // Check if 'godot' is in PATH first
    ];

    // Add platform-specific paths
    if (osPlatform === 'darwin') {
      possiblePaths.push(
        '/Applications/Godot.app/Contents/MacOS/Godot',
        '/Applications/Godot_4.app/Contents/MacOS/Godot',
        `${process.env.HOME}/Applications/Godot.app/Contents/MacOS/Godot`,
        `${process.env.HOME}/Applications/Godot_4.app/Contents/MacOS/Godot`,
        `${process.env.HOME}/Library/Application Support/Steam/steamapps/common/Godot Engine/Godot.app/Contents/MacOS/Godot`
      );
    } else if (osPlatform === 'win32') {
      possiblePaths.push(
        'C:\\Program Files\\Godot\\Godot.exe',
        'C:\\Program Files (x86)\\Godot\\Godot.exe',
        'C:\\Program Files\\Godot_4\\Godot.exe',
        'C:\\Program Files (x86)\\Godot_4\\Godot.exe',
        `${process.env.USERPROFILE}\\Godot\\Godot.exe`
      );
    } else if (osPlatform === 'linux') {
      possiblePaths.push(
        '/usr/bin/godot',
        '/usr/local/bin/godot',
        '/snap/bin/godot',
        `${process.env.HOME}/.local/bin/godot`
      );
    }

    // Try each possible path
    for (const path of possiblePaths) {
      const normalizedPath = normalize(path);
      if (await this.isValidGodotPath(normalizedPath)) {
        this.godotPath = normalizedPath;
        this.logDebug(`Found Godot at: ${normalizedPath}`);
        return;
      }
    }

    // If we get here, we couldn't find Godot
    this.logDebug(`Warning: Could not find Godot in common locations for ${osPlatform}`);
    console.error(`[SERVER] Could not find Godot in common locations for ${osPlatform}`);
    console.error(`[SERVER] Set GODOT_PATH=/path/to/godot environment variable or pass { godotPath: '/path/to/godot' } in the config to specify the correct path.`);

    if (this.strictPathValidation) {
      // In strict mode, throw an error
      throw new Error(`Could not find a valid Godot executable. Set GODOT_PATH or provide a valid path in config.`);
    } else {
      // Fallback to a default path in non-strict mode; this may not be valid and requires user configuration for reliability
      if (osPlatform === 'win32') {
        this.godotPath = normalize('C:\\Program Files\\Godot\\Godot.exe');
      } else if (osPlatform === 'darwin') {
        this.godotPath = normalize('/Applications/Godot.app/Contents/MacOS/Godot');
      } else {
        this.godotPath = normalize('/usr/bin/godot');
      }

      this.logDebug(`Using default path: ${this.godotPath}, but this may not work.`);
      console.error(`[SERVER] Using default path: ${this.godotPath}, but this may not work.`);
      console.error(`[SERVER] This fallback behavior will be removed in a future version. Set strictPathValidation: true to opt-in to the new behavior.`);
    }
  }

  /**
   * Convert camelCase keys to snake_case
   */
  private convertCamelToSnakeCase(params: OperationParams): OperationParams {
    const result: OperationParams = {};
    
    for (const key in params) {
      if (Object.prototype.hasOwnProperty.call(params, key)) {
        // Convert camelCase to snake_case
        const snakeKey = this.reverseParameterMappings[key] || key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
        
        // Handle nested objects recursively
        if (typeof params[key] === 'object' && params[key] !== null && !Array.isArray(params[key])) {
          result[snakeKey] = this.convertCamelToSnakeCase(params[key] as OperationParams);
        } else {
          result[snakeKey] = params[key];
        }
      }
    }
    
    return result;
  }

  /**
   * Execute a Godot operation using the operations script
   */
  public async executeOperation(
    operation: string,
    params: OperationParams,
    projectPath: string
  ): Promise<{ stdout: string; stderr: string }> {
    this.logDebug(`Executing operation: ${operation} in project: ${projectPath}`);
    this.logDebug(`Original operation params: ${JSON.stringify(params)}`);

    // Convert camelCase parameters to snake_case for Godot script
    const snakeCaseParams = this.convertCamelToSnakeCase(params);
    this.logDebug(`Converted snake_case params: ${JSON.stringify(snakeCaseParams)}`);

    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) {
        throw new Error('Could not find a valid Godot executable path');
      }
    }

    try {
      // Serialize the snake_case parameters to a valid JSON string
      const paramsJson = JSON.stringify(snakeCaseParams);
      // Escape single quotes in the JSON string to prevent command injection
      const escapedParams = paramsJson.replace(/'/g, "'\\''");
      // On Windows, cmd.exe does not strip single quotes, so we use
      // double quotes and escape them to ensure the JSON is parsed
      // correctly by Godot.
      const isWindows = process.platform === 'win32';
      const quotedParams = isWindows
        ? `\"${paramsJson.replace(/\"/g, '\\"')}\"`
        : `'${escapedParams}'`;

      // Add debug arguments if debug mode is enabled
      const debugArgs = GODOT_DEBUG_MODE ? ['--debug-godot'] : [];

      // Construct the command with the operation and JSON parameters
      const cmd = [
        `"${this.godotPath}"`,
        '--headless',
        '--path',
        `"${projectPath}"`,
        '--script',
        `"${this.operationsScriptPath}"`,
        operation,
        quotedParams, // Pass the JSON string as a single argument
        ...debugArgs,
      ].join(' ');

      this.logDebug(`Command: ${cmd}`);

      const { stdout, stderr } = await execAsync(cmd);

      return { stdout, stderr };
    } catch (error: unknown) {
      // If execAsync throws, it still contains stdout/stderr
      if (error instanceof Error && 'stdout' in error && 'stderr' in error) {
        const execError = error as Error & { stdout: string; stderr: string };
        return {
          stdout: execError.stdout,
          stderr: execError.stderr,
        };
      }

      throw error;
    }
  }

  /**
   * Find Godot projects in a directory
   */
  public findGodotProjects(directory: string, recursive: boolean): Array<{ path: string; name: string }> {
    const projects: Array<{ path: string; name: string }> = [];

    try {
      // Check if the directory itself is a Godot project
      const projectFile = join(directory, 'project.godot');
      if (existsSync(projectFile)) {
        projects.push({
          path: directory,
          name: basename(directory),
        });
      }

      // If not recursive, only check immediate subdirectories
      if (!recursive) {
        const entries = readdirSync(directory, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const subdir = join(directory, entry.name);
            const projectFile = join(subdir, 'project.godot');
            if (existsSync(projectFile)) {
              projects.push({
                path: subdir,
                name: entry.name,
              });
            }
          }
        }
      } else {
        // Recursive search
        const entries = readdirSync(directory, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const subdir = join(directory, entry.name);
            // Skip hidden directories
            if (entry.name.startsWith('.')) {
              continue;
            }
            // Check if this directory is a Godot project
            const projectFile = join(subdir, 'project.godot');
            if (existsSync(projectFile)) {
              projects.push({
                path: subdir,
                name: entry.name,
              });
            } else {
              // Recursively search this directory
              const subProjects = this.findGodotProjects(subdir, true);
              projects.push(...subProjects);
            }
          }
        }
      }
    } catch (error) {
      this.logDebug(`Error searching directory ${directory}: ${error}`);
    }

    return projects;
  }

  /**
   * Get the structure of a Godot project asynchronously by counting files recursively
   */
  public getProjectStructureAsync(projectPath: string): Promise<any> {
    return new Promise((resolve) => {
      try {
        const structure = {
          scenes: 0,
          scripts: 0,
          assets: 0,
          other: 0,
        };

        const scanDirectory = (currentPath: string) => {
          const entries = readdirSync(currentPath, { withFileTypes: true });
          
          for (const entry of entries) {
            const entryPath = join(currentPath, entry.name);
            
            // Skip hidden files and directories
            if (entry.name.startsWith('.')) {
              continue;
            }
            
            if (entry.isDirectory()) {
              // Recursively scan subdirectories
              scanDirectory(entryPath);
            } else if (entry.isFile()) {
              // Count file by extension
              const ext = entry.name.split('.').pop()?.toLowerCase();
              
              if (ext === 'tscn') {
                structure.scenes++;
              } else if (ext === 'gd' || ext === 'gdscript' || ext === 'cs') {
                structure.scripts++;
              } else if (['png', 'jpg', 'jpeg', 'webp', 'svg', 'ttf', 'wav', 'mp3', 'ogg'].includes(ext || '')) {
                structure.assets++;
              } else {
                structure.other++;
              }
            }
          }
        };
        
        // Start scanning from the project root
        scanDirectory(projectPath);
        resolve(structure);
      } catch (error) {
        this.logDebug(`Error getting project structure asynchronously: ${error}`);
        resolve({ 
          error: 'Failed to get project structure',
          scenes: 0,
          scripts: 0,
          assets: 0,
          other: 0
        });
      }
    });
  }

  // Exposed methods for tool handlers

  public async launchEditor(projectPath: string) {
    if (!this.validatePath(projectPath)) throw new Error('Invalid project path');
    
    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) throw new Error('Could not find a valid Godot executable path');
    }

    const projectFile = join(projectPath, 'project.godot');
    if (!existsSync(projectFile)) throw new Error(`Not a valid Godot project: ${projectPath}`);

    this.logDebug(`Launching Godot editor for project: ${projectPath}`);
    const process = spawn(this.godotPath, ['-e', '--path', projectPath], {
      stdio: 'pipe',
    });

    process.on('error', (err: Error) => {
      console.error('Failed to start Godot editor:', err);
    });

    return `Godot editor launched successfully for project at ${projectPath}.`;
  }

  public async runProject(projectPath: string, scene?: string) {
    if (!this.validatePath(projectPath)) throw new Error('Invalid project path');
    
    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) throw new Error('Could not find a valid Godot executable path');
    }

    const projectFile = join(projectPath, 'project.godot');
    if (!existsSync(projectFile)) throw new Error(`Not a valid Godot project: ${projectPath}`);

    // Kill any existing process
    if (this.activeProcess) {
      this.logDebug('Killing existing Godot process before starting a new one');
      this.activeProcess.process.kill();
    }

    const cmdArgs = ['-d', '--path', projectPath];
    if (scene && this.validatePath(scene)) {
      this.logDebug(`Adding scene parameter: ${scene}`);
      cmdArgs.push(scene);
    }

    this.logDebug(`Running Godot project: ${projectPath}`);
    const process = spawn(this.godotPath!, cmdArgs, { stdio: 'pipe' });
    const output: string[] = [];
    const errors: string[] = [];

    process.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      output.push(...lines);
      lines.forEach((line: string) => {
        if (line.trim()) this.logDebug(`[Godot stdout] ${line}`);
      });
    });

    process.stderr?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      errors.push(...lines);
      lines.forEach((line: string) => {
        if (line.trim()) this.logDebug(`[Godot stderr] ${line}`);
      });
    });

    process.on('exit', (code: number | null) => {
      this.logDebug(`Godot process exited with code ${code}`);
      if (this.activeProcess && this.activeProcess.process === process) {
        this.activeProcess = null;
      }
    });

    process.on('error', (err: Error) => {
      console.error('Failed to start Godot process:', err);
      if (this.activeProcess && this.activeProcess.process === process) {
        this.activeProcess = null;
      }
    });

    this.activeProcess = { process, output, errors };

    return `Godot project started in debug mode. Use get_debug_output to see output.`;
  }

  public getDebugOutput() {
    if (!this.activeProcess) throw new Error('No active Godot process.');
    return JSON.stringify({
      output: this.activeProcess.output,
      errors: this.activeProcess.errors,
    }, null, 2);
  }

  public stopProject() {
    if (!this.activeProcess) throw new Error('No active Godot process to stop.');
    
    this.logDebug('Stopping active Godot process');
    this.activeProcess.process.kill();
    const output = this.activeProcess.output;
    const errors = this.activeProcess.errors;
    this.activeProcess = null;

    return JSON.stringify({
      message: 'Godot project stopped',
      finalOutput: output,
      finalErrors: errors,
    }, null, 2);
  }

  public async getGodotVersion() {
    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) throw new Error('Could not find a valid Godot executable path');
    }

    this.logDebug('Getting Godot version');
    const { stdout } = await execAsync(`"${this.godotPath}" --version`);
    return stdout.trim();
  }

  public async getProjectInfo(projectPath: string) {
    if (!this.validatePath(projectPath)) throw new Error('Invalid project path');
    
    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) throw new Error('Could not find a valid Godot executable path');
    }

    const projectFile = join(projectPath, 'project.godot');
    if (!existsSync(projectFile)) throw new Error(`Not a valid Godot project: ${projectPath}`);

    this.logDebug(`Getting project info for: ${projectPath}`);

    // Get Godot version
    const execOptions = { timeout: 10000 }; // 10 second timeout
    const { stdout } = await execAsync(`"${this.godotPath}" --version`, execOptions);

    // Get project structure using the recursive method
    const projectStructure = await this.getProjectStructureAsync(projectPath);

    // Extract project name from project.godot file
    let projectName = basename(projectPath);
    try {
      const fs = await import('fs');
      const projectFileContent = fs.readFileSync(projectFile, 'utf8');
      const configNameMatch = projectFileContent.match(/config\/name="([^"]+)"/);
      if (configNameMatch && configNameMatch[1]) {
        projectName = configNameMatch[1];
        this.logDebug(`Found project name in config: ${projectName}`);
      }
    } catch (error) {
      this.logDebug(`Error reading project file: ${error}`);
      // Continue with default project name if extraction fails
    }

    return JSON.stringify({
      name: projectName,
      path: projectPath,
      godotVersion: stdout.trim(),
      structure: projectStructure,
    }, null, 2);
  }

  public async captureViewport(projectPath: string): Promise<string> {
    if (!this.validatePath(projectPath)) throw new Error('Invalid project path');

    // Ensure godotPath is set
    if (!this.godotPath) {
      await this.detectGodotPath();
      if (!this.godotPath) throw new Error('Could not find a valid Godot executable path');
    }

    const projectFile = join(projectPath, 'project.godot');
    if (!existsSync(projectFile)) throw new Error(`Not a valid Godot project: ${projectPath}`);

    this.logDebug(`Capturing viewport for project: ${projectPath}`);

    // Add debug arguments if debug mode is enabled
    const debugArgs = GODOT_DEBUG_MODE ? ['--debug-godot'] : [];

    const cmd = [
      `"${this.godotPath}"`,
      '--headless',
      '--path',
      `"${projectPath}"`,
      '-s',
      `"${this.viewportCaptureScriptPath}"`,
      ...debugArgs,
    ].join(' ');

    this.logDebug(`Command: ${cmd}`);

    const { stdout, stderr } = await execAsync(cmd);

    // Parse stdout for SCREENSHOT_PATH
    const match = stdout.match(/SCREENSHOT_PATH:(.+)/);
    if (match && match[1]) {
      const screenshotPath = match[1].trim();
      return screenshotPath;
    }

    // If we couldn't find the path, log output and throw
    this.logDebug(`Stdout: ${stdout}`);
    this.logDebug(`Stderr: ${stderr}`);
    throw new Error('Failed to capture viewport: Could not find screenshot path in output');
  }

  public async cleanup() {
    if (this.activeProcess) {
      this.activeProcess.process.kill();
      this.activeProcess = null;
    }
  }
}

// Initialize server and handler
const handler = new GodotHandler();
const server = new McpServer({
  name: "godot-mcp",
  version: "0.1.0"
});

// Register tools
server.tool(
  "launch_editor",
  { projectPath: z.string() },
  async ({ projectPath }) => {
    try {
      const result = await handler.launchEditor(projectPath);
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "run_project",
  { projectPath: z.string(), scene: z.string().optional() },
  async ({ projectPath, scene }) => {
    try {
      const result = await handler.runProject(projectPath, scene);
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "get_debug_output",
  {},
  async () => {
    try {
      const result = handler.getDebugOutput();
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "stop_project",
  {},
  async () => {
    try {
      const result = handler.stopProject();
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "get_godot_version",
  {},
  async () => {
    try {
      const result = await handler.getGodotVersion();
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "list_projects",
  { directory: z.string(), recursive: z.boolean().optional() },
  async ({ directory, recursive }) => {
    try {
      if (!existsSync(directory)) throw new Error(`Directory does not exist: ${directory}`);
      const projects = handler.findGodotProjects(directory, recursive || false);
      return { content: [{ type: "text", text: JSON.stringify(projects, null, 2) }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "get_project_info",
  { projectPath: z.string() },
  async ({ projectPath }) => {
    try {
      const result = await handler.getProjectInfo(projectPath);
      return { content: [{ type: "text", text: result }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "create_scene",
  { projectPath: z.string(), scenePath: z.string(), rootNodeType: z.string().optional() },
  async ({ projectPath, scenePath, rootNodeType }) => {
    try {
      const params = { scenePath, rootNodeType: rootNodeType || 'Node2D' };
      const { stdout, stderr } = await handler.executeOperation('create_scene', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Scene created successfully at: ${scenePath}\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "add_node",
  { 
    projectPath: z.string(), 
    scenePath: z.string(), 
    parentNodePath: z.string().optional(), 
    nodeType: z.string(), 
    nodeName: z.string(), 
    properties: z.record(z.string(), z.any()).optional() 
  },
  async ({ projectPath, scenePath, parentNodePath, nodeType, nodeName, properties }) => {
    try {
      const params = { scenePath, parentNodePath, nodeType, nodeName, properties };
      const { stdout, stderr } = await handler.executeOperation('add_node', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Node added successfully.\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "load_sprite",
  { projectPath: z.string(), scenePath: z.string(), nodePath: z.string(), texturePath: z.string() },
  async ({ projectPath, scenePath, nodePath, texturePath }) => {
    try {
      const params = { scenePath, nodePath, texturePath };
      const { stdout, stderr } = await handler.executeOperation('load_sprite', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Sprite loaded successfully.\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "export_mesh_library",
  { projectPath: z.string(), scenePath: z.string(), outputPath: z.string(), meshItemNames: z.array(z.string()).optional() },
  async ({ projectPath, scenePath, outputPath, meshItemNames }) => {
    try {
      const params = { scenePath, outputPath, meshItemNames };
      const { stdout, stderr } = await handler.executeOperation('export_mesh_library', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Mesh library exported successfully.\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "save_scene",
  { projectPath: z.string(), scenePath: z.string(), newPath: z.string().optional() },
  async ({ projectPath, scenePath, newPath }) => {
    try {
      const params = { scenePath, newPath };
      const { stdout, stderr } = await handler.executeOperation('save_scene', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Scene saved successfully.\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "get_uid",
  { projectPath: z.string(), filePath: z.string() },
  async ({ projectPath, filePath }) => {
    try {
      const params = { filePath };
      const { stdout, stderr } = await handler.executeOperation('get_uid', params, projectPath);
      if (stderr && stderr.includes('Error')) throw new Error(stderr);
      // stdout contains the JSON result
      return { content: [{ type: "text", text: stdout.trim() }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "update_project_uids",
  { projectPath: z.string() },
  async ({ projectPath }) => {
    try {
      const params = { projectPath };
      const { stdout, stderr } = await handler.executeOperation('resave_resources', params, projectPath);
      if (stderr && stderr.includes('Failed to')) throw new Error(stderr);
      return { content: [{ type: "text", text: `Project UIDs updated.\n\nOutput: ${stdout}` }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "capture_viewport",
  { projectPath: z.string() },
  async ({ projectPath }) => {
    try {
      const result = await handler.captureViewport(projectPath);
      return { content: [{ type: "text", text: JSON.stringify({ path: result }) }] };
    } catch (error: any) {
      return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
    }
  }
);

async function startServer() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

startServer().catch((err) => {
  console.error(err);
  process.exit(1);
});

process.on('SIGINT', async () => {
  await handler.cleanup();
  process.exit(0);
});
