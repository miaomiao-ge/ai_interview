const REDUCE_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function gaussian(x, center, width) {
    const n = (x - center) / width;
    return Math.exp(-n * n);
}

function mix(a, b, t) {
    return a + (b - a) * t;
}

function smoothstep(edge0, edge1, value) {
    const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return t * t * (3 - 2 * t);
}

function roundedRect(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
}

function colorStop(t, alpha, variant) {
    if (variant === "light") {
        if (t < 0.55) return `rgba(18, 194, 196, ${alpha})`;
        return `rgba(22, ${Math.round(mix(164, 116, t))}, 235, ${alpha})`;
    }
    if (t > 0.62) return `rgba(151, 216, 106, ${alpha})`;
    if (t > 0.45) return `rgba(178, 246, 233, ${alpha})`;
    return `rgba(96, 222, 233, ${alpha})`;
}

function darkWaveY(t, h, phase) {
    const breath = 1 + Math.sin(phase * 0.34) * 0.045;
    const drift = Math.sin(phase * 0.18) * h * 0.006;
    const ascent = h * (0.72 - 0.35 * smoothstep(0, 1, t));
    const broadWave = Math.sin(t * Math.PI * 2.02 - phase * 0.14) * h * 0.056 * breath;
    const quietDetail = Math.sin(t * Math.PI * 5.8 + phase * 0.1) * h * 0.01;
    const middleValley = gaussian(t, 0.47, 0.13) * h * 0.044;
    const rightArcLift = smoothstep(0.6, 1, t) * h * 0.052;
    return ascent + broadWave + quietDetail + middleValley - rightArcLift + drift;
}

function lightWaveY(t, h, phase) {
    return h * 0.45
        - Math.sin(t * Math.PI * 2.22 + phase * 0.34) * h * 0.055
        + Math.sin(t * Math.PI * 5.2 - phase * 0.18) * h * 0.018;
}

function darkEnvelope(t, phase) {
    const attack = 0.8 * gaussian(t, 0.19, 0.075);
    const body = 0.52 * gaussian(t, 0.41, 0.11);
    const tail = 0.18 * gaussian(t, 0.72, 0.18);
    const pulse = 0.025 * Math.sin(phase * 1.2 + t * 24);
    return clamp(0.08 + attack + body + tail + pulse, 0.05, 0.95);
}

function lightEnvelope(t, phase) {
    const first = 0.52 * gaussian(t, 0.22, 0.085);
    const middle = 1.05 * gaussian(t, 0.5, 0.085);
    const last = 0.83 * gaussian(t, 0.78, 0.11);
    const floor = 0.08 + 0.025 * Math.sin(phase * 1.6 + t * 23);
    return clamp(floor + first + middle + last, 0.04, 1.16);
}

function echoRibbonY(t, h, phase, lane = 0) {
    const center = h * 0.52;
    const edgeCalm = smoothstep(0.02, 0.2, t) * (1 - smoothstep(0.84, 1, t));
    const breath = 0.86 + Math.sin(phase * 0.42) * 0.06;
    const broad = Math.sin(t * Math.PI * 2.18 - phase * 0.3) * h * 0.048;
    const detail = Math.sin(t * Math.PI * 5.6 + phase * 0.16) * h * 0.012;
    const lift = gaussian(t, 0.53, 0.18) * h * 0.018;
    const laneOffset = lane * h * 0.014;
    const laneDrift = Math.sin(phase * 0.22 + lane * 1.7 + t * 3.4) * h * 0.004;
    return center + (broad + detail) * edgeCalm * breath - lift + laneOffset + laneDrift;
}

function echoRibbonEnvelope(t, phase) {
    const left = 0.32 * gaussian(t, 0.24, 0.13);
    const middle = 0.48 * gaussian(t, 0.52, 0.17);
    const right = 0.28 * gaussian(t, 0.76, 0.16);
    const breath = 0.04 * Math.sin(phase * 0.8 + t * 12);
    return clamp(0.24 + left + middle + right + breath, 0.18, 0.86);
}

function fract(value) {
    return value - Math.floor(value);
}

function auroraCorePoint(w, h) {
    return {
        x: w * 0.52,
        y: h * 0.49,
        radius: clamp(Math.min(w, h) * 0.19, 24, 48),
    };
}

function auroraFlowPoint(t, w, h, phase, seed = 0) {
    const { x: cx, y: cy } = auroraCorePoint(w, h);
    const noise = fract(Math.sin(seed * 93.17 + 2.7) * 43758.5453);
    const lane = (noise - 0.5) * 2;

    if (t < 0.58) {
        const u = t / 0.58;
        const eased = smoothstep(0, 1, u);
        const startY = h * (0.25 + noise * 0.5);
        const arc = Math.sin(u * Math.PI + seed * 1.7 + phase * 0.22) * h * 0.105 * (1 - eased);
        return {
            x: mix(-w * 0.05, cx - w * 0.018, eased),
            y: mix(startY, cy + lane * h * 0.045, eased) + arc,
            focus: eased,
        };
    }

    const u = (t - 0.58) / 0.42;
    const eased = smoothstep(0, 1, u);
    const exitBand = (Math.round(noise * 6) - 3) * h * 0.04;
    const arc = Math.sin(u * Math.PI * 1.45 + seed * 3.1 + phase * 0.18) * h * 0.036 * (1 - u);
    return {
        x: mix(cx + w * 0.02, w * 1.04, eased),
        y: mix(cy + lane * h * 0.03, h * 0.49 + exitBand, eased) + arc,
        focus: 1 - eased * 0.5,
    };
}

class AuthWaveCanvas {
    constructor(target) {
        this.target = target;
        this.canvas = target.querySelector("[data-auth-wave-canvas]");
        this.ctx = this.canvas?.getContext("2d", { alpha: true });
        this.overlay = target.closest("#loginOverlay");
        this.variant = target.classList.contains("auth-forgot-illustration")
            ? "recovery"
            : target.classList.contains("auth-register-wave")
                ? "light"
                : "dark";
        this.motionQuery = window.matchMedia(REDUCE_MOTION_QUERY);
        this.resizeObserver = null;
        this.modeObserver = null;
        this.frame = 0;
        this.width = 0;
        this.height = 0;
        this.dpr = 1;
        this.phase = 0;
        this.sceneAge = 0;
        this.memoryStartedAt = performance.now() * 0.001;
        this.mode = this.overlay?.dataset.mode || "login";
        this.running = false;
        this.render = this.render.bind(this);
        this.resize = this.resize.bind(this);
        this.onVisibilityChange = this.onVisibilityChange.bind(this);
        this.onMotionChange = this.onMotionChange.bind(this);
    }

    init() {
        if (!this.canvas || !this.ctx || this.target.dataset.waveReady === "true") return;

        this.target.dataset.waveReady = "true";
        this.resizeObserver = new ResizeObserver(this.resize);
        this.resizeObserver.observe(this.target);

        this.modeObserver = new MutationObserver(() => {
            const nextMode = this.overlay?.dataset.mode || "login";
            if (this.variant === "recovery" && nextMode === "forgot" && this.mode !== "forgot") {
                this.memoryStartedAt = performance.now() * 0.001;
            }
            this.mode = nextMode;
            requestAnimationFrame(this.resize);
        });
        if (this.overlay) {
            this.modeObserver.observe(this.overlay, { attributes: true, attributeFilter: ["data-mode", "style"] });
        }

        document.addEventListener("visibilitychange", this.onVisibilityChange);
        this.motionQuery.addEventListener?.("change", this.onMotionChange);
        window.addEventListener("beforeunload", () => this.destroy(), { once: true });

        this.resize();
        this.start();
    }

    resize() {
        const rect = this.target.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) {
            this.width = 0;
            this.height = 0;
            return;
        }

        this.dpr = Math.min(window.devicePixelRatio || 1, 2);
        this.width = Math.round(rect.width);
        this.height = Math.round(rect.height);
        this.canvas.width = Math.round(this.width * this.dpr);
        this.canvas.height = Math.round(this.height * this.dpr);
        this.canvas.style.width = `${this.width}px`;
        this.canvas.style.height = `${this.height}px`;
        this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        const staticFrame = !(this.variant === "recovery" && this.mode === "forgot" && !this.motionQuery.matches);
        this.draw(performance.now(), staticFrame);
    }

    start() {
        if (this.motionQuery.matches) {
            this.stop();
            this.draw(performance.now(), true);
            return;
        }
        if (this.running) return;
        this.running = true;
        this.frame = requestAnimationFrame(this.render);
    }

    stop() {
        this.running = false;
        if (this.frame) {
            cancelAnimationFrame(this.frame);
            this.frame = 0;
        }
    }

    onVisibilityChange() {
        if (document.visibilityState === "hidden") this.stop();
        else this.start();
    }

    onMotionChange() {
        if (this.motionQuery.matches) {
            this.stop();
            this.draw(performance.now(), true);
        } else {
            this.start();
        }
    }

    render(now) {
        if (!this.running) return;
        this.draw(now, false);
        this.frame = requestAnimationFrame(this.render);
    }

    draw(now, staticFrame) {
        if (!this.width || !this.height || !this.ctx) return;
        this.phase = staticFrame ? 1.28 : now * 0.001;
        this.sceneAge = staticFrame ? 3 : Math.max(0, now * 0.001 - this.memoryStartedAt);
        const ctx = this.ctx;
        ctx.clearRect(0, 0, this.width, this.height);

        if (this.variant === "recovery") {
            this.drawMemoryConstellationScene(ctx, this.width, this.height);
        } else if (this.variant === "light") {
            this.drawLightScene(ctx, this.width, this.height);
        } else {
            this.drawDarkScene(ctx, this.width, this.height);
        }

        this.target.classList.add("is-canvas-ready");
    }

    drawDarkScene(ctx, w, h) {
        this.drawDarkAtmosphere(ctx, w, h);
        this.drawDarkBackgroundDots(ctx, w, h);
        this.drawDarkVerticalSpectrum(ctx, w, h);
        this.drawDarkQuietSource(ctx, w, h);
        this.drawDarkSilkBridge(ctx, w, h);
        this.drawDarkTransitionDots(ctx, w, h);
        this.drawDarkDotRibbon(ctx, w, h);
        this.drawDarkCrestDots(ctx, w, h);
        this.drawDarkPulse(ctx, w, h);
    }

    drawDarkAtmosphere(ctx, w, h) {
        const aura = ctx.createRadialGradient(w * 0.17, h * 0.62, 0, w * 0.17, h * 0.62, w * 0.54);
        aura.addColorStop(0, "rgba(87, 235, 221, 0.12)");
        aura.addColorStop(0.42, "rgba(42, 203, 184, 0.038)");
        aura.addColorStop(1, "rgba(42, 203, 196, 0)");
        ctx.fillStyle = aura;
        ctx.fillRect(0, 0, w, h);

        const rightAura = ctx.createRadialGradient(w * 0.78, h * 0.43, 0, w * 0.78, h * 0.43, w * 0.5);
        rightAura.addColorStop(0, "rgba(126, 212, 110, 0.052)");
        rightAura.addColorStop(0.48, "rgba(75, 197, 184, 0.022)");
        rightAura.addColorStop(1, "rgba(75, 197, 200, 0)");
        ctx.fillStyle = rightAura;
        ctx.fillRect(0, 0, w, h);

        const midHaze = ctx.createLinearGradient(0, 0, w, 0);
        midHaze.addColorStop(0, "rgba(89, 235, 218, 0.028)");
        midHaze.addColorStop(0.45, "rgba(183, 255, 241, 0.03)");
        midHaze.addColorStop(1, "rgba(130, 218, 111, 0.016)");
        ctx.fillStyle = midHaze;
        ctx.fillRect(0, h * 0.37, w, h * 0.34);

        const lowBand = ctx.createLinearGradient(0, h * 0.48, 0, h);
        lowBand.addColorStop(0, "rgba(5, 46, 50, 0)");
        lowBand.addColorStop(1, "rgba(4, 34, 39, 0.2)");
        ctx.fillStyle = lowBand;
        ctx.fillRect(0, h * 0.46, w, h * 0.54);
    }

    drawDarkBackgroundDots(ctx, w, h) {
        const stepX = clamp(w * 0.029, 11, 16);
        const stepY = clamp(h * 0.068, 9, 13);
        ctx.save();
        for (let x = -stepX; x <= w + stepX; x += stepX) {
            const t = x / w;
            const center = darkWaveY(clamp(t, 0, 1), h, this.phase * 0.72);
            const spread = h * (0.06 + smoothstep(0.34, 1, t) * 0.22);
            for (let y = center - spread; y <= center + spread; y += stepY) {
                const distance = Math.abs(y - center) / Math.max(1, spread);
                const alpha = clamp((1 - distance) * 0.055 * smoothstep(0.18, 0.92, t), 0, 0.048);
                if (alpha <= 0.01) continue;
                ctx.fillStyle = `rgba(130, 229, 218, ${alpha})`;
                ctx.beginPath();
                ctx.arc(x, y, 0.46 + (1 - distance) * 0.3, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawDarkQuietSource(ctx, w, h) {
        const originX = w * 0.14;
        const originY = darkWaveY(0.12, h, this.phase);
        const glow = ctx.createRadialGradient(originX, originY, 0, originX, originY, w * 0.22);
        glow.addColorStop(0, "rgba(116, 239, 218, 0.105)");
        glow.addColorStop(0.48, "rgba(68, 218, 203, 0.032)");
        glow.addColorStop(1, "rgba(68, 218, 214, 0)");
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, w * 0.4, h);

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        const count = 34;
        for (let i = 0; i < count; i += 1) {
            const t = i / (count - 1);
            const x = w * (0.018 + t * 0.282);
            const curveT = 0.025 + t * 0.25;
            const center = darkWaveY(curveT, h, this.phase * 0.84);
            const voice = 0.62 * gaussian(t, 0.18, 0.07)
                + 0.42 * gaussian(t, 0.4, 0.1)
                + 0.15 * gaussian(t, 0.68, 0.15);
            const jitter = 0.94 + Math.sin(this.phase * 1.02 + i * 0.72) * 0.07;
            const height = h * (0.025 + voice * 0.155) * jitter;
            const alpha = clamp(0.12 + voice * 0.38, 0.12, 0.46);
            const grad = ctx.createLinearGradient(0, center - height, 0, center + height);
            grad.addColorStop(0, `rgba(174, 255, 239, ${alpha * 0.68})`);
            grad.addColorStop(0.5, `rgba(82, 229, 214, ${alpha})`);
            grad.addColorStop(1, `rgba(105, 130, 216, ${alpha * 0.2})`);
            ctx.fillStyle = grad;
            roundedRect(ctx, x - 0.95, center - height * 0.58, 1.9, height, 2);
            ctx.fill();
        }

        for (let i = 0; i < 32; i += 1) {
            const t = i / 31;
            const x = w * (0.042 + t * 0.29);
            const y = darkWaveY(0.05 + t * 0.26, h, this.phase * 0.82)
                + Math.sin(this.phase * 0.36 + i * 0.55) * h * 0.013;
            const alpha = 0.045 + Math.sin(t * Math.PI) * 0.145;
            ctx.fillStyle = `rgba(160, 250, 238, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 0.48 + Math.sin(t * Math.PI) * 0.46, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    drawDarkSilkBridge(ctx, w, h) {
        ctx.save();
        const breath = 0.94 + Math.sin(this.phase * 0.44) * 0.06;
        const ribbonGrad = ctx.createLinearGradient(w * 0.04, 0, w * 0.92, 0);
        ribbonGrad.addColorStop(0, "rgba(91, 229, 214, 0.052)");
        ribbonGrad.addColorStop(0.27, "rgba(164, 250, 235, 0.31)");
        ribbonGrad.addColorStop(0.52, `rgba(229, 255, 247, ${0.5 * breath})`);
        ribbonGrad.addColorStop(0.72, `rgba(162, 233, 136, ${0.48 * breath})`);
        ribbonGrad.addColorStop(1, "rgba(91, 211, 203, 0.038)");

        ctx.strokeStyle = ribbonGrad;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.shadowColor = "rgba(151, 255, 229, 0.15)";
        ctx.shadowBlur = 5.5 * breath;

        for (let pass = 0; pass < 3; pass += 1) {
            ctx.globalAlpha = (pass === 0 ? 0.18 : pass === 1 ? 0.42 : 0.92) * breath;
            ctx.lineWidth = (pass === 0 ? 8 : pass === 1 ? 3.2 : 1.08) * breath;
            ctx.beginPath();
            for (let i = 0; i <= 180; i += 1) {
                const local = i / 180;
                const t = 0.04 + local * 0.86;
                const x = w * (0.032 + local * 0.92);
                const y = darkWaveY(t, h, this.phase * 0.82)
                    + Math.sin(local * Math.PI * 2.05 + this.phase * 0.14) * h * 0.0035;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        ctx.shadowBlur = 0;
        for (let i = 0; i < 46; i += 1) {
            const local = i / 45;
            const t = 0.27 + local * 0.32;
            const x = w * (0.24 + local * 0.35);
            const y = darkWaveY(t, h, this.phase * 0.82)
                + Math.sin(this.phase * 0.42 + i * 0.5) * h * 0.012;
            const density = smoothstep(0.08, 0.72, local);
            const alpha = (0.02 + Math.sin(local * Math.PI) * 0.15) * density;
            ctx.fillStyle = `rgba(156, 246, 235, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 0.48 + density * 0.58, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    drawDarkTransitionDots(ctx, w, h) {
        const columns = 58;
        const progress = (this.phase * 0.038 + 0.08) % 1;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        for (let i = 0; i < columns; i += 1) {
            const local = i / (columns - 1);
            const t = 0.31 + local * 0.3;
            const x = w * (0.285 + local * 0.32);
            const center = darkWaveY(t, h, this.phase * 0.82);
            const rows = Math.round(mix(1, 11, smoothstep(0.04, 0.95, local)));
            const spread = h * (0.012 + smoothstep(0.08, 1, local) * 0.102);
            const sweep = gaussian(t, progress, 0.085) + gaussian(t, progress - 1, 0.085);

            for (let r = -rows; r <= rows; r += 1) {
                const rn = rows ? r / rows : 0;
                const fade = Math.pow(1 - Math.abs(rn), 0.84);
                const y = center
                    + rn * spread
                    + Math.sin(this.phase * 0.26 + i * 0.27 + r * 0.42) * h * 0.0045;
                const alpha = clamp((0.024 + fade * 0.16 + local * 0.048 + sweep * 0.075) * smoothstep(0, 0.14, local), 0.016, 0.3);
                ctx.fillStyle = `rgba(158, 248, 232, ${alpha})`;
                ctx.beginPath();
                ctx.arc(x, y, 0.46 + fade * 0.62 + local * 0.16 + sweep * 0.24, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawDarkVerticalSpectrum(ctx, w, h) {
        const count = 42;
        const startX = -w * 0.018;
        const endX = w * 0.33;
        const barWidth = clamp(w * 0.0034, 1.2, 2.1);

        for (let i = 0; i < count; i += 1) {
            const t = i / (count - 1);
            const x = startX + (endX - startX) * t;
            const curveT = 0.02 + t * 0.29;
            const centerY = darkWaveY(curveT, h, this.phase * 0.86);
            const env = darkEnvelope(t, this.phase);
            const taper = 1 - smoothstep(0.7, 1, t) * 0.74;
            const spike = 0.76 + 0.22 * Math.pow(Math.sin(i * 0.96 + this.phase * 0.36) * 0.5 + 0.5, 2);
            const height = h * clamp((0.024 + env * 0.24) * spike * taper, 0.028, 0.285);
            const top = centerY - height * 0.52;
            const bottom = centerY + height * 0.48;
            const grad = ctx.createLinearGradient(0, top, 0, bottom);
            grad.addColorStop(0, "rgba(170, 255, 238, 0.62)");
            grad.addColorStop(0.48, "rgba(74, 222, 210, 0.5)");
            grad.addColorStop(1, "rgba(96, 118, 210, 0.12)");

            ctx.save();
            ctx.globalAlpha = clamp(0.14 + env * 0.42, 0.16, 0.58) * (1 - smoothstep(0.84, 1, t) * 0.45);
            ctx.shadowColor = "rgba(90, 232, 214, 0.15)";
            ctx.shadowBlur = env > 0.7 ? 5 : 1.5;
            ctx.fillStyle = grad;
            roundedRect(ctx, x - barWidth / 2, top, barWidth, bottom - top, barWidth);
            ctx.fill();
            ctx.restore();

            const dotSpacing = clamp(h * 0.048, 7, 10);
            const dotCount = Math.floor(height / dotSpacing);
            ctx.fillStyle = "rgba(176, 250, 236, 0.22)";
            for (let d = 0; d <= dotCount; d += 1) {
                const y = top + d * dotSpacing;
                if (y > bottom) continue;
                ctx.beginPath();
                ctx.arc(x, y, 0.56 + env * 0.24, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    drawDarkDotRibbon(ctx, w, h) {
        const columns = 144;
        const rows = 19;
        const progress = (this.phase * 0.04 + 0.12) % 1;

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        for (let i = 0; i < columns; i += 1) {
            const local = i / (columns - 1);
            const t = 0.46 + local * 0.58;
            const x = w * (0.42 + local * 0.66);
            const center = darkWaveY(t, h, this.phase * 0.82);
            const rightStrength = smoothstep(0.42, 0.98, t);
            const spread = h * (0.045 + rightStrength * 0.245);
            const rowsVisible = Math.round(mix(4, rows, rightStrength));
            const windowGlow = gaussian(t, progress, 0.075) + gaussian(t, progress - 1, 0.075);

            for (let r = -rowsVisible; r <= rowsVisible; r += 1) {
                const rowNorm = rowsVisible ? r / rowsVisible : 0;
                const strand = rowNorm * spread;
                const curveLift = -Math.abs(rowNorm) * rightStrength * h * 0.035;
                const y = center + strand + curveLift
                    + Math.sin(t * Math.PI * 4.35 + r * 0.31 + this.phase * 0.23) * h * 0.0072;
                const rowFade = Math.pow(1 - Math.abs(rowNorm), 0.72);
                const sideFade = smoothstep(0.45, 0.54, t) * (1 - smoothstep(1.0, 1.06, t));
                const alpha = sideFade * clamp(0.022 + rowFade * 0.19 + rightStrength * 0.05 + windowGlow * 0.12, 0.012, 0.38);
                const radius = 0.52 + rowFade * 0.84 + rightStrength * 0.22 + windowGlow * 0.31;
                ctx.fillStyle = colorStop(t, alpha, "dark");
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawDarkCrestDots(ctx, w, h) {
        const progress = (this.phase * 0.034 + 0.18) % 1;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        for (let strand = 0; strand < 8; strand += 1) {
            const strandNorm = strand / 7;
            for (let i = 0; i < 98; i += 1) {
                const local = i / 97;
                const t = 0.5 + local * 0.5;
                const x = w * (0.47 + local * 0.58);
                const lift = h * (0.014 + strandNorm * 0.056) * smoothstep(0.5, 0.94, t);
                const y = darkWaveY(t, h, this.phase * 0.84)
                    - lift
                    + Math.sin(local * Math.PI * 2 + strand * 0.42 + this.phase * 0.14) * h * 0.008;
                const centerFade = Math.sin(local * Math.PI);
                const sweep = gaussian(t, progress, 0.09) + gaussian(t, progress - 1, 0.09);
                const alpha = clamp((0.038 + centerFade * 0.16 + sweep * 0.086) * (0.58 + strandNorm * 0.28), 0.016, 0.33);
                const radius = 0.5 + centerFade * 0.66 + strandNorm * 0.22 + sweep * 0.28;
                const greenBias = smoothstep(0.58, 0.88, t);
                ctx.fillStyle = greenBias > 0.35
                    ? `rgba(158, 225, 112, ${alpha})`
                    : `rgba(142, 244, 234, ${alpha})`;
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawDarkTrace(ctx, w, h) {
        const grad = ctx.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, "rgba(107, 236, 232, 0.05)");
        grad.addColorStop(0.42, "rgba(225, 255, 246, 0.48)");
        grad.addColorStop(0.68, "rgba(176, 246, 138, 0.52)");
        grad.addColorStop(1, "rgba(96, 202, 213, 0.07)");

        ctx.save();
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.18;
        ctx.shadowColor = "rgba(170, 255, 238, 0.18)";
        ctx.shadowBlur = 5;
        for (let line = -1; line <= 1; line += 1) {
            ctx.globalAlpha = line === 0 ? 1 : 0.34;
            ctx.beginPath();
            for (let i = 0; i <= 170; i += 1) {
                const t = i / 170;
                const x = w * (-0.02 + t * 1.06);
                const offset = line * h * (0.018 + smoothstep(0.48, 1, t) * 0.052);
                const y = darkWaveY(t, h, this.phase) + offset;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
        ctx.restore();
    }

    drawDarkPulse(ctx, w, h) {
        const progress = (this.phase * 0.043) % 1;
        const x = w * (-0.04 + progress * 1.1);
        const y = darkWaveY(progress, h, this.phase * 0.92);
        const glow = ctx.createRadialGradient(x, y, 0, x, y, w * 0.16);
        glow.addColorStop(0, "rgba(220, 255, 238, 0.105)");
        glow.addColorStop(0.34, "rgba(111, 236, 215, 0.04)");
        glow.addColorStop(1, "rgba(104, 232, 217, 0)");
        ctx.fillStyle = glow;
        ctx.fillRect(x - w * 0.18, y - h * 0.5, w * 0.36, h);
    }

    drawLightScene(ctx, w, h) {
        this.drawIdentityGatewayField(ctx, w, h);
        this.drawIdentityGatewayStreams(ctx, w, h);
        this.drawIdentityGatewayParticles(ctx, w, h);
        this.drawIdentityGatewayPortal(ctx, w, h);
        this.drawIdentityGatewayScan(ctx, w, h);
    }

    quantumGardenCore(w, h) {
        return {
            x: w * 0.42,
            y: h * 0.53,
            radius: clamp(Math.min(w, h) * 0.14, 20, 36),
        };
    }

    identityGatewayCore(w, h) {
        return {
            x: w * 0.5,
            y: h * 0.52,
            radius: clamp(Math.min(w, h) * 0.19, 26, 42),
        };
    }

    drawIdentityGatewayField(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.identityGatewayCore(w, h);
        const breath = 0.9 + Math.sin(this.phase * 0.64) * 0.1;

        const wash = ctx.createLinearGradient(0, h * 0.06, w, h * 0.96);
        wash.addColorStop(0, "rgba(221, 255, 251, 0.46)");
        wash.addColorStop(0.45, "rgba(238, 252, 255, 0.08)");
        wash.addColorStop(0.72, "rgba(213, 222, 255, 0.18)");
        wash.addColorStop(1, "rgba(255, 226, 251, 0.2)");
        ctx.fillStyle = wash;
        ctx.fillRect(0, 0, w, h);

        const coreGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 5.6);
        coreGlow.addColorStop(0, `rgba(38, 236, 219, ${0.28 * breath})`);
        coreGlow.addColorStop(0.28, `rgba(94, 183, 255, ${0.16 * breath})`);
        coreGlow.addColorStop(0.58, "rgba(145, 103, 255, 0.08)");
        coreGlow.addColorStop(0.82, "rgba(255, 104, 203, 0.045)");
        coreGlow.addColorStop(1, "rgba(255, 104, 203, 0)");
        ctx.fillStyle = coreGlow;
        ctx.fillRect(0, 0, w, h);

        const leftAura = ctx.createRadialGradient(w * 0.08, h * 0.52, 0, w * 0.08, h * 0.52, w * 0.34);
        leftAura.addColorStop(0, "rgba(23, 213, 198, 0.12)");
        leftAura.addColorStop(1, "rgba(23, 213, 198, 0)");
        ctx.fillStyle = leftAura;
        ctx.fillRect(0, 0, w * 0.5, h);

        const rightAura = ctx.createRadialGradient(w * 0.96, h * 0.44, 0, w * 0.96, h * 0.44, w * 0.36);
        rightAura.addColorStop(0, "rgba(137, 120, 255, 0.11)");
        rightAura.addColorStop(0.62, "rgba(255, 105, 209, 0.055)");
        rightAura.addColorStop(1, "rgba(255, 105, 209, 0)");
        ctx.fillStyle = rightAura;
        ctx.fillRect(w * 0.42, 0, w * 0.58, h);

        ctx.save();
        ctx.globalAlpha = 0.14;
        ctx.lineWidth = 0.58;
        for (let i = 0; i < 8; i += 1) {
            const y = h * (0.15 + i * 0.1);
            const grad = ctx.createLinearGradient(0, y, w, y);
            grad.addColorStop(0, "rgba(25, 204, 192, 0)");
            grad.addColorStop(0.42, "rgba(25, 204, 192, 0.22)");
            grad.addColorStop(0.7, "rgba(108, 137, 255, 0.13)");
            grad.addColorStop(1, "rgba(255, 98, 204, 0)");
            ctx.strokeStyle = grad;
            ctx.beginPath();
            ctx.moveTo(-w * 0.04, y + Math.sin(this.phase * 0.12 + i) * h * 0.008);
            ctx.bezierCurveTo(w * 0.22, y - h * 0.09, w * 0.6, y + h * 0.12, w * 1.04, y - h * 0.03);
            ctx.stroke();
        }
        ctx.restore();
    }

    drawIdentityGatewayStreams(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.identityGatewayCore(w, h);
        const open = 0.72 + Math.sin(this.phase * 0.54) * 0.08;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        for (let side = -1; side <= 1; side += 2) {
            for (let i = 0; i < 9; i += 1) {
                const lane = (i - 4) / 4;
                const startX = side < 0 ? -w * 0.06 : w * 1.06;
                const endX = cx + side * radius * (1.15 + open * 0.18);
                const startY = h * (0.2 + i * 0.068) + Math.sin(this.phase * 0.28 + i) * h * 0.01;
                const endY = cy + lane * radius * 0.62;
                const grad = ctx.createLinearGradient(startX, startY, endX, endY);
                grad.addColorStop(0, side < 0 ? "rgba(25, 211, 198, 0)" : "rgba(255, 105, 207, 0)");
                grad.addColorStop(0.42, side < 0 ? "rgba(39, 223, 211, 0.18)" : "rgba(135, 128, 255, 0.16)");
                grad.addColorStop(0.84, "rgba(244, 255, 252, 0.42)");
                grad.addColorStop(1, "rgba(244, 255, 252, 0)");
                ctx.strokeStyle = grad;
                ctx.lineWidth = i === 4 ? 1.25 : 0.66 + (i % 3) * 0.11;
                ctx.beginPath();
                ctx.moveTo(startX, startY);
                ctx.bezierCurveTo(
                    mix(startX, endX, 0.34),
                    startY + lane * h * 0.075,
                    mix(startX, endX, 0.72),
                    endY - lane * h * 0.095,
                    endX,
                    endY
                );
                ctx.stroke();
            }
        }
        ctx.restore();
    }

    drawIdentityGatewayParticles(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.identityGatewayCore(w, h);
        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        for (let side = -1; side <= 1; side += 2) {
            for (let i = 0; i < 42; i += 1) {
                const seed = i * 0.618 + (side > 0 ? 9.2 : 0.6);
                const raw = fract(seed * 0.37 + this.phase * (0.055 + (i % 5) * 0.003));
                const t = smoothstep(0, 1, raw);
                const lane = fract(Math.sin(seed * 12.91) * 91.7) - 0.5;
                const startX = side < 0 ? -w * 0.02 : w * 1.02;
                const endX = cx + side * radius * (1.04 + lane * 0.16);
                const x = mix(startX, endX, t);
                const baseY = h * (0.3 + fract(Math.sin(seed * 7.3) * 11.7) * 0.42);
                const y = mix(baseY, cy + lane * radius * 1.05, t)
                    + Math.sin(t * Math.PI + this.phase * 0.36 + seed) * h * 0.055 * (1 - t);
                const focus = smoothstep(0.18, 1, t);
                const alpha = clamp((0.08 + focus * 0.25) * (1 - t * 0.38), 0.035, 0.34);
                const size = 0.8 + focus * 1.4 + Math.sin(this.phase * 1.2 + seed) * 0.18;
                ctx.fillStyle = side < 0
                    ? `rgba(34, 230, 216, ${alpha})`
                    : `rgba(${Math.round(mix(112, 255, focus))}, ${Math.round(mix(133, 112, focus))}, ${Math.round(mix(255, 210, focus))}, ${alpha * 0.88})`;
                ctx.beginPath();
                ctx.arc(x, y, Math.max(0.5, size), 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawIdentityGatewayPortal(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.identityGatewayCore(w, h);
        const r = radius * (1 + Math.sin(this.phase * 0.62) * 0.026);
        const gateW = r * 2.52;
        const gateH = r * 2.04;
        const gateX = -gateW / 2;
        const gateY = -gateH / 2;
        const open = 0.54 + Math.sin(this.phase * 0.48) * 0.08;
        const panelGap = gateW * (0.1 + open * 0.055);
        const panelW = gateW * 0.5 - panelGap * 0.5;
        const scan = ((this.phase * 0.074) % 1) * gateW;

        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        const halo = ctx.createRadialGradient(cx, cy, r * 0.1, cx, cy, r * 3.8);
        halo.addColorStop(0, "rgba(255, 255, 255, 0.46)");
        halo.addColorStop(0.24, "rgba(36, 236, 219, 0.28)");
        halo.addColorStop(0.5, "rgba(97, 176, 255, 0.16)");
        halo.addColorStop(0.76, "rgba(255, 101, 204, 0.07)");
        halo.addColorStop(1, "rgba(255, 101, 204, 0)");
        ctx.fillStyle = halo;
        ctx.fillRect(cx - r * 3.8, cy - r * 3.1, r * 7.6, r * 6.2);

        ctx.save();
        ctx.translate(cx, cy + Math.sin(this.phase * 0.5) * r * 0.035);
        ctx.rotate(Math.sin(this.phase * 0.26) * 0.01);

        const drop = ctx.createRadialGradient(0, gateH * 0.52, r * 0.2, 0, gateH * 0.54, gateW * 0.72);
        drop.addColorStop(0, "rgba(22, 180, 190, 0.18)");
        drop.addColorStop(0.58, "rgba(126, 115, 255, 0.11)");
        drop.addColorStop(1, "rgba(126, 115, 255, 0)");
        ctx.fillStyle = drop;
        ctx.fillRect(-gateW * 0.78, gateY + gateH * 0.2, gateW * 1.56, gateH * 1.4);

        const frameFill = ctx.createLinearGradient(gateX, gateY, gateX + gateW, gateY + gateH);
        frameFill.addColorStop(0, "rgba(255, 255, 255, 0.56)");
        frameFill.addColorStop(0.34, "rgba(210, 255, 250, 0.34)");
        frameFill.addColorStop(0.66, "rgba(153, 175, 255, 0.25)");
        frameFill.addColorStop(1, "rgba(255, 129, 219, 0.2)");
        ctx.fillStyle = frameFill;
        roundedRect(ctx, gateX, gateY, gateW, gateH, r * 0.24);
        ctx.fill();

        const frameStroke = ctx.createLinearGradient(gateX, 0, gateX + gateW, 0);
        frameStroke.addColorStop(0, "rgba(35, 232, 216, 0.78)");
        frameStroke.addColorStop(0.42, "rgba(255, 255, 255, 0.68)");
        frameStroke.addColorStop(0.7, "rgba(120, 132, 255, 0.64)");
        frameStroke.addColorStop(1, "rgba(255, 96, 204, 0.58)");
        ctx.strokeStyle = frameStroke;
        ctx.lineWidth = Math.max(1.2, r * 0.04);
        ctx.shadowColor = "rgba(40, 232, 216, 0.26)";
        ctx.shadowBlur = r * 0.18;
        roundedRect(ctx, gateX, gateY, gateW, gateH, r * 0.24);
        ctx.stroke();
        ctx.shadowBlur = 0;

        const panelGrad = ctx.createLinearGradient(0, gateY, 0, gateY + gateH);
        panelGrad.addColorStop(0, "rgba(255, 255, 255, 0.4)");
        panelGrad.addColorStop(0.45, "rgba(220, 255, 252, 0.2)");
        panelGrad.addColorStop(1, "rgba(120, 145, 255, 0.12)");
        ctx.fillStyle = panelGrad;
        roundedRect(ctx, gateX + r * 0.12, gateY + r * 0.12, panelW - r * 0.08, gateH - r * 0.24, r * 0.18);
        ctx.fill();
        roundedRect(ctx, panelGap * 0.5, gateY + r * 0.12, panelW - r * 0.08, gateH - r * 0.24, r * 0.18);
        ctx.fill();

        ctx.save();
        roundedRect(ctx, gateX + r * 0.1, gateY + r * 0.1, gateW - r * 0.2, gateH - r * 0.2, r * 0.2);
        ctx.clip();
        ctx.strokeStyle = "rgba(28, 151, 185, 0.22)";
        ctx.lineWidth = 0.62;
        for (let row = 0; row < 5; row += 1) {
            const y = gateY + gateH * (0.22 + row * 0.13);
            ctx.beginPath();
            ctx.moveTo(gateX + gateW * 0.12, y);
            ctx.lineTo(gateX + gateW * 0.36, y);
            ctx.lineTo(gateX + gateW * 0.43, y + (row % 2 ? -gateH * 0.055 : gateH * 0.055));
            ctx.lineTo(gateX + gateW * 0.78, y + (row % 2 ? -gateH * 0.055 : gateH * 0.055));
            ctx.stroke();
        }
        ctx.fillStyle = "rgba(255, 255, 255, 0.48)";
        for (let i = 0; i < 18; i += 1) {
            const x = gateX + gateW * (0.14 + (i % 6) * 0.13);
            const y = gateY + gateH * (0.2 + Math.floor(i / 6) * 0.24);
            const twinkle = 0.75 + Math.sin(this.phase * 1.2 + i) * 0.25;
            ctx.beginPath();
            ctx.arc(x, y, Math.max(0.7, r * 0.022 * twinkle), 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();

        const avatarX = gateX + gateW * 0.36;
        const shieldX = gateX + gateW * 0.66;
        const iconY = gateY + gateH * 0.5;
        const iconR = r * 0.24;

        const avatarGlow = ctx.createRadialGradient(avatarX - iconR * 0.22, iconY - iconR * 0.28, iconR * 0.16, avatarX, iconY, iconR * 1.7);
        avatarGlow.addColorStop(0, "rgba(255, 255, 255, 0.86)");
        avatarGlow.addColorStop(0.5, "rgba(45, 232, 216, 0.48)");
        avatarGlow.addColorStop(1, "rgba(119, 132, 255, 0.14)");
        ctx.fillStyle = avatarGlow;
        ctx.beginPath();
        ctx.arc(avatarX, iconY, iconR, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = "rgba(6, 58, 84, 0.72)";
        ctx.lineWidth = Math.max(1.2, r * 0.04);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(avatarX, iconY - iconR * 0.14, iconR * 0.23, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(avatarX - iconR * 0.43, iconY + iconR * 0.48);
        ctx.bezierCurveTo(avatarX - iconR * 0.3, iconY + iconR * 0.14, avatarX + iconR * 0.3, iconY + iconR * 0.14, avatarX + iconR * 0.43, iconY + iconR * 0.48);
        ctx.stroke();

        const shieldR = r * 0.25;
        const shieldGrad = ctx.createLinearGradient(shieldX - shieldR, iconY - shieldR, shieldX + shieldR, iconY + shieldR);
        shieldGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)");
        shieldGrad.addColorStop(0.48, "rgba(43, 232, 216, 0.74)");
        shieldGrad.addColorStop(1, "rgba(130, 126, 255, 0.54)");
        ctx.fillStyle = shieldGrad;
        ctx.beginPath();
        ctx.moveTo(shieldX, iconY - shieldR * 0.95);
        ctx.lineTo(shieldX + shieldR * 0.68, iconY - shieldR * 0.48);
        ctx.lineTo(shieldX + shieldR * 0.58, iconY + shieldR * 0.18);
        ctx.bezierCurveTo(shieldX + shieldR * 0.48, iconY + shieldR * 0.62, shieldX + shieldR * 0.16, iconY + shieldR * 0.92, shieldX, iconY + shieldR);
        ctx.bezierCurveTo(shieldX - shieldR * 0.16, iconY + shieldR * 0.92, shieldX - shieldR * 0.48, iconY + shieldR * 0.62, shieldX - shieldR * 0.58, iconY + shieldR * 0.18);
        ctx.lineTo(shieldX - shieldR * 0.68, iconY - shieldR * 0.48);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.66)";
        ctx.lineWidth = Math.max(0.8, r * 0.018);
        ctx.stroke();

        ctx.strokeStyle = "rgba(7, 56, 80, 0.82)";
        ctx.lineWidth = Math.max(1.2, r * 0.038);
        ctx.beginPath();
        ctx.moveTo(shieldX - shieldR * 0.31, iconY + shieldR * 0.04);
        ctx.lineTo(shieldX - shieldR * 0.08, iconY + shieldR * 0.28);
        ctx.lineTo(shieldX + shieldR * 0.36, iconY - shieldR * 0.25);
        ctx.stroke();

        const seam = ctx.createLinearGradient(0, gateY, 0, gateY + gateH);
        seam.addColorStop(0, "rgba(255,255,255,0)");
        seam.addColorStop(0.48, "rgba(255,255,255,0.45)");
        seam.addColorStop(1, "rgba(255,255,255,0)");
        ctx.strokeStyle = seam;
        ctx.lineWidth = Math.max(0.8, r * 0.02);
        ctx.beginPath();
        ctx.moveTo(0, gateY + r * 0.2);
        ctx.lineTo(0, gateY + gateH - r * 0.2);
        ctx.stroke();

        const scanX = gateX + scan;
        const scanGrad = ctx.createLinearGradient(scanX - gateW * 0.2, gateY, scanX + gateW * 0.05, gateY + gateH);
        scanGrad.addColorStop(0, "rgba(255,255,255,0)");
        scanGrad.addColorStop(0.5, "rgba(255,255,255,0.26)");
        scanGrad.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = scanGrad;
        ctx.beginPath();
        ctx.moveTo(scanX - gateW * 0.15, gateY + gateH * 0.08);
        ctx.lineTo(scanX + gateW * 0.02, gateY + gateH * 0.08);
        ctx.lineTo(scanX - gateW * 0.12, gateY + gateH * 0.92);
        ctx.lineTo(scanX - gateW * 0.29, gateY + gateH * 0.92);
        ctx.closePath();
        ctx.fill();

        ctx.restore();
        ctx.restore();
    }

    drawIdentityGatewayScan(ctx, w, h) {
        const progress = (this.phase * 0.065) % 1;
        const x = -w * 0.18 + progress * w * 1.36;
        const grad = ctx.createLinearGradient(x - w * 0.16, 0, x + w * 0.16, 0);
        grad.addColorStop(0, "rgba(255, 255, 255, 0)");
        grad.addColorStop(0.46, "rgba(255, 255, 255, 0.12)");
        grad.addColorStop(0.58, "rgba(46, 232, 216, 0.11)");
        grad.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.save();
        ctx.globalCompositeOperation = "screen";
        ctx.translate(x, h * 0.5);
        ctx.rotate(-0.22);
        ctx.fillStyle = grad;
        ctx.fillRect(-w * 0.17, -h, w * 0.34, h * 2);
        ctx.restore();
    }

    drawQuantumGardenField(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.quantumGardenCore(w, h);
        const pulse = 0.9 + Math.sin(this.phase * 0.72) * 0.1;

        const wash = ctx.createLinearGradient(0, 0, w, h);
        wash.addColorStop(0, "rgba(232, 255, 250, 0.36)");
        wash.addColorStop(0.48, "rgba(244, 250, 255, 0.1)");
        wash.addColorStop(1, "rgba(231, 236, 255, 0.28)");
        ctx.fillStyle = wash;
        ctx.fillRect(0, 0, w, h);

        const coreHalo = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 5.8);
        coreHalo.addColorStop(0, `rgba(41, 236, 215, ${0.28 * pulse})`);
        coreHalo.addColorStop(0.34, `rgba(92, 177, 255, ${0.13 * pulse})`);
        coreHalo.addColorStop(0.68, "rgba(161, 109, 255, 0.06)");
        coreHalo.addColorStop(1, "rgba(161, 109, 255, 0)");
        ctx.fillStyle = coreHalo;
        ctx.fillRect(0, 0, w, h);

        const roseHalo = ctx.createRadialGradient(w * 0.78, h * 0.36, 0, w * 0.78, h * 0.36, w * 0.28);
        roseHalo.addColorStop(0, "rgba(255, 100, 200, 0.09)");
        roseHalo.addColorStop(0.62, "rgba(130, 103, 255, 0.035)");
        roseHalo.addColorStop(1, "rgba(130, 103, 255, 0)");
        ctx.fillStyle = roseHalo;
        ctx.fillRect(0, 0, w, h);

        ctx.save();
        ctx.globalAlpha = 0.22;
        ctx.lineWidth = 0.55;
        for (let i = 0; i < 6; i += 1) {
            const y = h * (0.18 + i * 0.12);
            const grad = ctx.createLinearGradient(0, y, w, y);
            grad.addColorStop(0, "rgba(25, 202, 190, 0)");
            grad.addColorStop(0.38, "rgba(25, 202, 190, 0.2)");
            grad.addColorStop(0.72, "rgba(91, 125, 255, 0.12)");
            grad.addColorStop(1, "rgba(255, 90, 192, 0)");
            ctx.strokeStyle = grad;
            ctx.beginPath();
            ctx.moveTo(-w * 0.04, y);
            ctx.bezierCurveTo(w * 0.2, y - h * 0.12, w * 0.58, y + h * 0.16, w * 1.05, y - h * 0.04);
            ctx.stroke();
        }
        ctx.restore();
    }

    drawQuantumGardenFilaments(ctx, w, h) {
        const { x: cx, y: cy } = this.quantumGardenCore(w, h);
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        for (let i = 0; i < 12; i += 1) {
            const lane = (i - 5.5) / 5.5;
            const drift = Math.sin(this.phase * 0.38 + i * 0.7) * h * 0.012;
            const startY = h * (0.2 + i * 0.048) + drift;
            const grad = ctx.createLinearGradient(0, startY, cx, cy);
            grad.addColorStop(0, "rgba(23, 197, 186, 0)");
            grad.addColorStop(0.36, "rgba(35, 217, 204, 0.16)");
            grad.addColorStop(0.78, i % 3 ? "rgba(80, 180, 255, 0.22)" : "rgba(171, 92, 255, 0.17)");
            grad.addColorStop(1, "rgba(244, 255, 252, 0.36)");
            ctx.strokeStyle = grad;
            ctx.lineWidth = i % 4 === 0 ? 1.2 : 0.72;
            ctx.beginPath();
            ctx.moveTo(-w * 0.04, startY);
            ctx.bezierCurveTo(
                w * 0.13,
                startY + lane * h * 0.06,
                w * 0.28,
                cy - lane * h * 0.13,
                cx,
                cy + lane * h * 0.04
            );
            ctx.stroke();
        }

        for (let i = 0; i < 7; i += 1) {
            const lane = (i - 3) / 3;
            const grad = ctx.createLinearGradient(cx, cy, w, cy + lane * h * 0.16);
            grad.addColorStop(0, "rgba(245, 255, 252, 0.35)");
            grad.addColorStop(0.34, "rgba(35, 220, 205, 0.22)");
            grad.addColorStop(0.66, "rgba(74, 147, 255, 0.2)");
            grad.addColorStop(1, i > 4 ? "rgba(255, 91, 196, 0.05)" : "rgba(115, 92, 255, 0.04)");
            ctx.strokeStyle = grad;
            ctx.lineWidth = i === 3 ? 1.25 : 0.8;
            ctx.beginPath();
            ctx.moveTo(cx, cy + lane * h * 0.025);
            ctx.bezierCurveTo(w * 0.55, cy - h * 0.16 + lane * h * 0.06, w * 0.78, cy + lane * h * 0.2, w * 1.05, cy - h * 0.04 + lane * h * 0.22);
            ctx.stroke();
        }
        ctx.restore();
    }

    drawIdentityStarRingCore(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.quantumGardenCore(w, h);
        const breath = 1 + Math.sin(this.phase * 0.76) * 0.026;
        const r = radius * breath;
        const chipW = r * 3.86;
        const chipH = r * 1.12;
        const chipX = -chipW / 2;
        const chipY = -chipH / 2;
        const tilt = -0.035 + Math.sin(this.phase * 0.32) * 0.012;
        const scan = ((this.phase * 0.08) % 1) * chipW;

        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        const halo = ctx.createRadialGradient(cx, cy, r * 0.08, cx, cy, r * 3.6);
        halo.addColorStop(0, "rgba(255, 255, 255, 0.42)");
        halo.addColorStop(0.24, "rgba(40, 232, 216, 0.24)");
        halo.addColorStop(0.52, "rgba(130, 140, 255, 0.12)");
        halo.addColorStop(0.78, "rgba(255, 108, 214, 0.06)");
        halo.addColorStop(1, "rgba(255, 108, 214, 0)");
        ctx.fillStyle = halo;
        ctx.fillRect(cx - r * 3.8, cy - r * 2.4, r * 7.6, r * 4.8);

        ctx.save();
        ctx.translate(cx, cy + Math.sin(this.phase * 0.56) * r * 0.035);
        ctx.rotate(tilt);

        const shadow = ctx.createRadialGradient(0, chipH * 0.58, r * 0.2, 0, chipH * 0.58, chipW * 0.62);
        shadow.addColorStop(0, "rgba(20, 170, 190, 0.17)");
        shadow.addColorStop(0.5, "rgba(132, 113, 255, 0.1)");
        shadow.addColorStop(1, "rgba(20, 170, 190, 0)");
        ctx.fillStyle = shadow;
        ctx.fillRect(-chipW * 0.7, chipY + chipH * 0.34, chipW * 1.4, chipH * 1.35);

        const chipFill = ctx.createLinearGradient(chipX, chipY, chipX + chipW, chipY + chipH);
        chipFill.addColorStop(0, "rgba(255, 255, 255, 0.58)");
        chipFill.addColorStop(0.28, "rgba(220, 255, 252, 0.42)");
        chipFill.addColorStop(0.58, "rgba(155, 178, 255, 0.28)");
        chipFill.addColorStop(1, "rgba(255, 137, 220, 0.22)");
        ctx.fillStyle = chipFill;
        roundedRect(ctx, chipX, chipY, chipW, chipH, chipH * 0.28);
        ctx.fill();

        const border = ctx.createLinearGradient(chipX, 0, chipX + chipW, 0);
        border.addColorStop(0, "rgba(39, 232, 216, 0.76)");
        border.addColorStop(0.36, "rgba(255, 255, 255, 0.68)");
        border.addColorStop(0.68, "rgba(117, 137, 255, 0.62)");
        border.addColorStop(1, "rgba(255, 96, 199, 0.52)");
        ctx.strokeStyle = border;
        ctx.lineWidth = Math.max(1.1, r * 0.036);
        ctx.shadowColor = "rgba(41, 232, 216, 0.28)";
        ctx.shadowBlur = r * 0.18;
        roundedRect(ctx, chipX, chipY, chipW, chipH, chipH * 0.28);
        ctx.stroke();
        ctx.shadowBlur = 0;

        const glassBand = ctx.createLinearGradient(chipX, chipY, chipX + chipW, chipY + chipH);
        glassBand.addColorStop(0, "rgba(255, 255, 255, 0)");
        glassBand.addColorStop(0.48, "rgba(255, 255, 255, 0.26)");
        glassBand.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = glassBand;
        ctx.beginPath();
        ctx.moveTo(chipX + chipW * 0.08, chipY + chipH * 0.18);
        ctx.lineTo(chipX + chipW * 0.72, chipY + chipH * 0.18);
        ctx.lineTo(chipX + chipW * 0.52, chipY + chipH * 0.42);
        ctx.lineTo(chipX + chipW * 0.02, chipY + chipH * 0.42);
        ctx.closePath();
        ctx.fill();

        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        const contactAlpha = 0.34 + Math.sin(this.phase * 1.3) * 0.05;
        ctx.fillStyle = `rgba(226, 253, 255, ${contactAlpha})`;
        for (let i = 0; i < 7; i += 1) {
            const x = chipX + chipW * 0.17 + i * chipW * 0.105;
            roundedRect(ctx, x, chipY - chipH * 0.13, chipW * 0.026, chipH * 0.08, chipH * 0.02);
            roundedRect(ctx, x + chipW * 0.016, chipY + chipH * 1.05, chipW * 0.026, chipH * 0.08, chipH * 0.02);
            ctx.fill();
        }

        for (let i = 0; i < 4; i += 1) {
            const y = chipY + chipH * (0.18 + i * 0.19);
            roundedRect(ctx, chipX - chipW * 0.025, y, chipW * 0.034, chipH * 0.08, chipH * 0.018);
            roundedRect(ctx, chipX + chipW - chipW * 0.009, y, chipW * 0.034, chipH * 0.08, chipH * 0.018);
            ctx.fill();
        }

        const userX = chipX + chipW * 0.24;
        const shieldX = chipX + chipW * 0.78;
        const iconY = 0;
        const iconR = chipH * 0.25;

        const iconPlate = ctx.createRadialGradient(userX - iconR * 0.3, iconY - iconR * 0.35, iconR * 0.2, userX, iconY, iconR * 1.5);
        iconPlate.addColorStop(0, "rgba(255, 255, 255, 0.84)");
        iconPlate.addColorStop(0.48, "rgba(77, 231, 224, 0.4)");
        iconPlate.addColorStop(1, "rgba(123, 132, 255, 0.16)");
        ctx.fillStyle = iconPlate;
        ctx.beginPath();
        ctx.arc(userX, iconY, iconR, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.58)";
        ctx.lineWidth = Math.max(0.8, r * 0.02);
        ctx.stroke();

        ctx.strokeStyle = "rgba(6, 56, 82, 0.72)";
        ctx.lineWidth = Math.max(1.3, r * 0.045);
        ctx.beginPath();
        ctx.arc(userX, iconY - iconR * 0.16, iconR * 0.22, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(userX - iconR * 0.42, iconY + iconR * 0.48);
        ctx.bezierCurveTo(userX - iconR * 0.32, iconY + iconR * 0.16, userX + iconR * 0.32, iconY + iconR * 0.16, userX + iconR * 0.42, iconY + iconR * 0.48);
        ctx.stroke();

        const shieldR = chipH * 0.26;
        const shieldGrad = ctx.createLinearGradient(shieldX - shieldR, iconY - shieldR, shieldX + shieldR, iconY + shieldR);
        shieldGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)");
        shieldGrad.addColorStop(0.48, "rgba(43, 232, 216, 0.74)");
        shieldGrad.addColorStop(1, "rgba(126, 126, 255, 0.5)");
        ctx.fillStyle = shieldGrad;
        ctx.beginPath();
        ctx.moveTo(shieldX, iconY - shieldR * 0.95);
        ctx.lineTo(shieldX + shieldR * 0.68, iconY - shieldR * 0.48);
        ctx.lineTo(shieldX + shieldR * 0.58, iconY + shieldR * 0.18);
        ctx.bezierCurveTo(shieldX + shieldR * 0.48, iconY + shieldR * 0.62, shieldX + shieldR * 0.16, iconY + shieldR * 0.9, shieldX, iconY + shieldR * 1.02);
        ctx.bezierCurveTo(shieldX - shieldR * 0.16, iconY + shieldR * 0.9, shieldX - shieldR * 0.48, iconY + shieldR * 0.62, shieldX - shieldR * 0.58, iconY + shieldR * 0.18);
        ctx.lineTo(shieldX - shieldR * 0.68, iconY - shieldR * 0.48);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.64)";
        ctx.lineWidth = Math.max(0.8, r * 0.018);
        ctx.stroke();

        ctx.strokeStyle = "rgba(7, 56, 80, 0.82)";
        ctx.lineWidth = Math.max(1.2, r * 0.038);
        ctx.beginPath();
        ctx.moveTo(shieldX - shieldR * 0.31, iconY + shieldR * 0.04);
        ctx.lineTo(shieldX - shieldR * 0.08, iconY + shieldR * 0.28);
        ctx.lineTo(shieldX + shieldR * 0.36, iconY - shieldR * 0.25);
        ctx.stroke();

        const circuitGrad = ctx.createLinearGradient(userX + iconR, 0, shieldX - shieldR, 0);
        circuitGrad.addColorStop(0, "rgba(42, 232, 216, 0.18)");
        circuitGrad.addColorStop(0.48, "rgba(255, 255, 255, 0.4)");
        circuitGrad.addColorStop(1, "rgba(255, 100, 204, 0.22)");
        ctx.strokeStyle = circuitGrad;
        ctx.lineWidth = Math.max(0.72, r * 0.022);
        [
            [userX + iconR * 1.08, -chipH * 0.18, shieldX - shieldR * 1.2, -chipH * 0.18],
            [userX + iconR * 0.92, chipH * 0.03, shieldX - shieldR * 1.42, chipH * 0.03],
            [userX + iconR * 1.2, chipH * 0.23, shieldX - shieldR * 1.12, chipH * 0.23],
        ].forEach(([x1, y1, x2, y2], index) => {
            const step = index === 1 ? chipH * 0.12 : -chipH * 0.08;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x1 + chipW * 0.12, y1);
            ctx.lineTo(x1 + chipW * 0.17, y1 + step);
            ctx.lineTo(x2, y2 + step);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        });

        ctx.fillStyle = "rgba(245, 254, 255, 0.62)";
        [
            [chipX + chipW * 0.44, -chipH * 0.18],
            [chipX + chipW * 0.55, chipH * 0.03],
            [chipX + chipW * 0.63, chipH * 0.15],
        ].forEach(([x, y], index) => {
            const node = 1 + Math.sin(this.phase * 1.4 + index * 0.9) * 0.16;
            ctx.beginPath();
            ctx.arc(x, y, Math.max(1.15, r * 0.035 * node), 0, Math.PI * 2);
            ctx.fill();
        });

        const scanX = chipX + scan;
        const scanGrad = ctx.createLinearGradient(scanX - chipW * 0.14, chipY, scanX + chipW * 0.06, chipY + chipH);
        scanGrad.addColorStop(0, "rgba(255, 255, 255, 0)");
        scanGrad.addColorStop(0.52, "rgba(255, 255, 255, 0.22)");
        scanGrad.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = scanGrad;
        ctx.beginPath();
        ctx.moveTo(scanX - chipW * 0.12, chipY + chipH * 0.05);
        ctx.lineTo(scanX + chipW * 0.02, chipY + chipH * 0.05);
        ctx.lineTo(scanX - chipW * 0.1, chipY + chipH * 0.95);
        ctx.lineTo(scanX - chipW * 0.24, chipY + chipH * 0.95);
        ctx.closePath();
        ctx.fill();

        ctx.restore();
        ctx.restore();
    }

    drawQuantumGardenDataFan(ctx, w, h) {
        const { x: cx, y: cy } = this.quantumGardenCore(w, h);
        const progress = (this.phase * 0.032 + 0.12) % 1;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        for (let strand = 0; strand < 8; strand += 1) {
            const lane = (strand - 3.5) / 3.5;
            for (let i = 0; i < 32; i += 1) {
                const local = i / 31;
                const x = mix(cx + w * 0.04, w * 0.96, local);
                const curve = Math.sin(local * Math.PI * 1.18 + lane * 0.28) * h * 0.11;
                const fan = lane * h * (0.035 + local * 0.14);
                const y = cy - h * 0.08 * local + curve + fan + Math.sin(this.phase * 0.3 + i * 0.35 + strand) * h * 0.004;
                const sweep = gaussian(local, progress, 0.085) + gaussian(local, progress - 1, 0.085);
                const fade = (1 - smoothstep(0.88, 1, local)) * smoothstep(0, 0.12, local);
                const alpha = clamp((0.052 + sweep * 0.22) * fade * (0.72 + Math.abs(lane) * 0.18), 0.018, 0.32);
                const radius = 0.7 + smoothstep(0, 0.75, local) * 0.62 + sweep * 0.42;
                ctx.fillStyle = local > 0.72
                    ? `rgba(255, 95, 198, ${alpha * 0.72})`
                    : `rgba(${Math.round(mix(32, 84, local))}, ${Math.round(mix(225, 148, local))}, 245, ${alpha})`;
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawQuantumGardenNodes(ctx, w, h) {
        const { x: cx, y: cy, radius } = this.quantumGardenCore(w, h);
        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        for (let i = 0; i < 38; i += 1) {
            const seed = i * 0.83 + 0.2;
            const orbit = radius * (1.08 + fract(Math.sin(seed * 9.7) * 19.4) * 2.1);
            const angle = seed + this.phase * (0.1 + (i % 5) * 0.012);
            const x = cx + Math.cos(angle) * orbit * 1.45;
            const y = cy + Math.sin(angle) * orbit * 0.82;
            const twinkle = 0.65 + Math.sin(this.phase * 1.3 + seed) * 0.35;
            ctx.fillStyle = i % 6 === 0
                ? `rgba(255, 96, 199, ${0.16 * twinkle})`
                : `rgba(37, 229, 214, ${0.2 * twinkle})`;
            ctx.beginPath();
            ctx.arc(x, y, 0.9 + twinkle * 0.7, 0, Math.PI * 2);
            ctx.fill();
        }

        for (let i = 0; i < 18; i += 1) {
            const local = i / 17;
            const x = w * (0.05 + local * 0.26);
            const y = h * (0.34 + Math.sin(local * Math.PI * 1.4 + this.phase * 0.22) * 0.13);
            const alpha = 0.08 + Math.sin(local * Math.PI) * 0.12;
            ctx.fillStyle = `rgba(26, 210, 199, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 0.9 + alpha * 3, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    drawQuantumGardenScan(ctx, w, h) {
        const progress = (this.phase * 0.075) % 1;
        const x = -w * 0.12 + progress * w * 1.24;
        const grad = ctx.createLinearGradient(x - w * 0.13, 0, x + w * 0.13, 0);
        grad.addColorStop(0, "rgba(255, 255, 255, 0)");
        grad.addColorStop(0.45, "rgba(255, 255, 255, 0.12)");
        grad.addColorStop(0.58, "rgba(37, 231, 216, 0.1)");
        grad.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.save();
        ctx.globalCompositeOperation = "screen";
        ctx.translate(x, h * 0.5);
        ctx.rotate(-0.24);
        ctx.fillStyle = grad;
        ctx.fillRect(-w * 0.15, -h, w * 0.3, h * 2);
        ctx.restore();
    }

    drawLightAuroraField(ctx, w, h) {
        const { x: cx, y: cy } = auroraCorePoint(w, h);
        const pulse = 0.86 + Math.sin(this.phase * 0.72) * 0.14;
        const wash = ctx.createLinearGradient(0, h * 0.08, w, h * 0.92);
        wash.addColorStop(0, "rgba(166, 255, 239, 0.18)");
        wash.addColorStop(0.42, "rgba(235, 253, 255, 0.04)");
        wash.addColorStop(1, "rgba(165, 197, 255, 0.2)");
        ctx.fillStyle = wash;
        ctx.fillRect(0, 0, w, h);

        const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, w * 0.36);
        halo.addColorStop(0, `rgba(82, 245, 224, ${0.26 * pulse})`);
        halo.addColorStop(0.28, `rgba(112, 207, 255, ${0.14 * pulse})`);
        halo.addColorStop(0.58, "rgba(121, 105, 255, 0.05)");
        halo.addColorStop(1, "rgba(97, 201, 255, 0)");
        ctx.fillStyle = halo;
        ctx.fillRect(0, 0, w, h);

        const leftGlow = ctx.createRadialGradient(w * 0.13, h * 0.53, 0, w * 0.13, h * 0.53, w * 0.24);
        leftGlow.addColorStop(0, "rgba(21, 207, 190, 0.08)");
        leftGlow.addColorStop(1, "rgba(21, 207, 190, 0)");
        ctx.fillStyle = leftGlow;
        ctx.fillRect(0, 0, w * 0.42, h);

        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.strokeStyle = "rgba(38, 139, 180, 0.5)";
        ctx.lineWidth = 0.62;
        for (let i = 0; i < 5; i += 1) {
            const radius = Math.min(w, h) * (0.27 + i * 0.095);
            ctx.beginPath();
            ctx.ellipse(cx, cy, radius * 1.36, radius * 0.56, -0.13 + i * 0.04, Math.PI * 0.04, Math.PI * 0.96);
            ctx.stroke();
        }
        ctx.restore();
    }

    drawLightAuroraStreams(ctx, w, h) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        for (let stream = 0; stream < 7; stream += 1) {
            const seed = stream * 1.41 + 0.2;
            const grad = ctx.createLinearGradient(0, 0, w * 0.62, 0);
            grad.addColorStop(0, "rgba(16, 176, 178, 0)");
            grad.addColorStop(0.35, stream % 2 ? "rgba(72, 222, 209, 0.13)" : "rgba(70, 177, 255, 0.1)");
            grad.addColorStop(0.88, stream % 2 ? "rgba(211, 255, 247, 0.32)" : "rgba(142, 143, 255, 0.22)");
            grad.addColorStop(1, "rgba(218, 255, 249, 0)");
            ctx.strokeStyle = grad;
            ctx.lineWidth = 0.76 + (stream % 3) * 0.28;
            ctx.beginPath();
            for (let i = 0; i <= 80; i += 1) {
                const t = (i / 80) * 0.6;
                const point = auroraFlowPoint(t, w, h, this.phase, seed);
                if (i === 0) ctx.moveTo(point.x, point.y);
                else ctx.lineTo(point.x, point.y);
            }
            ctx.stroke();
        }
        ctx.restore();
    }

    drawLightAuroraOutput(ctx, w, h) {
        const { x: cx, y: cy, radius } = auroraCorePoint(w, h);
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";

        for (let row = 0; row < 3; row += 1) {
            const y = cy + (row - 1) * h * 0.095;
            const grad = ctx.createLinearGradient(cx, 0, w * 0.96, 0);
            grad.addColorStop(0, "rgba(218, 255, 249, 0.28)");
            grad.addColorStop(0.42, row === 1 ? "rgba(39, 204, 220, 0.28)" : "rgba(83, 146, 255, 0.18)");
            grad.addColorStop(1, "rgba(70, 112, 230, 0)");
            ctx.strokeStyle = grad;
            ctx.lineWidth = row === 1 ? 1.28 : 0.86;
            ctx.beginPath();
            ctx.moveTo(cx + radius * 0.86, cy + (row - 1) * radius * 0.24);
            ctx.bezierCurveTo(cx + w * 0.12, y - h * 0.02, w * 0.72, y, w * 0.94, y);
            ctx.stroke();

            for (let i = 0; i < 4; i += 1) {
                const x = w * (0.66 + i * 0.072);
                const sparkle = 0.72 + Math.sin(this.phase * 1.4 + row * 1.9 + i * 0.8) * 0.28;
                ctx.fillStyle = row === 1
                    ? `rgba(32, 210, 203, ${0.18 * sparkle})`
                    : `rgba(73, 127, 236, ${0.15 * sparkle})`;
                ctx.beginPath();
                ctx.arc(x, y, 1.45 + sparkle * 0.5, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawLightAuroraRibbons(ctx, w, h) {
        const { x: cx, y: cy } = auroraCorePoint(w, h);
        const ribbons = [
            { rx: w * 0.185, ry: h * 0.34, speed: 0.42, offset: 0.2, width: 7.8, color: "teal" },
            { rx: w * 0.235, ry: h * 0.25, speed: -0.32, offset: 1.95, width: 5.8, color: "blue" },
            { rx: w * 0.155, ry: h * 0.39, speed: 0.24, offset: 3.25, width: 4.6, color: "violet" },
        ];

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        ribbons.forEach((ribbon, index) => {
            const phase = this.phase * ribbon.speed + ribbon.offset;
            const grad = ctx.createLinearGradient(cx - ribbon.rx, cy - ribbon.ry, cx + ribbon.rx, cy + ribbon.ry);
            if (ribbon.color === "teal") {
                grad.addColorStop(0, "rgba(33, 222, 199, 0.04)");
                grad.addColorStop(0.44, "rgba(36, 232, 207, 0.36)");
                grad.addColorStop(0.72, "rgba(219, 255, 246, 0.38)");
                grad.addColorStop(1, "rgba(37, 139, 229, 0.08)");
            } else if (ribbon.color === "blue") {
                grad.addColorStop(0, "rgba(61, 131, 255, 0.02)");
                grad.addColorStop(0.45, "rgba(71, 177, 255, 0.28)");
                grad.addColorStop(0.72, "rgba(189, 230, 255, 0.26)");
                grad.addColorStop(1, "rgba(69, 105, 239, 0.1)");
            } else {
                grad.addColorStop(0, "rgba(117, 92, 255, 0.02)");
                grad.addColorStop(0.52, "rgba(134, 107, 255, 0.2)");
                grad.addColorStop(0.8, "rgba(94, 224, 243, 0.18)");
                grad.addColorStop(1, "rgba(117, 92, 255, 0.04)");
            }

            for (let pass = 0; pass < 2; pass += 1) {
                ctx.strokeStyle = grad;
                ctx.globalAlpha = pass === 0 ? 0.33 : 0.96;
                ctx.lineWidth = ribbon.width * (pass === 0 ? 2.25 : 0.72);
                ctx.shadowColor = index === 2 ? "rgba(120, 96, 255, 0.16)" : "rgba(41, 224, 209, 0.22)";
                ctx.shadowBlur = pass === 0 ? 8 : 3;
                ctx.beginPath();
                for (let i = 0; i <= 170; i += 1) {
                    const local = i / 170;
                    const angle = phase + local * Math.PI * 2;
                    const x = cx + Math.cos(angle) * ribbon.rx + Math.sin(angle * 2.1 + this.phase * 0.18) * w * 0.009;
                    const y = cy + Math.sin(angle) * ribbon.ry + Math.cos(angle * 1.7 + ribbon.offset) * h * 0.012;
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
                ctx.stroke();
            }
        });
        ctx.restore();
    }

    drawLightAuroraParticles(ctx, w, h) {
        const count = 76;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        for (let i = 0; i < count; i += 1) {
            const seed = i * 0.73 + 0.15;
            const offset = fract(Math.sin(seed * 41.2) * 2813.2);
            const t = (i / count + this.phase * 0.018 + offset * 0.2) % 1;
            const point = auroraFlowPoint(t, w, h, this.phase, seed);
            const trailT = clamp(t - 0.026, 0, 1);
            const trail = auroraFlowPoint(trailT, w, h, this.phase, seed);
            const coreGlow = gaussian(t, 0.58, 0.11);
            const alpha = clamp(0.08 + point.focus * 0.13 + coreGlow * 0.34, 0.06, 0.5);
            const radius = clamp(0.8 + coreGlow * 1.2 + offset * 0.55, 0.7, 2.3);

            const stroke = ctx.createLinearGradient(trail.x, trail.y, point.x, point.y);
            stroke.addColorStop(0, "rgba(35, 209, 196, 0)");
            stroke.addColorStop(1, t > 0.62 ? `rgba(72, 139, 255, ${alpha})` : `rgba(33, 218, 200, ${alpha})`);
            ctx.strokeStyle = stroke;
            ctx.lineWidth = radius * 0.7;
            ctx.beginPath();
            ctx.moveTo(trail.x, trail.y);
            ctx.lineTo(point.x, point.y);
            ctx.stroke();

            ctx.fillStyle = t > 0.62
                ? `rgba(78, 126, 246, ${alpha * 1.06})`
                : `rgba(34, 219, 201, ${alpha})`;
            ctx.beginPath();
            ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    drawLightAuroraCore(ctx, w, h) {
        const { x: cx, y: cy, radius } = auroraCorePoint(w, h);
        const pulse = 0.96 + Math.sin(this.phase * 0.92) * 0.055;
        const r = radius * pulse;

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 3.2);
        halo.addColorStop(0, "rgba(234, 255, 248, 0.48)");
        halo.addColorStop(0.18, "rgba(44, 231, 207, 0.3)");
        halo.addColorStop(0.48, "rgba(74, 160, 255, 0.13)");
        halo.addColorStop(1, "rgba(93, 109, 255, 0)");
        ctx.fillStyle = halo;
        ctx.fillRect(cx - r * 3.2, cy - r * 3.2, r * 6.4, r * 6.4);

        const points = [];
        for (let i = 0; i < 8; i += 1) {
            const angle = -Math.PI / 2 + i * Math.PI * 0.25 + Math.sin(this.phase * 0.26) * 0.04;
            const pointRadius = r * (i % 2 ? 0.82 : 1.04);
            points.push({
                x: cx + Math.cos(angle) * pointRadius,
                y: cy + Math.sin(angle) * pointRadius * 0.96,
            });
        }

        const body = ctx.createRadialGradient(cx - r * 0.24, cy - r * 0.3, r * 0.1, cx, cy, r * 1.18);
        body.addColorStop(0, "rgba(248, 255, 252, 0.86)");
        body.addColorStop(0.38, "rgba(76, 235, 215, 0.48)");
        body.addColorStop(0.72, "rgba(82, 151, 255, 0.24)");
        body.addColorStop(1, "rgba(105, 82, 238, 0.14)");
        ctx.fillStyle = body;
        ctx.beginPath();
        points.forEach((point, index) => {
            if (index === 0) ctx.moveTo(point.x, point.y);
            else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = "rgba(236, 255, 250, 0.62)";
        ctx.lineWidth = 1.05;
        ctx.stroke();

        ctx.strokeStyle = "rgba(225, 255, 250, 0.32)";
        ctx.lineWidth = 0.7;
        points.forEach((point, index) => {
            if (index % 2 === 0) {
                ctx.beginPath();
                ctx.moveTo(cx, cy);
                ctx.lineTo(point.x, point.y);
                ctx.stroke();
            }
        });

        const shine = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
        shine.addColorStop(0, "rgba(255, 255, 255, 0)");
        shine.addColorStop(0.5, "rgba(255, 255, 255, 0.44)");
        shine.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.strokeStyle = shine;
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.moveTo(cx - r * 0.5, cy - r * 0.58);
        ctx.lineTo(cx + r * 0.55, cy + r * 0.4);
        ctx.stroke();
        ctx.restore();
    }

    memoryConstellationLayout(w, h) {
        const span = clamp(Math.min(w, h) * 0.35, 54, 75);
        const size = clamp(Math.min(w, h) * 0.18, 25, 38);
        const center = {
            key: "account",
            role: "account",
            x: w * 0.51,
            y: h * 0.51,
            size,
            delay: 0.36,
            hue: 0,
        };
        const nodes = [
            {
                key: "email",
                role: "email",
                x: center.x - span * 1.55,
                y: center.y - span * 0.44,
                size: size * 0.52,
                delay: 0.08,
                hue: -0.08,
            },
            {
                key: "code",
                role: "code",
                x: center.x - span * 0.72,
                y: center.y + span * 0.7,
                size: size * 0.48,
                delay: 0.22,
                hue: 0.1,
            },
            center,
            {
                key: "password",
                role: "password",
                x: center.x + span * 0.84,
                y: center.y - span * 0.66,
                size: size * 0.5,
                delay: 0.52,
                hue: 0.18,
            },
            {
                key: "access",
                role: "access",
                x: center.x + span * 1.55,
                y: center.y + span * 0.34,
                size: size * 0.48,
                delay: 0.68,
                hue: 0.28,
            },
        ];

        const byKey = Object.fromEntries(nodes.map((node) => [node.key, node]));
        const links = [
            { from: byKey.email, to: byKey.account, bend: -0.52, delay: 0.18 },
            { from: byKey.code, to: byKey.account, bend: 0.46, delay: 0.34 },
            { from: byKey.account, to: byKey.password, bend: -0.38, delay: 0.56 },
            { from: byKey.account, to: byKey.access, bend: 0.4, delay: 0.72 },
            { from: byKey.email, to: byKey.code, bend: 0.35, delay: 0.28 },
            { from: byKey.password, to: byKey.access, bend: 0.48, delay: 0.82 },
        ];

        return { center, nodes, links };
    }

    memoryReveal(delay = 0, duration = 0.7) {
        return smoothstep(0, 1, (this.sceneAge - delay) / duration);
    }

    memoryCurveControl(from, to, bend = 0) {
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const length = Math.hypot(dx, dy) || 1;
        const lift = length * 0.22 * bend;
        return {
            x: (from.x + to.x) / 2 + (-dy / length) * lift,
            y: (from.y + to.y) / 2 + (dx / length) * lift,
        };
    }

    memoryCurvePoint(from, to, bend, t) {
        const c = this.memoryCurveControl(from, to, bend);
        const inv = 1 - t;
        return {
            x: inv * inv * from.x + 2 * inv * t * c.x + t * t * to.x,
            y: inv * inv * from.y + 2 * inv * t * c.y + t * t * to.y,
        };
    }

    drawMemoryCurvePath(ctx, from, to, bend = 0) {
        const c = this.memoryCurveControl(from, to, bend);
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.quadraticCurveTo(c.x, c.y, to.x, to.y);
    }

    drawMemoryConstellationScene(ctx, w, h) {
        const layout = this.memoryConstellationLayout(w, h);
        this.drawMemoryConstellationField(ctx, w, h, layout);
        this.drawMemoryConstellationLinks(ctx, layout);
        this.drawMemoryConstellationFlow(ctx, layout);
        this.drawMemoryConstellationNodes(ctx, layout);
        this.drawMemoryConfirmationHalo(ctx, layout.center);
    }

    drawMemoryConstellationField(ctx, w, h, layout) {
        const { center } = layout;
        const breath = 0.88 + Math.sin(this.phase * 0.62) * 0.12;

        ctx.save();
        ctx.globalCompositeOperation = "lighter";

        const coreRadius = Math.min(center.size * 4.7, h * 0.64, w * 0.38);
        const coreGlow = ctx.createRadialGradient(center.x, center.y, 0, center.x, center.y, coreRadius);
        coreGlow.addColorStop(0, `rgba(225, 255, 252, ${0.38 * breath})`);
        coreGlow.addColorStop(0.22, `rgba(37, 227, 209, ${0.25 * breath})`);
        coreGlow.addColorStop(0.54, "rgba(71, 153, 255, 0.1)");
        coreGlow.addColorStop(0.78, "rgba(139, 111, 255, 0.032)");
        coreGlow.addColorStop(1, "rgba(139, 111, 255, 0)");
        ctx.fillStyle = coreGlow;
        ctx.fillRect(center.x - coreRadius, center.y - coreRadius, coreRadius * 2, coreRadius * 2);

        const diagonal = ctx.createLinearGradient(w * 0.08, h * 0.9, w * 0.96, h * 0.12);
        diagonal.addColorStop(0, "rgba(16, 221, 200, 0)");
        diagonal.addColorStop(0.34, "rgba(16, 221, 200, 0.08)");
        diagonal.addColorStop(0.64, "rgba(88, 150, 255, 0.075)");
        diagonal.addColorStop(1, "rgba(139, 111, 255, 0)");
        ctx.strokeStyle = diagonal;
        ctx.lineWidth = 1.1;
        for (let i = 0; i < 5; i += 1) {
            const offset = (i - 2) * h * 0.095 + Math.sin(this.phase * 0.18 + i) * h * 0.012;
            ctx.beginPath();
            ctx.moveTo(w * 0.02, h * 0.72 + offset);
            ctx.bezierCurveTo(w * 0.28, h * 0.42 + offset, w * 0.63, h * 0.68 - offset * 0.18, w * 0.98, h * 0.34 - offset * 0.36);
            ctx.stroke();
        }

        for (let i = 0; i < 42; i += 1) {
            const seed = i * 1.77 + 0.23;
            const x = w * fract(Math.sin(seed * 41.1) * 411.7);
            const y = h * fract(Math.sin(seed * 67.3) * 619.3);
            const twinkle = 0.55 + Math.sin(this.phase * 0.9 + seed) * 0.45;
            const edgeFade = smoothstep(0, w * 0.1, x) * smoothstep(0, w * 0.1, w - x);
            ctx.fillStyle = `rgba(181, 252, 247, ${0.045 * twinkle * edgeFade})`;
            ctx.beginPath();
            ctx.arc(x, y, 0.65 + twinkle * 0.7, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.restore();
    }

    drawMemoryConstellationLinks(ctx, layout) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";

        layout.links.forEach((link, index) => {
            const reveal = this.memoryReveal(link.delay, 0.74);
            if (reveal <= 0.01) return;
            const pulse = 0.74 + Math.sin(this.phase * 0.82 + index * 0.96) * 0.26;
            const grad = ctx.createLinearGradient(link.from.x, link.from.y, link.to.x, link.to.y);
            grad.addColorStop(0, "rgba(37, 230, 211, 0)");
            grad.addColorStop(0.28, `rgba(51, 233, 216, ${0.2 * reveal * pulse})`);
            grad.addColorStop(0.58, `rgba(180, 250, 255, ${0.26 * reveal * pulse})`);
            grad.addColorStop(1, `rgba(130, 125, 255, ${0.16 * reveal * pulse})`);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 0.72 + reveal * 0.72;
            this.drawMemoryCurvePath(ctx, link.from, link.to, link.bend);
            ctx.stroke();

            const head = clamp(reveal * 1.08, 0, 1);
            const tail = clamp(head - 0.18, 0, 1);
            const p1 = this.memoryCurvePoint(link.from, link.to, link.bend, tail);
            const p2 = this.memoryCurvePoint(link.from, link.to, link.bend, head);
            const highlight = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
            highlight.addColorStop(0, "rgba(255, 255, 255, 0)");
            highlight.addColorStop(0.68, `rgba(235, 255, 255, ${0.34 * reveal})`);
            highlight.addColorStop(1, `rgba(54, 235, 218, ${0.2 * reveal})`);
            ctx.strokeStyle = highlight;
            ctx.lineWidth = 1.4 + reveal * 0.8;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
        });

        ctx.restore();
    }

    drawMemoryConstellationFlow(ctx, layout) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        layout.links.forEach((link, linkIndex) => {
            const reveal = this.memoryReveal(link.delay + 0.18, 0.64);
            if (reveal <= 0.02) return;
            const count = linkIndex < 4 ? 5 : 3;
            for (let i = 0; i < count; i += 1) {
                const seed = linkIndex * 7.31 + i * 1.67;
                const raw = fract(this.phase * 0.04 + seed * 0.13);
                const t = smoothstep(0, 1, raw);
                const point = this.memoryCurvePoint(link.from, link.to, link.bend, t);
                const trail = this.memoryCurvePoint(link.from, link.to, link.bend, clamp(t - 0.055, 0, 1));
                const edge = smoothstep(0, 0.22, t) * smoothstep(0, 0.18, 1 - t);
                const alpha = reveal * edge * (0.17 + 0.08 * Math.sin(this.phase * 1.1 + seed));
                const grad = ctx.createLinearGradient(trail.x, trail.y, point.x, point.y);
                grad.addColorStop(0, "rgba(46, 228, 214, 0)");
                grad.addColorStop(1, `rgba(126, 245, 255, ${alpha})`);
                ctx.strokeStyle = grad;
                ctx.lineWidth = 1.15;
                ctx.beginPath();
                ctx.moveTo(trail.x, trail.y);
                ctx.lineTo(point.x, point.y);
                ctx.stroke();

                const color = linkIndex % 3 === 2
                    ? `rgba(156, 142, 255, ${alpha * 1.24})`
                    : `rgba(58, 237, 220, ${alpha * 1.32})`;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(point.x, point.y, 1.15 + alpha * 4.2, 0, Math.PI * 2);
                ctx.fill();
            }
        });
        ctx.restore();
    }

    drawMemoryConstellationNodes(ctx, layout) {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        layout.nodes.forEach((node, index) => {
            const reveal = this.memoryReveal(node.delay, 0.62);
            if (reveal <= 0.01) return;
            const breath = node.role === "account"
                ? 1 + Math.sin(this.phase * 0.86) * 0.045
                : 1 + Math.sin(this.phase * 0.72 + index * 0.9) * 0.035;
            this.drawMemoryCrystalNode(ctx, node, reveal, breath);
        });
        ctx.restore();
    }

    drawMemoryCrystalNode(ctx, node, reveal, breath) {
        const r = node.size * breath * (0.78 + reveal * 0.22);
        const isCenter = node.role === "account";
        const glowRadius = Math.min(r * (isCenter ? 3.4 : 2.75), isCenter ? 94 : 62);
        const glow = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowRadius);
        glow.addColorStop(0, `rgba(241, 255, 255, ${0.44 * reveal})`);
        glow.addColorStop(0.22, `rgba(48, 236, 219, ${0.28 * reveal})`);
        glow.addColorStop(0.58, `rgba(80, 147, 255, ${0.1 * reveal})`);
        glow.addColorStop(0.82, `rgba(147, 126, 255, ${0.035 * reveal})`);
        glow.addColorStop(1, "rgba(80, 147, 255, 0)");
        ctx.fillStyle = glow;
        ctx.fillRect(node.x - glowRadius, node.y - glowRadius, glowRadius * 2, glowRadius * 2);

        const sides = isCenter ? 10 : 8;
        const points = [];
        const spin = this.phase * (isCenter ? 0.03 : -0.025) + node.hue;
        for (let i = 0; i < sides; i += 1) {
            const angle = -Math.PI / 2 + spin + (Math.PI * 2 * i) / sides;
            const variance = 0.88 + 0.13 * Math.sin(i * 1.9 + node.hue * 8);
            points.push({
                x: node.x + Math.cos(angle) * r * variance,
                y: node.y + Math.sin(angle) * r * variance,
            });
        }

        const fill = ctx.createRadialGradient(node.x - r * 0.22, node.y - r * 0.32, 0, node.x, node.y, r * 1.35);
        fill.addColorStop(0, `rgba(252, 255, 255, ${0.82 * reveal})`);
        fill.addColorStop(0.38, `rgba(82, 235, 224, ${0.48 * reveal})`);
        fill.addColorStop(0.72, `rgba(81, 153, 255, ${0.32 * reveal})`);
        fill.addColorStop(1, `rgba(147, 126, 255, ${0.18 * reveal})`);
        ctx.fillStyle = fill;
        ctx.beginPath();
        points.forEach((point, i) => {
            if (i === 0) ctx.moveTo(point.x, point.y);
            else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = `rgba(236, 255, 255, ${0.62 * reveal})`;
        ctx.lineWidth = isCenter ? 1.28 : 0.88;
        ctx.stroke();

        ctx.strokeStyle = `rgba(220, 255, 255, ${0.22 * reveal})`;
        ctx.lineWidth = 0.72;
        for (let i = 0; i < points.length; i += 2) {
            ctx.beginPath();
            ctx.moveTo(node.x, node.y);
            ctx.lineTo(points[i].x, points[i].y);
            ctx.stroke();
        }

        const shine = ctx.createLinearGradient(node.x - r, node.y - r, node.x + r, node.y + r);
        shine.addColorStop(0, "rgba(255, 255, 255, 0)");
        shine.addColorStop(0.48, `rgba(255, 255, 255, ${0.56 * reveal})`);
        shine.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.strokeStyle = shine;
        ctx.lineWidth = isCenter ? 1.9 : 1.25;
        ctx.beginPath();
        ctx.moveTo(node.x - r * 0.42, node.y - r * 0.52);
        ctx.lineTo(node.x + r * 0.42, node.y + r * 0.34);
        ctx.stroke();

        this.drawMemoryNodeIcon(ctx, node.role, node.x, node.y, r, reveal);
    }

    drawMemoryNodeIcon(ctx, role, x, y, r, reveal) {
        ctx.save();
        ctx.translate(x, y);
        ctx.strokeStyle = `rgba(5, 49, 73, ${0.58 * reveal})`;
        ctx.fillStyle = `rgba(6, 57, 78, ${0.42 * reveal})`;
        ctx.lineWidth = Math.max(0.9, r * 0.075);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        if (role === "email") {
            roundedRect(ctx, -r * 0.42, -r * 0.28, r * 0.84, r * 0.56, r * 0.09);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(-r * 0.38, -r * 0.18);
            ctx.lineTo(0, r * 0.08);
            ctx.lineTo(r * 0.38, -r * 0.18);
            ctx.stroke();
        } else if (role === "code") {
            ctx.beginPath();
            ctx.moveTo(-r * 0.42, -r * 0.16);
            ctx.lineTo(-r * 0.18, 0);
            ctx.lineTo(-r * 0.42, r * 0.18);
            ctx.moveTo(r * 0.42, -r * 0.16);
            ctx.lineTo(r * 0.18, 0);
            ctx.lineTo(r * 0.42, r * 0.18);
            ctx.moveTo(-r * 0.05, r * 0.26);
            ctx.lineTo(r * 0.1, -r * 0.26);
            ctx.stroke();
        } else if (role === "password") {
            for (let i = 0; i < 3; i += 1) {
                ctx.beginPath();
                ctx.arc((i - 1) * r * 0.24, -r * 0.03, r * 0.06, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.beginPath();
            ctx.moveTo(-r * 0.36, r * 0.28);
            ctx.lineTo(r * 0.36, r * 0.28);
            ctx.stroke();
        } else if (role === "access") {
            ctx.beginPath();
            ctx.arc(-r * 0.08, 0, r * 0.26, -Math.PI * 0.25, Math.PI * 1.24);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(r * 0.04, -r * 0.18);
            ctx.lineTo(r * 0.42, -r * 0.18);
            ctx.lineTo(r * 0.42, r * 0.06);
            ctx.stroke();
        } else {
            ctx.beginPath();
            ctx.arc(0, 0, r * 0.21, 0, Math.PI * 2);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(-r * 0.44, r * 0.42);
            ctx.quadraticCurveTo(0, r * 0.18, r * 0.44, r * 0.42);
            ctx.stroke();
        }

        ctx.restore();
    }

    drawMemoryConfirmationHalo(ctx, center) {
        const reveal = this.memoryReveal(0.76, 0.82);
        if (reveal <= 0.01) return;
        const pulse = 0.72 + Math.sin(this.phase * 0.92) * 0.28;
        const r = center.size * (1.72 + pulse * 0.08);
        const sweep = (this.phase * 0.18) % (Math.PI * 2);

        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.translate(center.x, center.y);
        ctx.rotate(sweep);
        const grad = ctx.createLinearGradient(-r, 0, r, 0);
        grad.addColorStop(0, "rgba(46, 233, 217, 0)");
        grad.addColorStop(0.3, `rgba(46, 233, 217, ${0.2 * reveal})`);
        grad.addColorStop(0.58, `rgba(239, 255, 255, ${0.36 * reveal})`);
        grad.addColorStop(1, "rgba(137, 124, 255, 0)");
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.1 + pulse * 0.6;
        ctx.beginPath();
        ctx.ellipse(0, 0, r * 1.18, r * 0.72, 0.08, -Math.PI * 0.2, Math.PI * 1.18);
        ctx.stroke();

        ctx.rotate(-sweep * 1.82);
        ctx.strokeStyle = `rgba(120, 245, 238, ${0.12 * reveal})`;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.ellipse(0, 0, r * 1.46, r * 0.92, -0.22, Math.PI * 0.08, Math.PI * 1.46);
        ctx.stroke();
        ctx.restore();
    }

    destroy() {
        this.stop();
        this.resizeObserver?.disconnect();
        this.modeObserver?.disconnect();
        document.removeEventListener("visibilitychange", this.onVisibilityChange);
        this.motionQuery.removeEventListener?.("change", this.onMotionChange);
    }
}

export function initAuthWave(selector = ".auth-signal") {
    document.querySelectorAll(selector).forEach((target) => {
        const renderer = new AuthWaveCanvas(target);
        renderer.init();
    });
}
