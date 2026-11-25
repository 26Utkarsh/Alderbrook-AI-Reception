export const TARGET_SAMPLE_RATE = 16000;

export class VoiceAudioBridge {
  constructor({ onMicPcm, onLevel }) {
    this.onMicPcm = onMicPcm;
    this.onLevel = onLevel;
    this.ctx = null;
    this.micStream = null;
    this.processor = null;
    this.micAnalyser = null;
    this.outAnalyser = null;
    this.nextPlayTime = 0;
    this.activeSources = new Set();
    this.muted = false;
    this.ringTimer = null;
  }

  async init() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AudioCtx();
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }

    this.outAnalyser = this.ctx.createAnalyser();
    this.outAnalyser.fftSize = 64;
    this.outGain = this.ctx.createGain();
    this.outGain.gain.value = 1.2;
    this.outGain.connect(this.outAnalyser);
    this.outAnalyser.connect(this.ctx.destination);
  }

  startRingback() {
    if (!this.ctx) return;
    const playPulse = () => {
      if (!this.ctx) return;
      const now = this.ctx.currentTime;
      const osc1 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc1.frequency.value = 440;
      osc2.frequency.value = 480;
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(0.04, now + 0.04);
      gain.gain.setValueAtTime(0.04, now + 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.95);
      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(this.ctx.destination);
      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 1.0);
      osc2.stop(now + 1.0);
    };

    playPulse();
    this.ringTimer = setInterval(playPulse, 2600);
  }

  stopRingback() {
    if (this.ringTimer) {
      clearInterval(this.ringTimer);
      this.ringTimer = null;
    }
  }

  playHangupTone() {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.frequency.setValueAtTime(520, now);
    osc.frequency.exponentialRampToValueAtTime(340, now + 0.18);
    gain.gain.setValueAtTime(0.06, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(now);
    osc.stop(now + 0.24);
  }

  async startMicrophone() {
    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: TARGET_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const source = this.ctx.createMediaStreamSource(this.micStream);
    this.micAnalyser = this.ctx.createAnalyser();
    this.micAnalyser.fftSize = 64;
    source.connect(this.micAnalyser);

    this.processor = this.ctx.createScriptProcessor(1024, 1, 1);
    const silentGain = this.ctx.createGain();
    silentGain.gain.value = 0;

    this.processor.onaudioprocess = (event) => {
      if (this.muted) return;
      const input = event.inputBuffer.getChannelData(0);
      const resampled = resampleFloat32(input, this.ctx.sampleRate, TARGET_SAMPLE_RATE);
      const pcm = floatTo16BitPCM(resampled);
      this.onMicPcm(pcm.buffer);
    };

    source.connect(this.processor);
    this.processor.connect(silentGain);
    silentGain.connect(this.ctx.destination);
  }

  enqueuePcm16(arrayBuffer) {
    if (!this.ctx || !arrayBuffer || arrayBuffer.byteLength < 2) return;
    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
    const evenBytes = arrayBuffer.byteLength - (arrayBuffer.byteLength % 2);
    const int16 = new Int16Array(arrayBuffer, 0, evenBytes / 2);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    const audioBuffer = this.ctx.createBuffer(1, float32.length, TARGET_SAMPLE_RATE);
    audioBuffer.copyToChannel(float32, 0);

    const source = this.ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.outGain || this.outAnalyser);

    const now = this.ctx.currentTime;
    const startAt = this.nextPlayTime > now ? this.nextPlayTime : now + 0.06;
    source.start(startAt);
    this.nextPlayTime = startAt + audioBuffer.duration;
    this.activeSources.add(source);
    source.onended = () => {
      this.activeSources.delete(source);
    };
  }

  clearPlayback() {
    for (const src of this.activeSources) {
      try {
        src.stop();
      } catch (_) {}
    }
    this.activeSources.clear();
    if (this.ctx) {
      this.nextPlayTime = this.ctx.currentTime;
    }
  }

  setMuted(muted) {
    this.muted = muted;
  }

  sampleSpectrum(targetBins) {
    const out = new Uint8Array(targetBins);
    if (!this.ctx) return out;

    const buf = new Uint8Array(32);
    let maxEnergy = 0;

    if (this.outAnalyser) {
      this.outAnalyser.getByteFrequencyData(buf);
      for (let i = 0; i < targetBins; i++) {
        out[i] = buf[i % buf.length];
        if (out[i] > maxEnergy) maxEnergy = out[i];
      }
    }

    if (maxEnergy < 12 && this.micAnalyser && !this.muted) {
      this.micAnalyser.getByteFrequencyData(buf);
      for (let i = 0; i < targetBins; i++) {
        out[i] = Math.max(out[i], buf[i % buf.length]);
      }
    }

    return out;
  }

  close() {
    this.stopRingback();
    this.clearPlayback();
    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach((t) => t.stop());
      this.micStream = null;
    }
    if (this.ctx) {
      this.ctx.close().catch(() => {});
      this.ctx = null;
    }
  }
}

function resampleFloat32(input, fromRate, toRate) {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const newLength = Math.round(input.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const s0 = input[Math.min(idx, input.length - 1)];
    const s1 = input[Math.min(idx + 1, input.length - 1)];
    result[i] = s0 + (s1 - s0) * frac;
  }
  return result;
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return out;
}
