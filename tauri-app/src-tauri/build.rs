use std::process::Command;
use std::path::{Path, PathBuf};

fn main() {
    let profile = std::env::var("PROFILE").unwrap_or_default();
    let is_release = profile == "release";
    let build_mcp_debug = std::env::var("BUILD_MCP_DEBUG").unwrap_or_default() == "1";

    // Build the RAG server bundle if building for release
    if is_release {
        build_rag_bundle();

        // After building, check if the executable exists and add it to resources
        let exe_name = if cfg!(target_os = "windows") {
            "rag_server.exe"
        } else {
            "rag_server"
        };

        let resource_path = Path::new("resources").join(exe_name);
        if resource_path.exists() {
            println!("cargo:warning=RAG server executable found, will be included in bundle");
            // Tell Tauri to rerun if the executable changes
            println!("cargo:rerun-if-changed=resources/{}", exe_name);
        } else {
            println!("cargo:warning=RAG server executable not found at {:?}, application will require Python at runtime", resource_path);
        }
    }

    // Build MCP server binaries in release mode or when explicitly requested for debug
    if is_release || build_mcp_debug {
        if build_mcp_debug {
            println!("cargo:warning=Building MCP server binaries in debug mode (BUILD_MCP_DEBUG=1)");
        }
        build_mcp_binaries();
    }

    tauri_build::build()
}

fn build_rag_bundle() {
    println!("cargo:warning=Building RAG server bundle...");

    let build_script = Path::new("build_rag_bundle.py");

    if !build_script.exists() {
        println!("cargo:warning=build_rag_bundle.py not found, skipping RAG bundle build");
        return;
    }

    // Try to find Python executable
    let python_cmd = find_python_executable();

    match python_cmd {
        Some(cmd) => {
            println!("cargo:warning=Using Python: {}", cmd);

            let output = Command::new(&cmd)
                .arg(build_script)
                .output();

            match output {
                Ok(output) => {
                    if output.status.success() {
                        println!("cargo:warning=RAG server bundle built successfully");
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        println!("cargo:warning=RAG bundle build failed: {}", stderr);
                    }
                }
                Err(e) => {
                    println!("cargo:warning=Failed to execute Python build script: {}", e);
                }
            }
        }
        None => {
            println!("cargo:warning=Python not found, skipping RAG bundle build");
            println!("cargo:warning=The application will require Python to be installed on the target system");
        }
    }
}

fn find_python_executable() -> Option<String> {
    // Try common Python executable names
    let candidates = if cfg!(target_os = "windows") {
        vec!["py", "python", "python3"]
    } else {
        vec!["python3", "python"]
    };

    for cmd in candidates {
        if Command::new(cmd).arg("--version").output().is_ok() {
            return Some(cmd.to_string());
        }
    }

    None
}

fn build_mcp_binaries() {
    println!("cargo:warning=Building MCP server binaries...");

    // Try to find Node.js/npm
    let node_cmd = find_node_executable();
    let npm_cmd = find_npm_executable();

    match (node_cmd, npm_cmd) {
        (Some(node), Some(npm)) => {
            println!("cargo:warning=Using Node.js: {}", node);
            println!("cargo:warning=Using npm: {}", npm);

            // Define MCP server packages to build
            let mcp_servers = vec![
                ("desktop-commander", "@wonderwhy-er/desktop-commander@latest"),
                ("sequential-thinking", "@modelcontextprotocol/server-sequential-thinking@latest"),
                ("context7", "@upstash/context7-mcp@latest"),
            ];

            let platform_dir = get_platform_directory();
            let mcp_resources_dir = Path::new("resources").join("mcp").join(&platform_dir);

            // Create the resources directory structure
            if let Err(e) = std::fs::create_dir_all(&mcp_resources_dir) {
                println!("cargo:warning=Failed to create MCP resources directory: {}", e);
                return;
            }

            for (server_name, package_name) in mcp_servers {
                if let Err(e) = build_single_mcp_binary(&npm, server_name, package_name, &mcp_resources_dir, &platform_dir) {
                    println!("cargo:warning=Failed to build MCP server '{}': {}", server_name, e);
                } else {
                    println!("cargo:warning=Successfully built MCP server: {}", server_name);
                }
            }
        }
        (None, Some(_)) => {
            println!("cargo:warning=Node.js not found, skipping MCP binary build");
            println!("cargo:warning=The application will fall back to npx for MCP servers");
        }
        (Some(_), None) => {
            println!("cargo:warning=npm not found, skipping MCP binary build");
            println!("cargo:warning=The application will fall back to npx for MCP servers");
        }
        (None, None) => {
            println!("cargo:warning=Node.js and npm not found, skipping MCP binary build");
            println!("cargo:warning=The application will fall back to npx for MCP servers");
        }
    }
}

fn find_node_executable() -> Option<String> {
    let candidates = if cfg!(target_os = "windows") {
        vec!["node.exe", "node"]
    } else {
        vec!["node"]
    };

    for cmd in candidates {
        if Command::new(cmd).arg("--version").output().is_ok() {
            return Some(cmd.to_string());
        }
    }

    None
}

fn find_npm_executable() -> Option<String> {
    let candidates = if cfg!(target_os = "windows") {
        vec!["npm.cmd", "npm"]
    } else {
        vec!["npm"]
    };

    for cmd in candidates {
        if Command::new(cmd).arg("--version").output().is_ok() {
            return Some(cmd.to_string());
        }
    }

    None
}

fn get_platform_directory() -> String {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("windows", "x86_64") => "windows-x64".to_string(),
        ("windows", "aarch64") => "windows-arm64".to_string(),
        ("macos", "x86_64") => "macos-x64".to_string(),
        ("macos", "aarch64") => "macos-arm64".to_string(),
        ("linux", "x86_64") => "linux-x64".to_string(),
        ("linux", "aarch64") => "linux-arm64".to_string(),
        (os, arch) => format!("{}-{}", os, arch),
    }
}

fn build_single_mcp_binary(
    npm_cmd: &str,
    server_name: &str,
    package_name: &str,
    output_dir: &Path,
    _platform_dir: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:warning=Building MCP server '{}' from package '{}'", server_name, package_name);

    // First, install the package temporarily
    let temp_dir = std::env::temp_dir().join(format!("mcp-build-{}", server_name));
    std::fs::create_dir_all(&temp_dir)?;

    let output = Command::new(npm_cmd)
        .args(&["install", "--no-save", package_name])
        .current_dir(&temp_dir)
        .output()?;

    if !output.status.success() {
        return Err(format!("Failed to install package '{}': {}",
                         package_name,
                         String::from_utf8_lossy(&output.stderr)).into());
    }

    // Find the package directory
    let node_modules = temp_dir.join("node_modules");
    let package_dir = find_package_directory(&node_modules, package_name)?;

    if !package_dir.exists() {
        return Err(format!("Package directory not found for '{}'", package_name).into());
    }

    // Use pkg to compile to binary
    let output_path = format!("../{}", server_name);
    let pkg_args = match std::env::consts::OS {
        "windows" => vec![
            "--targets".to_string(),
            "node18-win-x64".to_string(),
            "--output".to_string(),
            output_path.clone(),
        ],
        "macos" => vec![
            "--targets".to_string(),
            format!("node18-macos-{}", std::env::consts::ARCH),
            "--output".to_string(),
            output_path.clone(),
        ],
        "linux" => vec![
            "--targets".to_string(),
            format!("node18-linux-{}", std::env::consts::ARCH),
            "--output".to_string(),
            output_path.clone(),
        ],
        _ => return Err("Unsupported platform".into()),
    };

    let pkg_output = Command::new(npm_cmd)
        .args(&["run", "pkg", "--"])
        .args(&pkg_args)
        .args(&[package_dir.to_str().unwrap()])
        .current_dir(&temp_dir)
        .output()?;

    if !pkg_output.status.success() {
        // If pkg fails, try installing pkg first
        println!("cargo:warning=pkg not found, installing...");
        let install_pkg = Command::new(npm_cmd)
            .args(&["install", "-g", "pkg"])
            .output()?;

        if install_pkg.status.success() {
            // Try again with pkg
            let pkg_output = Command::new("pkg")
                .args(&pkg_args)
                .args(&[package_dir.to_str().unwrap()])
                .current_dir(&temp_dir)
                .output()?;

            if !pkg_output.status.success() {
                return Err(format!("Failed to compile with pkg: {}",
                                 String::from_utf8_lossy(&pkg_output.stderr)).into());
            }
        } else {
            return Err("Failed to install pkg".into());
        }
    }

    // Move the built binary to the resources directory
    let binary_name = if std::env::consts::OS == "windows" {
        format!("{}.exe", server_name)
    } else {
        server_name.to_string()
    };

    let built_binary = temp_dir.join(&binary_name);
    let target_binary = output_dir.join(&binary_name);

    if built_binary.exists() {
        std::fs::copy(&built_binary, &target_binary)?;
        println!("cargo:warning=Copied {} to {:?}", server_name, target_binary);

        // Tell Tauri to rerun if the binary changes
        println!("cargo:rerun-if-changed={}", target_binary.display());
    } else {
        // Try to find any executable file in temp_dir
        for entry in std::fs::read_dir(&temp_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_file() {
                let filename = path.file_name().unwrap().to_string_lossy();
                if filename.starts_with(server_name) {
                    std::fs::copy(&path, &target_binary)?;
                    println!("cargo:warning=Copied {} to {:?}", filename, target_binary);
                    println!("cargo:rerun-if-changed={}", target_binary.display());
                    break;
                }
            }
        }
    }

    // Clean up temporary directory
    std::fs::remove_dir_all(&temp_dir)?;

    Ok(())
}

fn find_package_directory(node_modules: &Path, package_name: &str) -> Result<PathBuf, Box<dyn std::error::Error>> {
    // Handle scoped packages like @upstash/context7-mcp
    let parts: Vec<&str> = package_name.split('@').filter(|s| !s.is_empty()).collect();
    let search_path = if parts.len() > 1 {
        // Scoped package
        node_modules.join(parts[0]).join(parts[1])
    } else {
        // Regular package
        node_modules.join(package_name)
    };

    // Try the direct path first
    if search_path.exists() {
        return Ok(search_path);
    }

    // If that fails, search for any directory containing the package name
    for entry in std::fs::read_dir(node_modules)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            let dirname = path.file_name().unwrap().to_string_lossy();
            if dirname.contains(package_name) ||
               (package_name.starts_with('@') && dirname.contains(&package_name[1..])) {
                return Ok(path);
            }
        }
    }

    Err(format!("Package directory not found for '{}'", package_name).into())
}
