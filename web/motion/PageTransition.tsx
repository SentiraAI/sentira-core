"use client";

import { motion, useReducedMotion } from "motion/react";

interface PageTransitionProps {
  children: React.ReactNode;
  className?: string;
}

/** La pagina intera che arriva. Corsa più corta di FadeIn: una superficie grande
 *  che si sposta di 16px sembra uno scossone, di 8px sembra posarsi. */
export function PageTransition({ children, className }: PageTransitionProps) {
  const shouldReduce = useReducedMotion();

  return (
    <motion.div
      initial={shouldReduce ? undefined : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
