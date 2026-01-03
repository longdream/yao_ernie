use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
struct LauncherConfig {
    version: String,
    pip_mirror: String,
    first_run: bool,
}

fn main() {
    println!("========================================");
    println!("  YaoScope Service Launcher");
    println!("========================================\n");

    // 获取当前可执行文件的目录
    let exe_path = env::current_exe().expect("无法获取可执行文件路径");
    let base_dir = exe_path.parent().expect("无法获取父目录");
    
    // 切换到基础目录
    env::set_current_dir(base_dir).expect("无法切换到基础目录");
    
    println!("[INFO] 工作目录: {}", base_dir.display());
    
    // 检查 Python 环境
    let python_dir = base_dir.join("python");
    let python_exe = python_dir.join("python.exe");
    
    if !python_exe.exists() {
        eprintln!("[ERROR] 找不到 Python 环境: {}", python_exe.display());
        eprintln!("[INFO] 请确保 python/ 目录存在");
        pause();
        std::process::exit(1);
    }
    
    println!("[OK] Python 环境: {}", python_exe.display());
    
    // 检查是否为 Lite 版本并需要安装依赖
    let config_file = base_dir.join("launcher_config.json");
    if config_file.exists() {
        println!("[INFO] 检测到 Lite 版本配置");
        
        if let Ok(config_content) = fs::read_to_string(&config_file) {
            if let Ok(mut config) = serde_json::from_str::<LauncherConfig>(&config_content) {
                if config.first_run {
                    println!("\n[INFO] 首次运行，需要安装依赖包");
                    println!("[INFO] 这可能需要 5-10 分钟，请耐心等待...\n");
                    
                    if !install_dependencies(&python_exe, &config.pip_mirror, base_dir) {
                        eprintln!("\n[ERROR] 依赖安装失败");
                        pause();
                        std::process::exit(1);
                    }
                    
                    // 更新配置，标记已完成首次安装
                    config.first_run = false;
                    if let Ok(updated_config) = serde_json::to_string_pretty(&config) {
                        let _ = fs::write(&config_file, updated_config);
                    }
                    
                    println!("\n[OK] 依赖安装完成！");
                }
            }
        }
    }
    
    // 检查服务文件
    let service_main = base_dir.join("service").join("main.py");
    if !service_main.exists() {
        eprintln!("[ERROR] 找不到服务文件: {}", service_main.display());
        pause();
        std::process::exit(1);
    }
    
    println!("[OK] 服务文件: {}", service_main.display());
    
    // 设置环境变量
    let pythonpath = format!("{};{}", 
        base_dir.display(),
        env::var("PYTHONPATH").unwrap_or_default()
    );
    
    println!("\n========================================");
    println!("  启动 YaoScope 服务...");
    println!("========================================\n");
    
    // 启动服务
    let status = Command::new(&python_exe)
        .arg(service_main)
        .env("PYTHONPATH", pythonpath)
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status();
    
    match status {
        Ok(exit_status) => {
            if !exit_status.success() {
                eprintln!("\n[ERROR] 服务异常退出，退出码: {:?}", exit_status.code());
                pause();
                std::process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("\n[ERROR] 启动服务失败: {}", e);
            pause();
            std::process::exit(1);
        }
    }
    
    println!("\n[INFO] 服务已停止");
    pause();
}

fn install_dependencies(python_exe: &Path, pip_mirror: &str, base_dir: &Path) -> bool {
    let requirements = base_dir.join("requirements.txt");
    
    if !requirements.exists() {
        eprintln!("[ERROR] 找不到 requirements.txt");
        return false;
    }
    
    println!("[INFO] 开始安装依赖...");
    println!("[INFO] 镜像源: {}", pip_mirror);
    
    let status = Command::new(python_exe)
        .args(&[
            "-m", "pip", "install",
            "-r", requirements.to_str().unwrap(),
            "-i", pip_mirror,
            "--no-warn-script-location"
        ])
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status();
    
    match status {
        Ok(exit_status) => exit_status.success(),
        Err(e) => {
            eprintln!("[ERROR] 执行 pip 失败: {}", e);
            false
        }
    }
}

fn pause() {
    print!("\n按 Enter 键退出...");
    io::stdout().flush().unwrap();
    let mut input = String::new();
    io::stdin().read_line(&mut input).unwrap();
}
