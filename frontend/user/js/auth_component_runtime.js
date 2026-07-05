import React, { Fragment, useEffect, useMemo, useRef, useState } from 'https://esm.sh/react@18.3.1';
import { createRoot } from 'https://esm.sh/react-dom@18.3.1/client';

const h = React.createElement;

const CDN = {
    antd: 'https://esm.sh/antd@5.27.6?deps=react@18.3.1,react-dom@18.3.1',
    antDesignX: 'https://esm.sh/@ant-design/x@2.7.0?deps=react@18.3.1,react-dom@18.3.1,antd@5.27.6',
};

function cn(...values) {
    return values.filter(Boolean).join(' ');
}

function useComponentLibraries() {
    const [libraries, setLibraries] = useState({ antd: null, antDesignX: null });

    useEffect(() => {
        let alive = true;
        Promise.allSettled([
            import(CDN.antd),
            import(CDN.antDesignX),
        ]).then(([antd, antDesignX]) => {
            if (!alive) return;
            setLibraries({
                antd: antd.status === 'fulfilled' ? antd.value : null,
                antDesignX: antDesignX.status === 'fulfilled' ? antDesignX.value : null,
            });
        });
        return () => {
            alive = false;
        };
    }, []);

    return libraries;
}

function ComponentProvider({ libraries, children }) {
    const ConfigProvider = libraries.antd?.ConfigProvider;
    const XProvider = libraries.antDesignX?.XProvider;
    const theme = useMemo(() => ({
        token: {
            colorPrimary: '#049a92',
            borderRadius: 8,
            fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", system-ui, sans-serif',
        },
    }), []);

    let content = children;
    if (XProvider) {
        content = h(XProvider, null, content);
    }
    if (ConfigProvider) {
        content = h(ConfigProvider, { theme }, content);
    }
    return content;
}

function ShadcnSurface({ className, children }) {
    return h('div', { className: cn('shadcn-surface', className) }, children);
}

function useCanvas(renderer, deps = []) {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return undefined;
        const ctx = canvas.getContext('2d');
        let frame = 0;
        let raf = 0;
        let width = 1;
        let height = 1;
        let dpr = 1;

        const resize = () => {
            const rect = canvas.getBoundingClientRect();
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            width = Math.max(1, rect.width);
            height = Math.max(1, rect.height);
            canvas.width = Math.round(width * dpr);
            canvas.height = Math.round(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        };

        const tick = (time) => {
            frame += 1;
            ctx.clearRect(0, 0, width, height);
            renderer(ctx, width, height, time / 1000, frame);
            raf = requestAnimationFrame(tick);
        };

        resize();
        const observer = new ResizeObserver(resize);
        observer.observe(canvas);
        raf = requestAnimationFrame(tick);

        return () => {
            observer.disconnect();
            cancelAnimationFrame(raf);
        };
    }, deps);

    return canvasRef;
}

function gaussian(x, center, width) {
    const delta = (x - center) / width;
    return Math.exp(-delta * delta * 0.5);
}

function profile(x, phase) {
    const n = (x + phase) % 1;
    const peaks = gaussian(n, 0.18, 0.05) * 0.46
        + gaussian(n, 0.34, 0.05) * 0.78
        + gaussian(n, 0.62, 0.055) * 0.56
        + gaussian(n, 0.73, 0.045) * 0.88
        + gaussian(n, 0.86, 0.065) * 0.40;
    const valley = gaussian(n, 0.51, 0.078) * 0.28;
    return Math.max(0.16, Math.min(1, 0.22 + peaks - valley));
}

function drawReferenceWave(ctx, width, height, time, options) {
    const {
        baseY = height * 0.5,
        maxHeight = 130,
        dark = false,
        barAlpha = 0.36,
        dotAlpha = 0.46,
        step = 12,
    } = options;
    const phase = (time * 0.028) % 1;
    const teal = dark ? 'rgba(87, 239, 218, .58)' : 'rgba(82, 224, 211, .58)';
    const blue = dark ? 'rgba(20, 118, 238, .46)' : 'rgba(61, 144, 248, .36)';
    const lineA = dark ? 'rgba(91, 236, 218, .24)' : 'rgba(38, 211, 199, .25)';
    const lineB = dark ? 'rgba(70, 175, 243, .13)' : 'rgba(90, 174, 255, .18)';

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    for (let layer = 0; layer < 3; layer += 1) {
        ctx.beginPath();
        for (let x = -40; x <= width + 40; x += 8) {
            const n = x / width;
            const y = baseY
                + Math.sin(n * Math.PI * (2.05 + layer * 0.28) + time * (0.26 + layer * 0.07)) * maxHeight * (0.12 + layer * 0.045)
                + Math.sin(n * Math.PI * (5.5 + layer) - time * 0.17) * maxHeight * 0.035
                + (layer - 1) * 10;
            if (x === -40) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = layer === 1 ? lineA : lineB;
        ctx.globalAlpha = layer === 1 ? 1 : 0.74;
        ctx.lineWidth = layer === 1 ? 1.25 : 0.95;
        ctx.stroke();
    }

    for (let x = -8; x <= width + 8; x += step) {
        const n = Math.max(0, Math.min(1, x / width));
        const p = profile(n, phase);
        const local = Math.sin(n * Math.PI * 4.2 + time * 0.72) * maxHeight * 0.065;
        const breath = 0.92 + Math.sin(time * 2.4 + n * 18) * 0.08;
        const hgt = (maxHeight * 0.16) + p * maxHeight * breath;

        ctx.globalAlpha = barAlpha * (0.62 + p * 0.58);
        ctx.fillStyle = teal;
        ctx.fillRect(x, baseY + local - hgt / 2, dark ? 3 : 4, hgt);

        const dots = Math.floor(3 + p * 13);
        for (let i = 0; i < dots; i += 1) {
            const t = dots <= 1 ? 0.5 : i / (dots - 1);
            const y = baseY + local + (t - 0.5) * hgt * 1.18;
            const middle = 1 - Math.abs(t - 0.5) * 1.55;
            ctx.globalAlpha = dotAlpha * Math.max(0.18, Math.min(0.82, 0.28 + middle * 0.7));
            ctx.fillStyle = (t > 0.54 || Math.sin(n * 28 + time * 0.7) > 0.66) ? blue : teal;
            ctx.beginPath();
            ctx.arc(x + step * 0.52, y, dark ? 2.2 : 2.7, 0, Math.PI * 2);
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

function AuthWaveCanvas({ mode }) {
    const canvasRef = useCanvas((ctx, width, height, time) => {
        const dark = mode === 'login';
        drawReferenceWave(ctx, width, height, time, {
            baseY: dark ? height * 0.56 : height * 0.52,
            maxHeight: dark ? 102 : 128,
            dark,
            barAlpha: dark ? 0.40 : 0.34,
            dotAlpha: dark ? 0.32 : 0.46,
            step: dark ? 11 : 12,
        });
    }, [mode]);

    return h('canvas', {
        ref: canvasRef,
        className: cn('component-wave-canvas', `component-wave-${mode}`),
        'aria-hidden': 'true',
    });
}

function ForgotSignalCanvas() {
    const canvasRef = useCanvas((ctx, width, height, time) => {
        const baseY = height * 0.34;
        drawReferenceWave(ctx, width, height, time, {
            baseY,
            maxHeight: 86,
            dark: false,
            barAlpha: 0.18,
            dotAlpha: 0.30,
            step: 10,
        });

        for (let layer = 0; layer < 10; layer += 1) {
            ctx.beginPath();
            for (let x = -40; x <= width + 40; x += 9) {
                const n = x / width;
                const y = baseY + 5
                    + Math.sin(n * Math.PI * 2.2 + layer * 0.22 + time * 0.15) * (52 + layer * 2)
                    + Math.sin(n * Math.PI * 5.3 - time * 0.12) * 8
                    + (layer - 5) * 2.4;
                if (x === -40) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.globalAlpha = 0.06 + layer * 0.006;
            ctx.strokeStyle = layer % 2 ? 'rgba(13, 186, 177, .55)' : 'rgba(61, 145, 248, .32)';
            ctx.lineWidth = 0.8;
            ctx.stroke();
        }
        ctx.globalAlpha = 1;
    }, []);

    return h('canvas', {
        ref: canvasRef,
        className: 'component-signal-canvas',
        'aria-hidden': 'true',
    });
}

function Icon({ type }) {
    const paths = {
        shield: 'M12 3 20 6v6c0 5-3.1 8.4-8 10-4.9-1.6-8-5-8-10V6l8-3Zm-3 9 2 2 4-5',
        users: 'M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
        heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 1 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8Z',
    };
    return h('svg', {
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: '2',
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        'aria-hidden': 'true',
    }, h('path', { d: paths[type] }));
}

function BooksStack() {
    return h('div', { className: 'scene-books' }, [
        h('div', { className: 'scene-book', key: 'b1' }),
        h('div', { className: 'scene-book', key: 'b2' }),
        h('div', { className: 'scene-book', key: 'b3' }),
        h('div', { className: 'scene-cap', key: 'cap' }),
    ]);
}

function Laptop() {
    return h('div', { className: 'scene-laptop' }, [
        h('div', { className: 'scene-laptop-screen', key: 'screen' }, h('span', { className: 'scene-avatar' })),
        h('div', { className: 'scene-laptop-base', key: 'base' }),
    ]);
}

function Plant() {
    return h('div', { className: 'scene-plant' }, [
        h('span', { className: 'scene-leaf', key: 'l1' }),
        h('span', { className: 'scene-leaf', key: 'l2' }),
        h('span', { className: 'scene-leaf', key: 'l3' }),
        h('span', { className: 'scene-pot', key: 'pot' }),
    ]);
}

function TrustRow() {
    const items = [
        ['shield', '安全可靠', '多重保护，确保账户安全'],
        ['users', '公平公正', 'AI 驱动，公平评估每个人'],
        ['heart', '助力成长', '智能反馈，成就更好的你'],
    ];
    return h('div', { className: 'scene-trust-row' }, items.map(([icon, title, text]) => (
        h('div', { className: 'scene-trust-item', key: title }, [
            h(Icon, { type: icon, key: 'icon' }),
            h('b', { key: 'title' }, title),
            h('span', { key: 'text' }, text),
        ])
    )));
}

function ForgotArtScene({ libraries }) {
    return h(ComponentProvider, { libraries },
        h(ShadcnSurface, { className: 'forgot-art-scene' }, [
            h(ForgotSignalCanvas, { key: 'wave' }),
            h('div', { className: 'scene-ai-mark', key: 'ai' }, 'AI'),
            h(BooksStack, { key: 'books' }),
            h(Laptop, { key: 'laptop' }),
            h('div', { className: 'scene-campus', key: 'campus' }),
            h(Plant, { key: 'plant' }),
        ])
    );
}

function WaveStage({ overlay, libraries }) {
    const [mode, setMode] = useState(overlay.dataset.mode || 'login');

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setMode(overlay.dataset.mode || 'login');
        });
        observer.observe(overlay, { attributes: true, attributeFilter: ['data-mode'] });
        return () => observer.disconnect();
    }, [overlay]);

    return h(ComponentProvider, { libraries }, h(AuthWaveCanvas, { mode }));
}

function mountReactRoot(host, className, component) {
    let mount = host.querySelector(`:scope > .${className}`);
    if (!mount) {
        mount = document.createElement('div');
        mount.className = className;
        host.appendChild(mount);
    }
    if (!mount.__componentRoot) {
        mount.__componentRoot = createRoot(mount);
    }
    mount.__componentRoot.render(component);
}

function AuthComponentRuntime() {
    const libraries = useComponentLibraries();

    useEffect(() => {
        document.documentElement.classList.add('component-auth-runtime');
        if (libraries.antDesignX || libraries.antd) {
            document.documentElement.dataset.componentLibraries = [
                libraries.antDesignX ? 'ant-design-x' : '',
                libraries.antd ? 'ant-design' : '',
                'shadcn-primitives',
            ].filter(Boolean).join(' ');
        }
    }, [libraries]);

    return libraries;
}

const overlay = document.getElementById('loginOverlay');
if (overlay) {
    const runtimeHost = document.createElement('div');
    runtimeHost.hidden = true;
    document.body.appendChild(runtimeHost);
    const runtimeRoot = createRoot(runtimeHost);
    const RuntimeBridge = () => {
        const libraries = AuthComponentRuntime();
        useEffect(() => {
            const waveHost = overlay.querySelector('.audio-wave');
            if (waveHost) {
                mountReactRoot(waveHost, 'component-wave-root', h(WaveStage, { overlay, libraries }));
            }
            const forgotHost = overlay.querySelector('.forgot-illustration');
            if (forgotHost) {
                mountReactRoot(forgotHost, 'component-forgot-root', h(ForgotArtScene, { libraries }));
                document.documentElement.classList.add('component-forgot-ready');
            }
        }, [libraries]);
        return h(Fragment);
    };
    runtimeRoot.render(h(RuntimeBridge));
}
