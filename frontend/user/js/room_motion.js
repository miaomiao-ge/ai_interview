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

function isVisible(element) {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
}

function getTargets(root) {
    return {
        topbar: root.querySelector(".interview-topbar"),
        panels: root.querySelectorAll(".left-panel, .center-panel, .right-panel"),
        cards: root.querySelectorAll(".dimension-card"),
        notice: root.querySelector(".interview-notice"),
        trust: root.querySelector(".room-trust-row"),
        questionBubble: root.querySelector(".chat-bubble"),
        statusPill: root.querySelector(".connection-pill"),
        controls: root.querySelector(".controls-wrapper"),
        answerControls: root.querySelector("#answerControls"),
        buttons: root.querySelectorAll(".room-action-button, #startBtn, #extendTimeBtn, #finishAnswerBtn"),
    };
}

function animateRoomEnter(gsap, ScrollTrigger, root) {
    const targets = getTargets(root);
    const entranceTargets = [
        targets.topbar,
        ...targets.panels,
    ].filter(Boolean);

    gsap.killTweensOf(entranceTargets);
    gsap.set(entranceTargets, { willChange: "transform, opacity" });
    gsap.fromTo(
        entranceTargets,
        { y: 18, autoAlpha: 0 },
        {
            y: 0,
            autoAlpha: 1,
            duration: 0.52,
            ease: "power4.out",
            stagger: 0.055,
            overwrite: "auto",
            clearProps: "visibility",
        }
    );

    if (targets.cards.length) {
        gsap.fromTo(
            targets.cards,
            { y: 10, autoAlpha: 0 },
            {
                y: 0,
                autoAlpha: 1,
                duration: 0.38,
                delay: 0.18,
                ease: "power3.out",
                stagger: 0.035,
                overwrite: "auto",
                clearProps: "visibility",
            }
        );
    }

    if (targets.controls) {
        gsap.fromTo(
            targets.controls,
            { y: 12, autoAlpha: 0 },
            { y: 0, autoAlpha: 1, duration: 0.42, delay: 0.2, ease: "power3.out", overwrite: "auto" }
        );
    }

    if (ScrollTrigger) {
        window.setTimeout(() => ScrollTrigger.refresh(), 80);
    }
}

function bindHover(gsap, root) {
    const { buttons } = getTargets(root);
    const cleanups = [];

    buttons.forEach((element) => {
        const enter = () => {
            if (element.disabled) return;
            gsap.to(element, { y: -1, scale: 1.005, duration: 0.18, ease: "power3.out", overwrite: "auto" });
        };
        const leave = () => {
            gsap.to(element, { y: 0, scale: 1, duration: 0.22, ease: "power3.out", overwrite: "auto" });
        };

        element.addEventListener("pointerenter", enter);
        element.addEventListener("pointerleave", leave);
        element.addEventListener("blur", leave);
        cleanups.push(() => {
            element.removeEventListener("pointerenter", enter);
            element.removeEventListener("pointerleave", leave);
            element.removeEventListener("blur", leave);
        });
    });

    return () => cleanups.forEach((cleanup) => cleanup());
}

function observeStateChanges(gsap, root) {
    const observers = [];
    const { statusPill, questionBubble, answerControls } = getTargets(root);
    const status = root.querySelector("#status");
    const question = root.querySelector("#aiFirstQuestion");
    let answerVisible = isVisible(answerControls);

    if (status && statusPill) {
        const observer = new MutationObserver(() => {
            if (!isVisible(root)) return;
            gsap.fromTo(
                statusPill,
                { scale: 0.985, autoAlpha: 0.88 },
                { scale: 1, autoAlpha: 1, duration: 0.28, ease: "power3.out", overwrite: "auto" }
            );
        });
        observer.observe(status, { childList: true, subtree: true, characterData: true, attributes: true });
        observers.push(observer);
    }

    if (question && questionBubble) {
        const observer = new MutationObserver(() => {
            if (!isVisible(root)) return;
            gsap.fromTo(
                questionBubble,
                { y: 7, autoAlpha: 0.9 },
                { y: 0, autoAlpha: 1, duration: 0.32, ease: "power3.out", overwrite: "auto" }
            );
        });
        observer.observe(question, { childList: true, subtree: true, characterData: true });
        observers.push(observer);
    }

    if (answerControls) {
        const observer = new MutationObserver(() => {
            const nextVisible = isVisible(answerControls);
            if (nextVisible && !answerVisible && isVisible(root)) {
                gsap.killTweensOf(answerControls);
                gsap.fromTo(
                    answerControls,
                    { y: 8 },
                    { y: 0, duration: 0.28, ease: "power3.out", overwrite: "auto" }
                );
            }
            answerVisible = nextVisible;
        });
        observer.observe(answerControls, { attributes: true, attributeFilter: ["style", "class"] });
        observers.push(observer);
    }

    return () => observers.forEach((observer) => observer.disconnect());
}

function setupMobileScrollReveal(gsap, ScrollTrigger, root) {
    if (!ScrollTrigger) return () => {};

    const matchMedia = gsap.matchMedia();
    matchMedia.add("(max-width: 1080px)", () => {
        const revealTargets = root.querySelectorAll(".panel, .dimension-card, .interview-notice, .room-trust-row");
        if (!revealTargets.length) return undefined;

        gsap.set(revealTargets, { y: 10 });
        const triggers = ScrollTrigger.batch(revealTargets, {
            start: "top 90%",
            once: true,
            interval: 0.08,
            batchMax: 4,
            onEnter: (batch) => {
                gsap.to(batch, {
                    y: 0,
                    duration: 0.42,
                    ease: "power3.out",
                    stagger: 0.04,
                    overwrite: "auto",
                });
            },
        });

        return () => triggers.forEach((trigger) => trigger.kill());
    });

    return () => matchMedia.revert();
}

export async function initRoomMotion(rootSelector) {
    const root = document.querySelector(rootSelector);
    if (!root || root.dataset.roomMotionReady === "true") return;

    root.dataset.roomMotionReady = "true";
    root.classList.add("room-motion-ready");

    try {
        const { gsap, ScrollTrigger } = await loadGsap();
        if (!gsap) return;

        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reduceMotion) {
            root.classList.add("room-motion-reduced");
            return;
        }

        const cleanupHover = bindHover(gsap, root);
        const cleanupState = observeStateChanges(gsap, root);
        const cleanupScroll = setupMobileScrollReveal(gsap, ScrollTrigger, root);
        let wasVisible = isVisible(root);

        if (wasVisible) {
            window.requestAnimationFrame(() => animateRoomEnter(gsap, ScrollTrigger, root));
        }

        const visibilityObserver = new MutationObserver(() => {
            const visible = isVisible(root);
            if (visible && !wasVisible) {
                animateRoomEnter(gsap, ScrollTrigger, root);
            }
            wasVisible = visible;
        });
        visibilityObserver.observe(root, { attributes: true, attributeFilter: ["style", "class"] });

        window.addEventListener("beforeunload", () => {
            visibilityObserver.disconnect();
            cleanupHover();
            cleanupState();
            cleanupScroll();
            gsap.killTweensOf(root.querySelectorAll("*"));
        }, { once: true });
    } catch (error) {
        root.classList.add("room-motion-fallback");
        console.info("[room-motion] GSAP unavailable, CSS transitions remain active.");
    }
}
