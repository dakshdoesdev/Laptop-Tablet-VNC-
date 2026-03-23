use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const PROFILE_WRITE_ORDER: [&str; 9] = [
    "PROFILE_POSITION",
    "PROFILE_REFRESH",
    "PROFILE_FPS",
    "PROFILE_ALIGN",
    "PROFILE_MODE",
    "PROFILE_HOST",
    "PROFILE_WS_START",
    "PROFILE_WS_COUNT",
    "GUI_ENABLED",
];

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct CommandResult {
    ok: bool,
    code: i32,
    stdout: String,
    stderr: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct TabletStatus {
    key: String,
    title: String,
    name: String,
    running: bool,
    summary: String,
    details: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ProfileData {
    position: String,
    refresh: u32,
    fps: u32,
    align: String,
    mode: String,
    host: String,
    ws_start: u32,
    ws_count: u32,
    gui_enabled: bool,
}

#[derive(Clone)]
struct ProfileSpec {
    key: &'static str,
    title: &'static str,
    name: &'static str,
    script: PathBuf,
    profile_path: PathBuf,
    defaults: ProfileData,
}

fn home_path() -> PathBuf {
    env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/home/dux"))
}

fn stack_script_path() -> PathBuf {
    home_path().join(".local/bin/tablet-vnc-stack")
}

fn spec_for(key: &str) -> Option<ProfileSpec> {
    let home = home_path();
    match key {
        "usb" => Some(ProfileSpec {
            key: "usb",
            title: "USB Tablet",
            name: "Wacom Cintiq",
            script: home.join(".local/bin/tablet-vnc"),
            profile_path: home.join(".local/state/tablet-vnc/profile.env"),
            defaults: ProfileData {
                position: "left".to_string(),
                refresh: 60,
                fps: 30,
                align: "top".to_string(),
                mode: "adb".to_string(),
                host: "127.0.0.1".to_string(),
                ws_start: 7,
                ws_count: 3,
                gui_enabled: true,
            },
        }),
        "typec" => Some(ProfileSpec {
            key: "typec",
            title: "Type-C Tablet",
            name: "iPad Pro",
            script: home.join(".local/bin/tablet-vnc-top"),
            profile_path: home.join(".local/state/tablet-vnc-top/profile.env"),
            defaults: ProfileData {
                position: "top".to_string(),
                refresh: 60,
                fps: 30,
                align: "top".to_string(),
                mode: "tether".to_string(),
                host: "192.168.1.18".to_string(),
                ws_start: 9,
                ws_count: 1,
                gui_enabled: false,
            },
        }),
        _ => None,
    }
}

fn parse_bool(raw: Option<&String>, default_value: bool) -> bool {
    match raw.map(|value| value.to_ascii_lowercase()) {
        Some(value) if value == "1" || value == "true" || value == "yes" || value == "on" => true,
        Some(value) if value == "0" || value == "false" || value == "no" || value == "off" => false,
        _ => default_value,
    }
}

fn parse_u32(raw: Option<&String>, default_value: u32) -> u32 {
    raw.and_then(|value| value.parse::<u32>().ok())
        .unwrap_or(default_value)
}

fn read_env_file(path: &Path) -> BTreeMap<String, String> {
    let Ok(contents) = fs::read_to_string(path) else {
        return BTreeMap::new();
    };
    let mut values = BTreeMap::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if let Some((key, value)) = trimmed.split_once('=') {
            values.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    values
}

fn profile_to_map(profile: &ProfileData) -> BTreeMap<String, String> {
    let mut values = BTreeMap::new();
    values.insert("PROFILE_POSITION".to_string(), profile.position.clone());
    values.insert("PROFILE_REFRESH".to_string(), profile.refresh.to_string());
    values.insert("PROFILE_FPS".to_string(), profile.fps.to_string());
    values.insert("PROFILE_ALIGN".to_string(), profile.align.clone());
    values.insert("PROFILE_MODE".to_string(), profile.mode.clone());
    values.insert("PROFILE_HOST".to_string(), profile.host.clone());
    values.insert("PROFILE_WS_START".to_string(), profile.ws_start.to_string());
    values.insert("PROFILE_WS_COUNT".to_string(), profile.ws_count.to_string());
    values.insert(
        "GUI_ENABLED".to_string(),
        if profile.gui_enabled { "1" } else { "0" }.to_string(),
    );
    values
}

fn read_profile(spec: &ProfileSpec) -> ProfileData {
    let values = read_env_file(&spec.profile_path);
    ProfileData {
        position: values
            .get("PROFILE_POSITION")
            .cloned()
            .unwrap_or_else(|| spec.defaults.position.clone()),
        refresh: parse_u32(values.get("PROFILE_REFRESH"), spec.defaults.refresh),
        fps: parse_u32(values.get("PROFILE_FPS"), spec.defaults.fps),
        align: values
            .get("PROFILE_ALIGN")
            .cloned()
            .unwrap_or_else(|| spec.defaults.align.clone()),
        mode: values
            .get("PROFILE_MODE")
            .cloned()
            .unwrap_or_else(|| spec.defaults.mode.clone()),
        host: values
            .get("PROFILE_HOST")
            .cloned()
            .unwrap_or_else(|| spec.defaults.host.clone()),
        ws_start: parse_u32(values.get("PROFILE_WS_START"), spec.defaults.ws_start),
        ws_count: parse_u32(values.get("PROFILE_WS_COUNT"), spec.defaults.ws_count),
        gui_enabled: parse_bool(values.get("GUI_ENABLED"), spec.defaults.gui_enabled),
    }
}

fn write_profile(spec: &ProfileSpec, profile: &ProfileData) -> Result<(), String> {
    let mut merged = read_env_file(&spec.profile_path);
    for (key, value) in profile_to_map(profile) {
        merged.insert(key, value);
    }
    if let Some(parent) = spec.profile_path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "failed creating profile directory '{}': {err}",
                parent.display()
            )
        })?;
    }
    let mut lines = Vec::new();
    for key in PROFILE_WRITE_ORDER {
        let value = merged.get(key).cloned().unwrap_or_default();
        lines.push(format!("{key}={value}"));
    }
    for (key, value) in &merged {
        if PROFILE_WRITE_ORDER.contains(&key.as_str()) {
            continue;
        }
        lines.push(format!("{key}={value}"));
    }
    fs::write(&spec.profile_path, lines.join("\n") + "\n").map_err(|err| {
        format!(
            "failed writing profile '{}': {err}",
            spec.profile_path.display()
        )
    })
}

fn run_command(binary: &Path, args: &[&str]) -> CommandResult {
    if !binary.exists() {
        return CommandResult {
            ok: false,
            code: -1,
            stdout: String::new(),
            stderr: format!("missing executable: {}", binary.display()),
        };
    }
    let mut command = Command::new(binary);
    command.args(args);
    if env::var("DISPLAY").is_err() {
        command.env("DISPLAY", ":0");
    }
    if env::var("WAYLAND_DISPLAY").is_err() {
        command.env("WAYLAND_DISPLAY", "wayland-1");
    }
    if let Ok(runtime_dir) = env::var("XDG_RUNTIME_DIR") {
        command.env("XDG_RUNTIME_DIR", runtime_dir);
    }
    match command.output() {
        Ok(output) => CommandResult {
            ok: output.status.success(),
            code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(err) => CommandResult {
            ok: false,
            code: -1,
            stdout: String::new(),
            stderr: format!("failed to execute '{}': {err}", binary.display()),
        },
    }
}

fn format_details(result: &CommandResult) -> String {
    match (result.stdout.trim(), result.stderr.trim()) {
        ("", "") => String::new(),
        ("", stderr) => stderr.to_string(),
        (stdout, "") => stdout.to_string(),
        (stdout, stderr) => format!("{stdout}\n{stderr}"),
    }
}

fn status_for(spec: &ProfileSpec) -> TabletStatus {
    let result = run_command(&spec.script, &["status"]);
    let details = format_details(&result);
    let detail_upper = details.to_ascii_uppercase();
    let running = result.ok && detail_upper.contains("RUNNING");
    TabletStatus {
        key: spec.key.to_string(),
        title: spec.title.to_string(),
        name: spec.name.to_string(),
        running,
        summary: if running {
            "Active".to_string()
        } else {
            "Off".to_string()
        },
        details,
    }
}

#[tauri::command]
fn get_statuses() -> Result<Vec<TabletStatus>, String> {
    let usb = spec_for("usb").ok_or_else(|| "missing USB spec".to_string())?;
    let typec = spec_for("typec").ok_or_else(|| "missing Type-C spec".to_string())?;
    Ok(vec![status_for(&usb), status_for(&typec)])
}

#[tauri::command]
fn get_profile(key: String) -> Result<ProfileData, String> {
    let spec = spec_for(&key).ok_or_else(|| format!("unknown profile key: {key}"))?;
    Ok(read_profile(&spec))
}

#[tauri::command]
fn save_profile(key: String, profile: ProfileData) -> Result<CommandResult, String> {
    let spec = spec_for(&key).ok_or_else(|| format!("unknown profile key: {key}"))?;
    write_profile(&spec, &profile)?;
    Ok(CommandResult {
        ok: true,
        code: 0,
        stdout: format!("saved {key} profile"),
        stderr: String::new(),
    })
}

#[tauri::command]
fn stack_start() -> Result<CommandResult, String> {
    Ok(run_command(&stack_script_path(), &["start"]))
}

#[tauri::command]
fn stack_stop() -> Result<CommandResult, String> {
    Ok(run_command(&stack_script_path(), &["stop"]))
}

#[tauri::command]
fn profile_action(key: String, action: String) -> Result<CommandResult, String> {
    if !matches!(action.as_str(), "start" | "stop" | "status") {
        return Err(format!("unsupported action: {action}"));
    }
    let spec = spec_for(&key).ok_or_else(|| format!("unknown profile key: {key}"))?;
    Ok(run_command(&spec.script, &[action.as_str()]))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            get_statuses,
            get_profile,
            save_profile,
            stack_start,
            stack_stop,
            profile_action,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
