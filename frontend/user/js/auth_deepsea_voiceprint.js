const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function mix(a, b, t) {
    return a + (b - a) * t;
}

function smoothstep(edge0, edge1, value) {
    const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return t * t * (3 - 2 * t);
}

function fract(value) {
    return value - Math.floor(value);
}

function seeded(seed) {
    return fract(Math.sin(seed * 127.1 + 311.7) * 43758.5453);
}

function auroraPoint(t, width, height, time, lane = 0) {
    const eased = smoothstep(0, 1, t);
    const x = width * (-0.11 + t * 1.2);
    const base = mix(height * 0.82, height * 0.24, eased);
    const primary = Math.sin(t * Math.PI * 1.42 - time * 0.28 + lane * 0.38) * height * 0.115;
    const secondary = Math.sin(t * Math.PI * 3.2 + time * 0.17 + lane * 1.15) * height * 0.028;
    const rightLift = smoothstep(0.58, 1, t) * height * 0.08;
    const calmEdges = Math.sin(t * Math.PI);
    return {
        x,
        y: base + (primary + secondary) * (0.42 + calmEdges * 0.58) - rightLift + lane * height * 0.033,
    };
}

function normalAt(t, width, height, time, lane) {
    const a = auroraPoint(clamp(t - 0.006, 0, 1), width, height, time, lane);
    const b = auroraPoint(clamp(t + 0.006, 0, 1), width, height, time, lane);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = Math.max(0.001, Math.hypot(dx, dy));
    return {
        x: -dy / length,
        y: dx / length,
    };
}

function drawCurve(ctx, width, height, time, lane, segments = 96) {
    ctx.beginPath();
    for (let i = 0; i <= segments; i += 1) {
        const t = i / segments;
        const point = auroraPoint(t, width, height, time, lane);
        if (i === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
    }
}

class AuroraDataCurtain {
    constructor(target) {
        this.target = target;
        this.canvas = target.querySelector("[data-auth-wave-canvas]");
        this.ctx = this.canvas?.getContext("2d", { alpha: true });
        this.motion = window.matchMedia(REDUCED_MOTION);
        this.width = 0;
        this.height = 0;
        this.dpr = 1;
        this.frame = 0;
        this.running = false;
        this.resizeObserver = null;
        this.draw = this.draw.bind(this);
        this.resize = this.resize.bind(this);
        this.handleMotionChange = this.handleMotionChange.bind(this);
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
    }

    init() {
        if (!this.canvas || !this.ctx || this.target.dataset.deepseaReady === "true") return;
        this.target.dataset.deepseaReady = "true";
        this.resizeObserver = new ResizeObserver(this.resize);
        this.resizeObserver.observe(this.target);
        this.motion.addEventListener?.("change", this.handleMotionChange);
        document.addEventListener("visibilitychange", this.handleVisibilityChange);
        window.addEventListener("beforeunload", () => this.destroy(), { once: true });
        this.resize();
        this.start();
    }

    resize() {
        const rect = this.target.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return;
        this.dpr = Math.min(window.devicePixelRatio || 1, 2);
        this.width = Math.round(rect.width);
        this.height = Math.round(rect.height);
        this.canvas.width = Math.round(this.width * this.dpr);
        this.canvas.height = Math.round(this.height * this.dpr);
        this.canvas.style.width = `${this.width}px`;
        this.canvas.style.height = `${this.height}px`;
        this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        this.paint(3.6, true);
    }

    start() {
        if (this.motion.matches) {
            this.stop();
            this.paint(3.6, true);
            return;
        }
        if (this.running) return;
        this.running = true;
        this.frame = requestAnimationFrame(this.draw);
    }

    stop() {
        this.running = false;
        if (this.frame) cancelAnimationFrame(this.frame);
        this.frame = 0;
    }

    draw(now) {
        if (!this.running) return;
        this.paint(now * 0.001, false);
        this.frame = requestAnimationFrame(this.draw);
    }

    paint(time, staticFrame) {
        if (!this.ctx || !this.width || !this.height) return;
        const phase = staticFrame ? 3.6 : time;
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this.width, this.height);
        this.paintAtmosphere(ctx, this.width, this.height, phase);
        this.paintAuroraCurtains(ctx, this.width, this.height, phase);
        this.paintDataParticles(ctx, this.width, this.height, phase);
        this.paintSignalTrace(ctx, this.width, this.height, phase);
        this.paintScanLight(ctx, this.width, this.height, phase);
        this.paintVignette(ctx, this.width, this.height);
        this.target.classList.add("is-deepsea-ready", "is-aurora-ready");
    }

    paintAtmosphere(ctx, width, height, time) {
        const cyanGlow = ctx.createRadialGradient(width * 0.18, height * 0.82, 0, width * 0.18, height * 0.82, width * 0.56);
        cyanGlow.addColorStop(0, "rgba(24, 228, 220, 0.22)");
        cyanGlow.addColorStop(0.42, "rgba(17, 126, 160, 0.08)");
        cyanGlow.addColorStop(1, "rgba(17, 126, 160, 0)");
        ctx.fillStyle = cyanGlow;
        ctx.fillRect(0, 0, width, height);

        const blueGlow = ctx.createRadialGradient(width * 0.66, height * 0.34, 0, width * 0.66, height * 0.34, width * 0.5);
        blueGlow.addColorStop(0, "rgba(37, 99, 235, 0.13)");
        blueGlow.addColorStop(0.5, "rgba(37, 99, 235, 0.045)");
        blueGlow.addColorStop(1, "rgba(37, 99, 235, 0)");
        ctx.fillStyle = blueGlow;
        ctx.fillRect(0, 0, width, height);

        const tealGlow = ctx.createRadialGradient(width * (0.74 + Math.sin(time * 0.17) * 0.03), height * 0.58, 0, width * 0.74, height * 0.58, width * 0.42);
        tealGlow.addColorStop(0, "rgba(20, 184, 166, 0.1)");
        tealGlow.addColorStop(0.44, "rgba(20, 184, 166, 0.035)");
        tealGlow.addColorStop(1, "rgba(20, 184, 166, 0)");
        ctx.fillStyle = tealGlow;
        ctx.fillRect(0, 0, width, height);
    }

    paintAuroraCurtains(ctx, width, height, time) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        const lanes = [-2.6, -1.75, -0.92, -0.2, 0.54, 1.2, 1.86];
        lanes.forEach((lane, index) => {
            const distance = Math.abs(lane) / 2.6;
            const breath = 0.9 + Math.sin(time * 0.42 + index) * 0.1;
            const gradient = ctx.createLinearGradient(width * 0.02, height, width, 0);
            gradient.addColorStop(0, `rgba(20, 235, 218, ${0.16 * breath})`);
            gradient.addColorStop(0.34, `rgba(20, 184, 166, ${0.18 * breath})`);
            gradient.addColorStop(0.58, `rgba(80, 164, 255, ${0.16 * breath})`);
            gradient.addColorStop(0.78, `rgba(37, 99, 235, ${0.13 * breath})`);
            gradient.addColorStop(1, "rgba(37, 99, 235, 0)");

            ctx.strokeStyle = gradient;
            ctx.lineWidth = height * (0.09 - distance * 0.035);
            ctx.shadowColor = index % 2 === 0 ? "rgba(28, 235, 226, 0.28)" : "rgba(37, 99, 235, 0.2)";
            ctx.shadowBlur = height * 0.052;
            ctx.globalAlpha = 0.74 - distance * 0.22;
            drawCurve(ctx, width, height, time * (0.84 + index * 0.012), lane, 128);
            ctx.stroke();
        });

        ctx.globalAlpha = 1;
        const coreGradient = ctx.createLinearGradient(width * 0.02, height, width * 0.96, 0);
        coreGradient.addColorStop(0, "rgba(84, 255, 235, 0.08)");
        coreGradient.addColorStop(0.3, "rgba(128, 244, 255, 0.58)");
        coreGradient.addColorStop(0.58, "rgba(130, 202, 255, 0.62)");
        coreGradient.addColorStop(0.82, "rgba(37, 99, 235, 0.48)");
        coreGradient.addColorStop(1, "rgba(37, 99, 235, 0.04)");
        ctx.strokeStyle = coreGradient;
        ctx.lineWidth = 1.25 + Math.sin(time * 0.5) * 0.2;
        ctx.shadowColor = "rgba(166, 255, 246, 0.36)";
        ctx.shadowBlur = 9;
        drawCurve(ctx, width, height, time * 0.92, -0.3, 160);
        ctx.stroke();
        ctx.restore();
    }

    paintDataParticles(ctx, width, height, time) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        for (let i = 0; i < 165; i += 1) {
            const seed = i + 4.7;
            const stream = seeded(seed);
            const t = fract(stream + time * (0.006 + seeded(seed + 20) * 0.012));
            const lane = mix(-1.9, 1.7, seeded(seed + 2));
            const normal = normalAt(t, width, height, time * 0.82, lane);
            const point = auroraPoint(t, width, height, time * 0.82, lane);
            const scatter = (seeded(seed + 7) - 0.5) * height * mix(0.08, 0.28, smoothstep(0.24, 0.9, t));
            const x = point.x + normal.x * scatter + Math.sin(time * 0.24 + seed) * 1.4;
            const y = point.y + normal.y * scatter + Math.cos(time * 0.18 + seed * 0.7) * 1.4;
            const focus = Math.sin(t * Math.PI);
            const twinkle = 0.56 + Math.sin(time * (1.1 + seeded(seed + 9) * 1.8) + seed) * 0.44;
            const radius = mix(0.55, 1.9, seeded(seed + 4)) * (0.72 + focus * 0.42);
            const huePick = seeded(seed + 12);
            const alpha = clamp((0.05 + focus * 0.27) * twinkle, 0.025, 0.36);
            const color = huePick > 0.72
                ? `rgba(37, 99, 235, ${alpha})`
                : huePick > 0.48
                    ? `rgba(80, 164, 255, ${alpha})`
                    : `rgba(92, 250, 236, ${alpha})`;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, Math.PI * 2);
            ctx.fill();
        }

        for (let i = 0; i < 34; i += 1) {
            const seed = i + 80;
            const x = width * mix(0.06, 0.96, seeded(seed));
            const y = height * mix(0.13, 0.84, seeded(seed + 1));
            const alpha = (0.025 + seeded(seed + 2) * 0.055) * (0.65 + Math.sin(time * 0.8 + seed) * 0.35);
            ctx.fillStyle = `rgba(205, 249, 255, ${alpha})`;
            ctx.fillRect(x, y, 1, 1);
        }

        ctx.restore();
    }

    paintSignalTrace(ctx, width, height, time) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        const traceGradient = ctx.createLinearGradient(width * 0.04, height, width * 0.9, 0);
        traceGradient.addColorStop(0, "rgba(56, 241, 226, 0)");
        traceGradient.addColorStop(0.22, "rgba(56, 241, 226, 0.2)");
        traceGradient.addColorStop(0.52, "rgba(235, 247, 255, 0.26)");
        traceGradient.addColorStop(0.78, "rgba(37, 99, 235, 0.18)");
        traceGradient.addColorStop(1, "rgba(37, 99, 235, 0)");
        ctx.strokeStyle = traceGradient;
        ctx.lineWidth = 0.75;
        ctx.shadowColor = "rgba(106, 252, 239, 0.16)";
        ctx.shadowBlur = 5;
        for (let lane = -2; lane <= 2; lane += 1) {
            ctx.globalAlpha = lane === 0 ? 0.58 : 0.22;
            drawCurve(ctx, width, height, time * 0.7 + lane * 0.1, lane * 0.74, 116);
            ctx.stroke();
        }
        ctx.restore();
    }

    paintScanLight(ctx, width, height, time) {
        const progress = fract(time * 0.07);
        const x = width * (-0.18 + progress * 1.36);
        const y = mix(height * 0.84, height * 0.26, smoothstep(0, 1, progress));

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.translate(x, y);
        ctx.rotate(-0.55);
        const beam = ctx.createLinearGradient(-width * 0.18, 0, width * 0.18, 0);
        beam.addColorStop(0, "rgba(255, 255, 255, 0)");
        beam.addColorStop(0.45, "rgba(197, 247, 255, 0.035)");
        beam.addColorStop(0.52, "rgba(255, 255, 255, 0.13)");
        beam.addColorStop(0.62, "rgba(37, 99, 235, 0.035)");
        beam.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = beam;
        ctx.fillRect(-width * 0.18, -height * 0.75, width * 0.36, height * 1.5);
        ctx.restore();
    }

    paintVignette(ctx, width, height) {
        const top = ctx.createLinearGradient(0, 0, 0, height);
        top.addColorStop(0, "rgba(2, 24, 35, 0.24)");
        top.addColorStop(0.44, "rgba(2, 24, 35, 0)");
        top.addColorStop(1, "rgba(2, 24, 35, 0.22)");
        ctx.fillStyle = top;
        ctx.fillRect(0, 0, width, height);

        const left = ctx.createLinearGradient(0, 0, width, 0);
        left.addColorStop(0, "rgba(1, 20, 28, 0.34)");
        left.addColorStop(0.16, "rgba(1, 20, 28, 0)");
        left.addColorStop(1, "rgba(1, 20, 28, 0.28)");
        ctx.fillStyle = left;
        ctx.fillRect(0, 0, width, height);
    }

    handleMotionChange() {
        if (this.motion.matches) this.stop();
        this.start();
    }

    handleVisibilityChange() {
        if (document.visibilityState === "hidden") this.stop();
        else this.start();
    }

    destroy() {
        this.stop();
        this.resizeObserver?.disconnect();
        this.motion.removeEventListener?.("change", this.handleMotionChange);
        document.removeEventListener("visibilitychange", this.handleVisibilityChange);
    }
}

export function initDeepSeaVoiceprint(selector = "#loginOverlay .auth-signal") {
    document.querySelectorAll(selector).forEach((target) => {
        new AuroraDataCurtain(target).init();
    });
}
