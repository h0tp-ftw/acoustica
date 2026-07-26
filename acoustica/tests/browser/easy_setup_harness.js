(() => {
  "use strict";

  const result = document.getElementById("browser-test-result");

  function assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  async function waitFor(predicate, message, timeoutMs = 4000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error(message);
  }

  function action(name) {
    return document.querySelector(`button[data-action="${name}"]`);
  }

  async function run() {
    await waitFor(
      () => document.querySelector("#acoustica-easy-setup"),
      "Easy setup did not render",
    );
    await waitFor(
      () => document.querySelector("#acoustica-device-select option[value='2']"),
      "Microphone list did not load",
    );

    assert(document.body.classList.contains("acoustica-simple-mode"), "Easy setup was not the default view");
    assert(getComputedStyle(document.getElementById("root")).display === "none", "Advanced tuner was visible by default");
    assert(document.querySelector("#acoustica-live-detectors").textContent.includes("Smoke Alarm"), "Live detectors did not render");

    action("new-detector").click();
    assert(!document.querySelector("[data-step='1']").hidden, "Step 1 did not open");

    action("check-microphone").click();
    await waitFor(
      () => !document.getElementById("acoustica-microphone-result").hidden,
      "Microphone result did not appear",
    );
    assert(document.getElementById("acoustica-microphone-title").textContent.includes("sounds good"), "Microphone guidance was not plain language");

    action("next-step").click();
    assert(!document.querySelector("[data-step='2']").hidden, "Step 2 did not open");

    const doorbell = document.querySelector('input[name="acoustica-category"][value="doorbell"]');
    doorbell.click();
    const name = document.getElementById("acoustica-detector-name");
    name.value = "Front Door Chime";
    name.dispatchEvent(new Event("input", {bubbles: true}));
    action("next-step").click();
    assert(!document.querySelector("[data-step='3']").hidden, "Step 3 did not open");

    action("learn-sound").click();
    await waitFor(
      () => !document.getElementById("acoustica-learned-result").hidden,
      "Learned pattern summary did not appear",
    );
    assert(document.getElementById("acoustica-learned-summary").textContent.includes("repeating pattern"), "Learned result was not understandable");

    action("next-step").click();
    assert(!document.querySelector("[data-step='4']").hidden, "Step 4 did not open");

    action("test-sound").click();
    await waitFor(
      () => !document.getElementById("acoustica-test-result").hidden,
      "Fresh test result did not appear",
    );
    assert(document.getElementById("acoustica-test-title").textContent.includes("recognized"), "Fresh test did not show success");

    action("next-step").click();
    assert(!document.querySelector("[data-step='5']").hidden, "Step 5 did not open");
    assert(document.getElementById("acoustica-review-name").textContent === "Front Door Chime", "Review name was incorrect");
    assert(document.getElementById("acoustica-review-test").textContent === "Passed", "Review did not require the fresh test");

    action("save-enable").click();
    await waitFor(
      () => !document.getElementById("acoustica-save-result").hidden,
      "Save-and-enable confirmation did not appear",
    );

    const advanced = Array.from(document.querySelectorAll('button[data-action="advanced"]'))[0];
    advanced.click();
    assert(!document.body.classList.contains("acoustica-simple-mode"), "Advanced tuner did not open");
    assert(getComputedStyle(document.getElementById("root")).display !== "none", "Advanced tuner remained hidden");
    document.getElementById("acoustica-return-simple").click();
    assert(document.body.classList.contains("acoustica-simple-mode"), "Easy setup return button did not work");

    const calledPaths = new Set(window.__acousticaApiCalls.map((call) => call.path));
    for (const endpoint of [
      "api/acoustica/setup/microphone-check",
      "api/acoustica/setup/learn",
      "api/acoustica/setup/test",
      "api/acoustica/setup/save-and-enable",
    ]) {
      assert(calledPaths.has(endpoint), `Wizard did not call ${endpoint}`);
    }

    result.dataset.status = "passed";
    result.textContent = "Beginner wizard browser flow passed";
  }

  run().catch((error) => {
    result.dataset.status = "failed";
    result.textContent = `Browser flow failed: ${error.message}`;
    console.error(error);
  });
})();
