const finePointer = window.matchMedia('(pointer: fine)').matches;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (finePointer && !reducedMotion) {
    const dot = document.createElement('div');
    const ring = document.createElement('div');
    dot.className = 'ai-cursor';
    ring.className = 'ai-cursor-ring';
    document.body.append(dot, ring);
    document.body.classList.add('has-ai-cursor');

    let x = -100;
    let y = -100;

    const move = (event) => {
        x = event.clientX;
        y = event.clientY;
        dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        ring.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    };

    const setActive = (active) => document.body.classList.toggle('cursor-active', active);

    window.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerover', (event) => {
        setActive(Boolean(event.target.closest('button, a, input, select, textarea, [role="button"]')));
    });
    document.addEventListener('pointerdown', () => setActive(true));
    document.addEventListener('pointerup', () => setActive(false));
}
