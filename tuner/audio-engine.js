class AddonRecorder {
  constructor() {
    this.state = {
      recording: false,
      has_recording: false,
      duration_seconds: 0,
      level: 0,
      max_seconds: 30,
    };
  }

  async start() {
    this.state = await this._request("api/record/start", { method: "POST" });
  }

  async stop() {
    this.state = await this._request("api/record/stop", { method: "POST" });
  }

  async refresh() {
    this.state = await this._request("api/record/status");
    return this.state;
  }

  get duration() {
    return this.state.duration_seconds || 0;
  }

  get level() {
    return this.state.level || 0;
  }

  hasRecording() {
    return Boolean(this.state.has_recording);
  }

  async play() {
    if (!this.hasRecording()) return;
    const response = await fetch("api/record/audio", { cache: "no-store" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Could not load the recording");
    }
    const url = URL.createObjectURL(await response.blob());
    const audio = new Audio(url);
    audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
    await audio.play();
  }

  async _request(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({ error: "Invalid server response" }));
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }
}
