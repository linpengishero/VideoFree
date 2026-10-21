// VideoFree Studio site interactions, progressively enhanced — everything works without JS.
// 1. Header gains a border once the page scrolls.
// 2. Mobile nav toggle.
// 3. Subtle reveal-on-scroll for cards and section heads.
// 4. Copy buttons on code blocks and prompt blockquotes.

const header = document.querySelector('.site-header');

if (header) {
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  const toggle = header.querySelector('.nav-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const open = header.classList.toggle('nav-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
    header.querySelector('.main-nav')?.addEventListener('click', (e) => {
      if (e.target.closest('a')) header.classList.remove('nav-open');
    });
  }
}

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!reduced && 'IntersectionObserver' in window) {
  const targets = document.querySelectorAll('.card, .info-card, .section-head, .plugin-group, .qr-item, .channel, .spec, .panel');
  const io = new IntersectionObserver(
    (entries) => {
      for (const en of entries) {
        if (en.isIntersecting) {
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
  );
  targets.forEach((el, i) => {
    el.classList.add('reveal');
    el.style.transitionDelay = `${Math.min(i % 4, 3) * 60}ms`;
    io.observe(el);
  });
}

const copyLabel = document.documentElement.lang === 'en' ? 'Copy' : '复制';
const copiedLabel = document.documentElement.lang === 'en' ? 'Copied' : '已复制';
document.querySelectorAll('pre, blockquote').forEach((block) => {
  const text = block.innerText.trim(); // capture before the button becomes part of the block
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'copy-btn';
  btn.textContent = copyLabel;
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = copiedLabel;
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = copyLabel; btn.classList.remove('copied'); }, 1600);
    } catch {
      /* clipboard unavailable; button stays inert */
    }
  });
  block.appendChild(btn);
});
