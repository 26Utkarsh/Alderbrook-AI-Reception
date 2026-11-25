import { VoiceAudioBridge } from "/static/audio.js";

const state = {
  doctors: [],
  appointments: [],
  selectedDate: "all",
  openOnly: false,
  activeOnly: false,
  highlightedIds: new Set(),
  callActive: false,
  muted: false,
  timerInterval: null,
  callSeconds: 0,
  ws: null,
  audio: null,
  waveRaf: null,
  keysConfigured: true,
};

const els = {
  dateTabs: document.getElementById("dateTabs"),
  doctorsList: document.getElementById("doctorsList"),
  appointmentsList: document.getElementById("appointmentsList"),
  apptCount: document.getElementById("apptCount"),
  openOnlyBtn: document.getElementById("openOnlyBtn"),
  activeOnlyBtn: document.getElementById("activeOnlyBtn"),
  lineStatus: document.getElementById("lineStatus"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  tryCallBtn: document.getElementById("tryCallBtn"),
  phoneBackdrop: document.getElementById("phoneBackdrop"),
  phoneAvatar: document.querySelector(".phone-avatar"),
  phoneState: document.getElementById("phoneState"),
  phoneTimer: document.getElementById("phoneTimer"),
  phoneCardSlot: document.getElementById("phoneCardSlot"),
  phoneTranscript: document.getElementById("phoneTranscript"),
  transcriptEmpty: document.getElementById("transcriptEmpty"),
  muteBtn: document.getElementById("muteBtn"),
  muteLabel: document.getElementById("muteLabel"),
  micIconOn: document.getElementById("micIconOn"),
  micIconOff: document.getElementById("micIconOff"),
  hangupBtn: document.getElementById("hangupBtn"),
  hangupLabel: document.getElementById("hangupLabel"),
  waveformCanvas: document.getElementById("waveformCanvas"),
};

function formatDateLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((dt - today) / 86400000);
  const short = dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  if (diffDays === 0) return `Today · ${short}`;
  if (diffDays === 1) return `Tomorrow · ${short}`;
  return short;
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();
    state.keysConfigured = Boolean(data.keys_configured);
    updateLineIndicator();
  } catch (_) {}
}

function updateLineIndicator() {
  if (state.callActive) {
    els.statusDot.className = "status-dot busy";
    els.statusText.textContent = "Live";
    return;
  }
  if (!state.keysConfigured) {
    els.statusDot.className = "status-dot warn";
    els.statusText.textContent = "No Keys";
    return;
  }
  els.statusDot.className = "status-dot";
  els.statusText.textContent = "Ready";
}

async function fetchDashboard() {
  const res = await fetch("/api/dashboard");
  if (!res.ok) return;
  const data = await res.json();
  state.doctors = data.doctors || [];
  state.appointments = data.appointments || [];
  renderDateTabs();
  renderDoctors();
  renderAppointments();
}

function renderDateTabs() {
  const dateSet = new Set();
  state.doctors.forEach((doc) => {
    doc.slots.forEach((slot) => dateSet.add(slot.slot_date));
  });
  const dates = Array.from(dateSet).sort();

  const buttons = [
    { key: "all", label: "All" },
    ...dates.map((d) => ({ key: d, label: formatDateLabel(d).split(" · ")[0] })),
  ];

  els.dateTabs.innerHTML = "";
  buttons.forEach(({ key, label }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `date-tab${state.selectedDate === key ? " active" : ""}`;
    btn.textContent = label;
    btn.addEventListener("click", () => {
      state.selectedDate = key;
      renderDateTabs();
      renderDoctors();
    });
    els.dateTabs.appendChild(btn);
  });
}

function renderDoctors() {
  els.doctorsList.innerHTML = "";
  if (!state.doctors.length) {
    els.doctorsList.innerHTML = '<div class="empty-state">No doctors configured.</div>';
    return;
  }

  state.doctors.forEach((doc) => {
    const card = document.createElement("article");
    card.className = "doctor-card";

    const filtered = (
      state.selectedDate === "all"
        ? doc.slots
        : doc.slots.filter((s) => s.slot_date === state.selectedDate)
    ).filter((s) => !state.openOnly || !s.is_booked);

    const openCount = filtered.filter((s) => !s.is_booked).length;

    const meta = document.createElement("div");
    meta.className = "doctor-meta";
    meta.innerHTML = `
      <div>
        <div class="doctor-name">${escapeHtml(doc.name)}</div>
        <div class="doctor-sub">${escapeHtml(doc.specialty)} · ${escapeHtml(doc.room)}</div>
      </div>
      <div class="doctor-sub">${openCount} open</div>
    `;
    card.appendChild(meta);

    const byDate = {};
    filtered.forEach((slot) => {
      if (!byDate[slot.slot_date]) byDate[slot.slot_date] = [];
      byDate[slot.slot_date].push(slot);
    });

    Object.keys(byDate)
      .sort()
      .forEach((d) => {
        const group = document.createElement("div");
        group.className = "slot-group";
        const label = document.createElement("div");
        label.className = "slot-date-label";
        label.textContent = formatDateLabel(d);
        group.appendChild(label);

        const grid = document.createElement("div");
        grid.className = "slot-grid";
        byDate[d].forEach((slot) => {
          const chip = document.createElement("span");
          chip.className = `slot-chip${slot.is_booked ? " booked" : ""}`;
          if (state.highlightedIds.has(slot.id)) {
            chip.classList.add("flash");
          }
          chip.textContent = slot.slot_time;
          grid.appendChild(chip);
        });
        group.appendChild(grid);
        card.appendChild(group);
      });

    els.doctorsList.appendChild(card);
  });
}

function renderAppointments() {
  const confirmed = state.appointments.filter((a) => a.status === "confirmed");
  els.apptCount.textContent = String(confirmed.length);
  els.appointmentsList.innerHTML = "";

  const visible = state.activeOnly ? confirmed : state.appointments;
  if (!visible.length) {
    els.appointmentsList.innerHTML = '<div class="empty-state">No appointments</div>';
    return;
  }

  visible.forEach((appt) => {
    const row = document.createElement("div");
    row.className = `appt-row${appt.status === "cancelled" ? " cancelled" : ""}`;
    if (state.highlightedIds.has(appt.id)) {
      row.classList.add("flash");
    }

    const patientLabel = appt.patient_name ? ` · ${escapeHtml(appt.patient_name)}` : "";
    row.innerHTML = `
      <div class="appt-top">
        <span class="appt-phone">${escapeHtml(appt.phone_display)}${patientLabel}</span>
        <span class="appt-status ${escapeHtml(appt.status)}">${escapeHtml(appt.status)}</span>
      </div>
      <div class="appt-detail">${escapeHtml(appt.doctor_name)} (${escapeHtml(appt.specialty)})</div>
      <div class="appt-sub">
        <span>${escapeHtml(formatDateLabel(appt.slot_date))} at ${escapeHtml(appt.slot_time)}</span>
        <span>${escapeHtml(appt.id)}</span>
      </div>
    `;
    els.appointmentsList.appendChild(row);
  });
}

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "appointment_booked" || data.type === "appointment_cancelled") {
        const appt = data.appointment;
        if (appt) {
          state.highlightedIds.add(appt.id);
          if (appt.slot_id) state.highlightedIds.add(appt.slot_id);
          setTimeout(() => {
            state.highlightedIds.delete(appt.id);
            if (appt.slot_id) state.highlightedIds.delete(appt.slot_id);
          }, 2500);
        }
        fetchDashboard();
      }
    } catch (_) {}
  };
}

function openPhoneModal() {
  els.phoneBackdrop.hidden = false;
  requestAnimationFrame(() => {
    els.phoneBackdrop.classList.add("open");
  });
}

function closePhoneModal() {
  els.phoneBackdrop.classList.remove("open");
  setTimeout(() => {
    els.phoneBackdrop.hidden = true;
  }, 200);
}

function setCallState(statusKey, label) {
  els.phoneState.textContent = label;
  els.phoneState.className = `phone-state ${statusKey}`;
  if (els.phoneAvatar) {
    els.phoneAvatar.classList.toggle("ringing", statusKey === "ringing");
  }
  updateLineIndicator();
}

function startTimer() {
  stopTimer();
  state.callSeconds = 0;
  els.phoneTimer.textContent = "00:00";
  state.timerInterval = setInterval(() => {
    state.callSeconds += 1;
    const mins = String(Math.floor(state.callSeconds / 60)).padStart(2, "0");
    const secs = String(state.callSeconds % 60).padStart(2, "0");
    els.phoneTimer.textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
}

function appendTranscript(role, text) {
  if (!text) return;
  if (els.transcriptEmpty) {
    els.transcriptEmpty.hidden = true;
  }
  const msg = document.createElement("div");
  msg.className = `msg ${role === "user" ? "user" : "assistant"}`;
  msg.innerHTML = `
    <span class="msg-role">${role === "user" ? "Caller" : "Claire"}</span>
    <span>${escapeHtml(text)}</span>
  `;
  els.phoneTranscript.appendChild(msg);
  els.phoneTranscript.scrollTop = els.phoneTranscript.scrollHeight;
}

function showBookingCard(type, appt) {
  if (!appt) return;
  const isCancel = type === "appointment_cancelled";
  els.phoneCardSlot.innerHTML = `
    <div class="confirm-card${isCancel ? " cancelled" : ""}">
      <div class="confirm-card-title">${isCancel ? "Appointment Cancelled" : "Appointment Confirmed"}</div>
      <div class="confirm-card-body">
        ${escapeHtml(appt.doctor_name)} · ${escapeHtml(appt.date)} at ${escapeHtml(appt.time)}<br>
        Phone: ${escapeHtml(appt.phone_display)} (${escapeHtml(appt.id)})
      </div>
    </div>
  `;
}

function drawWaveform() {
  const canvas = els.waveformCanvas;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const bins = 28;
  const gap = 4;
  const barWidth = (w - gap * (bins - 1)) / bins;

  const renderFrame = () => {
    ctx.clearRect(0, 0, w, h);
    const levels = state.audio ? state.audio.sampleSpectrum(bins) : new Uint8Array(bins);
    for (let i = 0; i < bins; i++) {
      const normalized = levels[i] / 255;
      const barH = Math.max(4, Math.round(normalized * (h - 8)));
      const x = i * (barWidth + gap);
      const y = (h - barH) / 2;
      ctx.fillStyle = normalized > 0.15 ? "#5eead4" : "#354039";
      ctx.beginPath();
      ctx.roundRect(x, y, barWidth, barH, 2);
      ctx.fill();
    }
    if (state.callActive) {
      state.waveRaf = requestAnimationFrame(renderFrame);
    }
  };

  state.waveRaf = requestAnimationFrame(renderFrame);
}

async function startCall() {
  if (state.callActive) {
    openPhoneModal();
    return;
  }

  els.phoneCardSlot.innerHTML = "";
  els.phoneTranscript.innerHTML = "";
  const emptyHint = document.createElement("div");
  emptyHint.className = "transcript-empty";
  emptyHint.id = "transcriptEmpty";
  emptyHint.textContent = "Listening. State your number to book or cancel.";
  els.phoneTranscript.appendChild(emptyHint);
  els.transcriptEmpty = emptyHint;

  els.muteBtn.disabled = true;
  els.hangupLabel.textContent = "End Call";
  els.phoneTimer.textContent = "00:00";
  setCallState("ringing", "Ringing...");
  openPhoneModal();

  const audio = new VoiceAudioBridge({
    onMicPcm: (buffer) => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(buffer);
      }
    },
  });

  state.audio = audio;
  await audio.init();
  audio.startRingback();

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/call`);
  ws.binaryType = "arraybuffer";
  state.ws = ws;
  state.callActive = true;
  updateLineIndicator();
  drawWaveform();

  ws.onopen = async () => {
    try {
      await audio.startMicrophone();
      audio.stopRingback();
      setCallState("connected", "Connected");
      els.muteBtn.disabled = false;
      startTimer();
    } catch (_) {
      audio.stopRingback();
      appendTranscript("assistant", "Microphone permission is required to place a call.");
      endCall();
    }
  };

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      audio.enqueuePcm16(event.data);
      return;
    }
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "transcript") {
        appendTranscript(msg.role, msg.text);
      } else if (msg.type === "clear_audio") {
        audio.clearPlayback();
      } else if (msg.type === "appointment_booked" || msg.type === "appointment_cancelled") {
        showBookingCard(msg.type, msg.appointment);
        fetchDashboard();
      } else if (msg.type === "error") {
        appendTranscript("assistant", msg.message || "Voice service unavailable.");
        endCall();
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    if (state.callActive) {
      endCall(true);
    }
  };
}

function endCall(fromRemote = false) {
  if (!state.callActive && els.phoneBackdrop.hidden) return;

  const wasActive = state.callActive;
  state.callActive = false;
  stopTimer();

  if (state.waveRaf) {
    cancelAnimationFrame(state.waveRaf);
    state.waveRaf = null;
  }

  if (state.audio) {
    if (wasActive) state.audio.playHangupTone();
    setTimeout(() => {
      state.audio?.close();
      state.audio = null;
    }, 220);
  }

  if (state.ws && !fromRemote && state.ws.readyState === WebSocket.OPEN) {
    state.ws.close();
  }
  state.ws = null;

  state.muted = false;
  els.muteBtn.classList.remove("muted");
  els.muteBtn.disabled = true;
  els.muteLabel.textContent = "Mute";
  els.micIconOn.hidden = false;
  els.micIconOff.hidden = true;
  setCallState("ended", "Call Ended");
  els.hangupLabel.textContent = "Close";

  if (!wasActive) {
    closePhoneModal();
  }
}

function toggleMute() {
  if (!state.audio) return;
  state.muted = !state.muted;
  state.audio.setMuted(state.muted);
  els.muteBtn.classList.toggle("muted", state.muted);
  els.muteLabel.textContent = state.muted ? "Unmute" : "Mute";
  els.micIconOn.hidden = state.muted;
  els.micIconOff.hidden = !state.muted;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

els.tryCallBtn.addEventListener("click", startCall);
els.muteBtn.addEventListener("click", toggleMute);
els.hangupBtn.addEventListener("click", () => {
  if (state.callActive) {
    endCall(false);
  } else {
    closePhoneModal();
  }
});

els.phoneBackdrop.addEventListener("click", (e) => {
  if (e.target === els.phoneBackdrop && !state.callActive) {
    closePhoneModal();
  }
});

els.openOnlyBtn.addEventListener("click", () => {
  state.openOnly = !state.openOnly;
  els.openOnlyBtn.classList.toggle("active", state.openOnly);
  els.openOnlyBtn.setAttribute("aria-pressed", String(state.openOnly));
  renderDoctors();
});

els.activeOnlyBtn.addEventListener("click", () => {
  state.activeOnly = !state.activeOnly;
  els.activeOnlyBtn.classList.toggle("active", state.activeOnly);
  els.activeOnlyBtn.setAttribute("aria-pressed", String(state.activeOnly));
  renderAppointments();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !els.phoneBackdrop.hidden && !state.callActive) {
    closePhoneModal();
  }
});

checkHealth();
fetchDashboard();
connectEvents();
