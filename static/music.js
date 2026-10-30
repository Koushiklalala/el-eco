/* A haunted music-box waltz, played live with the Web Audio API.
   Nothing is downloaded: every note is synthesised in the browser, so there is nothing to license. */
(() => {
  const BEAT = 0.62;
  const STORE = "el-eco-music";
  const midi = (m) => 440 * Math.pow(2, (m - 69) / 12);

  // Eight bars of 3/4 in A minor. Each bar: chord root (bass), chord tones, melody as [midi, beats].
  const AM = { bass: 45, chord: [57, 60, 64] };
  const DM = { bass: 50, chord: [57, 62, 65] };
  const E7 = { bass: 40, chord: [56, 59, 64] };
  const BARS = [
    { ...AM, tune: [[76, 1.5], [75, 0.5], [76, 1]] },
    { ...AM, tune: [[72, 1], [69, 2]] },
    { ...DM, tune: [[74, 1.5], [73, 0.5], [74, 1]] },
    { ...AM, tune: [[69, 1], [64, 2]] },
    { ...E7, tune: [[71, 1.5], [68, 0.5], [71, 1]] },
    { ...E7, tune: [[76, 1], [71, 2]] },
    { ...AM, tune: [[72, 1], [69, 1], [64, 1]] },
    { ...E7, tune: [[68, 2], [69, 1]] },
  ];
  const LOOP = BARS.length * 3 * BEAT;

  let ctx = null;
  let master = null;
  let duckGain = null;
  let bus = null;
  let echoIn = null;
  let analyser = null;
  let timer = 0;
  let nextStart = 0;
  let playing = false;
  let ducked = false;
  let stopTimer = 0;

  const button = document.querySelector("#music");

  function impulse(seconds) {
    const length = Math.floor(ctx.sampleRate * seconds);
    const buffer = ctx.createBuffer(2, length, ctx.sampleRate);
    for (let channel = 0; channel < 2; channel += 1) {
      const data = buffer.getChannelData(channel);
      for (let index = 0; index < length; index += 1) {
        data[index] = (Math.random() * 2 - 1) * Math.pow(1 - index / length, 2.6);
      }
    }
    return buffer;
  }

  function build() {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = 0;
    duckGain = ctx.createGain();
    duckGain.gain.value = ducked ? 0.22 : 1;
    analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    master.connect(duckGain);
    duckGain.connect(analyser);
    duckGain.connect(ctx.destination);

    bus = ctx.createGain();
    bus.connect(master);

    const reverb = ctx.createConvolver();
    reverb.buffer = impulse(3);
    const wet = ctx.createGain();
    wet.gain.value = 0.55;
    bus.connect(reverb);
    reverb.connect(wet);
    wet.connect(master);

    echoIn = ctx.createGain();
    const delay = ctx.createDelay(1);
    delay.delayTime.value = BEAT * 0.75;
    const feedback = ctx.createGain();
    feedback.gain.value = 0.34;
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = 2400;
    echoIn.connect(delay);
    delay.connect(tone);
    tone.connect(feedback);
    feedback.connect(delay);
    tone.connect(master);

    // a low drone on A, two saws a hair apart, breathing through a slow filter
    const droneFilter = ctx.createBiquadFilter();
    droneFilter.type = "lowpass";
    droneFilter.frequency.value = 340;
    droneFilter.Q.value = 3;
    const droneGain = ctx.createGain();
    droneGain.gain.value = 0.05;
    [110, 110.6, 55].forEach((frequency) => {
      const osc = ctx.createOscillator();
      osc.type = "sawtooth";
      osc.frequency.value = frequency;
      osc.connect(droneFilter);
      osc.start();
    });
    droneFilter.connect(droneGain);
    droneGain.connect(bus);
    const breath = ctx.createOscillator();
    breath.frequency.value = 0.09;
    const breathDepth = ctx.createGain();
    breathDepth.gain.value = 150;
    breath.connect(breathDepth);
    breathDepth.connect(droneFilter.frequency);
    breath.start();

    // wind through the graveyard
    const noise = ctx.createBufferSource();
    const noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 4, ctx.sampleRate);
    const noiseData = noiseBuffer.getChannelData(0);
    for (let index = 0; index < noiseData.length; index += 1) noiseData[index] = Math.random() * 2 - 1;
    noise.buffer = noiseBuffer;
    noise.loop = true;
    const windFilter = ctx.createBiquadFilter();
    windFilter.type = "bandpass";
    windFilter.frequency.value = 520;
    windFilter.Q.value = 0.8;
    const windGain = ctx.createGain();
    windGain.gain.value = 0.035;
    noise.connect(windFilter);
    windFilter.connect(windGain);
    windGain.connect(bus);
    const gust = ctx.createOscillator();
    gust.frequency.value = 0.07;
    const gustDepth = ctx.createGain();
    gustDepth.gain.value = 0.03;
    gust.connect(gustDepth);
    gustDepth.connect(windGain.gain);
    noise.start();
    gust.start();
  }

  function musicBox(time, note, beats) {
    const frequency = midi(note);
    const length = 1.7 + beats * 0.35;
    const envelope = ctx.createGain();
    envelope.gain.setValueAtTime(0.0001, time);
    envelope.gain.exponentialRampToValueAtTime(0.2, time + 0.006);
    envelope.gain.exponentialRampToValueAtTime(0.0001, time + length);
    const body = ctx.createOscillator();
    body.type = "triangle";
    body.frequency.value = frequency;
    const sparkle = ctx.createOscillator();
    sparkle.type = "sine";
    sparkle.frequency.value = frequency * 2;
    const sparkleGain = ctx.createGain();
    sparkleGain.gain.value = 0.4;
    body.connect(envelope);
    sparkle.connect(sparkleGain);
    sparkleGain.connect(envelope);
    envelope.connect(bus);
    envelope.connect(echoIn);
    body.start(time);
    sparkle.start(time);
    body.stop(time + length);
    sparkle.stop(time + length);
  }

  function soft(time, note, beats, type, peak, decay) {
    const length = beats * BEAT * decay;
    const envelope = ctx.createGain();
    envelope.gain.setValueAtTime(0.0001, time);
    envelope.gain.exponentialRampToValueAtTime(peak, time + 0.02);
    envelope.gain.exponentialRampToValueAtTime(0.0001, time + length);
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = midi(note);
    osc.connect(envelope);
    envelope.connect(bus);
    osc.start(time);
    osc.stop(time + length + 0.05);
  }

  function bell(time, note, peak) {
    [1, 2.76, 5.4].forEach((ratio, index) => {
      const envelope = ctx.createGain();
      envelope.gain.setValueAtTime(0.0001, time);
      envelope.gain.exponentialRampToValueAtTime(peak / (index + 1), time + 0.01);
      envelope.gain.exponentialRampToValueAtTime(0.0001, time + 5.5 / (index + 1));
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = midi(note) * ratio;
      osc.connect(envelope);
      envelope.connect(bus);
      osc.start(time);
      osc.stop(time + 6);
    });
  }

  function scheduleLoop(start) {
    BARS.forEach((bar, index) => {
      const barStart = start + index * 3 * BEAT;
      soft(barStart, bar.bass, 1, "sine", 0.34, 2.6);
      bar.chord.forEach((note) => {
        soft(barStart + BEAT, note, 1, "triangle", 0.05, 1.5);
        soft(barStart + 2 * BEAT, note, 1, "triangle", 0.04, 1.5);
      });
      let offset = 0;
      bar.tune.forEach(([note, beats]) => {
        musicBox(barStart + offset * BEAT, note, beats);
        offset += beats;
      });
    });
    bell(start, 93, 0.05);
    bell(start + 4 * 3 * BEAT, 81, 0.04);
  }

  function tick() {
    while (nextStart < ctx.currentTime + 2.5) {
      scheduleLoop(nextStart);
      nextStart += LOOP;
    }
  }

  function paint() {
    button.classList.toggle("on", playing);
    button.setAttribute("aria-pressed", String(playing));
    button.querySelector(".music-label").textContent = playing ? "Haunting" : "Silent";
    button.title = playing ? "Turn the haunted music off" : "Turn the haunted music on";
  }

  function start() {
    window.clearTimeout(stopTimer);
    if (!ctx) build();
    ctx.resume();
    playing = true;
    nextStart = ctx.currentTime + 0.25;
    window.clearInterval(timer);
    tick();
    timer = window.setInterval(tick, 500);
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(0.7, ctx.currentTime, 0.9);
    localStorage.setItem(STORE, "on");
    paint();
  }

  function stop(remember = true) {
    if (!ctx) return;
    playing = false;
    window.clearInterval(timer);
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(0, ctx.currentTime, 0.25);
    stopTimer = window.setTimeout(() => ctx.suspend(), 1500);
    if (remember) localStorage.setItem(STORE, "off");
    paint();
  }

  function duck(on) {
    ducked = on;
    if (duckGain) duckGain.gain.setTargetAtTime(on ? 0.22 : 1, ctx.currentTime, 0.3);
  }

  function level() {
    if (!analyser) return 0;
    const data = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(data);
    return Math.sqrt(data.reduce((sum, value) => sum + value * value, 0) / data.length);
  }

  button.addEventListener("click", () => (playing ? stop() : start()));

  // Browsers keep pages silent until someone touches them. The first touch starts the music,
  // unless it was switched off earlier.
  const wake = (event) => {
    if (button.contains(event.target)) return;
    document.removeEventListener("pointerdown", wake, true);
    document.removeEventListener("keydown", wake, true);
    if (localStorage.getItem(STORE) !== "off" && !playing) start();
  };
  document.addEventListener("pointerdown", wake, true);
  document.addEventListener("keydown", wake, true);

  paint();
  window.haunt = { start, stop, duck, level, isPlaying: () => playing };
})();
