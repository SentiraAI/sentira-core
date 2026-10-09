"use client";

import { motion, useReducedMotion } from "motion/react";

interface FadeInProps {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}

/** Un elemento che entra: dissolvenza e breve salita. */
export function FadeIn({ children, delay = 0, className }: FadeInProps) {
  const shouldReduce = useReducedMotion();

  return (
    <motion.div
      initial={shouldReduce ? undefined : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut", delay: shouldReduce ? 0 : delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
