import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import "./App.css";

type TabletKey = "usb" | "typec";
type View = "dashboard" | "usb_profile" | "typec_profile" | "diagnostics";

interface CommandResult {
  ok: boolean;
  code: number;
  stdout: string;
  stderr: string;
}

interface TabletStatus {
  key: TabletKey;
  title: string;
  name: string;
  running: boolean;
  summary: string;
  details: string;
}

interface ProfileData {
  position: string;
  refresh: number;
  fps: number;
  align: string;
  mode: string;
  host: string;
  wsStart: number;
  wsCount: number;
  guiEnabled: boolean;
}

const PROFILE_META: Record<
  TabletKey,
  { label: string; subtitle: string; accent: "usb" | "typec"; interfaceLabel: string }
> = {
  usb: {
    label: "USB Tablet",
    subtitle: "Wacom Cintiq",
    accent: "usb",
    interfaceLabel: "USB 3.0",
  },
  typec: {
    label: "Type-C Tablet",
    subtitle: "iPad Pro",
    accent: "typec",
    interfaceLabel: "Type-C",
  },
};

const INITIAL_PROFILES: Record<TabletKey, ProfileData> = {
  usb: {
    position: "left",
    refresh: 60,
    fps: 30,
    align: "top",
    mode: "adb",
    host: "127.0.0.1",
    wsStart: 7,
    wsCount: 3,
    guiEnabled: true,
  },
  typec: {
    position: "top",
    refresh: 60,
    fps: 30,
    align: "top",
    mode: "tether",
    host: "192.168.1.18",
    wsStart: 9,
    wsCount: 1,
    guiEnabled: false,
  },
};

function stamp(message: string) {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `[${hh}:${mm}:${ss}] ${message}`;
}

function commandSummary(result: CommandResult) {
  if (result.stdout) return result.stdout;
  if (result.stderr) return result.stderr;
  return result.ok ? "ok" : "command failed";
}

function resolutionFromDetails(details: string) {
  const match = details.match(/resolution:\s*(.+)/i);
  if (match?.[1]) return match[1].trim();
  return "1280x800 @60Hz";
}

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [profiles, setProfiles] =
    useState<Record<TabletKey, ProfileData>>(INITIAL_PROFILES);
  const [statuses, setStatuses] = useState<Record<TabletKey, TabletStatus | null>>({
    usb: null,
    typec: null,
  });
  const [logs, setLogs] = useState<string[]>([]);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  function addLog(message: string) {
    setLogs((prev) => [stamp(message), ...prev].slice(0, 220));
  }

  async function refreshStatuses() {
    try {
      const next = await invoke<TabletStatus[]>("get_statuses");
      const normalized: Record<TabletKey, TabletStatus | null> = { usb: null, typec: null };
      for (const status of next) {
        if (status.key === "usb" || status.key === "typec") {
          normalized[status.key] = status;
        }
      }
      setStatuses(normalized);
    } catch (error) {
      addLog(`status refresh failed: ${String(error)}`);
    }
  }

  async function loadProfiles() {
    try {
      const [usb, typec] = await Promise.all([
        invoke<ProfileData>("get_profile", { key: "usb" }),
        invoke<ProfileData>("get_profile", { key: "typec" }),
      ]);
      setProfiles({ usb, typec });
    } catch (error) {
      addLog(`profile load failed: ${String(error)}`);
    }
  }

  async function runStack(action: "start" | "stop") {
    const command = action === "start" ? "stack_start" : "stack_stop";
    setBusyAction(command);
    try {
      const result = await invoke<CommandResult>(command);
      addLog(`stack ${action}: ${commandSummary(result)}`);
      await refreshStatuses();
    } catch (error) {
      addLog(`stack ${action} failed: ${String(error)}`);
    } finally {
      setBusyAction(null);
    }
  }

  async function runProfileAction(key: TabletKey, action: "start" | "stop" | "status") {
    const token = `${key}-${action}`;
    setBusyAction(token);
    try {
      const result = await invoke<CommandResult>("profile_action", { key, action });
      addLog(`${key} ${action}: ${commandSummary(result)}`);
      await refreshStatuses();
    } catch (error) {
      addLog(`${key} ${action} failed: ${String(error)}`);
    } finally {
      setBusyAction(null);
    }
  }

  async function saveProfile(key: TabletKey) {
    const token = `save-${key}`;
    setBusyAction(token);
    try {
      const result = await invoke<CommandResult>("save_profile", {
        key,
        profile: profiles[key],
      });
      addLog(`${key} profile: ${commandSummary(result)}`);
    } catch (error) {
      addLog(`${key} profile save failed: ${String(error)}`);
    } finally {
      setBusyAction(null);
    }
  }

  function updateProfile<K extends keyof ProfileData>(
    key: TabletKey,
    field: K,
    value: ProfileData[K],
  ) {
    setProfiles((prev) => ({
      ...prev,
      [key]: {
        ...prev[key],
        [field]: value,
      },
    }));
  }

  useEffect(() => {
    let active = true;
    const boot = async () => {
      await Promise.all([loadProfiles(), refreshStatuses()]);
      if (active) setIsBootstrapping(false);
    };
    void boot();
    const timer = window.setInterval(() => {
      void refreshStatuses();
    }, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const daemonRunning = useMemo(
    () => Object.values(statuses).some((status) => Boolean(status?.running)),
    [statuses],
  );

  const renderProfileEditor = (key: TabletKey) => {
    const profile = profiles[key];
    const meta = PROFILE_META[key];
    const status = statuses[key];
    const saving = busyAction === `save-${key}`;
    return (
      <section className="panel-grid">
        <article className="card wide">
          <div className="card-header">
            <div>
              <h3>{meta.label} Profile</h3>
              <p>{meta.subtitle}</p>
            </div>
            <span className={`status-pill ${status?.running ? "on" : "off"}`}>
              {status?.summary ?? "Unknown"}
            </span>
          </div>

          <div className="field-grid">
            <label className="field">
              <span>Connection Mode</span>
              <div className="segmented">
                <button
                  className={profile.mode === "adb" ? "active" : ""}
                  onClick={() => updateProfile(key, "mode", "adb")}
                  type="button"
                >
                  ADB Reverse
                </button>
                <button
                  className={profile.mode === "tether" ? "active" : ""}
                  onClick={() => updateProfile(key, "mode", "tether")}
                  type="button"
                >
                  USB Tether
                </button>
              </div>
            </label>

            <label className="field">
              <span>Framerate</span>
              <div className="segmented">
                <button
                  className={profile.fps === 30 ? "active" : ""}
                  onClick={() => updateProfile(key, "fps", 30)}
                  type="button"
                >
                  30 FPS
                </button>
                <button
                  className={profile.fps === 60 ? "active" : ""}
                  onClick={() => updateProfile(key, "fps", 60)}
                  type="button"
                >
                  60 FPS
                </button>
              </div>
            </label>

            <label className="field">
              <span>Display Refresh ({profile.refresh} Hz)</span>
              <input
                max={60}
                min={30}
                onChange={(event) => updateProfile(key, "refresh", Number(event.currentTarget.value))}
                step={30}
                type="range"
                value={profile.refresh}
              />
            </label>

            <label className="field">
              <span>Workspace Start</span>
              <input
                min={1}
                onChange={(event) =>
                  updateProfile(key, "wsStart", Number(event.currentTarget.value))
                }
                type="number"
                value={profile.wsStart}
              />
            </label>

            <label className="field">
              <span>Workspace Count</span>
              <input
                min={1}
                onChange={(event) =>
                  updateProfile(key, "wsCount", Number(event.currentTarget.value))
                }
                type="number"
                value={profile.wsCount}
              />
            </label>

            <label className="field">
              <span>Host</span>
              <input
                onChange={(event) => updateProfile(key, "host", event.currentTarget.value)}
                type="text"
                value={profile.host}
              />
            </label>

            <label className="field checkbox">
              <input
                checked={profile.guiEnabled}
                onChange={(event) => updateProfile(key, "guiEnabled", event.currentTarget.checked)}
                type="checkbox"
              />
              <span>Enable GUI integration</span>
            </label>
          </div>

          <div className="button-row">
            <button
              className="btn primary"
              disabled={saving}
              onClick={() => {
                void saveProfile(key);
              }}
              type="button"
            >
              {saving ? "Saving..." : `Save ${meta.label}`}
            </button>
            <button
              className="btn subtle"
              disabled={busyAction === `${key}-status`}
              onClick={() => {
                void runProfileAction(key, "status");
              }}
              type="button"
            >
              Refresh Status
            </button>
          </div>
        </article>
      </section>
    );
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <header className="brand">
          <h1>VNC Manager</h1>
          <p>Tauri + React Control Surface</p>
        </header>

        <nav className="nav">
          <button
            className={view === "dashboard" ? "active" : ""}
            onClick={() => setView("dashboard")}
            type="button"
          >
            Dashboard
          </button>
          <button
            className={view === "usb_profile" ? "active" : ""}
            onClick={() => setView("usb_profile")}
            type="button"
          >
            USB Profile
          </button>
          <button
            className={view === "typec_profile" ? "active" : ""}
            onClick={() => setView("typec_profile")}
            type="button"
          >
            Type-C Profile
          </button>
          <button
            className={view === "diagnostics" ? "active" : ""}
            onClick={() => setView("diagnostics")}
            type="button"
          >
            Diagnostics
          </button>
        </nav>

        <div className="daemon-card">
          <p className="label">Daemon Status</p>
          <p className={`daemon-state ${daemonRunning ? "on" : "off"}`}>
            {daemonRunning ? "Running" : "Stopped"}
          </p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h2>
              {view === "dashboard" && "Dashboard"}
              {view === "usb_profile" && "USB Profile"}
              {view === "typec_profile" && "Type-C Profile"}
              {view === "diagnostics" && "Diagnostics"}
            </h2>
            <p>Dual tablet orchestration on Hyprland/Wayland</p>
          </div>
          <div className="button-row">
            <button
              className="btn subtle"
              disabled={busyAction === "stack-stop"}
              onClick={() => {
                void runStack("stop");
              }}
              type="button"
            >
              Stop Stack
            </button>
            <button
              className="btn primary"
              disabled={busyAction === "stack-start"}
              onClick={() => {
                void runStack("start");
              }}
              type="button"
            >
              Start Stack
            </button>
          </div>
        </header>

        {isBootstrapping ? (
          <section className="panel-grid">
            <article className="card wide">
              <h3>Initializing</h3>
              <p>Loading profiles and current tablet status...</p>
            </article>
          </section>
        ) : (
          <>
            {view === "dashboard" && (
              <section className="panel-grid">
                {(["usb", "typec"] as TabletKey[]).map((key) => {
                  const status = statuses[key];
                  const meta = PROFILE_META[key];
                  return (
                    <article className="card" key={key}>
                      <div className="card-header">
                        <div>
                          <h3>{meta.subtitle}</h3>
                          <p>{meta.label}</p>
                        </div>
                        <span className={`status-pill ${status?.running ? "on" : "off"}`}>
                          {status?.summary ?? "Unknown"}
                        </span>
                      </div>
                      <div className="metrics">
                        <div>
                          <span>Interface</span>
                          <strong className={meta.accent}>{meta.interfaceLabel}</strong>
                        </div>
                        <div>
                          <span>Resolution</span>
                          <strong>{resolutionFromDetails(status?.details ?? "")}</strong>
                        </div>
                      </div>
                      <div className="button-row">
                        <button
                          className="btn subtle"
                          disabled={busyAction === `${key}-stop`}
                          onClick={() => {
                            void runProfileAction(key, "stop");
                          }}
                          type="button"
                        >
                          Stop
                        </button>
                        <button
                          className="btn primary"
                          disabled={busyAction === `${key}-start`}
                          onClick={() => {
                            void runProfileAction(key, "start");
                          }}
                          type="button"
                        >
                          Start
                        </button>
                      </div>
                    </article>
                  );
                })}

                <article className="card wide">
                  <div className="card-header">
                    <div>
                      <h3>System Info</h3>
                      <p>Host runtime and hardware profile</p>
                    </div>
                  </div>
                  <div className="metrics">
                    <div>
                      <span>Host</span>
                      <strong>Hyprland / Wayland</strong>
                    </div>
                    <div>
                      <span>GPU</span>
                      <strong className="cyan">RTX 3050 Mobile</strong>
                    </div>
                    <div>
                      <span>Control Plane</span>
                      <strong className="mono">tablet-vnc-stack</strong>
                    </div>
                  </div>
                </article>
              </section>
            )}

            {view === "usb_profile" && renderProfileEditor("usb")}
            {view === "typec_profile" && renderProfileEditor("typec")}

            {view === "diagnostics" && (
              <section className="panel-grid">
                <article className="card wide">
                  <div className="card-header">
                    <div>
                      <h3>Command Logs</h3>
                      <p>Recent Tauri command output and status checks</p>
                    </div>
                    <div className="button-row">
                      <button
                        className="btn subtle"
                        onClick={() => setLogs([])}
                        type="button"
                      >
                        Clear
                      </button>
                      <button
                        className="btn primary"
                        onClick={() => {
                          void refreshStatuses();
                        }}
                        type="button"
                      >
                        Poll Status
                      </button>
                    </div>
                  </div>
                  <pre className="logs">
                    {logs.length > 0
                      ? logs.join("\n")
                      : "No logs yet. Run stack/profile actions to populate diagnostics."}
                  </pre>
                </article>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
