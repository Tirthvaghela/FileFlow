import { useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";

export default function TiltCard({
  children,
  className = "",
  style = {},
  maxRotate = 12,
  glareOpacityMax = 0.15,
}) {
  const cardRef = useRef(null);

  // Track cursor position from 0 to 1 across card width/height
  const x = useMotionValue(0.5);
  const y = useMotionValue(0.5);

  // Map position to rotation angles (e.g. -12 to +12 degrees)
  const rotateX = useSpring(useTransform(y, [0, 1], [maxRotate, -maxRotate]), {
    stiffness: 220,
    damping: 25,
  });
  const rotateY = useSpring(useTransform(x, [0, 1], [-maxRotate, maxRotate]), {
    stiffness: 220,
    damping: 25,
  });

  // Glare overlay positioning & opacity
  const glareLeft = useSpring(useTransform(x, [0, 1], ["-20%", "120%"]), {
    stiffness: 220,
    damping: 25,
  });
  const glareTop = useSpring(useTransform(y, [0, 1], ["-20%", "120%"]), {
    stiffness: 220,
    damping: 25,
  });
  const glareOpacity = useSpring(useMotionValue(0), {
    stiffness: 220,
    damping: 25,
  });

  const handleMouseMove = (e) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    x.set(mouseX / width);
    y.set(mouseY / height);
    glareOpacity.set(glareOpacityMax);
  };

  const handleMouseLeave = () => {
    x.set(0.5);
    y.set(0.5);
    glareOpacity.set(0);
  };

  return (
    <motion.div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        rotateX,
        rotateY,
        transformStyle: "preserve-3d",
        perspective: 1000,
        ...style,
      }}
      className={`relative overflow-hidden ${className}`}
    >
      {/* Glare Shine Overlay */}
      <motion.div
        className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 h-[150%] w-[150%] rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.2)_0%,transparent_50%)]"
        style={{
          left: glareLeft,
          top: glareTop,
          opacity: glareOpacity,
          zIndex: 10,
        }}
      />
      {/* Inner wrapper to apply depth effect to children */}
      <div style={{ transform: "translateZ(20px)", transformStyle: "preserve-3d" }}>
        {children}
      </div>
    </motion.div>
  );
}
