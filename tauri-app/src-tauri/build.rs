use std::process::Command;
use std::path::Path;

fn main() {
    // Build the RAG server bundle if building for release
    if std::env::var("PROFILE").unwrap_or_default() == "release" {
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
