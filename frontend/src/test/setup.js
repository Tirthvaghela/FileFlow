import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement matchMedia at all -- gsap's ScrollTrigger plugin
// (src/lib/gsap.js, pulled in by any component using the Slider control,
// e.g. Settings.jsx) calls it once at module load time to register itself,
// which previously threw "matchMedia is not a function" and made every
// test file that ever imports such a component fail to even load, with no
// connection to whatever that test file was actually trying to verify.
// This is the standard minimal stub (no test here cares about real media
// query matching, just that gsap's own setup call doesn't crash).
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

// jsdom doesn't implement IntersectionObserver either -- framer-motion's
// `whileInView`/viewport tracking (motion.div on Reports.jsx and others)
// calls it as soon as such a component mounts, which otherwise throws
// "IntersectionObserver is not defined" as an uncaught async exception
// unrelated to whatever the test actually asserts on.
if (!window.IntersectionObserver) {
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
