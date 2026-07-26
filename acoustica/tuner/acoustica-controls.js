(() => {
  "use strict";

  const apiUrl = (path) => new URL(path, document.baseURI).toString();
  const state = {
    status: null,
    profiles: [],
    devices: [],
    currentDevice: null,
  };

  const panel = document.createElement("aside");
  panel.id = "acoustica-runtime-panel";
  panel.innerHTML = `
    <header class="acoustica-panel-header">
      <div>
        <strong>Acoustica runtime</strong>
        <span id="acoustica-runtime-summary">Checking…</span>
      </div>
      <button type="button" id="acoustica-panel-toggle" aria-expanded="true">Hide</button>
    </header>
    <div id="acoustica-panel-body">
      <div class="acoustica-status-grid">
        <div><span>Audio</span><strong id="acoustica-audio-state">Checking…</strong></div>
        <div><span>Home Assistant</span><strong id="acoustica-ha-state">Checking…</strong></div>
        <div><span>Current match</span><strong id="acoustica-match-state">None</strong></div>
        <div><span>Last detection</span><strong id="acoustica-last-detection">Never</strong></div>
      </div>
      <p id="acoustica-guidance" class="acoustica-guidance">Loading runtime health…</p>

      <section>
        <h3>Microphone</h3>
        <div class="acoustica-inline-controls">
          <select id="acoustica-device-select" aria-label="Microphone"></select>
          <button type="button" id="acoustica-device-apply">Apply</button>
        </div>
        <small>Changing the microphone reloads the audio engine without restarting the add-on.</small>
      </section>

      <section>
        <h3>Enable a saved profile</h3>
        <label class="acoustica-field">
          Home Assistant type
          <select id="acoustica-device-class">
            <option value="sound">Sound</option>
            <option value="smoke">Smoke</option>
            <option value="carbon_monoxide">Carbon monoxide</option>
            <option value="gas">Gas</option>
            <option value="safety">Safety</option>
            <option value="running">Running appliance</option>
            <option value="vibration">Vibration</option>
            <option value="problem">Problem</option>
            <option value="moisture">Moisture</option>
          </select>
        </label>
        <div id="acoustica-profile-list" class="acoustica-profile-list"></div>
      </section>

      <section>
        <h3>Live detectors</h3>
        <div id="acoustica-detector-list" class="acoustica-detector-list"></div>
      </section>

      <p id="acoustica-feedback" class="acoustica-feedback" role="status"></p>
    </div>
  `;
  document.body.appendChild(panel);

  const elements = {
    body: panel.querySelector("#acoustica-panel-body"),
    toggle: panel.querySelector("#acoustica-panel-toggle"),
    summary: panel.querySelector("#acoustica-runtime-summary"),
    audio: panel.querySelector("#acoustica-audio-state"),
    homeAssistant: panel.querySelector("#acoustica-ha-state"),
    match: panel.querySelector("#acoustica-match-state"),
    lastDetection: panel.querySelector("#acoustica-last-detection"),
    guidance: panel.querySelector("#acoustica-guidance"),
    deviceSelect: panel.querySelector("#acoustica-device-select"),
    deviceApply: panel.querySelector("#acoustica-device-apply"),
    deviceClass: panel.querySelector("#acoustica-device-class"),
    profileList: panel.querySelector("#acoustica-profile-list"),
    detectorList: panel.querySelector("#acoustica-detector-list"),
    feedback: panel.querySelector("#acoustica-feedback"),
  };

  function setFeedback(message, kind = "") {
    elements.feedback.textContent = message;
    elements.feedback.dataset.kind = kind;
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  function setHealthValue(element, text, kind) {
    element.textContent = text;
    element.dataset.kind = kind;
  }

  function renderStatus() {
    const status = state.status;
    if (!status) {
      setHealthValue(elements.audio, "Unavailable", "bad");
      setHealthValue(elements.homeAssistant, "Unavailable", "bad");
      elements.summary.textContent = "Runtime unavailable";
      elements.guidance.textContent = "Check the add-on logs and confirm the detector process is running.";
      return;
    }

    const runtimeState = status.state || "unknown";
    const audioKind = runtimeState === "listening" ? "good" : runtimeState === "reloading" || runtimeState === "starting" ? "warn" : "bad";
    setHealthValue(elements.audio, runtimeState, audioKind);

    const ha = status.home_assistant || {};
    const haConnected = Boolean(ha.connected);
    setHealthValue(
      elements.homeAssistant,
      haConnected ? "Connected" : `${ha.pending_updates || 0} queued`,
      haConnected ? "good" : "warn",
    );

    const matches = Array.isArray(status.active_matches) ? status.active_matches : [];
    setHealthValue(elements.match, matches.length ? matches.join(", ") : "None", matches.length ? "warn" : "good");

    const last = status.last_detection;
    elements.lastDetection.textContent = last && last.at ? new Date(last.at).toLocaleString() : "Never";
    elements.summary.textContent = `${(status.detectors || []).length} detector(s) · generation ${status.generation ?? 0}`;

    if (runtimeState === "listening" && haConnected) {
      elements.guidance.textContent = "Listening normally. Use the tuner below to record and validate a profile, then enable it here.";
    } else if (runtimeState === "reloading") {
      elements.guidance.textContent = "Applying the new detector or microphone selection…";
    } else if (!haConnected) {
      elements.guidance.textContent = "Detection continues locally. Home Assistant updates will retry automatically.";
    } else {
      elements.guidance.textContent = "Audio is not listening. Check the selected microphone and add-on logs.";
    }

    renderDetectors();
    renderProfiles();
  }

  function renderDetectors() {
    elements.detectorList.replaceChildren();
    const detectors = state.status && Array.isArray(state.status.detectors) ? state.status.detectors : [];
    if (!detectors.length) {
      const empty = document.createElement("p");
      empty.textContent = "No live detectors.";
      elements.detectorList.appendChild(empty);
      return;
    }
    for (const detector of detectors) {
      const row = document.createElement("div");
      row.className = "acoustica-detector-row";
      const name = document.createElement("strong");
      name.textContent = detector.name || "Unnamed detector";
      const detail = document.createElement("span");
      detail.textContent = `${detector.device_class || "sound"} · ${detector.source_kind || "unknown"}`;
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = detectors.length === 1 ? "Keep one detector" : "Disable";
      button.disabled = detectors.length === 1;
      button.addEventListener("click", () => disableDetector(detector, button));
      row.append(name, detail, button);
      elements.detectorList.appendChild(row);
    }
  }

  function activeProfileFiles() {
    const detectors = state.status && Array.isArray(state.status.detectors) ? state.status.detectors : [];
    return new Set(
      detectors
        .filter((item) => item.source_kind === "profile")
        .map((item) => String(item.source_value || "")),
    );
  }

  function renderProfiles() {
    elements.profileList.replaceChildren();
    if (!state.profiles.length) {
      const empty = document.createElement("p");
      empty.textContent = "No saved profiles yet. Complete the tuner steps and save one first.";
      elements.profileList.appendChild(empty);
      return;
    }

    const activeFiles = activeProfileFiles();
    for (const profile of state.profiles) {
      const row = document.createElement("div");
      row.className = "acoustica-profile-row";
      const name = document.createElement("span");
      name.textContent = profile;
      const button = document.createElement("button");
      const active = activeFiles.has(`${profile}.yaml`);
      button.type = "button";
      button.textContent = active ? "Enabled" : "Enable";
      button.disabled = active;
      button.addEventListener("click", () => activateProfile(profile, button));
      row.append(name, button);
      elements.profileList.appendChild(row);
    }
  }

  async function disableDetector(detector, button) {
    button.disabled = true;
    setFeedback(`Disabling ${detector.name || "detector"}…`);
    try {
      await fetchJson("api/acoustica/detectors/disable", {
        method: "POST",
        body: JSON.stringify({
          source_kind: detector.source_kind,
          source_value: detector.source_value,
        }),
      });
      setFeedback(`${detector.name || "Detector"} is disabled. Its Home Assistant entity is now unavailable.`, "good");
      await Promise.all([refreshStatus(), refreshProfiles()]);
    } catch (error) {
      setFeedback(error.message, "bad");
      button.disabled = false;
    }
  }

  async function activateProfile(profile, button) {
    button.disabled = true;
    setFeedback(`Enabling ${profile}…`);
    try {
      await fetchJson("api/acoustica/profiles/activate", {
        method: "POST",
        body: JSON.stringify({
          profile_id: profile,
          device_class: elements.deviceClass.value,
        }),
      });
      setFeedback(`${profile} is now live. Home Assistant will receive its clear state shortly.`, "good");
      await refreshStatus();
    } catch (error) {
      setFeedback(error.message, "bad");
      button.disabled = false;
    }
  }

  async function refreshStatus() {
    try {
      state.status = await fetchJson("api/acoustica/status");
    } catch (error) {
      state.status = null;
      setFeedback(error.message, "bad");
    }
    renderStatus();
  }

  async function refreshProfiles() {
    try {
      const payload = await fetchJson("profiles");
      state.profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    } catch (error) {
      state.profiles = [];
      setFeedback(error.message, "bad");
    }
    renderProfiles();
  }

  async function refreshDevices() {
    try {
      const payload = await fetchJson("api/acoustica/audio/devices");
      state.devices = Array.isArray(payload.devices) ? payload.devices : [];
      state.currentDevice = payload.current_index;
      elements.deviceSelect.replaceChildren();

      const defaultOption = document.createElement("option");
      defaultOption.value = "-1";
      defaultOption.textContent = "System default microphone";
      elements.deviceSelect.appendChild(defaultOption);

      for (const device of state.devices) {
        const option = document.createElement("option");
        option.value = String(device.index);
        option.textContent = `${device.name}${device.default ? " (default)" : ""}`;
        elements.deviceSelect.appendChild(option);
      }
      elements.deviceSelect.value = state.currentDevice == null ? "-1" : String(state.currentDevice);
    } catch (error) {
      elements.deviceSelect.replaceChildren();
      const option = document.createElement("option");
      option.textContent = "Microphones unavailable";
      option.value = "-1";
      elements.deviceSelect.appendChild(option);
      setFeedback(error.message, "bad");
    }
  }

  elements.deviceApply.addEventListener("click", async () => {
    const value = Number(elements.deviceSelect.value);
    elements.deviceApply.disabled = true;
    setFeedback("Applying microphone selection…");
    try {
      await fetchJson("api/acoustica/audio/select", {
        method: "POST",
        body: JSON.stringify({device_index: value === -1 ? null : value}),
      });
      setFeedback("Microphone applied. The audio engine is listening again.", "good");
      await Promise.all([refreshStatus(), refreshDevices()]);
    } catch (error) {
      setFeedback(error.message, "bad");
    } finally {
      elements.deviceApply.disabled = false;
    }
  });

  elements.toggle.addEventListener("click", () => {
    const collapsed = elements.body.hidden;
    elements.body.hidden = !collapsed;
    elements.toggle.textContent = collapsed ? "Hide" : "Show";
    elements.toggle.setAttribute("aria-expanded", String(collapsed));
  });

  Promise.all([refreshStatus(), refreshProfiles(), refreshDevices()]);
  window.setInterval(refreshStatus, 5000);
  window.setInterval(refreshProfiles, 10000);
})();
