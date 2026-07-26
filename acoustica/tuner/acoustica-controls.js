(() => {
  "use strict";

  const apiUrl = (path) => new URL(path, document.baseURI).toString();
  const categories = [
    {
      id: "smoke",
      title: "Smoke alarm",
      description: "A repeating smoke-alarm warning",
      deviceClass: "smoke",
      suggestedName: "Smoke alarm",
      icon: "🔥",
    },
    {
      id: "carbon_monoxide",
      title: "Carbon monoxide alarm",
      description: "A repeating carbon-monoxide warning",
      deviceClass: "carbon_monoxide",
      suggestedName: "Carbon monoxide alarm",
      icon: "⚠️",
    },
    {
      id: "appliance",
      title: "Appliance finished",
      description: "A washer, dryer, oven, or other appliance chime",
      deviceClass: "running",
      suggestedName: "Appliance finished",
      icon: "🧺",
    },
    {
      id: "doorbell",
      title: "Doorbell or chime",
      description: "A doorbell, entry chime, or call button",
      deviceClass: "sound",
      suggestedName: "Doorbell",
      icon: "🔔",
    },
    {
      id: "water",
      title: "Water or leak alarm",
      description: "A water sensor or leak detector sound",
      deviceClass: "moisture",
      suggestedName: "Water alarm",
      icon: "💧",
    },
    {
      id: "warning",
      title: "Other warning sound",
      description: "A safety alarm that does not fit the choices above",
      deviceClass: "safety",
      suggestedName: "Warning sound",
      icon: "🚨",
    },
    {
      id: "other",
      title: "Something else",
      description: "Any repetitive beep, tone, or short melody",
      deviceClass: "sound",
      suggestedName: "My sound",
      icon: "🎵",
    },
  ];

  const state = {
    status: null,
    devices: [],
    currentDevice: null,
    profiles: [],
    screen: "dashboard",
    step: 1,
    category: categories[2],
    name: categories[2].suggestedName,
    nameTouched: false,
    recordSeconds: 12,
    testSeconds: 10,
    tolerance: "balanced",
    microphoneCheck: null,
    baseProfileYaml: null,
    profileYaml: null,
    summary: null,
    testResult: null,
    saving: false,
    tuning: false,
    tuneRevision: 0,
  };

  const app = document.createElement("main");
  app.id = "acoustica-easy-setup";
  app.innerHTML = `
    <div class="acoustica-shell">
      <header class="acoustica-topbar">
        <div>
          <p class="acoustica-eyebrow">Home Assistant sound detection</p>
          <h1>Acoustica</h1>
          <p class="acoustica-subtitle">Teach Home Assistant a sound without editing YAML.</p>
        </div>
        <div class="acoustica-top-actions">
          <span id="acoustica-listening-chip" class="acoustica-chip">Checking microphone…</span>
          <span id="acoustica-ha-chip" class="acoustica-chip">Checking Home Assistant…</span>
          <button type="button" class="acoustica-button acoustica-button-quiet" data-action="advanced">
            Advanced tuning
          </button>
        </div>
      </header>

      <div id="acoustica-announcement" class="acoustica-announcement" role="status" aria-live="polite"></div>

      <section id="acoustica-dashboard" class="acoustica-screen">
        <div class="acoustica-hero">
          <div>
            <p class="acoustica-eyebrow">Easy setup</p>
            <h2>Add a sound in about two minutes</h2>
            <p>Choose a microphone, play the sound a few times, test it, and turn it on. Acoustica handles the detector pattern for you.</p>
          </div>
          <button type="button" class="acoustica-button acoustica-button-primary acoustica-button-large" data-action="new-detector">
            Add a sound detector
          </button>
        </div>

        <div id="acoustica-recovery-note" class="acoustica-recovery-note" role="status" hidden>
          <strong>Acoustica recovered automatically</strong>
          <span id="acoustica-recovery-message"></span>
        </div>

        <div class="acoustica-overview-grid">
          <section class="acoustica-card">
            <div class="acoustica-section-heading">
              <div>
                <p class="acoustica-eyebrow">Listening now</p>
                <h2>Your sound detectors</h2>
              </div>
              <button type="button" class="acoustica-link-button" data-action="refresh">Refresh</button>
            </div>
            <div id="acoustica-live-detectors" class="acoustica-list"></div>
          </section>

          <section class="acoustica-card">
            <div class="acoustica-section-heading">
              <div>
                <p class="acoustica-eyebrow">Ready to reuse</p>
                <h2>Saved sounds</h2>
              </div>
            </div>
            <div id="acoustica-saved-profiles" class="acoustica-list"></div>
          </section>
        </div>

        <section class="acoustica-help-strip">
          <div>
            <strong>Use the physical test button on certified alarms.</strong>
            <span>Acoustica supplements smoke and carbon-monoxide alarms; it does not replace them.</span>
          </div>
          <button type="button" class="acoustica-link-button" data-action="microphone-only">Check microphone</button>
        </section>
      </section>

      <section id="acoustica-wizard" class="acoustica-screen" hidden>
        <div class="acoustica-wizard-header">
          <button type="button" class="acoustica-link-button" data-action="cancel-wizard">← Back to your detectors</button>
          <div>
            <span id="acoustica-step-label">Step 1 of 5</span>
            <div class="acoustica-progress" aria-hidden="true"><span id="acoustica-progress-bar"></span></div>
          </div>
        </div>

        <section class="acoustica-step" data-step="1">
          <p class="acoustica-eyebrow">Step 1</p>
          <h2>Make sure Acoustica can hear</h2>
          <p class="acoustica-step-intro">Choose the microphone nearest the sound, then make a short noise near it.</p>

          <label class="acoustica-field">
            <span>Microphone</span>
            <select id="acoustica-device-select"></select>
          </label>

          <button type="button" class="acoustica-button acoustica-button-primary" data-action="check-microphone">
            Test this microphone
          </button>

          <div id="acoustica-microphone-result" class="acoustica-result" hidden>
            <div class="acoustica-meter" aria-label="Recorded microphone level"><span id="acoustica-meter-fill"></span></div>
            <strong id="acoustica-microphone-title"></strong>
            <p id="acoustica-microphone-message"></p>
          </div>
        </section>

        <section class="acoustica-step" data-step="2" hidden>
          <p class="acoustica-eyebrow">Step 2</p>
          <h2>What does this sound mean?</h2>
          <p class="acoustica-step-intro">This helps Home Assistant choose the right icon and wording. You can rename it below.</p>

          <fieldset class="acoustica-category-fieldset">
            <legend class="acoustica-sr-only">Sound type</legend>
            <div id="acoustica-category-grid" class="acoustica-category-grid"></div>
          </fieldset>

          <div class="acoustica-form-grid">
            <label class="acoustica-field">
              <span>Name shown in Home Assistant</span>
              <input id="acoustica-detector-name" type="text" maxlength="80" autocomplete="off">
              <small>Examples: Kitchen smoke alarm, Washing machine finished, Front door chime.</small>
            </label>

            <label class="acoustica-field">
              <span>Teaching recording length</span>
              <select id="acoustica-record-seconds">
                <option value="8">8 seconds</option>
                <option value="12" selected>12 seconds — recommended</option>
                <option value="20">20 seconds</option>
                <option value="30">30 seconds</option>
              </select>
              <small>Choose enough time to play the sound three to five times.</small>
            </label>
          </div>
        </section>

        <section class="acoustica-step" data-step="3" hidden>
          <p class="acoustica-eyebrow">Step 3</p>
          <h2>Teach Acoustica the sound</h2>
          <div class="acoustica-instruction">
            <span class="acoustica-instruction-number">1</span>
            <div><strong>Press Start recording.</strong><p>Wait for the countdown to begin.</p></div>
          </div>
          <div class="acoustica-instruction">
            <span class="acoustica-instruction-number">2</span>
            <div><strong>Play the sound three to five times.</strong><p>Leave a little quiet space between repetitions.</p></div>
          </div>
          <div class="acoustica-instruction">
            <span class="acoustica-instruction-number">3</span>
            <div><strong>Keep background noise low.</strong><p>Normal room noise is fine; avoid speaking during the recording.</p></div>
          </div>

          <button type="button" class="acoustica-button acoustica-button-primary acoustica-button-large" data-action="learn-sound">
            Start teaching recording
          </button>

          <div id="acoustica-learned-result" class="acoustica-result" hidden>
            <strong id="acoustica-learned-title">Pattern learned</strong>
            <p id="acoustica-learned-summary"></p>
          </div>

          <fieldset id="acoustica-tolerance-fieldset" class="acoustica-tolerance" hidden>
            <legend>How closely should future sounds match?</legend>
            <label>
              <input type="radio" name="acoustica-tolerance" value="forgiving">
              <span><strong>Forgiving</strong><small>Best when volume or timing changes from day to day.</small></span>
            </label>
            <label>
              <input type="radio" name="acoustica-tolerance" value="balanced" checked>
              <span><strong>Balanced</strong><small>A good starting point for most alarms and appliance chimes.</small></span>
            </label>
            <label>
              <input type="radio" name="acoustica-tolerance" value="precise">
              <span><strong>Precise</strong><small>Reduces false matches but needs a very consistent sound.</small></span>
            </label>
          </fieldset>
        </section>

        <section class="acoustica-step" data-step="4" hidden>
          <p class="acoustica-eyebrow">Step 4</p>
          <h2>Test it with a fresh recording</h2>
          <p class="acoustica-step-intro">Play the sound again. This is a separate recording, so a successful result is a meaningful check.</p>

          <label class="acoustica-field acoustica-field-small">
            <span>Test recording length</span>
            <select id="acoustica-test-seconds">
              <option value="6">6 seconds</option>
              <option value="10" selected>10 seconds — recommended</option>
              <option value="20">20 seconds</option>
            </select>
          </label>

          <button type="button" class="acoustica-button acoustica-button-primary acoustica-button-large" data-action="test-sound">
            Start test recording
          </button>

          <div id="acoustica-test-result" class="acoustica-result" hidden>
            <strong id="acoustica-test-title"></strong>
            <p id="acoustica-test-message"></p>
            <div id="acoustica-test-actions" class="acoustica-inline-actions"></div>
          </div>
        </section>

        <section class="acoustica-step" data-step="5" hidden>
          <p class="acoustica-eyebrow">Step 5</p>
          <h2>Save and start listening</h2>
          <p class="acoustica-step-intro">Review the plain-language settings below. Acoustica will save the detector and turn it on immediately.</p>

          <dl class="acoustica-review">
            <div><dt>Name</dt><dd id="acoustica-review-name"></dd></div>
            <div><dt>Home Assistant type</dt><dd id="acoustica-review-type"></dd></div>
            <div><dt>Matching</dt><dd id="acoustica-review-tolerance"></dd></div>
            <div><dt>Fresh test</dt><dd id="acoustica-review-test"></dd></div>
          </dl>

          <button type="button" class="acoustica-button acoustica-button-primary acoustica-button-large" data-action="save-enable">
            Save and start listening
          </button>

          <div id="acoustica-save-result" class="acoustica-result" hidden>
            <strong>All set</strong>
            <p>This sound is now listening in Home Assistant. You can test it again or disable it from the main Acoustica screen.</p>
            <button type="button" class="acoustica-button acoustica-button-secondary" data-action="finish-wizard">View my detectors</button>
          </div>
        </section>

        <footer class="acoustica-wizard-footer">
          <button type="button" id="acoustica-back-button" class="acoustica-button acoustica-button-secondary" data-action="previous-step">Back</button>
          <button type="button" id="acoustica-next-button" class="acoustica-button acoustica-button-primary" data-action="next-step">Continue</button>
        </footer>

        <details class="acoustica-advanced-note">
          <summary>Need frequency, timing, YAML, or waveform controls?</summary>
          <p>The full engine tuner is still available for expert adjustments. Your saved profiles use the same production detector format.</p>
          <button type="button" class="acoustica-button acoustica-button-quiet" data-action="advanced">Open advanced tuner</button>
        </details>
      </section>
    </div>
  `;

  const engineRoot = document.getElementById("root");
  if (engineRoot) {
    engineRoot.before(app);
  } else {
    document.body.prepend(app);
  }

  const returnButton = document.createElement("button");
  returnButton.id = "acoustica-return-simple";
  returnButton.type = "button";
  returnButton.textContent = "← Easy setup";
  returnButton.addEventListener("click", showEasySetup);
  document.body.appendChild(returnButton);
  document.body.classList.add("acoustica-simple-mode");

  const elements = {
    dashboard: app.querySelector("#acoustica-dashboard"),
    wizard: app.querySelector("#acoustica-wizard"),
    announcement: app.querySelector("#acoustica-announcement"),
    listeningChip: app.querySelector("#acoustica-listening-chip"),
    haChip: app.querySelector("#acoustica-ha-chip"),
    liveDetectors: app.querySelector("#acoustica-live-detectors"),
    savedProfiles: app.querySelector("#acoustica-saved-profiles"),
    recoveryNote: app.querySelector("#acoustica-recovery-note"),
    recoveryMessage: app.querySelector("#acoustica-recovery-message"),
    stepLabel: app.querySelector("#acoustica-step-label"),
    progressBar: app.querySelector("#acoustica-progress-bar"),
    deviceSelect: app.querySelector("#acoustica-device-select"),
    microphoneResult: app.querySelector("#acoustica-microphone-result"),
    microphoneTitle: app.querySelector("#acoustica-microphone-title"),
    microphoneMessage: app.querySelector("#acoustica-microphone-message"),
    meterFill: app.querySelector("#acoustica-meter-fill"),
    categoryGrid: app.querySelector("#acoustica-category-grid"),
    detectorName: app.querySelector("#acoustica-detector-name"),
    recordSeconds: app.querySelector("#acoustica-record-seconds"),
    learnedResult: app.querySelector("#acoustica-learned-result"),
    learnedSummary: app.querySelector("#acoustica-learned-summary"),
    toleranceFieldset: app.querySelector("#acoustica-tolerance-fieldset"),
    testSeconds: app.querySelector("#acoustica-test-seconds"),
    testResult: app.querySelector("#acoustica-test-result"),
    testTitle: app.querySelector("#acoustica-test-title"),
    testMessage: app.querySelector("#acoustica-test-message"),
    testActions: app.querySelector("#acoustica-test-actions"),
    reviewName: app.querySelector("#acoustica-review-name"),
    reviewType: app.querySelector("#acoustica-review-type"),
    reviewTolerance: app.querySelector("#acoustica-review-tolerance"),
    reviewTest: app.querySelector("#acoustica-review-test"),
    saveResult: app.querySelector("#acoustica-save-result"),
    backButton: app.querySelector("#acoustica-back-button"),
    nextButton: app.querySelector("#acoustica-next-button"),
  };

  function announce(message, kind = "") {
    elements.announcement.textContent = message;
    elements.announcement.dataset.kind = kind;
    elements.announcement.hidden = !message;
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

  function showAdvanced() {
    document.body.classList.remove("acoustica-simple-mode");
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function showEasySetup() {
    document.body.classList.add("acoustica-simple-mode");
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function selectedDeviceIndex() {
    const raw = elements.deviceSelect.value;
    return raw === "default" ? null : Number(raw);
  }

  function categoryById(id) {
    return categories.find((category) => category.id === id) || categories[6];
  }

  function resetWizard() {
    state.step = 1;
    state.category = categories[2];
    state.name = state.category.suggestedName;
    state.nameTouched = false;
    state.recordSeconds = 12;
    state.testSeconds = 10;
    state.tolerance = "balanced";
    state.microphoneCheck = null;
    state.baseProfileYaml = null;
    state.profileYaml = null;
    state.summary = null;
    state.testResult = null;
    state.saving = false;
    elements.saveResult.hidden = true;
    elements.detectorName.value = state.name;
    elements.recordSeconds.value = String(state.recordSeconds);
    elements.testSeconds.value = String(state.testSeconds);
    const balanced = app.querySelector('input[name="acoustica-tolerance"][value="balanced"]');
    if (balanced) balanced.checked = true;
    renderCategories();
    renderWizard();
  }

  function openWizard() {
    state.screen = "wizard";
    resetWizard();
    elements.dashboard.hidden = true;
    elements.wizard.hidden = false;
    announce("");
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function closeWizard() {
    state.screen = "dashboard";
    elements.wizard.hidden = true;
    elements.dashboard.hidden = false;
    announce("");
    refreshAll();
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function renderCategories() {
    elements.categoryGrid.replaceChildren();
    for (const category of categories) {
      const label = document.createElement("label");
      label.className = "acoustica-category";
      label.dataset.selected = String(category.id === state.category.id);
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "acoustica-category";
      input.value = category.id;
      input.checked = category.id === state.category.id;
      input.addEventListener("change", () => {
        const previousSuggestion = state.category.suggestedName;
        state.category = category;
        if (!state.nameTouched || !state.name.trim() || state.name === previousSuggestion) {
          state.name = category.suggestedName;
          elements.detectorName.value = state.name;
        }
        renderCategories();
      });
      const icon = document.createElement("span");
      icon.className = "acoustica-category-icon";
      icon.textContent = category.icon;
      const text = document.createElement("span");
      text.innerHTML = `<strong>${category.title}</strong><small>${category.description}</small>`;
      label.append(input, icon, text);
      elements.categoryGrid.appendChild(label);
    }
  }

  function setChip(element, text, kind) {
    element.textContent = text;
    element.dataset.kind = kind;
  }

  function renderHealth() {
    const status = state.status;
    if (!status) {
      setChip(elements.listeningChip, "Detector unavailable", "bad");
      setChip(elements.haChip, "Home Assistant unavailable", "bad");
      return;
    }

    const runtimeState = status.state || "unknown";
    if (runtimeState === "listening") {
      setChip(elements.listeningChip, "Microphone listening", "good");
    } else if (runtimeState === "reloading" || runtimeState === "starting") {
      setChip(elements.listeningChip, "Applying changes…", "warn");
    } else {
      setChip(elements.listeningChip, "Microphone needs attention", "bad");
    }

    const ha = status.home_assistant || {};
    if (ha.connected) {
      setChip(elements.haChip, "Home Assistant connected", "good");
    } else {
      setChip(elements.haChip, `${ha.pending_updates || 0} update(s) waiting`, "warn");
    }

    if (status.last_error) {
      elements.recoveryNote.hidden = false;
      elements.recoveryMessage.textContent = `Details from automatic recovery: ${status.last_error}`;
    } else {
      elements.recoveryNote.hidden = true;
      elements.recoveryMessage.textContent = "";
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

  function renderDetectors() {
    elements.liveDetectors.replaceChildren();
    const detectors = state.status && Array.isArray(state.status.detectors) ? state.status.detectors : [];
    if (!detectors.length) {
      const empty = document.createElement("div");
      empty.className = "acoustica-empty";
      empty.innerHTML = "<strong>No detectors are listening.</strong><span>Add one to get started.</span>";
      elements.liveDetectors.appendChild(empty);
      return;
    }

    for (const detector of detectors) {
      const row = document.createElement("article");
      row.className = "acoustica-list-row";
      const text = document.createElement("div");
      const detectorName = document.createElement("strong");
      detectorName.textContent = detector.name || "Unnamed sound";
      const detectorType = document.createElement("span");
      detectorType.textContent = friendlyDeviceClass(detector.device_class);
      text.append(detectorName, detectorType);
      const actions = document.createElement("div");
      actions.className = "acoustica-row-actions";

      if (detector.source_kind === "profile" && detector.source_value) {
        const retest = document.createElement("button");
        retest.type = "button";
        retest.className = "acoustica-button acoustica-button-quiet acoustica-button-small";
        retest.textContent = "Tweak or retest";
        retest.addEventListener("click", () => loadSavedProfile(String(detector.source_value).replace(/\.yaml$/i, "")));
        actions.appendChild(retest);
      }

      const disable = document.createElement("button");
      disable.type = "button";
      disable.className = "acoustica-button acoustica-button-danger acoustica-button-small";
      disable.textContent = detectors.length === 1 ? "One detector must stay on" : "Disable";
      disable.disabled = detectors.length === 1;
      disable.addEventListener("click", () => disableDetector(detector, disable));
      actions.appendChild(disable);
      row.append(text, actions);
      elements.liveDetectors.appendChild(row);
    }
  }

  function renderProfiles() {
    elements.savedProfiles.replaceChildren();
    if (!state.profiles.length) {
      const empty = document.createElement("div");
      empty.className = "acoustica-empty";
      empty.innerHTML = "<strong>No saved custom sounds yet.</strong><span>Your taught sounds will appear here.</span>";
      elements.savedProfiles.appendChild(empty);
      return;
    }

    const active = activeProfileFiles();
    for (const profile of state.profiles) {
      const row = document.createElement("article");
      row.className = "acoustica-list-row";
      const text = document.createElement("div");
      const isActive = active.has(`${profile}.yaml`);
      const profileName = document.createElement("strong");
      profileName.textContent = profile.replaceAll("_", " ");
      const profileStatus = document.createElement("span");
      profileStatus.textContent = isActive ? "Listening now" : "Saved, not currently listening";
      text.append(profileName, profileStatus);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "acoustica-button acoustica-button-quiet acoustica-button-small";
      button.textContent = isActive ? "Tweak or retest" : "Set up and test";
      button.addEventListener("click", () => loadSavedProfile(profile));
      row.append(text, button);
      elements.savedProfiles.appendChild(row);
    }
  }

  function friendlyDeviceClass(value) {
    const labels = {
      smoke: "Smoke alarm",
      carbon_monoxide: "Carbon monoxide alarm",
      running: "Appliance or machine",
      moisture: "Water or leak alarm",
      safety: "Safety warning",
      sound: "Sound detector",
      problem: "Problem alert",
      vibration: "Vibration detector",
      gas: "Gas alarm",
    };
    return labels[value] || "Sound detector";
  }

  function friendlyTolerance(value) {
    return {
      forgiving: "Forgiving",
      balanced: "Balanced",
      precise: "Precise",
    }[value] || "Balanced";
  }

  function renderDevices() {
    elements.deviceSelect.replaceChildren();
    const defaultOption = document.createElement("option");
    defaultOption.value = "default";
    defaultOption.textContent = "System default microphone";
    elements.deviceSelect.appendChild(defaultOption);

    for (const device of state.devices) {
      const option = document.createElement("option");
      option.value = String(device.index);
      option.textContent = `${device.name}${device.default ? " (default)" : ""}`;
      elements.deviceSelect.appendChild(option);
    }
    elements.deviceSelect.value = state.currentDevice == null ? "default" : String(state.currentDevice);
  }

  function renderWizard() {
    for (const section of app.querySelectorAll(".acoustica-step")) {
      section.hidden = Number(section.dataset.step) !== state.step;
    }
    elements.stepLabel.textContent = `Step ${state.step} of 5`;
    elements.progressBar.style.width = `${state.step * 20}%`;
    elements.backButton.hidden = state.step === 1;
    elements.nextButton.hidden = state.step === 5;
    elements.nextButton.disabled = state.tuning;
    elements.nextButton.textContent = state.tuning
      ? "Applying matching…"
      : state.step === 4
        ? "Review and save"
        : "Continue";

    elements.microphoneResult.hidden = !state.microphoneCheck;
    if (state.microphoneCheck) {
      elements.microphoneTitle.textContent = state.microphoneCheck.label;
      elements.microphoneMessage.textContent = state.microphoneCheck.message;
      elements.meterFill.style.width = `${state.microphoneCheck.meter || 0}%`;
      elements.microphoneResult.dataset.kind = state.microphoneCheck.status;
    }

    elements.learnedResult.hidden = !state.summary;
    elements.toleranceFieldset.hidden = !state.summary;
    if (state.summary) {
      const tones = state.summary.tones_per_pattern;
      const repeats = state.summary.confirmation_repeats;
      elements.learnedSummary.textContent = `Found a repeating pattern with ${tones} tone${tones === 1 ? "" : "s"}. ${repeats} matching repeat${repeats === 1 ? " is" : "s are"} required.`;
    }

    elements.testResult.hidden = !state.testResult;
    if (state.testResult) {
      elements.testTitle.textContent = state.testResult.guidance.title;
      elements.testMessage.textContent = state.testResult.guidance.message;
      elements.testResult.dataset.kind = state.testResult.detected ? "good" : "warn";
      renderTestActions();
    }

    elements.reviewName.textContent = state.name || "Not named";
    elements.reviewType.textContent = state.category.title;
    elements.reviewTolerance.textContent = friendlyTolerance(state.tolerance);
    elements.reviewTest.textContent = state.testResult && state.testResult.detected ? "Passed" : "Not passed";
  }

  function renderTestActions() {
    elements.testActions.replaceChildren();
    if (!state.testResult || state.testResult.detected) return;

    if (state.tolerance !== "forgiving") {
      const forgiving = document.createElement("button");
      forgiving.type = "button";
      forgiving.className = "acoustica-button acoustica-button-secondary acoustica-button-small";
      forgiving.textContent = "Make matching more forgiving";
      forgiving.addEventListener("click", async () => {
        const radio = app.querySelector('input[name="acoustica-tolerance"][value="forgiving"]');
        if (radio) radio.checked = true;
        await changeTolerance("forgiving");
        announce("Matching is now more forgiving. Make another fresh test recording.", "good");
      });
      elements.testActions.appendChild(forgiving);
    }

    const reteach = document.createElement("button");
    reteach.type = "button";
    reteach.className = "acoustica-button acoustica-button-quiet acoustica-button-small";
    reteach.textContent = "Teach it again";
    reteach.addEventListener("click", () => {
      state.step = 3;
      state.baseProfileYaml = null;
      state.profileYaml = null;
      state.summary = null;
      state.testResult = null;
      renderWizard();
    });
    elements.testActions.appendChild(reteach);
  }

  function canContinue() {
    if (state.step === 1) {
      return state.microphoneCheck && state.microphoneCheck.status !== "silent";
    }
    if (state.step === 2) {
      return Boolean(state.name.trim());
    }
    if (state.step === 3) {
      return Boolean(state.profileYaml && state.summary);
    }
    if (state.step === 4) {
      return Boolean(state.testResult && state.testResult.detected);
    }
    return true;
  }

  async function nextStep() {
    state.name = elements.detectorName.value.trim();
    state.recordSeconds = Number(elements.recordSeconds.value);
    state.testSeconds = Number(elements.testSeconds.value);
    if (!canContinue()) {
      const messages = {
        1: "Test the microphone before continuing.",
        2: "Give this sound a name before continuing.",
        3: "Make a teaching recording before continuing.",
        4: "The detector needs to pass a fresh test before it can be saved.",
      };
      announce(messages[state.step] || "Complete this step first.", "warn");
      return;
    }
    announce("");
    state.step = Math.min(5, state.step + 1);
    renderWizard();
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function previousStep() {
    announce("");
    state.step = Math.max(1, state.step - 1);
    renderWizard();
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  async function runRecordingAction(button, seconds, startingText, operation) {
    const original = button.textContent;
    button.disabled = true;
    let remaining = seconds;
    button.textContent = `${startingText} ${remaining}s`;
    const timer = window.setInterval(() => {
      remaining -= 1;
      button.textContent = remaining > 0 ? `${startingText} ${remaining}s` : "Finishing analysis…";
    }, 1000);
    try {
      return await operation();
    } finally {
      window.clearInterval(timer);
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function checkMicrophone(button) {
    announce("Applying the microphone and listening for a short sample…");
    try {
      const requested = selectedDeviceIndex();
      await fetchJson("api/acoustica/audio/select", {
        method: "POST",
        body: JSON.stringify({device_index: requested}),
      });
      const result = await runRecordingAction(button, 2, "Listening…", () =>
        fetchJson("api/acoustica/setup/microphone-check", {
          method: "POST",
          body: JSON.stringify({seconds: 2}),
        }),
      );
      state.microphoneCheck = result;
      state.currentDevice = result.device_index;
      announce(result.message, result.status === "good" ? "good" : "warn");
      await refreshStatus();
      renderWizard();
    } catch (error) {
      announce(error.message, "bad");
    }
  }

  async function learnSound(button) {
    state.name = elements.detectorName.value.trim();
    state.recordSeconds = Number(elements.recordSeconds.value);
    if (!state.name) {
      state.step = 2;
      renderWizard();
      announce("Give this sound a name first.", "warn");
      return;
    }

    announce(`Recording ${state.recordSeconds} seconds. Play the sound three to five times.`);
    try {
      const result = await runRecordingAction(button, state.recordSeconds, "Recording…", () =>
        fetchJson("api/acoustica/setup/learn", {
          method: "POST",
          body: JSON.stringify({
            name: state.name,
            seconds: state.recordSeconds,
            tolerance: state.tolerance,
          }),
        }),
      );
      state.baseProfileYaml = result.base_profile_yaml;
      state.profileYaml = result.profile_yaml;
      state.summary = result.summary;
      state.testResult = null;
      announce("Pattern learned. You can adjust matching below, then continue to a fresh test.", "good");
      renderWizard();
    } catch (error) {
      announce(error.message, "bad");
    }
  }

  async function changeTolerance(level) {
    state.tolerance = level;
    state.testResult = null;
    const revision = ++state.tuneRevision;
    if (!state.baseProfileYaml) {
      renderWizard();
      return;
    }
    state.tuning = true;
    renderWizard();
    announce(`Applying ${friendlyTolerance(level).toLowerCase()} matching…`);
    try {
      const result = await fetchJson("api/acoustica/setup/tune", {
        method: "POST",
        body: JSON.stringify({
          profile_yaml: state.baseProfileYaml,
          tolerance: level,
        }),
      });
      if (revision !== state.tuneRevision) return;
      state.profileYaml = result.profile_yaml;
      state.summary = result.summary;
      announce("Matching updated. Make a fresh test recording to check it.", "good");
    } catch (error) {
      if (revision === state.tuneRevision) {
        announce(error.message, "bad");
      }
    } finally {
      if (revision === state.tuneRevision) {
        state.tuning = false;
        renderWizard();
      }
    }
  }

  async function testSound(button) {
    if (!state.profileYaml) {
      announce("Teach Acoustica the sound before testing it.", "warn");
      return;
    }
    state.testSeconds = Number(elements.testSeconds.value);
    announce(`Recording a fresh ${state.testSeconds}-second test. Play the sound again.`);
    try {
      const result = await runRecordingAction(button, state.testSeconds, "Testing…", () =>
        fetchJson("api/acoustica/setup/test", {
          method: "POST",
          body: JSON.stringify({
            profile_yaml: state.profileYaml,
            seconds: state.testSeconds,
          }),
        }),
      );
      state.testResult = result;
      announce(result.guidance.message, result.detected ? "good" : "warn");
      renderWizard();
    } catch (error) {
      announce(error.message, "bad");
    }
  }

  async function saveAndEnable(button) {
    if (!state.testResult || !state.testResult.detected) {
      announce("Pass a fresh test before saving this detector.", "warn");
      return;
    }
    button.disabled = true;
    button.textContent = "Saving and starting…";
    announce("Saving the detector and applying it to the live microphone…");
    try {
      await fetchJson("api/acoustica/setup/save-and-enable", {
        method: "POST",
        body: JSON.stringify({
          name: state.name,
          profile_yaml: state.profileYaml,
          device_class: state.category.deviceClass,
        }),
      });
      elements.saveResult.hidden = false;
      announce(`${state.name} is now listening in Home Assistant.`, "good");
      await refreshAll();
    } catch (error) {
      announce(error.message, "bad");
    } finally {
      button.disabled = false;
      button.textContent = "Save and start listening";
    }
  }

  async function disableDetector(detector, button) {
    button.disabled = true;
    button.textContent = "Disabling…";
    announce(`Disabling ${detector.name}…`);
    try {
      await fetchJson("api/acoustica/detectors/disable", {
        method: "POST",
        body: JSON.stringify({
          source_kind: detector.source_kind,
          source_value: detector.source_value,
        }),
      });
      announce(`${detector.name} is no longer listening. Its Home Assistant entity is unavailable.`, "good");
      await refreshAll();
    } catch (error) {
      announce(error.message, "bad");
      button.disabled = false;
      button.textContent = "Disable";
    }
  }

  async function loadSavedProfile(profileId) {
    announce(`Opening ${profileId.replaceAll("_", " ")}…`);
    try {
      const payload = await fetchJson(`profiles/${encodeURIComponent(profileId)}`);
      const tuned = await fetchJson("api/acoustica/setup/tune", {
        method: "POST",
        body: JSON.stringify({
          profile_yaml: payload.yaml,
          tolerance: "balanced",
        }),
      });
      resetWizard();
      state.baseProfileYaml = payload.yaml;
      state.profileYaml = tuned.profile_yaml;
      state.summary = tuned.summary;
      state.name = String(payload.name || profileId).replaceAll("_", " ");
      state.nameTouched = true;
      elements.detectorName.value = state.name;
      state.testResult = null;
      state.step = 2;
      state.screen = "wizard";
      elements.dashboard.hidden = true;
      elements.wizard.hidden = false;
      announce("Choose what the sound means, then continue to tweak and test it.", "good");
      renderWizard();
      window.scrollTo({top: 0, behavior: "smooth"});
    } catch (error) {
      announce(error.message, "bad");
    }
  }

  async function refreshStatus() {
    try {
      state.status = await fetchJson("api/acoustica/status");
    } catch (error) {
      state.status = null;
      announce(error.message, "bad");
    }
    renderHealth();
    renderDetectors();
  }

  async function refreshDevices() {
    try {
      const payload = await fetchJson("api/acoustica/audio/devices");
      state.devices = Array.isArray(payload.devices) ? payload.devices : [];
      state.currentDevice = payload.current_index;
    } catch (error) {
      state.devices = [];
      announce(error.message, "bad");
    }
    renderDevices();
  }

  async function refreshProfiles() {
    try {
      const payload = await fetchJson("profiles");
      state.profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    } catch (error) {
      state.profiles = [];
      announce(error.message, "bad");
    }
    renderProfiles();
  }

  async function refreshAll() {
    await Promise.all([refreshStatus(), refreshDevices(), refreshProfiles()]);
  }

  app.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "advanced") showAdvanced();
    if (action === "new-detector") openWizard();
    if (action === "cancel-wizard" || action === "finish-wizard") closeWizard();
    if (action === "refresh") refreshAll();
    if (action === "microphone-only") {
      openWizard();
      state.step = 1;
      renderWizard();
    }
    if (action === "previous-step") previousStep();
    if (action === "next-step") nextStep();
    if (action === "check-microphone") checkMicrophone(button);
    if (action === "learn-sound") learnSound(button);
    if (action === "test-sound") testSound(button);
    if (action === "save-enable") saveAndEnable(button);
  });

  elements.detectorName.addEventListener("input", () => {
    state.nameTouched = true;
    state.name = elements.detectorName.value;
  });
  elements.recordSeconds.addEventListener("change", () => {
    state.recordSeconds = Number(elements.recordSeconds.value);
  });
  elements.testSeconds.addEventListener("change", () => {
    state.testSeconds = Number(elements.testSeconds.value);
  });
  app.addEventListener("change", (event) => {
    if (event.target.matches('input[name="acoustica-tolerance"]')) {
      changeTolerance(event.target.value);
    }
  });

  renderCategories();
  renderWizard();
  refreshAll();
  window.setInterval(refreshStatus, 5000);
  window.setInterval(refreshProfiles, 15000);
})();
