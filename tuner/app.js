const recorder = new AddonRecorder();
let meterTimer = null;
let latestAnalysis = null;
let testTimer = null;
let activeSelection = null;
let activationCategoryInitialized = false;

const elements = {
  serviceStatus: document.getElementById("serviceStatus"),
  refreshStatus: document.getElementById("refreshStatus"),
  runtimeListening: document.getElementById("runtimeListening"),
  runtimeHomeAssistant: document.getElementById("runtimeHomeAssistant"),
  runtimeAlarmState: document.getElementById("runtimeAlarmState"),
  runtimeLastDetection: document.getElementById("runtimeLastDetection"),
  runtimeGuidance: document.getElementById("runtimeGuidance"),
  profileId: document.getElementById("profileId"),
  microphoneSelect: document.getElementById("microphoneSelect"),
  refreshMicrophones: document.getElementById("refreshMicrophones"),
  applyMicrophone: document.getElementById("applyMicrophone"),
  microphoneStatus: document.getElementById("microphoneStatus"),
  recordButton: document.getElementById("recordButton"),
  stopButton: document.getElementById("stopButton"),
  playButton: document.getElementById("playButton"),
  analyzeButton: document.getElementById("analyzeButton"),
  levelBar: document.getElementById("levelBar"),
  recordingStatus: document.getElementById("recordingStatus"),
  analysisPanel: document.getElementById("analysisPanel"),
  qualityBadge: document.getElementById("qualityBadge"),
  messageList: document.getElementById("messageList"),
  metrics: document.getElementById("metrics"),
  yamlOutput: document.getElementById("yamlOutput"),
  copyYamlButton: document.getElementById("copyYamlButton"),
  acceptReview: document.getElementById("acceptReview"),
  overwriteProfile: document.getElementById("overwriteProfile"),
  saveButton: document.getElementById("saveButton"),
  saveResult: document.getElementById("saveResult"),
  refreshProfiles: document.getElementById("refreshProfiles"),
  profileList: document.getElementById("profileList"),
  activeProfile: document.getElementById("activeProfile"),
  activationStatus: document.getElementById("activationStatus"),
  activationCategory: document.getElementById("activationCategory"),
  testPanel: document.getElementById("testPanel"),
  testTitle: document.getElementById("testTitle"),
  testStatus: document.getElementById("testStatus"),
  stopTestButton: document.getElementById("stopTestButton"),
  importFile: document.getElementById("importFile"),
  importId: document.getElementById("importId"),
  importButton: document.getElementById("importButton"),
};

function profileId() {
  return elements.profileId.value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function setBusy(button, busy, label) {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.label;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({ error: "Invalid server response" }));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function checkHealth() {
  try {
    const health = await fetchJson("api/health");
    activeSelection = health.active_profile;
    renderActiveSelection();
    renderRuntimeStatus(health.runtime);
    elements.serviceStatus.textContent = `Ready · v${health.version}`;
    elements.serviceStatus.className = "status status-ready";
  } catch (error) {
    elements.serviceStatus.textContent = "Setup service unavailable";
    elements.serviceStatus.className = "status status-error";
    renderRuntimeStatus(null);
  }
}

function setRuntimeValue(element, text, className) {
  element.textContent = text;
  element.className = className;
}

function renderRuntimeStatus(runtime) {
  if (!runtime) {
    setRuntimeValue(elements.runtimeListening, "Unavailable", "status-bad");
    setRuntimeValue(elements.runtimeHomeAssistant, "Unknown", "status-bad");
    setRuntimeValue(elements.runtimeAlarmState, "Unknown", "status-bad");
    elements.runtimeLastDetection.textContent = "Unknown";
    elements.runtimeGuidance.textContent =
      "The setup service is unavailable. Check whether the add-on is running.";
    return;
  }

  if (runtime.listening) {
    setRuntimeValue(elements.runtimeListening, "Listening", "status-good");
  } else if (runtime.ready) {
    setRuntimeValue(elements.runtimeListening, "Starting", "status-warning");
  } else {
    setRuntimeValue(elements.runtimeListening, "Audio unavailable", "status-bad");
  }

  const homeAssistant = runtime.home_assistant || {};
  if (homeAssistant.connected) {
    setRuntimeValue(elements.runtimeHomeAssistant, "Connected", "status-good");
  } else {
    const pending = homeAssistant.pending_updates || 0;
    setRuntimeValue(
      elements.runtimeHomeAssistant,
      pending ? `Reconnecting · ${pending} queued` : "Reconnecting",
      "status-warning",
    );
  }

  const activeDetector = (runtime.detectors || []).find((item) => item.active);
  if (activeDetector) {
    setRuntimeValue(
      elements.runtimeAlarmState,
      `Detected · ${activeDetector.profile_id}`,
      "status-bad",
    );
  } else {
    setRuntimeValue(elements.runtimeAlarmState, "Clear", "status-good");
  }

  if (runtime.last_detection?.detected_at) {
    const timestamp = new Date(runtime.last_detection.detected_at);
    elements.runtimeLastDetection.textContent = Number.isNaN(timestamp.getTime())
      ? runtime.last_detection.detected_at
      : timestamp.toLocaleString();
  } else {
    elements.runtimeLastDetection.textContent = "None recorded";
  }

  if (!runtime.ready) {
    elements.runtimeGuidance.textContent =
      "Audio could not be opened. Refresh the microphone list, select an input, and check the add-on logs.";
  } else if (!runtime.listening) {
    elements.runtimeGuidance.textContent =
      "The audio stream is starting. Refresh in a moment; persistent startup means the input could not be opened.";
  } else if (!homeAssistant.connected) {
    elements.runtimeGuidance.textContent =
      "Detection continues locally while Home Assistant reconnects. Only the newest state is retained for delivery.";
  } else if (activeDetector) {
    elements.runtimeGuidance.textContent =
      "An alarm pattern is currently matched. Verify the physical alarm and follow your safety plan.";
  } else {
    elements.runtimeGuidance.textContent =
      "The detector is listening normally and Home Assistant state delivery is connected.";
  }
}

function renderActiveSelection(message = null) {
  if (!activeSelection || !activeSelection.ready) {
    elements.activeProfile.textContent = "No active profile";
    elements.activationStatus.textContent =
      message || "The detector runtime is not ready for profile activation.";
    return;
  }

  const labels = {
    smoke: "Smoke alarm",
    co: "CO alarm",
    safety: "Other safety alarm",
  };
  elements.activeProfile.textContent =
    `${activeSelection.profile_id} · ${labels[activeSelection.alarm_type] || activeSelection.alarm_type}`;
  if (
    labels[activeSelection.alarm_type] &&
    !activationCategoryInitialized
  ) {
    elements.activationCategory.value = activeSelection.alarm_type;
    activationCategoryInitialized = true;
  }
  elements.activationStatus.textContent =
    message ||
    `Detector ${activeSelection.device_name} is listening with this profile.`;
}

async function loadMicrophones() {
  elements.microphoneSelect.disabled = true;
  elements.applyMicrophone.disabled = true;
  elements.microphoneStatus.textContent = "Loading microphones…";

  try {
    const status = await fetchJson("api/audio/devices");
    const options = [];
    const defaultOption = document.createElement("option");
    defaultOption.value = "default";
    defaultOption.textContent = "System default microphone";
    defaultOption.selected = status.current_index === null;
    options.push(defaultOption);

    for (const device of status.devices) {
      const option = document.createElement("option");
      option.value = String(device.index);
      option.textContent =
        `${device.name} · ${device.channels} channel${device.channels === 1 ? "" : "s"}` +
        `${device.default ? " · default" : ""}`;
      option.selected = device.index === status.current_index;
      options.push(option);
    }

    if (
      status.current_index !== null &&
      !status.devices.some((device) => device.index === status.current_index)
    ) {
      const unavailable = document.createElement("option");
      unavailable.value = String(status.current_index);
      unavailable.textContent = `Configured microphone ${status.current_index} · unavailable`;
      unavailable.selected = true;
      unavailable.disabled = true;
      options.push(unavailable);
    }

    elements.microphoneSelect.replaceChildren(...options);
    elements.microphoneSelect.disabled = false;
    elements.applyMicrophone.disabled = false;
    elements.microphoneStatus.textContent = status.devices.length
      ? "Select the microphone connected to the Home Assistant host. Applying a change restarts the add-on."
      : "No named input devices were reported. The system default may still work through Home Assistant audio.";
  } catch (error) {
    elements.microphoneSelect.replaceChildren();
    elements.microphoneStatus.textContent = `Could not list microphones: ${error.message}`;
  }
}

async function applyMicrophone() {
  const selected = elements.microphoneSelect.value;
  setBusy(elements.applyMicrophone, true, "Saving…");
  try {
    await fetchJson(
      `api/audio/select?device_index=${encodeURIComponent(selected)}`,
      { method: "POST" },
    );
    elements.microphoneStatus.textContent =
      "Microphone saved. The add-on is restarting; reopen this Web UI after it reconnects.";
    elements.microphoneSelect.disabled = true;
  } catch (error) {
    elements.microphoneStatus.textContent = `Could not select microphone: ${error.message}`;
    setBusy(elements.applyMicrophone, false, "Saving…");
  }
}

async function updateMeter() {
  try {
    await recorder.refresh();
    elements.levelBar.style.width = `${Math.round(recorder.level * 100)}%`;
    elements.recordingStatus.textContent = `Recording add-on microphone… ${recorder.duration.toFixed(1)} seconds`;
    if (!recorder.state.recording) {
      await stopRecording();
      return;
    }
  } catch (error) {
    elements.recordingStatus.textContent = `Could not read microphone status: ${error.message}`;
  }
  meterTimer = setTimeout(updateMeter, 250);
}

async function startRecording() {
  try {
    await recorder.start();
    latestAnalysis = null;
    elements.analysisPanel.classList.add("hidden");
    elements.saveResult.classList.add("hidden");
    elements.recordButton.disabled = true;
    elements.stopButton.disabled = false;
    elements.playButton.disabled = true;
    elements.analyzeButton.disabled = true;
    updateMeter();
  } catch (error) {
    elements.recordingStatus.textContent = `Microphone error: ${error.message}`;
  }
}

async function stopRecording() {
  await recorder.stop();
  if (meterTimer) clearTimeout(meterTimer);
  meterTimer = null;
  elements.levelBar.style.width = "0%";
  elements.recordButton.disabled = false;
  elements.stopButton.disabled = true;
  elements.playButton.disabled = !recorder.hasRecording();
  elements.analyzeButton.disabled = !recorder.hasRecording();
  elements.recordingStatus.textContent = recorder.hasRecording()
    ? `Captured ${recorder.duration.toFixed(1)} seconds. Ready to analyze.`
    : "No recording captured.";
}

function renderAnalysis(analysis) {
  latestAnalysis = analysis;
  elements.analysisPanel.classList.remove("hidden");
  elements.qualityBadge.textContent = analysis.quality;
  elements.qualityBadge.className = `quality quality-${analysis.quality}`;
  elements.messageList.replaceChildren(
    ...analysis.messages.map((message) => {
      const item = document.createElement("li");
      item.textContent = message;
      return item;
    }),
  );

  const metrics = [
    ["Duration", `${analysis.metrics.duration_seconds.toFixed(1)} s`],
    ["Peak level", `${Math.round(analysis.metrics.peak_ratio * 100)}%`],
    ["Clipping", `${(analysis.metrics.clipping_ratio * 100).toFixed(2)}%`],
    ["Learned tones", String(analysis.profile.tone_count)],
  ];
  elements.metrics.replaceChildren(
    ...metrics.flatMap(([name, value]) => {
      const term = document.createElement("dt");
      term.textContent = name;
      const description = document.createElement("dd");
      description.textContent = value;
      return [term, description];
    }),
  );
  elements.yamlOutput.textContent = analysis.yaml;
  elements.acceptReview.checked = false;
  elements.acceptReview.disabled = analysis.quality !== "review";
  elements.saveButton.disabled = analysis.quality === "poor";
}

async function analyzeRecording() {
  const id = profileId();
  if (!id) {
    elements.recordingStatus.textContent = "Enter a valid profile ID first.";
    elements.profileId.focus();
    return;
  }
  elements.profileId.value = id;
  setBusy(elements.analyzeButton, true, "Analyzing…");
  try {
    const analysis = await fetchJson(
      `api/analyze?profile_id=${encodeURIComponent(id)}`,
      { method: "POST" },
    );
    renderAnalysis(analysis);
  } catch (error) {
    elements.recordingStatus.textContent = `Analysis failed: ${error.message}`;
  } finally {
    setBusy(elements.analyzeButton, false, "Analyzing…");
    elements.analyzeButton.disabled = !recorder.hasRecording();
  }
}

async function saveProfile() {
  if (!latestAnalysis) return;
  const id = profileId();
  const query = new URLSearchParams({ profile_id: id });
  if (elements.acceptReview.checked) query.set("accept_review", "true");
  if (elements.overwriteProfile.checked) query.set("overwrite", "true");

  setBusy(elements.saveButton, true, "Saving…");
  try {
    const result = await fetchJson(`api/learn?${query}`, {
      method: "POST",
    });
    elements.saveResult.classList.remove("hidden");
    elements.saveResult.innerHTML = "";
    const heading = document.createElement("strong");
    heading.textContent = `Saved ${result.profile_id}.`;
    const instructions = document.createElement("p");
    instructions.textContent =
      "Use Live test below, then select a Home Assistant category and activate " +
      "the profile. Home Assistant will offer the detector for confirmation.";
    elements.saveResult.append(heading, instructions);
    await loadProfiles();
  } catch (error) {
    elements.saveResult.classList.remove("hidden");
    elements.saveResult.textContent = `Could not save: ${error.message}`;
  } finally {
    setBusy(elements.saveButton, false, "Saving…");
    elements.saveButton.disabled = latestAnalysis.quality === "poor";
  }
}

async function loadProfiles() {
  try {
    const profiles = await fetchJson("api/profiles");
    if (!profiles.length) {
      elements.profileList.innerHTML = '<p class="helper">No saved profiles yet.</p>';
      return;
    }

    elements.profileList.replaceChildren(
      ...profiles.map((profile) => {
        const row = document.createElement("article");
        row.className = "profile-row";
        const info = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = profile.profile_id;
        const summary = document.createElement("span");
        summary.textContent = `${profile.tone_count} tones · ${profile.confirmation_cycles} confirmations`;
        info.append(name, summary);

        const isActiveProfile =
          Boolean(activeSelection?.ready) &&
          activeSelection.profile_id === profile.profile_id;
        if (isActiveProfile) {
          const badge = document.createElement("span");
          badge.className = "status status-ready";
          badge.textContent = "Active";
          info.append(badge);
        }

        const actions = document.createElement("div");
        const use = document.createElement("button");
        use.textContent = "Use ID";
        use.addEventListener("click", () => {
          elements.profileId.value = profile.profile_id;
          elements.profileId.scrollIntoView({ behavior: "smooth", block: "center" });
        });
        const test = document.createElement("button");
        test.textContent = "Live test";
        test.addEventListener("click", () => startProfileTest(profile.profile_id));
        const activate = document.createElement("button");
        const isCurrentSelection =
          isActiveProfile &&
          activeSelection.alarm_type === elements.activationCategory.value;
        activate.textContent = isCurrentSelection
          ? "Active"
          : isActiveProfile
            ? "Apply category"
            : "Activate";
        activate.className = isCurrentSelection ? "" : "primary";
        activate.disabled = isCurrentSelection;
        activate.addEventListener("click", () => activateProfile(profile.profile_id));

        const remove = document.createElement("button");
        remove.textContent = "Delete";
        remove.className = "danger";
        remove.disabled = isActiveProfile;
        remove.title = isActiveProfile
          ? "Activate a different profile before deleting this one"
          : "Delete this saved profile";
        remove.addEventListener("click", () => deleteProfile(profile.profile_id));
        actions.append(use, test, activate, remove);
        row.append(info, actions);
        return row;
      }),
    );
  } catch (error) {
    elements.profileList.textContent = `Could not load profiles: ${error.message}`;
  }
}

async function activateProfile(id) {
  const alarmType = elements.activationCategory.value;
  elements.activationStatus.textContent = `Activating ${id}…`;
  try {
    const result = await fetchJson(
      `api/profiles/${encodeURIComponent(id)}/activate?alarm_type=${encodeURIComponent(alarmType)}`,
      { method: "POST" },
    );
    activeSelection = result;
    renderActiveSelection(
      result.activated
        ? "Activated immediately. Home Assistant will update an existing discovered entry or offer a confirmation."
        : "This profile and category were already active.",
    );
    await loadProfiles();
  } catch (error) {
    elements.activationStatus.textContent = `Activation failed: ${error.message}`;
  }
}

async function startProfileTest(id) {
  if (testTimer) clearTimeout(testTimer);
  try {
    const status = await fetchJson(
      `api/test/start?profile_id=${encodeURIComponent(id)}`,
      { method: "POST" },
    );
    elements.testPanel.classList.remove("hidden");
    elements.testTitle.textContent = `Testing ${id}`;
    renderTestStatus(status);
    pollProfileTest();
  } catch (error) {
    alert(`Could not start live test: ${error.message}`);
  }
}

async function pollProfileTest() {
  try {
    const status = await fetchJson("api/test/status");
    renderTestStatus(status);
    if (status.matched && status.testing) {
      await stopProfileTest();
      return;
    }
    if (status.testing) {
      testTimer = setTimeout(pollProfileTest, 500);
    }
  } catch (error) {
    elements.testStatus.textContent = `Could not read test status: ${error.message}`;
  }
}

function renderTestStatus(status) {
  if (status.error) {
    elements.testStatus.textContent = `Test failed: ${status.error}`;
    elements.testPanel.className = "live-test test-error";
    return;
  }
  if (status.matched) {
    elements.testStatus.textContent =
      `Match detected after ${status.duration_seconds.toFixed(1)} seconds. ` +
      "This test did not publish a Home Assistant alarm.";
    elements.testPanel.className = "live-test test-success";
    return;
  }
  if (status.testing) {
    elements.testStatus.textContent =
      `Listening… ${status.duration_seconds.toFixed(1)} / ${status.max_seconds.toFixed(0)} seconds. ` +
      "Activate the alarm test now.";
    elements.testPanel.className = "live-test";
    return;
  }
  elements.testStatus.textContent = "Test stopped without a match.";
  elements.testPanel.className = "live-test";
}

async function stopProfileTest() {
  if (testTimer) clearTimeout(testTimer);
  testTimer = null;
  try {
    const status = await fetchJson("api/test/stop", { method: "POST" });
    renderTestStatus(status);
  } catch (error) {
    elements.testStatus.textContent = `Could not stop test: ${error.message}`;
  }
}

async function deleteProfile(id) {
  if (!confirm(`Delete profile “${id}”?`)) return;
  try {
    await fetchJson(`api/profiles/${encodeURIComponent(id)}`, { method: "DELETE" });
    await loadProfiles();
  } catch (error) {
    alert(`Could not delete profile: ${error.message}`);
  }
}

async function importProfile() {
  const file = elements.importFile.files[0];
  if (!file) {
    alert("Choose a YAML profile first.");
    return;
  }
  const query = new URLSearchParams();
  const id = elements.importId.value.trim();
  if (id) query.set("profile_id", id);
  if (elements.overwriteProfile.checked) query.set("overwrite", "true");

  setBusy(elements.importButton, true, "Importing…");
  try {
    const result = await fetchJson(`api/import?${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/yaml" },
      body: await file.text(),
    });
    elements.profileId.value = result.profile_id;
    elements.importFile.value = "";
    elements.importId.value = "";
    await loadProfiles();
  } catch (error) {
    alert(`Import failed: ${error.message}`);
  } finally {
    setBusy(elements.importButton, false, "Importing…");
  }
}

elements.refreshStatus.addEventListener("click", checkHealth);
elements.refreshMicrophones.addEventListener("click", loadMicrophones);
elements.applyMicrophone.addEventListener("click", applyMicrophone);
elements.recordButton.addEventListener("click", startRecording);
elements.stopButton.addEventListener("click", stopRecording);
elements.playButton.addEventListener("click", () => recorder.play());
elements.analyzeButton.addEventListener("click", analyzeRecording);
elements.saveButton.addEventListener("click", saveProfile);
elements.refreshProfiles.addEventListener("click", loadProfiles);
elements.importButton.addEventListener("click", importProfile);
elements.stopTestButton.addEventListener("click", stopProfileTest);
elements.activationCategory.addEventListener("change", loadProfiles);
elements.copyYamlButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(elements.yamlOutput.textContent);
  elements.copyYamlButton.textContent = "Copied";
  setTimeout(() => (elements.copyYamlButton.textContent = "Copy YAML"), 1200);
});
elements.profileId.addEventListener("blur", () => {
  const id = profileId();
  if (id) elements.profileId.value = id;
});

async function initialize() {
  await checkHealth();
  await Promise.all([loadMicrophones(), loadProfiles()]);
}

initialize();
setInterval(checkHealth, 5000);
