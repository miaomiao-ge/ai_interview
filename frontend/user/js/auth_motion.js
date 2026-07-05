const GSAP_URL = "https://esm.sh/gsap@3.12.5?bundle";
const SCROLL_TRIGGER_URL = "https://esm.sh/gsap@3.12.5/ScrollTrigger?bundle";

let gsapLoadPromise = null;

async function loadGsap() {
    if (window.gsap) {
        return { gsap: window.gsap, ScrollTrigger: window.ScrollTrigger };
    }

    if (!gsapLoadPromise) {
        gsapLoadPromise = Promise.all([
            import(GSAP_URL),
            import(SCROLL_TRIGGER_URL),
        ]).then(([gsapModule, scrollModule]) => {
            const gsap = gsapModule.gsap || gsapModule.default || window.gsap;
            const ScrollTrigger = scrollModule.ScrollTrigger || scrollModule.default || window.ScrollTrigger;
            if (gsap && ScrollTrigger) {
                gsap.registerPlugin(ScrollTrigger);
            }
            return { gsap, ScrollTrigger };
        });
    }

    return gsapLoadPromise;
}

function getTargets(root) {
    return {
        card: root.querySelector(".auth-card"),
        brand: root.querySelector(".auth-brand-panel"),
        form: root.querySelector(".auth-form-panel"),
        signal: root.querySelector(".auth-signal"),
        registerWave: root.querySelector(".auth-register-wave"),
        forgotIllustration: root.querySelector(".auth-forgot-illustration"),
        headings: root.querySelectorAll(".login-title, .login-subtitle, .admin-form-heading, .admin-auth-top"),
        fields: root.querySelectorAll(".auth-field, .auth-remember, .auth-divider, .auth-switch, .admin-field-label, .admin-input-shell, .admin-login-row, .admin-status-card"),
        buttons: root.querySelectorAll(".login-btn, .btn-login, #sendCodeBtn, .text-link, .admin-forgot-link"),
        reveal: root.querySelectorAll(".auth-feature-item, .auth-trust-item, .admin-feature-cards > div, .admin-auth-footer > div"),
    };
}

function animateMode(gsap, root) {
    const targets = getTargets(root);
    const visibleBrand = root.querySelector(".brand-mode:not([hidden])") || targets.brand;

    gsap.killTweensOf([targets.fields, visibleBrand, targets.buttons, targets.registerWave, targets.forgotIllustration]);
    gsap.fromTo(
        [visibleBrand, ...targets.headings],
        { y: 10, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.42, ease: "power3.out", stagger: 0.035, overwrite: "auto" }
    );
    gsap.fromTo(
        targets.fields,
        { y: 12, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.36, ease: "power3.out", stagger: 0.035, overwrite: "auto" }
    );
    if (targets.signal) {
        gsap.fromTo(
            targets.signal,
            { y: 8, scaleX: 0.985, autoAlpha: 0.52 },
            { y: 0, scaleX: 1, autoAlpha: 1, duration: 0.48, ease: "power3.out", overwrite: "auto" }
        );
    }
    if (root.dataset.mode === "register" && targets.registerWave) {
        gsap.fromTo(
            targets.registerWave,
            { y: 14, opacity: 0.24, scaleX: 0.992 },
            { y: 0, opacity: 1, scaleX: 1, duration: 0.54, delay: 0.04, ease: "power4.out", overwrite: "auto" }
        );
    }
    if (root.dataset.mode === "forgot" && targets.forgotIllustration) {
        gsap.fromTo(
            targets.forgotIllustration,
            { y: 16, opacity: 0.22, scale: 0.985 },
            { y: 0, opacity: 1, scale: 1, duration: 0.58, delay: 0.04, ease: "power4.out", overwrite: "auto" }
        );
    }
}

function bindHover(gsap, root) {
    const interactive = root.querySelectorAll(".login-btn, .btn-login, #sendCodeBtn, .admin-forgot-link, .text-link");
    const cleanups = [];

    interactive.forEach((element) => {
        const enter = () => {
            if (element.disabled) return;
            gsap.to(element, { y: -2, scale: 1.01, duration: 0.18, ease: "power3.out", overwrite: "auto" });
        };
        const leave = () => {
            gsap.to(element, { y: 0, scale: 1, duration: 0.24, ease: "power3.out", overwrite: "auto" });
        };
        element.addEventListener("mouseenter", enter);
        element.addEventListener("mouseleave", leave);
        element.addEventListener("blur", leave);
        cleanups.push(() => {
            element.removeEventListener("mouseenter", enter);
            element.removeEventListener("mouseleave", leave);
            element.removeEventListener("blur", leave);
        });
    });

    return () => cleanups.forEach((cleanup) => cleanup());
}

export async function initAuthMotion(rootSelector) {
    const root = document.querySelector(rootSelector);
    if (!root || root.dataset.motionReady === "true") return;

    root.dataset.motionReady = "true";
    root.classList.add("auth-motion-ready");

    try {
        const { gsap, ScrollTrigger } = await loadGsap();
        if (!gsap) return;

        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reduceMotion) {
            root.classList.add("auth-motion-reduced");
            return;
        }

        const targets = getTargets(root);
        const animated = [
            targets.card,
            targets.brand,
            targets.form,
            targets.signal,
            targets.registerWave,
            targets.forgotIllustration,
            ...targets.fields,
            ...targets.reveal,
        ].filter(Boolean);

        gsap.set(animated, { willChange: "transform, opacity" });
        gsap.fromTo(
            [targets.card, targets.brand, targets.form, targets.signal].filter(Boolean),
            { y: 22, autoAlpha: 0 },
            { y: 0, autoAlpha: 1, duration: 0.58, ease: "power4.out", stagger: 0.06, clearProps: "visibility" }
        );

        animateMode(gsap, root);
        const cleanupHover = bindHover(gsap, root);

        const observer = new MutationObserver(() => animateMode(gsap, root));
        observer.observe(root, { attributes: true, attributeFilter: ["data-mode", "style"] });

        if (ScrollTrigger && targets.reveal.length) {
            ScrollTrigger.batch(targets.reveal, {
                scroller: root,
                start: "top 92%",
                once: true,
                onEnter: (batch) => {
                    gsap.fromTo(
                        batch,
                        { y: 14, autoAlpha: 0 },
                        { y: 0, autoAlpha: 1, duration: 0.42, ease: "power3.out", stagger: 0.045, overwrite: "auto" }
                    );
                },
            });
        }

        window.addEventListener("beforeunload", () => {
            observer.disconnect();
            cleanupHover();
            if (ScrollTrigger) {
                ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
            }
            gsap.killTweensOf(animated);
        }, { once: true });
    } catch (error) {
        root.classList.add("auth-motion-fallback");
        console.info("[auth-motion] GSAP unavailable, CSS transitions remain active.");
    }
}
