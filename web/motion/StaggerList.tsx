"use client";

import React from "react";
import { motion, useReducedMotion } from "motion/react";

interface StaggerListProps {
  children: React.ReactNode;
  /** Millisecondi fra un figlio e il successivo. */
  stagger?: number;
  className?: string;
}

/** Card che entrano una dopo l'altra. Il ritardo si ferma al decimo figlio: oltre,
 *  una lista lunga diventerebbe un'attesa. */
export function StaggerList({ children, stagger = 40, className }: StaggerListProps) {
  const shouldReduce = useReducedMotion();
  const items = React.Children.toArray(children);

  return (
    <div className={className}>
      {items.map((child, index) => (
        <motion.div
          key={index}
          initial={shouldReduce ? undefined : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.25,
            ease: "easeOut",
            delay: shouldReduce ? 0 : (Math.min(index, 10) * stagger) / 1000,
          }}
        >
          {child}
        </motion.div>
      ))}
    </div>
  );
}
